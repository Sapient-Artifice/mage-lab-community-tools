# Tool Call Rendering Fix for import_claude_code_sessions

**Date:** 2026-04-19  
**File:** `import_claude_code_sessions/import_claude_code_sessions.py`

## Problem

Tool calls and results are currently inlined as plain text annotations
(`[Tool call: Read({...})]`, `[Tool result (...): ...]`) inside message
`content` strings. Mage's renderer has no way to distinguish these from
regular text, so the tool-debug toggle has no effect on imported sessions.

## Goal

Imported sessions should use the same stored format as native Mage sessions,
so the tool-debug toggle works identically — users can view the clean
conversation flow or dive into execution details.

## Message Format (native Mage)

### Assistant turns

```json
{
  "role": "assistant",
  "content": "Let me read the file.",
  "tool_calls": [
    { "function": { "name": "Read", "arguments": "{\"file_path\": \"/path\"}" } }
  ]
}
```

- `tool_calls` omitted when no tool_use blocks.
- `content` is `""` when the turn has tool_use blocks but no text.
- Multiple tool_use blocks → multiple entries in `tool_calls`.
- `arguments` is a JSON string (matches OpenAI / Mage convention).

### Tool result turns

```json
{ "role": "tool", "name": "Read", "content": "file contents here" }
```

- One `role: "tool"` message per tool_result block.
- `name` resolved via a `tool_use_id → tool_name` lookup dict built from
  preceding assistant events. Falls back to `""` if not found.
- Error results prefixed with `[error] `.

### User text turns

```json
{ "role": "user", "content": "user text here" }
```

- Only emitted when the user event contains actual text blocks.
- If a user event contains only tool_result blocks (no text), no
  `role: "user"` message is emitted.

## How decorateHistoryMessages renders these

`frontend/src/lib/chat/history.ts → decorateHistoryMessages`:

- `role: "assistant"` with `tool_calls` → emits a `tool_debug / function_call`
  bubble per call (togglable), then a `tool_debug / mage_message` bubble, then
  the visible assistant message.
- `role: "tool"` → emits a `tool_debug / tool_message` bubble only (hidden
  when tool debug is off). No visible message.
- `role: "user"` → emits visible user message + `tool_debug / user_message`
  bubble.

No frontend changes needed.

## Truncation Option

New parameter: `truncate_tool_args: Optional[int] = None` (default off).

When set to an integer N:
- `arguments` JSON strings longer than N chars are trimmed to N chars +
  ` … [truncated]`.
- Tool result `content` strings longer than N chars are trimmed similarly.

Exposed as:
- Python function param: `truncate_tool_args: Optional[int] = None`
- CLI flag: `--truncate-tool-args N`

Documented in:
- Module docstring
- CLI `--help` epilog
- `function_schema` optional params list

## Code Changes

### Removed
- `_extract_content(content, include_thinking)` — replaced entirely.

### Added
- `_extract_assistant_messages(content_raw, include_thinking, tool_id_to_name, truncate)` → `List[Dict]`  
  Returns zero or one Mage message dicts for one assistant event's content.

- `_extract_user_messages(content_raw, tool_id_to_name, truncate)` → `List[Dict]`  
  Returns zero or more Mage message dicts (tool messages + optional user text)
  for one user event's content.

### Modified
- `_convert_session` — maintains `tool_id_to_name: Dict[str, str]` across
  events; calls the two new helpers; passes `truncate_tool_args` through.
- `_build_system_message` — footer note updated: removes reference to
  `[square brackets]` annotation format.
- `import_claude_code_sessions` — accepts and passes `truncate_tool_args`.
- `_cli` — adds `--truncate-tool-args` argument.
- `function_schema` registration — adds `truncate_tool_args` to optional params.

## Non-changes

- File discovery, filename generation, metadata extraction, index lookup:
  unchanged.
- `--thinking` flag behavior: thinking blocks still included in assistant
  `content` when enabled.
- Output filename format: unchanged.
- The `_extract_content` function is removed, not deprecated.
