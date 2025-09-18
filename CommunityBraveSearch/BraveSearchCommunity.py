import os
import time
import logging
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional, Union

import requests
from markdownify import markdownify
from urllib.parse import urlparse

from ws_manager import open_tab
from config import config
from utils.functions_metadata import function_schema


logger = logging.getLogger("brave_search_community")


class BraveSearchException(Exception):
    """Raised when the Brave Search API returns a non-success response."""


class RateLimitException(Exception):
    """Raised when Brave Search responds with HTTP 429 (rate-limit)."""


def _coerce_num_results(value: Optional[Union[str, int]]) -> int:
    """Ensure `num_results` is a positive integer; default to 1."""
    if value in (None, "", 0):
        return 1
    try:
        value_int = int(value)
        return max(value_int, 1)
    except (TypeError, ValueError):
        logger.warning("Invalid num_results '%s' supplied, defaulting to 1.", value)
        return 1


def _normalize_api_key(value: Optional[str]) -> Optional[str]:
    """Normalize Brave API key by trimming and removing 'Bearer ' prefix if present."""
    if not value:
        return None
    key = str(value).strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    return key or None


def _get_api_key(explicit_key: Optional[str]) -> str:
    """Return Brave API key from param or env vars.

    Checks `BRAVE_SEARCH_API_KEY` first, then `BRAVE_API_KEY` for convenience.
    """
    raw = explicit_key or os.getenv("BRAVE_SEARCH_API_KEY") or os.getenv("BRAVE_API_KEY")
    key = _normalize_api_key(raw) or ""
    if not key:
        raise BraveSearchException(
            "Missing Brave API key. Set BRAVE_SEARCH_API_KEY (or BRAVE_API_KEY) or pass brave_api_key."
        )
    # Masked debug log to confirm key source and presence
    try:
        source = (
            "param"
            if explicit_key
            else ("BRAVE_SEARCH_API_KEY" if os.getenv("BRAVE_SEARCH_API_KEY") else ("BRAVE_API_KEY" if os.getenv("BRAVE_API_KEY") else "unknown"))
        )
        masked_tail = key[-4:] if len(key) >= 4 else key
        logger.info(
            "brave_search_community: using key source=%s len=%s tail=%s",
            source,
            len(key),
            ("*" * (len(key) - len(masked_tail))) + masked_tail,
        )
    except Exception:
        pass
    return key


def _format_web_results(results: List[Dict]) -> str:
    def _fmt(res: Dict) -> str:
        title = res.get("title", "No title")
        snippet_html = res.get("description", "No snippet")
        snippet_markdown = markdownify(snippet_html, heading_style="ATX").strip()
        url = res.get("url", "No URL")
        return f"Title: {title}\nSnippet: {snippet_markdown}\nURL: {url}"

    return "\n\n".join(f"Result {i + 1}:\n{_fmt(res)}" for i, res in enumerate(results))


def _format_image_results(results: List[Dict]) -> str:
    """Format image results, save images to workspace/temp, open tabs, and summarize."""

    # Prepare workspace temp directory
    workspace_dir = Path(config.workspace_path).expanduser().resolve()
    temp_dir = workspace_dir / "temp"
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("Failed to ensure temp directory at %s", temp_dir)

    opened_tabs: List[str] = []
    failed_tabs: List[str] = []

    def _safe_filename(name: str) -> str:
        keep = "-. _()[]{}"
        return "".join(c for c in name if c.isalnum() or c in keep).strip() or "image"

    def _unique_path(base_dir: Path, stem: str, ext: str) -> Path:
        candidate = base_dir / f"{stem}{ext}"
        if not candidate.exists():
            return candidate
        i = 1
        while True:
            candidate = base_dir / f"{stem}_{i}{ext}"
            if not candidate.exists():
                return candidate
            i += 1

    def _fmt(res: Dict) -> str:
        title = res.get("title") or res.get("page_title") or "No title"
        # Prefer original image via properties.url; fallback to thumbnail.src and others
        props = res.get("properties") if isinstance(res.get("properties"), dict) else {}
        thumb = res.get("thumbnail") if isinstance(res.get("thumbnail"), dict) else None
        image_url = (
            (props.get("url") if props else None)
            or (thumb.get("src") if isinstance(thumb, dict) else None)
            or res.get("image_url")
            or res.get("image")
            or res.get("thumbnail")
            or ""
        )
        page_url = (
            res.get("page_url")
            or res.get("url")
            or res.get("link")
            or res.get("source")
            or res.get("site")
            or ""
        )

        saved_path_display = None
        # Attempt to download image and open locally
        if image_url:
            try:
                parsed = urlparse(image_url)
                url_name = os.path.basename(parsed.path) or ""
                stem, ext = os.path.splitext(url_name)
                if not stem:
                    stem = _safe_filename(title) or "image"
                # Fetch image (streamed)
                resp = requests.get(image_url, timeout=15, stream=True)
                resp.raise_for_status()
                # Infer missing extension from content-type
                if not ext:
                    ct = resp.headers.get("Content-Type", "").split(";")[0].strip()
                    guessed = mimetypes.guess_extension(ct) if ct else None
                    ext = guessed or ".jpg"
                dest_path = _unique_path(temp_dir, _safe_filename(stem), ext)
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                # Open in a new tab
                try:
                    open_tab(str(dest_path))
                    opened_tabs.append(str(dest_path))
                except Exception:
                    failed_tabs.append(image_url)
                    logger.exception("Failed to open saved image tab for %s", dest_path)
                try:
                    saved_path_display = str(dest_path.relative_to(workspace_dir))
                except Exception:
                    saved_path_display = str(dest_path)
            except Exception:
                failed_tabs.append(image_url)
                logger.exception("Failed to download or save image %s", image_url)

        parts = [f"Title: {title}"]
        if image_url:
            parts.append(f"Source: {image_url}")
        if page_url:
            parts.append(f"Page: {page_url}")
        if saved_path_display:
            parts.append(f"Saved: {saved_path_display}")
        return "\n".join(parts)

    body = "\n\n".join(f"Image {i + 1}:\n{_fmt(res)}" for i, res in enumerate(results))

    # Append open status summary for the model
    summary_lines: List[str] = []
    if opened_tabs:
        summary_lines.append(f"Opened in tabs: {len(opened_tabs)} file(s).")
    if failed_tabs:
        preview = ", ".join(failed_tabs[:5])
        more = "" if len(failed_tabs) <= 5 else f" (+{len(failed_tabs) - 5} more)"
        summary_lines.append(f"Failed to open: {len(failed_tabs)} — {preview}{more}")
    if summary_lines:
        body = body + "\n\n" + "\n".join(summary_lines)
    return body


def _brave_request(endpoint: str, params: Dict[str, Union[str, int]], api_key: str, timeout: int = 15) -> requests.Response:
    headers = {
        "Accept": "application/json",
        "User-Agent": "MageLab-Community-Tool/1.0",
        "X-Subscription-Token": api_key,
    }
    try:
        safe_params = {k: v for k, v in params.items() if k != "q"}
        logger.info(
            "brave_search_community: GET %s token_present=%s params=%s",
            endpoint,
            bool(api_key),
            safe_params,
        )
    except Exception:
        pass
    return requests.get(endpoint, headers=headers, params=params, timeout=timeout)


def _handle_response(resp: requests.Response, kind: str) -> Dict:
    if resp.status_code == 429:
        raise RateLimitException("Rate-limited by Brave Search")
    if not resp.ok:
        raise BraveSearchException(f"Brave {kind} search error {resp.status_code}: {resp.text}")
    try:
        return resp.json()
    except ValueError:
        raise BraveSearchException("Invalid JSON received from Brave Search")


@function_schema(
    name="search_web_community",
    description="Look up things on the web using Brave Search",
    required_params=["query"],
    optional_params=["num_results", "brave_api_key"],
)
def search_web_community(
    query: str,
    num_results: Optional[Union[int, str]] = 1,
    brave_api_key: Optional[str] = None,
) -> str:
    """
    Perform a Brave Search web query and return formatted top results with Markdown snippets.

    :param query: Search query string
    :param num_results: Number of results to return (default 1)
    :param brave_api_key: Optional Brave API key; otherwise uses env BRAVE_SEARCH_API_KEY
    """
    num_results = _coerce_num_results(num_results)
    api_key = _get_api_key(brave_api_key)

    attempts = 0
    max_attempts = 3
    base_wait_time = 2  # seconds

    while attempts < max_attempts:
        try:
            resp = _brave_request(
                "https://api.search.brave.com/res/v1/web/search",
                {"q": query, "count": num_results},
                api_key,
            )
            data = _handle_response(resp, "web")
            results = data.get("web", {}).get("results", [])
            if not results:
                return "No results found."
            return _format_web_results(results)
        except RateLimitException:
            logger.exception("Rate-limited by Brave web search. Retrying...")
        except BraveSearchException as e:
            logger.exception("BraveSearchException in search_web_community: %s", e)
            return (
                "We had trouble retrieving results from Brave at this time. "
                "Please try again or modify your query."
            )
        except requests.exceptions.RequestException:
            logger.exception("Network error in search_web_community.")
            return (
                "A network error occurred while contacting Brave Search. "
                "Please try again later."
            )
        except Exception:
            logger.exception("Unexpected error in search_web_community.")
            return "An unexpected error occurred while searching. Please try again later."

        attempts += 1
        if attempts < max_attempts:
            time.sleep(base_wait_time * attempts)
        else:
            return (
                "We are currently rate-limited by Brave Search. "
                "Please try again later."
            )

    return "We could not retrieve results at this time. Please try again later."


@function_schema(
    name="search_images_community",
    description="Find images using Brave Search",
    required_params=["query"],
    optional_params=["num_results", "brave_api_key"],
)
def search_images_community(
    query: str,
    num_results: Optional[Union[int, str]] = 1,
    brave_api_key: Optional[str] = None,
) -> str:
    """
    Perform a Brave Image Search query and return formatted results.

    :param query: Search query string
    :param num_results: Number of results to return (default 1)
    :param brave_api_key: Optional Brave API key; otherwise uses env BRAVE_SEARCH_API_KEY
    """
    num_results = _coerce_num_results(num_results)
    api_key = _get_api_key(brave_api_key)

    attempts = 0
    max_attempts = 3
    base_wait_time = 2  # seconds

    while attempts < max_attempts:
        try:
            resp = _brave_request(
                "https://api.search.brave.com/res/v1/images/search",
                {"q": query, "count": num_results},
                api_key,
            )
            data = _handle_response(resp, "image")
            # Per Brave Images API, top-level key is typically 'results'.
            results = data.get("results") if isinstance(data.get("results"), list) else []
            # Backward compatibility: if 'images' wrapper is present, use its 'results'.
            if not results and isinstance(data.get("images"), dict):
                results = data["images"].get("results") or []
            if not results:
                try:
                    logger.warning(
                        "brave_search_community: no image results; top-level keys=%s images_type=%s",
                        list(data.keys()), type(data.get("images")).__name__,
                    )
                except Exception:
                    pass
                return "No image results found."
            return _format_image_results(results)
        except RateLimitException:
            logger.exception("Rate-limited by Brave image search. Retrying...")
        except BraveSearchException as e:
            logger.exception("BraveSearchException in search_images_community: %s", e)
            return (
                "We had trouble retrieving image results from Brave at this time. "
                "Please try again or modify your query."
            )
        except requests.exceptions.RequestException:
            logger.exception("Network error in search_images_community.")
            return (
                "A network error occurred while contacting Brave Search. "
                "Please try again later."
            )
        except Exception:
            logger.exception("Unexpected error in search_images_community.")
            return "An unexpected error occurred while searching images. Please try again later."

        attempts += 1
        if attempts < max_attempts:
            time.sleep(base_wait_time * attempts)
        else:
            return (
                "We are currently rate-limited by Brave Search. "
                "Please try again later."
            )

    return "We could not retrieve results at this time. Please try again later."
