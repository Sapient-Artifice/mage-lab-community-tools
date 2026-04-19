# Tool Call Rendering Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `import_claude_code_sessions.py` to emit native Mage message format for tool calls so the tool-debug toggle works on imported sessions.

**Architecture:** Replace `_extract_content` with two focused helpers — `_extract_assistant_messages` and `_extract_user_messages` — that produce `role: "assistant"` with `tool_calls`, and `role: "tool"` messages respectively. `_convert_session` maintains a `tool_use_id → name` lookup dict across events and wires the helpers together.

**Tech Stack:** Python 3.9+, pytest, no new dependencies.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `import_claude_code_sessions/tests/__init__.py` | Makes tests a package |
| Create | `import_claude_code_sessions/tests/test_message_extraction.py` | Unit tests for the two new helpers |
| Modify | `import_claude_code_sessions/import_claude_code_sessions.py` | All code changes |

---

### Task 1: Create test scaffold

**Files:**
- Create: `import_claude_code_sessions/tests/__init__.py`
- Create: `import_claude_code_sessions/tests/test_message_extraction.py`

- [ ] **Step 1: Create the empty init file**

```bash
mkdir -p /home/bard/Desktop/mage-lab-community-tools/import_claude_code_sessions/tests
touch /home/bard/Desktop/mage-lab-community-tools/import_claude_code_sessions/tests/__init__.py
```

- [ ] **Step 2: Create the test file with imports and fixtures**

File: `import_claude_code_sessions/tests/test_message_extraction.py`

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from import_claude_code_sessions import _extract_assistant_messages, _extract_user_messages
```

- [ ] **Step 3: Verify the import works (functions don't exist yet — expect ImportError)**

```bash
cd /home/bard/Desktop/mage-lab-community-tools
python -c "
import sys; sys.path.insert(0, 'import_claude_code_sessions')
from import_claude_code_sessions import _extract_content
print('old function exists — ready to replace')
"
```

Expected: prints `old function exists — ready to replace`

- [ ] **Step 4: Commit scaffold**

```bash
git -C /home/bard/Desktop/mage-lab-community-tools add import_claude_code_sessions/tests/
git -C /home/bard/Desktop/mage-lab-community-tools commit -m "test: add test scaffold for message extraction helpers"
```

---

### Task 2: Write tests for `_extract_assistant_messages`

**Files:**
- Modify: `import_claude_code_sessions/tests/test_message_extraction.py`

- [ ] **Step 1: Write all tests for `_extract_assistant_messages`**

Replace the contents of `import_claude_code_sessions/tests/test_message_extraction.py` with:

```python
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from import_claude_code_sessions import _extract_assistant_messages, _extract_user_messages


# ---------------------------------------------------------------------------
# _extract_assistant_messages
# ---------------------------------------------------------------------------

def test_assistant_plain_string():
    msgs = _extract_assistant_messages("hello", False, {}, None)
    assert msgs == [{"role": "assistant", "content": "hello"}]


def test_assistant_plain_string_empty():
    assert _extract_assistant_messages("  ", False, {}, None) == []


def test_assistant_text_block_only():
    content = [{"type": "text", "text": "hello world"}]
    msgs = _extract_assistant_messages(content, False, {}, None)
    assert msgs == [{"role": "assistant", "content": "hello world"}]


def test_assistant_tool_use_only():
    content = [
        {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {"file_path": "/a/b"}}
    ]
    msgs = _extract_assistant_messages(content, False, {}, None)
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "assistant"
    assert msg["content"] == ""
    assert msg["tool_calls"] == [
        {"function": {"name": "Read", "arguments": '{"file_path": "/a/b"}'}}
    ]


def test_assistant_text_and_tool_use():
    content = [
        {"type": "text", "text": "Let me look."},
        {"type": "tool_use", "id": "tu_2", "name": "Bash", "input": {"command": "ls"}},
    ]
    msgs = _extract_assistant_messages(content, False, {}, None)
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "assistant"
    assert msg["content"] == "Let me look."
    assert msg["tool_calls"] == [
        {"function": {"name": "Bash", "arguments": '{"command": "ls"}'}}
    ]


def test_assistant_multiple_tool_uses():
    content = [
        {"type": "tool_use", "id": "tu_3", "name": "Read", "input": {"file_path": "/a"}},
        {"type": "tool_use", "id": "tu_4", "name": "Bash", "input": {"command": "pwd"}},
    ]
    msgs = _extract_assistant_messages(content, False, {}, None)
    assert len(msgs[0]["tool_calls"]) == 2
    assert msgs[0]["tool_calls"][0]["function"]["name"] == "Read"
    assert msgs[0]["tool_calls"][1]["function"]["name"] == "Bash"


def test_assistant_thinking_excluded_by_default():
    content = [
        {"type": "thinking", "thinking": "I should check the file."},
        {"type": "text", "text": "Let me check."},
    ]
    msgs = _extract_assistant_messages(content, False, {}, None)
    assert msgs[0]["content"] == "Let me check."


def test_assistant_thinking_included():
    content = [
        {"type": "thinking", "thinking": "I should check."},
        {"type": "text", "text": "Let me check."},
    ]
    msgs = _extract_assistant_messages(content, True, {}, None)
    assert "[Thinking: I should check.]" in msgs[0]["content"]
    assert "Let me check." in msgs[0]["content"]


def test_assistant_tool_id_tracked():
    lookup = {}
    content = [
        {"type": "tool_use", "id": "tu_5", "name": "Write", "input": {}}
    ]
    _extract_assistant_messages(content, False, lookup, None)
    assert lookup["tu_5"] == "Write"


def test_assistant_truncate_arguments():
    content = [
        {"type": "tool_use", "id": "tu_6", "name": "Write", "input": {"content": "x" * 200}}
    ]
    msgs = _extract_assistant_messages(content, False, {}, 50)
    args_str = msgs[0]["tool_calls"][0]["function"]["arguments"]
    assert args_str.endswith(" … [truncated]")
    # Total length: 50 chars of original + suffix
    assert len(args_str) < 200


def test_assistant_no_truncate_when_short():
    content = [
        {"type": "tool_use", "id": "tu_7", "name": "Read", "input": {"file_path": "/a"}}
    ]
    msgs = _extract_assistant_messages(content, False, {}, 500)
    args_str = msgs[0]["tool_calls"][0]["function"]["arguments"]
    assert "[truncated]" not in args_str


def test_assistant_empty_list():
    assert _extract_assistant_messages([], False, {}, None) == []


def test_assistant_no_tool_calls_key_when_text_only():
    content = [{"type": "text", "text": "hello"}]
    msgs = _extract_assistant_messages(content, False, {}, None)
    assert "tool_calls" not in msgs[0]


# ---------------------------------------------------------------------------
# _extract_user_messages
# ---------------------------------------------------------------------------

def test_user_plain_string():
    msgs = _extract_user_messages("hello", {}, None)
    assert msgs == [{"role": "user", "content": "hello"}]


def test_user_plain_string_empty():
    assert _extract_user_messages("  ", {}, None) == []


def test_user_text_block_only():
    content = [{"type": "text", "text": "hi there"}]
    msgs = _extract_user_messages(content, {}, None)
    assert msgs == [{"role": "user", "content": "hi there"}]


def test_user_tool_result_only_string_content():
    lookup = {"tu_1": "Read"}
    content = [
        {"type": "tool_result", "tool_use_id": "tu_1", "content": "file text here"}
    ]
    msgs = _extract_user_messages(content, lookup, None)
    assert len(msgs) == 1
    assert msgs[0] == {"role": "tool", "name": "Read", "content": "file text here"}


def test_user_tool_result_name_from_lookup():
    lookup = {"tu_abc": "Bash"}
    content = [{"type": "tool_result", "tool_use_id": "tu_abc", "content": "ok"}]
    msgs = _extract_user_messages(content, lookup, None)
    assert msgs[0]["name"] == "Bash"


def test_user_tool_result_name_missing_from_lookup():
    content = [{"type": "tool_result", "tool_use_id": "tu_unknown", "content": "ok"}]
    msgs = _extract_user_messages(content, {}, None)
    assert msgs[0]["name"] == ""


def test_user_tool_result_error_flag():
    content = [
        {"type": "tool_result", "tool_use_id": "tu_2", "is_error": True, "content": "oops"}
    ]
    msgs = _extract_user_messages(content, {}, None)
    assert msgs[0]["content"] == "[error] oops"


def test_user_multiple_tool_results():
    lookup = {"tu_a": "Read", "tu_b": "Bash"}
    content = [
        {"type": "tool_result", "tool_use_id": "tu_a", "content": "result a"},
        {"type": "tool_result", "tool_use_id": "tu_b", "content": "result b"},
    ]
    msgs = _extract_user_messages(content, lookup, None)
    assert len(msgs) == 2
    assert msgs[0]["name"] == "Read"
    assert msgs[1]["name"] == "Bash"


def test_user_tool_result_and_text():
    lookup = {"tu_c": "Write"}
    content = [
        {"type": "tool_result", "tool_use_id": "tu_c", "content": "written"},
        {"type": "text", "text": "please continue"},
    ]
    msgs = _extract_user_messages(content, lookup, None)
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    user_msgs = [m for m in msgs if m["role"] == "user"]
    assert len(tool_msgs) == 1
    assert len(user_msgs) == 1
    assert user_msgs[0]["content"] == "please continue"


def test_user_tool_result_list_content():
    content = [
        {
            "type": "tool_result",
            "tool_use_id": "tu_d",
            "content": [
                {"type": "text", "text": "line 1"},
                {"type": "text", "text": "line 2"},
            ],
        }
    ]
    msgs = _extract_user_messages(content, {}, None)
    assert "line 1" in msgs[0]["content"]
    assert "line 2" in msgs[0]["content"]


def test_user_truncate_result():
    content = [
        {"type": "tool_result", "tool_use_id": "tu_e", "content": "x" * 300}
    ]
    msgs = _extract_user_messages(content, {}, 100)
    assert msgs[0]["content"].endswith(" … [truncated]")
    assert len(msgs[0]["content"]) < 300


def test_user_no_truncate_when_short():
    content = [{"type": "tool_result", "tool_use_id": "tu_f", "content": "short"}]
    msgs = _extract_user_messages(content, {}, 500)
    assert "[truncated]" not in msgs[0]["content"]


def test_user_tool_result_only_emits_no_user_message():
    content = [{"type": "tool_result", "tool_use_id": "tu_g", "content": "ok"}]
    msgs = _extract_user_messages(content, {}, None)
    assert all(m["role"] == "tool" for m in msgs)


def test_user_empty_list():
    assert _extract_user_messages([], {}, None) == []
```

- [ ] **Step 2: Run tests — expect ImportError since functions don't exist yet**

```bash
cd /home/bard/Desktop/mage-lab-community-tools
python -m pytest import_claude_code_sessions/tests/test_message_extraction.py -v 2>&1 | head -20
```

Expected: collection error — `ImportError: cannot import name '_extract_assistant_messages'`

- [ ] **Step 3: Commit tests**

```bash
git -C /home/bard/Desktop/mage-lab-community-tools add import_claude_code_sessions/tests/test_message_extraction.py
git -C /home/bard/Desktop/mage-lab-community-tools commit -m "test: write failing tests for _extract_assistant_messages and _extract_user_messages"
```

---

### Task 3: Implement `_extract_assistant_messages`

**Files:**
- Modify: `import_claude_code_sessions/import_claude_code_sessions.py`

- [ ] **Step 1: Add `_extract_assistant_messages` after the `_extract_content` function (around line 144)**

Insert this block immediately after the closing of `_extract_content` (before the `# ---` metadata section separator):

```python
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
```

- [ ] **Step 2: Run only the `_extract_assistant_messages` tests**

```bash
cd /home/bard/Desktop/mage-lab-community-tools
python -m pytest import_claude_code_sessions/tests/test_message_extraction.py -v -k "assistant"
```

Expected: all `test_assistant_*` tests PASS; `test_user_*` tests still fail with ImportError.

- [ ] **Step 3: Commit**

```bash
git -C /home/bard/Desktop/mage-lab-community-tools add import_claude_code_sessions/import_claude_code_sessions.py
git -C /home/bard/Desktop/mage-lab-community-tools commit -m "feat: add _extract_assistant_messages with native Mage tool_calls format"
```

---

### Task 4: Implement `_extract_user_messages`

**Files:**
- Modify: `import_claude_code_sessions/import_claude_code_sessions.py`

- [ ] **Step 1: Add `_extract_user_messages` immediately after `_extract_assistant_messages`**

```python
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
```

- [ ] **Step 2: Run the full test suite**

```bash
cd /home/bard/Desktop/mage-lab-community-tools
python -m pytest import_claude_code_sessions/tests/test_message_extraction.py -v
```

Expected: all 28 tests PASS.

- [ ] **Step 3: Commit**

```bash
git -C /home/bard/Desktop/mage-lab-community-tools add import_claude_code_sessions/import_claude_code_sessions.py
git -C /home/bard/Desktop/mage-lab-community-tools commit -m "feat: add _extract_user_messages emitting role:tool for results"
```

---

### Task 5: Refactor `_convert_session` and add `truncate_tool_args` parameter

**Files:**
- Modify: `import_claude_code_sessions/import_claude_code_sessions.py`

- [ ] **Step 1: Update the `_convert_session` signature and body**

Find the current `_convert_session` function (around line 314). Replace the entire function with:

```python
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
```

- [ ] **Step 2: Run the full test suite to confirm nothing broke**

```bash
cd /home/bard/Desktop/mage-lab-community-tools
python -m pytest import_claude_code_sessions/tests/test_message_extraction.py -v
```

Expected: 28 tests PASS.

- [ ] **Step 3: Commit**

```bash
git -C /home/bard/Desktop/mage-lab-community-tools add import_claude_code_sessions/import_claude_code_sessions.py
git -C /home/bard/Desktop/mage-lab-community-tools commit -m "refactor: replace _extract_content with new helpers in _convert_session"
```

---

### Task 6: Wire `truncate_tool_args` through to the public API and CLI

**Files:**
- Modify: `import_claude_code_sessions/import_claude_code_sessions.py`

- [ ] **Step 1: Update `import_claude_code_sessions` function signature and body**

Find the `import_claude_code_sessions` function (around line 480). Add the `truncate_tool_args` parameter to its signature and docstring, and pass it to `_convert_session`.

Change the signature from:
```python
def import_claude_code_sessions(
    input_dir: str = None,
    output_dir: str = None,
    include_thinking: bool = False,
    overwrite: bool = False,
    include_agents: bool = False,
) -> str:
```

To:
```python
def import_claude_code_sessions(
    input_dir: str = None,
    output_dir: str = None,
    include_thinking: bool = False,
    overwrite: bool = False,
    include_agents: bool = False,
    truncate_tool_args: Optional[int] = None,
) -> str:
```

In the docstring, after the `include_agents` param entry, add:
```
    :param truncate_tool_args: When set to an integer N, tool call arguments
        and tool results longer than N characters are trimmed with a
        " … [truncated]" suffix. Default None preserves full fidelity.
```

In the `_convert_session` call (around line 577), change:
```python
            messages = _convert_session(
                session_file,
                project_dir_name,
                index_meta,
                include_thinking=include_thinking,
            )
```

To:
```python
            messages = _convert_session(
                session_file,
                project_dir_name,
                index_meta,
                include_thinking=include_thinking,
                truncate_tool_args=truncate_tool_args,
            )
```

- [ ] **Step 2: Update the `function_schema` registration block**

Find the `function_schema(...)` call near the bottom of the file. Change:
```python
        optional_params=[
            "input_dir",
            "output_dir",
            "include_thinking",
            "overwrite",
            "include_agents",
        ],
```

To:
```python
        optional_params=[
            "input_dir",
            "output_dir",
            "include_thinking",
            "overwrite",
            "include_agents",
            "truncate_tool_args",
        ],
```

- [ ] **Step 3: Add the `--truncate-tool-args` CLI argument**

In `_cli`, find the `--include-agents` argument block. After it, add:

```python
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
```

In the `import_claude_code_sessions(...)` call at the bottom of `_cli`, add:
```python
        truncate_tool_args=args.truncate_tool_args,
```

- [ ] **Step 4: Update the module docstring**

Find the CLI usage block at the top of the file (around line 9). Add `[--truncate-tool-args N]` to the usage line:

```
    python import_claude_code_sessions.py [input_dir] [output_dir] [--thinking] [--overwrite] [--include-agents] [--truncate-tool-args N]
```

Below the `--include-agents` description in the docstring, add:

```
    --truncate-tool-args N  Trim tool arguments and results to N chars. Off by
                            default (full fidelity). Enable to reduce file size
                            when sessions contain large file writes or output.
```

- [ ] **Step 5: Run the test suite to confirm nothing broke**

```bash
cd /home/bard/Desktop/mage-lab-community-tools
python -m pytest import_claude_code_sessions/tests/test_message_extraction.py -v
```

Expected: 28 tests PASS.

- [ ] **Step 6: Commit**

```bash
git -C /home/bard/Desktop/mage-lab-community-tools add import_claude_code_sessions/import_claude_code_sessions.py
git -C /home/bard/Desktop/mage-lab-community-tools commit -m "feat: add truncate_tool_args option to public API and CLI"
```

---

### Task 7: Remove `_extract_content` and update `_build_system_message` footer

**Files:**
- Modify: `import_claude_code_sessions/import_claude_code_sessions.py`

- [ ] **Step 1: Delete the `_extract_content` function**

Remove the entire `_extract_content` function (lines ~76–144 in the original file). It starts with `def _extract_content(` and ends before the `# ---` metadata section separator.

- [ ] **Step 2: Update the system message footer in `_build_system_message`**

Find this line near the end of `_build_system_message` (around line 308 in the original):
```python
        "This is a read-only historical record. Tool calls and their results are"
        " represented as inline annotations wrapped in [square brackets].",
```

Replace with:
```python
        "This is a read-only historical record. Tool calls and results are"
        " stored in native Mage format and shown in the tool-debug panel.",
```

- [ ] **Step 3: Verify the script still imports cleanly**

```bash
cd /home/bard/Desktop/mage-lab-community-tools
python -c "
import sys; sys.path.insert(0, 'import_claude_code_sessions')
import import_claude_code_sessions
print('import OK')
print('_extract_content present:', hasattr(import_claude_code_sessions, '_extract_content'))
print('_extract_assistant_messages present:', hasattr(import_claude_code_sessions, '_extract_assistant_messages'))
"
```

Expected:
```
import OK
_extract_content present: False
_extract_assistant_messages present: True
```

- [ ] **Step 4: Run the full test suite**

```bash
cd /home/bard/Desktop/mage-lab-community-tools
python -m pytest import_claude_code_sessions/tests/test_message_extraction.py -v
```

Expected: 28 tests PASS.

- [ ] **Step 5: Smoke-test the CLI help**

```bash
cd /home/bard/Desktop/mage-lab-community-tools/import_claude_code_sessions
python import_claude_code_sessions.py --help
```

Expected: help text includes `--truncate-tool-args N` and no reference to `[square brackets]`.

- [ ] **Step 6: Commit**

```bash
git -C /home/bard/Desktop/mage-lab-community-tools add import_claude_code_sessions/import_claude_code_sessions.py
git -C /home/bard/Desktop/mage-lab-community-tools commit -m "refactor: remove _extract_content, update system message footer"
```

---

### Task 8: End-to-end smoke test against a real session

**Files:** none modified — verification only.

- [ ] **Step 1: Run the importer against the live Claude projects directory**

```bash
cd /home/bard/Desktop/mage-lab-community-tools/import_claude_code_sessions
python import_claude_code_sessions.py --overwrite /tmp/cc-smoke-test
```

Expected: summary showing sessions imported into `/tmp/cc-smoke-test/`.

- [ ] **Step 2: Inspect one output file for native Mage structure**

```bash
python3 -c "
import json, glob, sys
files = sorted(glob.glob('/tmp/cc-smoke-test/*.json'))
if not files:
    print('no files'); sys.exit(1)
with open(files[0]) as f:
    msgs = json.load(f)
roles = [m.get('role') for m in msgs]
has_tool = any(m.get('role') == 'tool' for m in msgs)
has_tool_calls = any(m.get('tool_calls') for m in msgs)
has_bracket_inline = any('[Tool call:' in str(m.get('content','')) for m in msgs)
print('roles seen:', set(roles))
print('has role:tool messages:', has_tool)
print('has tool_calls on assistant:', has_tool_calls)
print('has old [Tool call: inline text (should be False):', has_bracket_inline)
"
```

Expected:
```
roles seen: {'system', 'user', 'assistant', 'tool'}
has role:tool messages: True
has tool_calls on assistant: True
has old [Tool call: inline text (should be False): False
```

- [ ] **Step 3: Final commit if any fixups were needed; otherwise just note it's clean**

```bash
git -C /home/bard/Desktop/mage-lab-community-tools status
```

Expected: clean working tree.
