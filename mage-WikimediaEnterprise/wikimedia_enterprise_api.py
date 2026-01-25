import json
import logging
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import quote

import requests
from utils.functions_metadata import function_schema

logger = logging.getLogger("wikimedia_enterprise")

API_BASE = os.getenv("WME_API_BASE", "https://api.enterprise.wikimedia.com/v2")
AUTH_BASE = os.getenv("WME_AUTH_BASE", "https://auth.enterprise.wikimedia.com/v1")

_ACCESS_TOKEN: Optional[str] = None
_TOKEN_EXPIRES_AT: float = 0.0


def _clean_env_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    return cleaned or None


def _normalize_bearer(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    value = str(token).strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value or None


def _get_access_token() -> str:
    global _ACCESS_TOKEN, _TOKEN_EXPIRES_AT

    env_token = _normalize_bearer(_clean_env_value(os.getenv("WME_ACCESS_TOKEN")))
    if not env_token:
        env_token = _normalize_bearer(_clean_env_value(os.getenv("WME_API_KEY")))
    if env_token:
        return env_token

    now = time.time()
    if _ACCESS_TOKEN and now < _TOKEN_EXPIRES_AT:
        return _ACCESS_TOKEN

    username = _clean_env_value(os.getenv("WME_USERNAME"))
    password = _clean_env_value(os.getenv("WME_PASSWORD"))
    if not username or not password:
        raise RuntimeError(
            "Missing credentials. Set WME_USERNAME and WME_PASSWORD, or provide WME_ACCESS_TOKEN."
        )

    url = f"{AUTH_BASE}/login"
    try:
        resp = requests.post(url, json={"username": username, "password": password}, timeout=20)
        if resp.status_code == 401:
            detail = resp.text.strip()
            raise RuntimeError(f"Authentication failed (401): {detail or 'Unauthorized'}")
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Authentication failed: {exc}") from exc

    data = resp.json()
    token = _normalize_bearer(data.get("access_token"))
    if not token:
        raise RuntimeError("Authentication response missing access_token.")

    expires_in = int(data.get("expires_in") or 0)
    _TOKEN_EXPIRES_AT = now + max(expires_in - 30, 0) if expires_in else now + 270
    _ACCESS_TOKEN = token
    return token


def _auth_headers() -> Dict[str, str]:
    token = _get_access_token()
    return {"Authorization": f"Bearer {token}"}


def _coerce_int(value: Optional[Union[int, str]], default: Optional[int] = None) -> Optional[int]:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_fields(value: Optional[Union[str, Iterable[str]]]) -> Optional[List[str]]:
    if value in (None, ""):
        return None
    if isinstance(value, (list, tuple, set)):
        fields = [str(v).strip() for v in value if str(v).strip()]
        return fields or None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.startswith("["):
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    fields = [str(v).strip() for v in data if str(v).strip()]
                    return fields or None
            except json.JSONDecodeError:
                pass
        return [v.strip() for v in raw.split(",") if v.strip()] or None
    return [str(value).strip()]


def _parse_filter_string(raw: str) -> Optional[Dict[str, str]]:
    if "=" in raw:
        field, value = raw.split("=", 1)
    elif ":" in raw:
        field, value = raw.split(":", 1)
    else:
        return None
    field = field.strip()
    value = value.strip()
    if not field or not value:
        return None
    return {"field": field, "value": value}


def _normalize_filters(
    value: Optional[Union[str, Dict[str, Any], Iterable[Union[str, Dict[str, Any]]]]]
) -> Optional[List[Dict[str, Any]]]:
    if value in (None, ""):
        return None
    filters: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        filters.append(value)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if isinstance(item, dict):
                filters.append(item)
            elif isinstance(item, str):
                parsed = _parse_filter_string(item.strip())
                if parsed:
                    filters.append(parsed)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.startswith("[") or raw.startswith("{"):
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    filters.extend([item for item in data if isinstance(item, dict)])
                elif isinstance(data, dict):
                    filters.append(data)
            except json.JSONDecodeError:
                parsed = _parse_filter_string(raw)
                if parsed:
                    filters.append(parsed)
        else:
            parsed = _parse_filter_string(raw)
            if parsed:
                filters.append(parsed)
    return filters or None


def _build_filters(
    filters: Optional[Union[str, Dict[str, Any], Iterable[Union[str, Dict[str, Any]]]]],
    language: Optional[str],
    project: Optional[str],
) -> Optional[List[Dict[str, Any]]]:
    filter_list = _normalize_filters(filters) or []
    if language:
        filter_list.append({"field": "in_language.identifier", "value": str(language).strip()})
    if project:
        filter_list.append({"field": "is_part_of.identifier", "value": str(project).strip()})
    return filter_list or None


def _request_articles(
    name: str,
    limit: Optional[int],
    fields: Optional[List[str]],
    filters: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    url = f"{API_BASE}/articles/{quote(str(name))}"
    headers = _auth_headers()
    body: Dict[str, Any] = {}
    if limit:
        body["limit"] = limit
    if fields:
        body["fields"] = fields
    if filters:
        body["filters"] = filters

    try:
        if body:
            resp = requests.post(url, headers=headers, json=body, timeout=20)
            if resp.status_code in (400, 405):
                params: Dict[str, Any] = {}
                if limit:
                    params["limit"] = limit
                if fields:
                    params["fields"] = ",".join(fields)
                if filters:
                    params["filters"] = json.dumps(filters)
                resp = requests.get(url, headers=headers, params=params, timeout=20)
        else:
            resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Wikimedia Enterprise API request failed: {exc}") from exc

    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError("Unexpected API response format: expected a list of articles.")
    return data


def _select_article_body(article: Dict[str, Any], fields: Optional[List[str]]) -> Tuple[str, str]:
    body = article.get("article_body") or {}
    if not isinstance(body, dict):
        body = {}

    prefer_html = fields and "article_body.html" in fields and "article_body.wikitext" not in fields
    if prefer_html:
        return body.get("html") or "", "html"

    if body.get("wikitext"):
        return body.get("wikitext") or "", "wikitext"
    if body.get("html"):
        return body.get("html") or "", "html"
    return "", "wikitext"


def _format_article_summary(article: Dict[str, Any]) -> str:
    name = article.get("name") or "Unknown"
    url = article.get("url") or "Unknown"
    abstract = article.get("abstract") or ""
    language = (article.get("in_language") or {}).get("identifier") or "Unknown"
    project = (article.get("is_part_of") or {}).get("identifier") or "Unknown"
    parts = [
        f"Name: {name}",
        f"URL: {url}",
        f"Language: {language}",
        f"Project: {project}",
    ]
    if abstract:
        parts.append(f"Abstract: {abstract}")
    return "\n".join(parts)


@function_schema(
    name="wme_search_articles",
    description="Lookup articles by name and return a compact list of matches.",
    required_params=["name"],
    optional_params=["limit", "fields", "filters", "language", "project"],
)
def wme_search_articles(
    name: str,
    limit: int = 5,
    fields: Optional[Union[str, Iterable[str]]] = None,
    filters: Optional[Union[str, Dict[str, Any], Iterable[Union[str, Dict[str, Any]]]]] = None,
    language: Optional[str] = None,
    project: Optional[str] = None,
) -> str:
    """
    Lookup articles by name. This uses the on-demand articles endpoint.
    """
    try:
        limit_val = _coerce_int(limit, default=5) or 5
        fields_list = _normalize_fields(fields)
        filter_list = _build_filters(filters, language, project)
        articles = _request_articles(name, limit_val, fields_list, filter_list)
        if not articles:
            return "No articles found for the provided name."
        lines = ["Article matches:"]
        for idx, article in enumerate(articles, 1):
            lines.append(f"\nResult {idx}:\n{_format_article_summary(article)}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error searching articles: {exc}"


@function_schema(
    name="wme_get_article",
    description="Retrieve a single article body and metadata.",
    required_params=["name"],
    optional_params=["fields", "filters", "language", "project", "max_chars"],
)
def wme_get_article(
    name: str,
    fields: Optional[Union[str, Iterable[str]]] = None,
    filters: Optional[Union[str, Dict[str, Any], Iterable[Union[str, Dict[str, Any]]]]] = None,
    language: Optional[str] = None,
    project: Optional[str] = None,
    max_chars: int = 12000,
) -> str:
    """
    Retrieve the most current revision of an article, including article_body content.
    """
    try:
        fields_list = _normalize_fields(fields)
        filter_list = _build_filters(filters, language, project)
        articles = _request_articles(name, 1, fields_list, filter_list)
        if not articles:
            return "No article found for the provided name."
        article = articles[0]
        body_text, body_kind = _select_article_body(article, fields_list)
        if not body_text:
            return "Article found, but no article_body content was returned."

        max_chars_val = _coerce_int(max_chars, default=12000) or 12000
        trimmed = False
        if max_chars_val > 0 and len(body_text) > max_chars_val:
            body_text = body_text[:max_chars_val].rstrip()
            trimmed = True

        name_out = article.get("name") or "Unknown"
        url = article.get("url") or "Unknown"
        date_modified = article.get("date_modified") or "Unknown"
        language_id = (article.get("in_language") or {}).get("identifier") or "Unknown"
        project_id = (article.get("is_part_of") or {}).get("identifier") or "Unknown"
        abstract = article.get("abstract") or ""

        lines = [
            f"Name: {name_out}",
            f"URL: {url}",
            f"Date modified: {date_modified}",
            f"Language: {language_id}",
            f"Project: {project_id}",
            f"Body format: {body_kind}",
        ]
        if abstract:
            lines.append(f"Abstract: {abstract}")
        if trimmed:
            lines.append(f"Note: article_body truncated to {max_chars_val} characters.")
        lines.append("\nArticle body:\n" + body_text)
        return "\n".join(lines)
    except Exception as exc:
        return f"Error retrieving article: {exc}"
