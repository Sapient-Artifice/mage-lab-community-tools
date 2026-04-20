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
    parsed = json.loads(args_str)  # must parse as valid JSON
    assert parsed.get("_truncated") is True
    assert "preview" in parsed


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
