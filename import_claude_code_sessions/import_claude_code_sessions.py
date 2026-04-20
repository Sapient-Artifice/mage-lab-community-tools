#!/usr/bin/env python3
"""Import Claude Code CLI session transcripts into Mage Lab chat format.

CLI usage:

    python import_claude_code_sessions.py [input_dir] [output_dir] [--thinking] [--overwrite] [--include-agents] [--truncate-tool-args N]

    input_dir     Path to the projects/ directory to scan (default: ~/.claude/projects).
                  Point this at an rsync backup copy to avoid touching live data.
    output_dir    Where to write converted chat files (default: ~/Mage/Chats).
    --thinking    Include Claude's extended thinking blocks as annotations.
    --overwrite   Replace existing files instead of skipping them.
    --include-agents  Also import sub-agent session files (agent-*.jsonl).
    --truncate-tool-args N  Trim tool arguments and results to N chars. Off by
                            default (full fidelity). Enable to reduce file size
                            when sessions contain large file writes or output.

Mage tool usage:

    Ask the assistant to run import_claude_code_sessions and optionally provide
    the path to your rsync backup of ~/.claude/projects.

Design notes:

    This tool is the Claude Code CLI counterpart to import_claude_history.py,
    which handles server-side Claude.ai chat exports. Both produce the same
    Mage-compatible JSON output format so that all conversations—regardless of
    origin—land in a single searchable archive.

    Intended workflow:
      1. Scheduled rsync job backs up ~/.claude/ to a stable location.
      2. This tool runs after each backup, scanning for new sessions.
      3. New sessions are converted and written to ~/Mage/Chats.

    Output filenames use the prefix 'claude-code-' (vs 'claude-' for GUI chats)
    so you can distinguish origin at a glance.
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file, skipping malformed lines.

    :param path: Path to a .jsonl file.
    :return: List of parsed JSON objects.
    """
    events: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                logger.debug("Skipping malformed JSON at %s:%d", path, lineno)
    return events


# ---------------------------------------------------------------------------
# Content extraction — mirrors import_claude_history.py's approach
# ---------------------------------------------------------------------------

def _extract_assistant_messages(
    content_raw: Any,
    include_thinking: bool,
    tool_id_to_name: Dict[str, str],
    truncate: Optional[int],
) -> List[Dict[str, Any]]:
    """Convert one assistant event's content to a list of Mage message dicts.

    Returns zero or one message. The message uses the native Mage format:
    ``role: "assistant"`` with an optional ``tool_calls`` list so that
    ``decorateHistoryMessages`` can generate toggleable tool-debug bubbles.

    :param content_raw: The message.content value — str or list of dicts.
    :param include_thinking: Whether to include extended thinking blocks.
    :param tool_id_to_name: Mutable dict updated with id→name for each
        tool_use block seen, so tool results can look up the tool name.
    :param truncate: If set, trim ``arguments`` strings to this many chars.
    :return: List of zero or one Mage message dicts.
    """
    if isinstance(content_raw, str):
        text = content_raw.strip()
        return [{"role": "assistant", "content": text}] if text else []

    if not isinstance(content_raw, list):
        return []

    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []

    for block in content_raw:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")

        if btype == "text":
            text = (block.get("text") or "").strip()
            if text:
                text_parts.append(text)

        elif btype == "thinking" and include_thinking:
            thinking = (block.get("thinking") or "").strip()
            if thinking:
                text_parts.append(f"[Thinking: {thinking}]")

        elif btype == "tool_use":
            name = block.get("name", "unknown")
            tool_id = block.get("id", "")
            if tool_id:
                tool_id_to_name[tool_id] = name
            inp = block.get("input") or {}
            try:
                args_str = json.dumps(inp, ensure_ascii=False)
            except Exception:
                args_str = str(inp)
            if truncate is not None and len(args_str) > truncate:
                args_str = args_str[:truncate] + " \u2026 [truncated]"
            tool_calls.append({"function": {"name": name, "arguments": args_str}})

    content = "\n\n".join(text_parts)
    if not content and not tool_calls:
        return []

    msg: Dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return [msg]


def _extract_user_messages(
    content_raw: Any,
    tool_id_to_name: Dict[str, str],
    truncate: Optional[int],
) -> List[Dict[str, Any]]:
    """Convert one user event's content to a list of Mage message dicts.

    Tool result blocks become ``role: "tool"`` messages (rendered only when
    tool-debug is on). Text blocks become a single ``role: "user"`` message.
    If the turn has no text blocks, no user message is emitted.

    :param content_raw: The message.content value — str or list of dicts.
    :param tool_id_to_name: Dict of tool_use_id→name built from assistant
        events, used to populate the ``name`` field on tool messages.
    :param truncate: If set, trim result ``content`` to this many chars.
    :return: List of zero or more Mage message dicts.
    """
    if isinstance(content_raw, str):
        text = content_raw.strip()
        return [{"role": "user", "content": text}] if text else []

    if not isinstance(content_raw, list):
        return []

    tool_messages: List[Dict[str, Any]] = []
    text_parts: List[str] = []

    for block in content_raw:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")

        if btype == "tool_result":
            tool_id = block.get("tool_use_id", "")
            is_error = bool(block.get("is_error"))
            result_content = block.get("content") or ""

            if isinstance(result_content, list):
                result_texts = []
                for item in result_content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        t = (item.get("text") or "").strip()
                        if t:
                            result_texts.append(t)
                result_str = "\n".join(result_texts) if result_texts else "[no result]"
            elif isinstance(result_content, str):
                result_str = result_content.strip() or "[no result]"
            else:
                result_str = "[no result]"

            if is_error:
                result_str = f"[error] {result_str}"

            if truncate is not None and len(result_str) > truncate:
                result_str = result_str[:truncate] + " \u2026 [truncated]"

            tool_messages.append({
                "role": "tool",
                "name": tool_id_to_name.get(tool_id, ""),
                "content": result_str,
            })

        elif btype == "text":
            text = (block.get("text") or "").strip()
            if text:
                text_parts.append(text)

    result: List[Dict[str, Any]] = list(tool_messages)
    if text_parts:
        result.append({"role": "user", "content": "\n\n".join(text_parts)})
    return result


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def _decode_project_dir_name(dirname: str) -> str:
    """Reverse the path-encoding Claude Code uses for project directories.

    Claude Code replaces '/' with '-' in directory names, with a leading
    dash for the root slash.  e.g. '-Users-sam-Projects-my-app'
    becomes '/Users/sam/Projects/my-app'.

    NOTE: This is a lossy encoding — hyphens in the original path are
    indistinguishable from separator hyphens.  The result is used only
    for display metadata; the authoritative path comes from the ``cwd``
    field in the session events themselves.

    :param dirname: The encoded directory name.
    :return: Best-effort decoded original path.
    """
    if dirname.startswith("-"):
        # Leading dash represents root '/'
        return "/" + dirname[1:].replace("-", "/")
    return dirname.replace("-", "/")


def _session_metadata_from_events(
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Extract session-level metadata from the first few JSONL events.

    :param events: Parsed JSONL events from a session file.
    :return: Dict with sessionId, gitBranch, cwd, version, first/last timestamps.
    """
    meta: Dict[str, Any] = {}
    first_ts: Optional[str] = None
    last_ts: Optional[str] = None

    for event in events:
        ts = event.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts

        if not meta.get("sessionId"):
            meta["sessionId"] = event.get("sessionId", "")
        if not meta.get("gitBranch"):
            meta["gitBranch"] = event.get("gitBranch", "")
        if not meta.get("cwd"):
            meta["cwd"] = event.get("cwd", "")
        if not meta.get("version"):
            meta["version"] = event.get("version", "")
        if not meta.get("slug"):
            meta["slug"] = event.get("slug", "")

    meta["first_timestamp"] = first_ts or ""
    meta["last_timestamp"] = last_ts or ""
    return meta


def _session_metadata_from_index(
    index_path: Path,
    session_id: str,
) -> Optional[Dict[str, Any]]:
    """Look up a session in sessions-index.json for richer metadata.

    :param index_path: Path to sessions-index.json.
    :param session_id: The session UUID to look up.
    :return: Index entry dict, or None if not found.
    """
    if not index_path.exists():
        return None
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    entries = data.get("entries") or data.get("sessions") or []
    if isinstance(data, list):
        entries = data

    for entry in entries:
        if isinstance(entry, dict):
            sid = entry.get("sessionId") or entry.get("id", "")
            if sid == session_id:
                return entry
    return None


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def _build_system_message(
    session_file: Path,
    project_dir_name: str,
    meta: Dict[str, Any],
    index_meta: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """Build a Mage system message with provenance metadata.

    Mirrors the system-message structure from import_claude_history.py
    but adapted for Claude Code session data.

    :param session_file: Path to the source .jsonl file.
    :param project_dir_name: Encoded project directory name.
    :param meta: Metadata extracted from JSONL events.
    :param index_meta: Optional metadata from sessions-index.json.
    :return: A message dict with role='system'.
    """
    decoded_path = _decode_project_dir_name(project_dir_name)
    cwd = meta.get("cwd") or ""
    # Prefer cwd from events (accurate) over decoded dirname (lossy)
    project_path = cwd or decoded_path
    session_id = meta.get("sessionId") or session_file.stem
    git_branch = meta.get("gitBranch") or ""
    version = meta.get("version") or ""
    slug = meta.get("slug") or ""
    first_ts = meta.get("first_timestamp") or ""
    last_ts = meta.get("last_timestamp") or ""

    # Enrich from index if available
    summary = ""
    message_count = ""
    if index_meta:
        summary = (index_meta.get("firstPrompt") or
                   index_meta.get("summary") or "").strip()
        mc = index_meta.get("messageCount")
        if mc is not None:
            message_count = str(mc)
        if not git_branch:
            git_branch = index_meta.get("gitBranch") or ""

    import_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "This conversation was imported from Claude Code (CLI).",
        f"Project: {project_path}",
    ]
    # Show decoded dirname as context if it differs (helps correlate to backup paths)
    if decoded_path != project_path and decoded_path:
        lines.append(f"Backup directory: {project_dir_name}")
    if git_branch:
        lines.append(f"Git branch: {git_branch}")
    if slug:
        lines.append(f"Session name: {slug}")
    if summary:
        lines.append(f"First prompt: {summary}")
    lines += [
        f"Session ID: {session_id}",
    ]
    if version:
        lines.append(f"Claude Code version: {version}")
    if message_count:
        lines.append(f"Message count: {message_count}")
    lines += [
        f"Session started: {first_ts}",
        f"Session last activity: {last_ts}",
        f"Imported into Mage Lab: {import_time}",
        "",
        "This is a read-only historical record. Tool calls and results are"
        " stored in native Mage format and shown in the tool-debug panel.",
    ]
    return {"role": "system", "content": "\n".join(lines)}


def _convert_session(
    session_file: Path,
    project_dir_name: str,
    index_meta: Optional[Dict[str, Any]],
    include_thinking: bool = False,
    truncate_tool_args: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Convert one Claude Code session JSONL file to Mage message list.

    :param session_file: Path to the .jsonl session file.
    :param project_dir_name: Encoded project directory name.
    :param index_meta: Optional sessions-index.json entry for this session.
    :param include_thinking: Whether to include extended thinking blocks.
    :param truncate_tool_args: If set, trim tool arguments and results to
        this many characters. None (default) preserves full fidelity.
    :return: List of {role, content, ...} dicts ready for a Mage chat file.
    """
    events = _read_jsonl(session_file)
    if not events:
        return []

    meta = _session_metadata_from_events(events)
    messages: List[Dict[str, Any]] = [
        _build_system_message(session_file, project_dir_name, meta, index_meta)
    ]

    # Maps tool_use id → tool name so tool results can carry the tool name.
    tool_id_to_name: Dict[str, str] = {}

    for event in events:
        etype = event.get("type", "")

        if etype in ("user", "human"):
            role_type = "user"
        elif etype == "assistant":
            role_type = "assistant"
        else:
            continue

        msg = event.get("message") or {}
        content_raw = msg.get("content")
        if content_raw is None:
            content_raw = event.get("content")
        if content_raw is None:
            continue

        if role_type == "assistant":
            new_msgs = _extract_assistant_messages(
                content_raw, include_thinking, tool_id_to_name, truncate_tool_args
            )
        else:
            new_msgs = _extract_user_messages(
                content_raw, tool_id_to_name, truncate_tool_args
            )

        messages.extend(new_msgs)

    return messages


# ---------------------------------------------------------------------------
# Filename helpers — mirrors import_claude_history.py conventions
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str, max_length: int = 55) -> str:
    """Convert a string to a safe, human-readable filename component.

    :param name: The raw string.
    :param max_length: Maximum character length of the result.
    :return: Lowercase, hyphenated, alphanumeric-only slug.
    """
    s = name.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:max_length]


def _make_output_filename(
    session_file: Path,
    project_dir_name: str,
    meta: Dict[str, Any],
    index_meta: Optional[Dict[str, Any]],
) -> str:
    """Build a descriptive, chronologically sortable output filename.

    Format: ``claude-code-YYYY-MM-DD-<project-slug>-<short-session-id>.json``

    Uses 'claude-code-' prefix to distinguish from GUI-origin 'claude-' files
    produced by import_claude_history.py.

    :param session_file: Path to the source .jsonl file.
    :param project_dir_name: Encoded project directory name.
    :param meta: Session metadata extracted from events.
    :param index_meta: Optional sessions-index.json entry.
    :return: Filename string.
    """
    session_id = meta.get("sessionId") or session_file.stem
    first_ts = meta.get("first_timestamp") or ""

    # Try to get a meaningful name: slug > first prompt > project path
    name = meta.get("slug") or ""
    if not name and index_meta:
        name = (index_meta.get("firstPrompt") or "").strip()
    if not name:
        name = _decode_project_dir_name(project_dir_name).split("/")[-1]

    date_prefix = ""
    if first_ts:
        try:
            dt = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            date_prefix = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    safe_name = _sanitize_filename(name)
    short_id = session_id[:8] if session_id else session_file.stem[:8]

    parts = ["claude-code"]
    if date_prefix:
        parts.append(date_prefix)
    if safe_name:
        parts.append(safe_name)
    parts.append(short_id)

    return "-".join(parts) + ".json"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _discover_sessions(
    projects_dir: Path,
    include_agents: bool = False,
) -> List[Tuple[Path, str]]:
    """Walk the projects directory and find all session JSONL files.

    :param projects_dir: Path to the projects/ directory.
    :param include_agents: Whether to include sub-agent files (agent-*.jsonl).
    :return: List of (session_file_path, project_dir_name) tuples.
    """
    sessions: List[Tuple[Path, str]] = []

    if not projects_dir.is_dir():
        return sessions

    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        project_name = project_dir.name

        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            # Skip sub-agent files unless requested
            if jsonl_file.name.startswith("agent-") and not include_agents:
                continue
            # Skip sessions-index.json and other non-session files
            if not jsonl_file.name.endswith(".jsonl"):
                continue
            sessions.append((jsonl_file, project_name))

    return sessions


# ---------------------------------------------------------------------------
# Main import function
# ---------------------------------------------------------------------------

def import_claude_code_sessions(
    input_dir: str = None,
    output_dir: str = None,
    include_thinking: bool = False,
    overwrite: bool = False,
    include_agents: bool = False,
    truncate_tool_args: Optional[int] = None,
) -> str:
    """Import Claude Code CLI session transcripts into Mage Lab format.

    Each session in ~/.claude/projects/ is written as a separate JSON file
    in the Mage chats folder, prefixed with metadata that identifies its
    origin. Output format is identical to import_claude_history.py so that
    GUI and CLI conversations coexist in a single searchable archive.

    :param input_dir: Path to the projects/ directory to scan.
        Defaults to ~/.claude/projects.  Point this at an rsync backup
        to avoid touching live data.
    :param output_dir: Destination folder for converted chat files.
        Defaults to ~/Mage/Chats.
    :param include_thinking: If True, include extended thinking blocks
        as annotations in the output.
    :param overwrite: If True, replace existing output files.
    :param include_agents: If True, also import sub-agent session files
        (agent-*.jsonl).  These are excluded by default since they are
        side conversations spawned by the main session.
    :param truncate_tool_args: When set to an integer N, tool call arguments
        and tool results longer than N characters are trimmed with a
        " … [truncated]" suffix. Default None preserves full fidelity.
    :return: Human-readable summary of the import result.
    """
    # Resolve input directory
    if input_dir:
        projects_dir = Path(input_dir).expanduser().resolve()
    else:
        projects_dir = Path.home() / ".claude" / "projects"

    if not projects_dir.exists():
        return f"Error: Projects directory does not exist: {projects_dir}"
    if not projects_dir.is_dir():
        return f"Error: Path is not a directory: {projects_dir}"

    # Resolve output directory
    if output_dir:
        out_dir = Path(output_dir).expanduser().resolve()
    else:
        try:
            from config import config  # noqa: PLC0415
            out_dir = Path(config.chats_folder)
        except Exception:
            out_dir = Path.home() / "Mage" / "Chats"

    out_dir.mkdir(parents=True, exist_ok=True)

    # Discover sessions
    session_files = _discover_sessions(projects_dir, include_agents=include_agents)
    if not session_files:
        return f"No session files found in: {projects_dir}"

    imported: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []
    empty: List[str] = []
    total_bytes: int = 0
    dates: List[str] = []  # collect session start dates for range summary

    total_sessions = len(session_files)
    for idx, (session_file, project_dir_name) in enumerate(session_files, 1):
        # Progress feedback for large archives
        if total_sessions >= 10 and (idx % 10 == 0 or idx == total_sessions):
            print(
                f"  Processing session {idx}/{total_sessions}...",
                file=sys.stderr,
                flush=True,
            )

        try:
            # Read just enough to get metadata for the filename
            events = _read_jsonl(session_file)
            if not events:
                empty.append(session_file.name)
                continue

            meta = _session_metadata_from_events(events)
            session_id = meta.get("sessionId") or session_file.stem

            # Try to load index metadata
            index_path = session_file.parent / "sessions-index.json"
            index_meta = _session_metadata_from_index(index_path, session_id)

            # Build output filename
            filename = _make_output_filename(
                session_file, project_dir_name, meta, index_meta
            )
            out_path = out_dir / filename

            if out_path.exists() and not overwrite:
                skipped.append(filename)
                continue

            # Full conversion
            messages = _convert_session(
                session_file,
                project_dir_name,
                index_meta,
                include_thinking=include_thinking,
                truncate_tool_args=truncate_tool_args,
            )

            if len(messages) <= 1:
                # Only the system message — no actual conversation
                empty.append(f"{session_file.name} (no user/assistant messages)")
                continue

            output_data = json.dumps(messages, indent=2, ensure_ascii=False)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(output_data)

            file_size = len(output_data.encode("utf-8"))
            total_bytes += file_size
            msg_count = len(messages) - 1  # exclude system message
            project_label = meta.get("cwd") or _decode_project_dir_name(project_dir_name)
            imported.append(f"{filename} ({msg_count} messages, {project_label})")

            # Track date for range summary
            first_ts = meta.get("first_timestamp") or ""
            if first_ts:
                dates.append(first_ts)

        except Exception as exc:  # noqa: BLE001
            errors.append(f'Failed "{session_file.name}": {exc}')
            logger.exception("Conversion error for %s", session_file)

    # Build summary report — always show all categories for confidence
    lines = ["Claude Code session import complete."]
    lines.append(f"  Source: {projects_dir}")
    lines.append(f"  Scanned: {total_sessions} session file(s)")
    lines.append(f"  Imported: {len(imported)} session(s) → {out_dir}")
    for item in imported:
        lines.append(f"    + {item}")
    lines.append(f"  Skipped: {len(skipped)} (already exist)")
    if skipped:
        for item in skipped:
            lines.append(f"    ~ {item}")
    lines.append(f"  Empty: {len(empty)} (no conversation content)")
    if empty:
        for item in empty:
            lines.append(f"    - {item}")
    lines.append(f"  Errors: {len(errors)}")
    if errors:
        for item in errors:
            lines.append(f"    ! {item}")

    # Date range
    if dates:
        sorted_dates = sorted(dates)
        try:
            oldest = datetime.fromisoformat(
                sorted_dates[0].replace("Z", "+00:00")
            ).strftime("%Y-%m-%d")
            newest = datetime.fromisoformat(
                sorted_dates[-1].replace("Z", "+00:00")
            ).strftime("%Y-%m-%d")
            lines.append(f"  Date range: {oldest} → {newest}")
        except Exception:
            pass

    # Size
    if total_bytes > 0:
        if total_bytes >= 1_048_576:
            size_str = f"{total_bytes / 1_048_576:.1f} MB"
        else:
            size_str = f"{total_bytes / 1024:.1f} KB"
        lines.append(f"  Total output size: {size_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mage tool registration
# ---------------------------------------------------------------------------

try:
    from utils.functions_metadata import function_schema  # noqa: PLC0415

    import_claude_code_sessions = function_schema(
        name="import_claude_code_sessions",
        description=(
            "Import Claude Code CLI session transcripts from ~/.claude/projects/ "
            "(or an rsync backup) into Mage Lab's chat storage. Each session is "
            "converted to a Mage-compatible JSON file in the chats folder with a "
            "system message recording its origin, project, git branch, and dates. "
            "Output format matches import_claude_history so GUI and CLI chats "
            "coexist in a single archive."
        ),
        required_params=[],
        optional_params=[
            "input_dir",
            "output_dir",
            "include_thinking",
            "overwrite",
            "include_agents",
            "truncate_tool_args",
        ],
    )(import_claude_code_sessions)
except ImportError:
    pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Import Claude Code CLI session transcripts into Mage Lab format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        default=None,
        help="Path to projects/ directory to scan (default: ~/.claude/projects).",
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
    parser.add_argument(
        "--include-agents",
        action="store_true",
        default=False,
        help="Also import sub-agent session files (agent-*.jsonl).",
    )
    parser.add_argument(
        "--truncate-tool-args",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Trim tool call arguments and results to N characters, appending"
            " ' … [truncated]'. Default: off (full fidelity). Useful when"
            " storing sessions with very large file writes or command output."
        ),
    )

    args = parser.parse_args()
    result = import_claude_code_sessions(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        include_thinking=args.thinking,
        overwrite=args.overwrite,
        include_agents=args.include_agents,
        truncate_tool_args=args.truncate_tool_args,
    )
    print(result)


if __name__ == "__main__":
    _cli()
