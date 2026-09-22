from __future__ import annotations

import json

from prompta.chromium import (
    _REACT_TOOL_SCRIPT,
    merge_tool_blocks,
    ordered_assistant_content_from_messages,
    tool_blocks_from_messages,
)

FENCE = chr(96) * 3
NL = chr(10)


def test_tool_blocks_from_completed_mcp_wrapper() -> None:
    messages = [
        {
            "role": "tool",
            "recipient": "all",
            "create_time": 1_700_000_000.25,
            "text": json.dumps(
                {
                    "appContext": {
                        "actionName": "execute_python",
                        "appName": "Nox Python MCP",
                    },
                    "arguments": {"code": "print(1)"},
                    "durationMs": 2666,
                    "error": None,
                    "result": {"content": [{"text": "1"}]},
                    "status": "completed",
                    "tool": "nox_python_mcp.execute_python",
                    "type": "mcpToolCall",
                }
            ),
            "invoked_resource": {
                "app_name": "Nox Python MCP",
                "resource_uri": "/app/link/execute_python",
            },
        }
    ]

    blocks = tool_blocks_from_messages(messages)

    assert len(blocks) == 1
    assert blocks[0].startswith(FENCE + "tool:Nox Python MCP · execute_python" + NL)
    assert '"code": "print(1)"' in blocks[0]
    assert '"status": "completed"' in blocks[0]
    assert '"duration_ms": 2666' in blocks[0]
    assert '"created_at": 1700000000.25' in blocks[0]
    assert '"result"' in blocks[0]


def test_tool_blocks_pair_invocation_with_nox_tool_result() -> None:
    messages = [
        {
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "create_time": 1_700_000_100.5,
            "text": json.dumps(
                {
                    "path": "/Nox Python MCP/link_123/execute_python",
                    "args": {"code": "print(1)"},
                }
            ),
            "connector_tool_payload": json.dumps({"code": "print(1)"}),
            "reasoning_title": "Checking the Python MCP call",
        },
        {
            "role": "tool",
            "recipient": "assistant",
            "create_time": 1_700_000_105.5,
            "text": json.dumps(
                {
                    "text": json.dumps(
                        {
                            "ok": True,
                            "returncode": 0,
                            "stdout": "PROMPTA_TOOL_RENDER_OK" + NL,
                        }
                    )
                }
            ),
            "invoked_resource": {
                "app_name": "Nox Python MCP",
                "resource_uri": "/asdk_app_123/link_123/execute_python",
            },
        },
    ]

    blocks = tool_blocks_from_messages(messages)

    assert len(blocks) == 1
    assert blocks[0].startswith(FENCE + "tool:Nox Python MCP · execute_python" + NL)
    assert '"status": "completed"' in blocks[0]
    assert '"summary": "Checking the Python MCP call"' in blocks[0]
    assert '"created_at": 1700000100.5' in blocks[0]
    assert '"created_at": 1700000105.5' not in blocks[0]
    assert '"arguments"' in blocks[0]
    assert "PROMPTA_TOOL_RENDER_OK" in blocks[0]
    assert '"returncode": 0' in blocks[0]


def test_merge_tool_blocks_replaces_generic_running_placeholder() -> None:
    content = (
        "Answer"
        + NL * 2
        + FENCE
        + "tool:tool"
        + NL
        + json.dumps({"status": "running"}, indent=2)
        + NL
        + FENCE
    )
    rich = (
        FENCE
        + "tool:Nox Python MCP · execute_python"
        + NL
        + json.dumps({"status": "completed"}, indent=2)
        + NL
        + FENCE
    )

    merged = merge_tool_blocks(content, [rich])

    assert merged.startswith("Answer" + NL * 2 + FENCE + "tool:Nox Python MCP · execute_python")
    assert '"status": "running"' not in merged


def test_merge_tool_blocks_preserves_existing_interleaving() -> None:
    first = (
        FENCE
        + "tool:tool"
        + NL
        + json.dumps({"status": "running", "slot": 1}, indent=2)
        + NL
        + FENCE
    )
    second = (
        FENCE
        + "tool:tool"
        + NL
        + json.dumps({"status": "running", "slot": 2}, indent=2)
        + NL
        + FENCE
    )
    rich_first = (
        FENCE
        + "tool:Nox Python MCP · execute_python"
        + NL
        + json.dumps({"arguments": {"code": "print(1)"}, "status": "completed"}, indent=2)
        + NL
        + FENCE
    )
    rich_second = (
        FENCE
        + "tool:Chrome DevTools · take_snapshot"
        + NL
        + json.dumps({"arguments": {"pageId": 4}, "status": "completed"}, indent=2)
        + NL
        + FENCE
    )
    content = "Before" + NL * 2 + first + NL * 2 + "Between" + NL * 2 + second + NL * 2 + "After"

    merged = merge_tool_blocks(content, [rich_first, rich_second])

    assert merged.index("Before") < merged.index("Nox Python MCP")
    assert merged.index("Nox Python MCP") < merged.index("Between")
    assert merged.index("Between") < merged.index("Chrome DevTools")
    assert merged.index("Chrome DevTools") < merged.index("After")
    assert '"status": "running"' not in merged


def test_merge_tool_blocks_does_not_end_on_embedded_backticks() -> None:
    body = json.dumps(
        {
            "arguments": {"code": "m = re.search(r'```tool:x', text)"},
            "status": "running",
        },
        indent=2,
    )
    placeholder = FENCE + "tool:Nox Python MCP · execute_python" + NL + body + NL + FENCE
    rich = (
        FENCE
        + "tool:Nox Python MCP · execute_python"
        + NL
        + json.dumps({"arguments": {"code": "print('ok')"}, "status": "completed"}, indent=2)
        + NL
        + FENCE
    )

    merged = merge_tool_blocks("Before" + NL * 2 + placeholder + NL * 2 + "After", [rich])

    assert "print('ok')" in merged
    assert merged.endswith("After")


def test_react_tool_script_scopes_to_latest_assistant_turn() -> None:
    assert "const latestAssistant=assistants.at(-1)" in _REACT_TOOL_SCRIPT
    assert "create_time:Number.isFinite(Number(message?.create_time))" in _REACT_TOOL_SCRIPT
    assert "reasoning_title:trimString(metadata?.reasoning_title" in _REACT_TOOL_SCRIPT
    assert (
        "end_turn:typeof message?.end_turn==='boolean'?message.end_turn:null" in _REACT_TOOL_SCRIPT
    )
    assert "messages.sort((left,right)=>" in _REACT_TOOL_SCRIPT
    assert "latestAssistant?.closest('[data-testid^=\"conversation-turn-\"]')" in _REACT_TOOL_SCRIPT
    assert "latestAssistant?.closest('.agent-turn')" in _REACT_TOOL_SCRIPT


def test_ordered_assistant_content_tolerates_missing_and_invalid_timestamps() -> None:
    messages = [
        {
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Timed"],
            "create_time": 1.0,
        },
        {
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Missing"],
        },
        {
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Invalid"],
            "create_time": None,
        },
    ]

    content = ordered_assistant_content_from_messages(messages)

    assert content.index("Timed") < content.index("Missing")
    assert content.index("Missing") < content.index("Invalid")


def test_ordered_assistant_content_uses_message_timestamps() -> None:
    messages = [
        {
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "create_time": 2.0,
            "text": json.dumps(
                {
                    "path": "/Nox Python MCP/link_123/execute_python",
                    "args": {"code": "print(1)"},
                }
            ),
            "connector_tool_payload": json.dumps({"code": "print(1)"}),
        },
        {
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "create_time": 1.0,
            "parts": ["Before tool"],
            "text": "",
        },
        {
            "role": "tool",
            "recipient": "assistant",
            "content_type": "code",
            "create_time": 2.5,
            "text": json.dumps({"text": json.dumps({"ok": True})}),
            "invoked_resource": {
                "app_name": "Nox Python MCP",
                "resource_uri": "/asdk_app_123/link_123/execute_python",
            },
        },
        {
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "create_time": 3.0,
            "parts": ["After tool"],
            "text": "",
        },
    ]

    content = ordered_assistant_content_from_messages(messages)

    assert content.index("Before tool") < content.index("Nox Python MCP · execute_python")
    assert content.index("Nox Python MCP · execute_python") < content.index("After tool")
    assert '"code": "print(1)"' in content


def test_ordered_assistant_content_keeps_completed_summary_after_tool_calls() -> None:
    messages = [
        {
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "create_time": 1.0,
            "parts": ["Working on it"],
            "text": "",
            "end_turn": False,
        },
        {
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "create_time": 2.0,
            "parts": ["Completed summary"],
            "text": "",
            "end_turn": True,
        },
        {
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "create_time": 3.0,
            "text": json.dumps(
                {
                    "path": "/Nox Python MCP/link_123/execute_python",
                    "args": {"code": "print(1)"},
                }
            ),
            "connector_tool_payload": json.dumps({"code": "print(1)"}),
        },
        {
            "role": "tool",
            "recipient": "assistant",
            "content_type": "code",
            "create_time": 4.0,
            "text": json.dumps({"text": json.dumps({"ok": True})}),
            "invoked_resource": {
                "app_name": "Nox Python MCP",
                "resource_uri": "/asdk_app_123/link_123/execute_python",
            },
        },
    ]

    content = ordered_assistant_content_from_messages(messages)

    assert content.index("Working on it") < content.index("Nox Python MCP · execute_python")
    assert content.index("Nox Python MCP · execute_python") < content.index("Completed summary")
