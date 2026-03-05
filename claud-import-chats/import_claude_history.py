#!/usr/bin/env python3
"""Import Claude.ai chat history exports into Mage Lab chat format.

CLI usage:
    python import_claude_history.py <input_path> [output_dir] [--thinking] [--overwrite]

    input_path  Path to conversations.json, a .zip export bundle, or a directory
                containing conversations.json.
    output_dir  Where to write converted chat files (default: ~/Mage/Chats).
    --thinking  Include Claude's extended thinking blocks as annotations.
    --overwrite Replace existing files instead of skipping them.

Mage tool usage:
    Ask the assistant to run import_claude_history and provide the path to your
    Claude export bundle.
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

def _extract_text_from_content(
    content_blocks: list,
    include_thinking: bool = False,
) -> str:
    """Convert a list of Claude.ai content blocks to a plain text string.

    Text blocks are included verbatim.  Tool calls and results are represented
    as readable inline annotations.  Thinking blocks are optional.

    :param content_blocks: List of content block dicts from the export.
    :param include_thinking: Whether to include extended thinking blocks.
    :return: Joined text suitable for a Mage message content field.
    """
    parts: List[str] = []

    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")

        if btype == "text":
            text = (block.get("text") or "").strip()
            if text:
                parts.append(text)

        elif btype == "thinking" and include_thinking:
            thinking = (block.get("thinking") or "").strip()
            if thinking:
                parts.append(f"[Extended thinking: {thinking}]")

        elif btype == "tool_use":
            name = block.get("name", "unknown")
            inp = block.get("input") or {}
            try:
                inp_str = json.dumps(inp, ensure_ascii=False)
            except Exception:
                inp_str = str(inp)
            parts.append(f"[Tool call: {name}({inp_str})]")

        elif btype == "tool_result":
            name = block.get("name", "unknown")
            is_error = bool(block.get("is_error"))
            result_content = block.get("content") or []
            result_texts: List[str] = []

            if isinstance(result_content, list):
                for item in result_content:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("type", "")
                    if item_type == "text":
                        t = (item.get("text") or "").strip()
                        if t:
                            result_texts.append(t)
                    elif item_type == "knowledge":
                        title = item.get("title", "")
                        url = item.get("url", "")
                        if title and url:
                            result_texts.append(f"{title} ({url})")
                        elif title:
                            result_texts.append(title)
            elif isinstance(result_content, str):
                result_texts = [result_content.strip()]

            result_str = "; ".join(result_texts) if result_texts else "[no result]"
            label = "Tool error" if is_error else "Tool result"
            parts.append(f"[{label} from {name}: {result_str}]")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def _build_system_message(conv: Dict[str, Any]) -> Dict[str, str]:
    """Build a Mage system message containing provenance metadata for a conversation.

    :param conv: A single conversation dict from Claude.ai's conversations.json.
    :return: A message dict with role='system' describing the import source.
    """
    name = conv.get("name") or "Untitled"
    summary = (conv.get("summary") or "").strip()
    uuid = conv.get("uuid") or ""
    created_at = conv.get("created_at") or ""
    updated_at = conv.get("updated_at") or ""
    import_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "This conversation was imported from Claude.ai.",
        f'Title: "{name}"',
    ]
    if summary:
        lines.append(f"Summary: {summary}")
    lines += [
        f"Original conversation ID: {uuid}",
        f"Originally created: {created_at}",
        f"Originally last updated: {updated_at}",
        f"Imported into Mage Lab: {import_time}",
        "",
        "This is a read-only historical record. Tool calls and their results are"
        " represented as inline annotations wrapped in [square brackets].",
    ]

    return {"role": "system", "content": "\n".join(lines)}


def _convert_conversation(
    conv: Dict[str, Any],
    include_thinking: bool = False,
) -> List[Dict[str, str]]:
    """Convert one Claude.ai conversation to a Mage-compatible message list.

    :param conv: A single conversation dict from Claude.ai's conversations.json.
    :param include_thinking: Whether to include extended thinking blocks.
    :return: List of {role, content} dicts ready to be written as a Mage chat file.
    """
    messages: List[Dict[str, str]] = [_build_system_message(conv)]

    for msg in conv.get("chat_messages") or []:
        sender = msg.get("sender", "")
        if sender == "human":
            role = "user"
        elif sender == "assistant":
            role = "assistant"
        else:
            logger.debug("Skipping message with unknown sender: %r", sender)
            continue

        content_blocks = msg.get("content") or []
        if content_blocks:
            text = _extract_text_from_content(
                content_blocks, include_thinking=include_thinking
            )
        else:
            # Fall back to the top-level 'text' field when content is absent
            text = (msg.get("text") or "").strip()

        if not text:
            logger.debug("Skipping empty %s message", role)
            continue

        messages.append({"role": role, "content": text})

    return messages


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str, max_length: int = 55) -> str:
    """Convert a conversation title to a safe, human-readable filename component.

    :param name: The raw conversation name.
    :param max_length: Maximum character length of the result.
    :return: Lowercase, hyphenated, alphanumeric-only slug.
    """
    s = name.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:max_length]


def _make_output_filename(conv: Dict[str, Any]) -> str:
    """Build a descriptive, chronologically sortable output filename.

    Format: ``claude-YYYY-MM-DD-<slugged-title>-<short-uuid>.json``

    :param conv: A single conversation dict.
    :return: Filename string.
    """
    name = conv.get("name") or "untitled"
    uuid = conv.get("uuid") or ""
    created_at = conv.get("created_at") or ""

    date_prefix = ""
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            date_prefix = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    safe_name = _sanitize_filename(name)
    short_uuid = uuid[:8] if uuid else "noid"

    parts = ["claude"]
    if date_prefix:
        parts.append(date_prefix)
    if safe_name:
        parts.append(safe_name)
    parts.append(short_uuid)

    return "-".join(parts) + ".json"


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def _load_conversations(input_path: Path) -> Tuple[List[Dict], Optional[Path]]:
    """Locate and parse conversations.json from various input forms.

    Accepts a direct ``conversations.json`` file, a directory containing one,
    or a ``.zip`` export bundle.

    :param input_path: Resolved path to the user-supplied input.
    :return: Tuple of (list of conversation dicts, temp_dir to clean up or None).
    :raises FileNotFoundError: If conversations.json cannot be located.
    :raises ValueError: If the JSON structure is not a recognised format.
    """
    temp_dir: Optional[Path] = None

    if input_path.suffix.lower() == ".zip":
        temp_dir = Path(tempfile.mkdtemp(prefix="mage_claude_import_"))
        try:
            with zipfile.ZipFile(input_path) as zf:
                zf.extractall(temp_dir)
        except zipfile.BadZipFile as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise FileNotFoundError(f"The file does not appear to be a valid zip archive: {exc}") from exc
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
        raise FileNotFoundError(f"Path does not exist or is not accessible: {input_path}")

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

def import_claude_history(
    input_path: str,
    output_dir: str = None,
    include_thinking: bool = False,
    overwrite: bool = False,
) -> str:
    """Import Claude.ai exported chat history into Mage Lab format.

    Each conversation in the export bundle is written as a separate JSON file
    in the Mage chats folder, prefixed with metadata that identifies its origin.

    :param input_path: Path to conversations.json, a .zip export bundle, or a directory containing conversations.json.
    :param output_dir: Destination folder for converted chat files. Defaults to ~/Mage/Chats.
    :param include_thinking: If True, include Claude's extended thinking blocks as annotations in the output.
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
            from config import config  # noqa: PLC0415  (conditional import for CLI use)
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
                messages = _convert_conversation(conv, include_thinking=include_thinking)
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(messages, f, indent=2, ensure_ascii=False)
                imported.append(f"{filename}  ({len(messages) - 1} messages)")
            except Exception as exc:  # noqa: BLE001
                title = conv.get("name") or "?"
                errors.append(f'Failed to convert "{title}": {exc}')
                logger.exception("Conversion error for conversation %r", title)

        lines = ["Claude.ai chat import complete."]
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

    import_claude_history = function_schema(
        name="import_claude_history",
        description=(
            "Import Claude.ai chat history from an export bundle into Mage Lab's chat "
            "storage. Accepts a conversations.json file, a .zip export bundle, or a "
            "directory containing conversations.json. Each conversation is converted to "
            "a Mage-compatible JSON file in the chats folder with a system message that "
            "records its origin, title, and dates."
        ),
        required_params=["input_path"],
        optional_params=["output_dir", "include_thinking", "overwrite"],
    )(import_claude_history)

except ImportError:
    # Running standalone — schema registration is not needed
    pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Import Claude.ai chat history exports into Mage Lab format.",
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
        "--thinking",
        action="store_true",
        default=False,
        help="Include Claude's extended thinking blocks as annotations.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing output files instead of skipping them.",
    )
    args = parser.parse_args()

    result = import_claude_history(
        input_path=args.input_path,
        output_dir=args.output_dir,
        include_thinking=args.thinking,
        overwrite=args.overwrite,
    )
    print(result)


if __name__ == "__main__":
    _cli()
