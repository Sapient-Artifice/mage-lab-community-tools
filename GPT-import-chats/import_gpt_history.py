#!/usr/bin/env python3
"""Import ChatGPT chat history exports into Mage Lab chat format.

CLI usage:
    python import_gpt_history.py <input_path> [output_dir] [--overwrite]

    input_path  Path to conversations.json, a .zip export bundle, or a directory
                containing conversations.json.
    output_dir  Where to write converted chat files (default: ~/Mage/Chats).
    --overwrite Replace existing files instead of skipping them.

Mage tool usage:
    Ask the assistant to run import_gpt_history and provide the path to your
    ChatGPT export bundle.
"""

import argparse
import json
import logging
import re
import shutil
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text utilities (retained from original, lightly cleaned up)
# ---------------------------------------------------------------------------

def _normalize_text(text: Any) -> str:
    """Apply Unicode NFKC normalization to a value coerced to string.

    :param text: Value to normalize.
    :return: Normalized string.
    """
    if not isinstance(text, str):
        text = str(text)
    return unicodedata.normalize("NFKC", text)


def _clean_text(text: str) -> str:
    """Strip C0/C1 control characters that would break JSON consumers.

    :param text: Raw text string.
    :return: Cleaned string with control characters replaced by spaces.
    """
    text = _normalize_text(text)
    return re.sub(r"[\x00-\x1F\x7F]+", " ", text)


def _format_timestamp(value: Any) -> str:
    """Format a Unix float timestamp or ISO string as a readable UTC date.

    :param value: Unix timestamp (int/float) or ISO 8601 string.
    :return: Human-readable UTC date string, or the raw value on failure.
    """
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(value)


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

def _extract_content(message: Dict[str, Any]) -> str:
    """Convert a ChatGPT message object to a plain text string.

    Handles all known content_type values.  Structured content (tool calls,
    code output, web results, images) is represented as inline annotations.

    :param message: A message dict from the conversation mapping.
    :return: Extracted text, or empty string if nothing useful is present.
    """
    content = message.get("content") or {}
    content_type = content.get("content_type", "text")
    parts = content.get("parts") or []

    if content_type == "text":
        texts = [_clean_text(p) for p in parts if isinstance(p, str) and p.strip()]
        return "\n".join(texts)

    if content_type == "multimodal_text":
        segments: List[str] = []
        for p in parts:
            if isinstance(p, str) and p.strip():
                segments.append(_clean_text(p))
            elif isinstance(p, dict):
                ct = p.get("content_type", "")
                if ct == "image_asset_pointer":
                    segments.append("[Image]")
                elif ct == "real_time_user_audio_video_asset_pointer":
                    segments.append("[Audio/Video]")
                else:
                    segments.append(f"[{ct}]")
        return "\n".join(segments)

    if content_type == "code":
        lang = content.get("language", "")
        code_parts = [_clean_text(p) for p in parts if isinstance(p, str)]
        code_text = "\n".join(code_parts)
        label = f"[Code ({lang})]" if lang else "[Code]"
        return f"{label}\n{code_text}" if code_text else label

    if content_type == "execution_output":
        output_parts = [_clean_text(p) for p in parts if isinstance(p, str)]
        output_text = "\n".join(output_parts)
        return f"[Code output]\n{output_text}" if output_text else "[Code output]"

    if content_type == "tether_quote":
        title = _clean_text(content.get("title") or "")
        url = _clean_text(content.get("url") or "")
        text_body = _clean_text(content.get("text") or "")
        label = f"[Web source: {title} ({url})]" if url else f"[Web source: {title}]"
        return f"{label}\n{text_body}" if text_body else label

    if content_type == "tether_browsing_display":
        result_parts = [_clean_text(p) for p in parts if isinstance(p, str)]
        return f"[Web browsing result]\n" + "\n".join(result_parts) if result_parts else "[Web browsing result]"

    if content_type == "image_asset_pointer":
        return "[Image]"

    # Generic fallback: join any string parts
    fallback = [_clean_text(p) for p in parts if isinstance(p, str) and p.strip()]
    if fallback:
        return "\n".join(fallback)
    return f"[{content_type}]"


# ---------------------------------------------------------------------------
# Tree traversal
# ---------------------------------------------------------------------------

def _get_active_path(mapping: Dict[str, Any], current_node_id: str) -> List[str]:
    """Walk from current_node back to root via parent pointers.

    This follows the active conversation branch only, correctly ignoring
    messages from edits or regenerations that were discarded.

    :param mapping: The full node mapping dict from the conversation.
    :param current_node_id: The ID of the last (most recent) node.
    :return: List of node IDs in chronological order (root → current).
    """
    path: List[str] = []
    node_id: Optional[str] = current_node_id

    visited = set()
    while node_id and node_id not in visited:
        visited.add(node_id)
        path.append(node_id)
        node = mapping.get(node_id) or {}
        node_id = node.get("parent")

    path.reverse()
    return path


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def _build_system_message(conv: Dict[str, Any]) -> Dict[str, str]:
    """Build a Mage system message containing provenance metadata.

    :param conv: A single conversation dict from ChatGPT's conversations.json.
    :return: A message dict with role='system'.
    """
    title = conv.get("title") or "Untitled"
    conv_id = conv.get("conversation_id") or conv.get("id") or ""
    create_time = conv.get("create_time")
    update_time = conv.get("update_time")
    model = conv.get("default_model_slug") or ""
    gizmo_name = conv.get("gizmo_name") or ""
    is_starred = bool(conv.get("is_starred"))
    import_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "This conversation was imported from ChatGPT (chat.openai.com).",
        f'Title: "{_normalize_text(title)}"',
    ]
    if model:
        lines.append(f"Model: {_normalize_text(model)}")
    if gizmo_name:
        lines.append(f"Custom GPT: {_normalize_text(gizmo_name)}")
    if is_starred:
        lines.append("Starred: yes")
    lines += [
        f"Original conversation ID: {conv_id}",
        f"Originally created: {_format_timestamp(create_time) if create_time is not None else 'unknown'}",
        f"Originally last updated: {_format_timestamp(update_time) if update_time is not None else 'unknown'}",
        f"Imported into Mage Lab: {import_time}",
        "",
        "This is a read-only historical record. Code blocks, tool calls, and web "
        "results are represented as inline annotations wrapped in [square brackets].",
    ]

    return {"role": "system", "content": "\n".join(lines)}


def _convert_conversation(conv: Dict[str, Any]) -> List[Dict[str, str]]:
    """Convert one ChatGPT conversation to a Mage-compatible message list.

    Follows the active branch from current_node back to root, skipping system
    and tool role messages.

    :param conv: A single conversation dict from ChatGPT's conversations.json.
    :return: List of {role, content} dicts ready to be written as a Mage chat file.
    """
    messages: List[Dict[str, str]] = [_build_system_message(conv)]

    mapping = conv.get("mapping") or {}
    current_node = conv.get("current_node")

    if not mapping:
        return messages

    if current_node and current_node in mapping:
        node_ids = _get_active_path(mapping, current_node)
    else:
        # Fallback: find root and do a linear DFS (for exports without current_node)
        roots = [v for v in mapping.values() if not v.get("parent")]
        node_ids = []
        stack = [r["id"] for r in roots]
        while stack:
            nid = stack.pop(0)
            node_ids.append(nid)
            node = mapping.get(nid) or {}
            stack = (node.get("children") or []) + stack

    for node_id in node_ids:
        node = mapping.get(node_id) or {}
        msg = node.get("message")
        if not msg:
            continue

        role = (msg.get("author") or {}).get("role", "")
        if role not in ("user", "assistant"):
            continue

        text = _extract_content(msg)
        if not text.strip():
            continue

        messages.append({"role": role, "content": text})

    return messages


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str, max_length: int = 55) -> str:
    """Convert a conversation title to a safe filename slug.

    :param name: Raw conversation title.
    :param max_length: Maximum character length of the slug.
    :return: Lowercase, hyphenated, alphanumeric slug.
    """
    s = _normalize_text(name).lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:max_length]


def _make_output_filename(conv: Dict[str, Any]) -> str:
    """Build a descriptive, chronologically sortable output filename.

    Format: ``gpt-YYYY-MM-DD-<slugged-title>-<short-id>.json``

    :param conv: A single conversation dict.
    :return: Filename string.
    """
    title = conv.get("title") or "untitled"
    conv_id = conv.get("conversation_id") or conv.get("id") or ""
    create_time = conv.get("create_time")

    date_prefix = ""
    if create_time is not None:
        try:
            dt = datetime.fromtimestamp(float(create_time), tz=timezone.utc)
            date_prefix = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    safe_title = _sanitize_filename(title)
    short_id = conv_id.replace("-", "")[:8] if conv_id else "noid"

    parts = ["gpt"]
    if date_prefix:
        parts.append(date_prefix)
    if safe_title:
        parts.append(safe_title)
    parts.append(short_id)

    return "-".join(parts) + ".json"


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def _load_conversations(input_path: Path) -> Tuple[List[Dict], Optional[Path]]:
    """Locate and parse conversations.json from various input forms.

    Accepts a direct conversations.json file, a directory containing one,
    or a .zip export bundle.

    :param input_path: Resolved path supplied by the user.
    :return: Tuple of (list of conversation dicts, temp_dir to clean up or None).
    :raises FileNotFoundError: If conversations.json cannot be located.
    :raises ValueError: If the JSON structure is not recognised.
    """
    temp_dir: Optional[Path] = None

    if input_path.suffix.lower() == ".zip":
        temp_dir = Path(tempfile.mkdtemp(prefix="mage_gpt_import_"))
        try:
            with zipfile.ZipFile(input_path) as zf:
                zf.extractall(temp_dir)
        except zipfile.BadZipFile as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise FileNotFoundError(
                f"The file does not appear to be a valid zip archive: {exc}"
            ) from exc
        matches = list(temp_dir.rglob("conversations.json"))
        if not matches:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise FileNotFoundError(
                "conversations.json was not found inside the zip archive."
            )
        json_path = matches[0]

    elif input_path.is_dir():
        json_path = input_path / "conversations.json"
        if not json_path.exists():
            raise FileNotFoundError(
                f"conversations.json not found in directory: {input_path}"
            )

    elif input_path.is_file():
        json_path = input_path

    else:
        raise FileNotFoundError(
            f"Path does not exist or is not accessible: {input_path}"
        )

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise ValueError(f"conversations.json is not valid JSON: {exc}") from exc

    if isinstance(data, list):
        return data, temp_dir
    if isinstance(data, dict):
        for key in ("conversations", "data"):
            if isinstance(data.get(key), list):
                return data[key], temp_dir

    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)
    raise ValueError(
        "Unexpected conversations.json structure. Expected a JSON array of conversations."
    )


# ---------------------------------------------------------------------------
# Main import function
# ---------------------------------------------------------------------------

def import_gpt_history(
    input_path: str,
    output_dir: str = None,
    overwrite: bool = False,
) -> str:
    """Import ChatGPT exported chat history into Mage Lab format.

    Each conversation in the export bundle is written as a separate JSON file
    in the Mage chats folder, prefixed with metadata that identifies its origin.

    :param input_path: Path to conversations.json, a .zip export bundle, or a directory containing conversations.json.
    :param output_dir: Destination folder for converted chat files. Defaults to ~/Mage/Chats.
    :param overwrite: If True, replace any existing output file with the same name.
    :return: Human-readable summary of the import result.
    """
    resolved_input = Path(input_path).expanduser().resolve()
    if not resolved_input.exists():
        return f"Error: Input path does not exist: {resolved_input}"

    if output_dir:
        out_dir = Path(output_dir).expanduser().resolve()
    else:
        try:
            from config import config  # noqa: PLC0415
            out_dir = Path(config.chats_folder)
        except Exception:
            out_dir = Path.home() / "Mage" / "Chats"

    out_dir.mkdir(parents=True, exist_ok=True)

    temp_dir: Optional[Path] = None
    try:
        conversations, temp_dir = _load_conversations(resolved_input)
    except (FileNotFoundError, ValueError) as exc:
        return f"Error: {exc}"

    try:
        imported: List[str] = []
        skipped: List[str] = []
        errors: List[str] = []

        for conv in conversations:
            if not isinstance(conv, dict):
                errors.append(f"Skipping unexpected entry of type {type(conv).__name__}.")
                continue

            filename = _make_output_filename(conv)
            out_path = out_dir / filename

            if out_path.exists() and not overwrite:
                skipped.append(
                    f"{filename}  (already exists — pass overwrite=True to replace)"
                )
                continue

            try:
                messages = _convert_conversation(conv)
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(messages, f, indent=2, ensure_ascii=False)
                imported.append(f"{filename}  ({len(messages) - 1} messages)")
            except Exception as exc:  # noqa: BLE001
                title = conv.get("title") or "?"
                errors.append(f'Failed to convert "{title}": {exc}')
                logger.exception("Conversion error for conversation %r", title)

        lines = ["ChatGPT chat import complete."]
        lines.append(f"  Imported:  {len(imported)} conversation(s) → {out_dir}")
        for item in imported:
            lines.append(f"    + {item}")
        if skipped:
            lines.append(f"  Skipped:   {len(skipped)} (already exist)")
            for item in skipped:
                lines.append(f"    ~ {item}")
        if errors:
            lines.append(f"  Errors:    {len(errors)}")
            for item in errors:
                lines.append(f"    ! {item}")

        return "\n".join(lines)

    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Mage tool registration
# ---------------------------------------------------------------------------

try:
    from utils.functions_metadata import function_schema  # noqa: PLC0415

    import_gpt_history = function_schema(
        name="import_gpt_history",
        description=(
            "Import ChatGPT chat history from an export bundle into Mage Lab's chat "
            "storage. Accepts a conversations.json file, a .zip export bundle, or a "
            "directory containing conversations.json. Each conversation is converted to "
            "a Mage-compatible JSON file in the chats folder with a system message that "
            "records its origin, title, model, and dates."
        ),
        required_params=["input_path"],
        optional_params=["output_dir", "overwrite"],
    )(import_gpt_history)

except ImportError:
    pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Import ChatGPT chat history exports into Mage Lab format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "input_path",
        help="Path to conversations.json, a .zip export bundle, or a directory.",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help="Destination folder (default: ~/Mage/Chats).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing output files instead of skipping them.",
    )
    args = parser.parse_args()

    result = import_gpt_history(
        input_path=args.input_path,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
    )
    print(result)


if __name__ == "__main__":
    _cli()
