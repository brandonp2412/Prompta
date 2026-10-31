"""Tool-call envelope and correlation regressions for owned response capture."""

from __future__ import annotations

import json
from collections.abc import Mapping

from prompta.response_capture import parse_sse_body
from prompta.tool_events import ToolEventCollector


def event(message: Mapping[str, object]) -> str:
    return "data: " + json.dumps({"conversation_id": "chat-1", "message": message}) + "\n\n"


def test_typed_text_tool_parts_are_captured_and_paired() -> None:
    call = {
        "id": "typed-call", "author": {"role": "assistant"},
        "recipient": "api_tool.call_tool",
        "content": {"content_type": "text", "parts": [{"type": "text", "text": json.dumps({
            "type": "mcpToolCall", "tool": "weather.lookup",
            "arguments": {"city": "Auckland"},
        })}]},
    }
    result = {
        "id": "typed-result", "author": {"role": "tool"},
        "metadata": {"tool_call_id": "typed-call"},
        "content": {"parts": [{"type": "text", "text": json.dumps({"temperature": 18})}]},
    }
    final = {
        "id": "typed-answer", "author": {"role": "assistant"},
        "recipient": "all", "channel": "final", "end_turn": True,
        "content": {"content_type": "text", "parts": ["18°C"]},
    }
    capture = parse_sse_body(event(call) + event(result) + event(final) + "data: [DONE]\n\n")
    assert capture.status == "complete"
    assert len(capture.tool_calls) == 1
    assert capture.tool_calls[0]["action"] == "lookup"
    assert capture.tool_calls[0]["status"] == "completed"
    assert '"temperature": 18' in str(capture.tool_calls[0]["result"])


def test_concurrent_tool_results_without_identity_are_not_misassigned() -> None:
    collector = ToolEventCollector()
    for identifier, tool in (("call-a", "weather.today"), ("call-b", "search.find")):
        assert collector.observe({
            "id": identifier, "author": {"role": "assistant"},
            "recipient": "api_tool.call_tool",
            "content": {"content_type": "text", "parts": [json.dumps({
                "type": "mcpToolCall", "tool": tool, "arguments": {},
            })]},
        })
    ambiguous: dict[str, object] = {
        "id": "result-unknown", "author": {"role": "tool"},
        "content": {"parts": ["Unidentified result"]},
    }
    assert collector.observe(ambiguous)
    assert all(call["status"] == "running" for call in collector.snapshot())
    assert collector.observe({
        **ambiguous, "id": "result-b", "metadata": {"tool_call_id": "call-b"},
    })
    calls = {call["id"]: call for call in collector.snapshot()}
    assert calls["call-a"]["status"] == "running"
    assert calls["call-b"]["status"] == "completed"
    assert calls["call-b"]["result"] == "Unidentified result"
