from __future__ import annotations

import json

from prompta.chromium import merge_tool_blocks, tool_blocks_from_messages

FENCE = chr(96) * 3
NL = chr(10)


def test_tool_blocks_from_completed_mcp_wrapper() -> None:
    messages = [
        {
            "role": "tool",
            "recipient": "all",
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
    assert '"result"' in blocks[0]


def test_tool_blocks_pair_invocation_with_nox_tool_result() -> None:
    messages = [
        {
            "role": "assistant",
            "recipient": "api_tool.call_tool",
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
        FENCE + "tool:tool" + NL
        + json.dumps({"status": "running", "slot": 1}, indent=2) + NL
        + FENCE
    )
    second = (
        FENCE + "tool:tool" + NL
        + json.dumps({"status": "running", "slot": 2}, indent=2) + NL
        + FENCE
    )
    rich_first = (
        FENCE + "tool:Nox Python MCP · execute_python" + NL
        + json.dumps({"arguments": {"code": "print(1)"}, "status": "completed"}, indent=2) + NL
        + FENCE
    )
    rich_second = (
        FENCE + "tool:Chrome DevTools · take_snapshot" + NL
        + json.dumps({"arguments": {"pageId": 4}, "status": "completed"}, indent=2) + NL
        + FENCE
    )
    content = (
        "Before" + NL * 2 + first + NL * 2
        + "Between" + NL * 2 + second + NL * 2 + "After"
    )

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
        FENCE + "tool:Nox Python MCP · execute_python" + NL
        + json.dumps({"arguments": {"code": "print('ok')"}, "status": "completed"}, indent=2) + NL
        + FENCE
    )

    merged = merge_tool_blocks("Before" + NL * 2 + placeholder + NL * 2 + "After", [rich])

    assert "print('ok')" in merged
    assert merged.endswith("After")
