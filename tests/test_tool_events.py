"""End-to-end tool events: owned POST -> capture -> private SQLite -> local turns."""

import json
from collections.abc import Mapping
from pathlib import Path

from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.response_capture import CaptureResult, parse_sse_body
from prompta.response_store import ResponseStore


def event(message: Mapping[str, object]) -> str:
    return "data: " + json.dumps({"conversation_id": "chat-1", "message": message}) + "\n\n"


def test_tool_calls_are_ordered_paired_redacted_and_persisted(tmp_path: Path) -> None:
    call = {
        "id": "invoke-1", "author": {"role": "assistant"},
        "recipient": "api_tool.call_tool",
        "content": {"content_type": "text", "parts": [json.dumps({
            "path": "/search/find", "args": {"query": "kiwi", "api_key": "private-value"},
        })]},
    }
    answer = {
        "id": "answer-1", "author": {"role": "assistant"},
        "recipient": "all", "channel": "final", "end_turn": True,
        "content": {"content_type": "text", "parts": ["The kiwi result is ready."]},
    }
    tool_result = {
        "id": "tool-result", "author": {"role": "tool"},
        "invoked_resource": {"resource_uri": "/search/find"},
        "content": {"content_type": "text", "parts": [json.dumps({"items": ["one", "two"]})]},
    }
    body = event(call) + event(call) + event(tool_result) + event(answer) + "data: [DONE]\n\n"
    capture = parse_sse_body(body)
    assert capture.status == "complete"
    assert capture.text == "The kiwi result is ready."
    assert len(capture.tool_calls) == 1
    item = capture.tool_calls[0]
    assert item["action"] == "find"
    assert item["status"] == "completed"
    assert item["connector"] == "search"
    assert '"query": "kiwi"' in str(item["arguments"])
    assert "private-value" not in str(item)
    assert "[redacted]" in str(item["arguments"])
    assert '"one"' in str(item["result"])

    path = tmp_path / "chat-results.sqlite3"
    store = ResponseStore(path)
    store.ensure_queued("send-1", "Find a kiwi", now=100)
    assert store.accept("send-1", "99999:owner", deadline=300, now=110)
    assert store.write("send-1", "99999:owner", capture, now=120)
    detail = store.detail("send-1")
    assert detail is not None
    assert detail["tool_calls"] == [item]
    turns = ManualReplyStore(path).turns("send-1")
    assert turns is not None
    assert turns[0]["tool_calls"] == [item]
    assert turns[0]["assistant_text"] == "The kiwi result is ready."
    assert path.stat().st_mode & 0o777 == 0o600


def test_mcp_combined_event_and_hidden_analysis_are_separate() -> None:
    hidden = {
        "id": "thought", "author": {"role": "assistant"}, "recipient": "all",
        "channel": "analysis", "content": {"content_type": "text", "parts": ["private thought"]},
    }
    combined = {
        "id": "combined", "author": {"role": "assistant"},
        "recipient": "api_tool.call_tool",
        "content": {"content_type": "text", "parts": [json.dumps({
            "type": "mcpToolCall", "tool": "gmail.search",
            "appContext": {"appName": "Gmail", "actionName": "search"},
            "arguments": {"query": "from:alice"}, "status": "completed",
            "result": {"count": 2},
        })]},
    }
    final = {
        "id": "answer", "author": {"role": "assistant"}, "recipient": "all",
        "content": {"content_type": "text", "parts": ["Found two"]},
    }
    # Some newer streams expose combined tool events as assistant/all messages.
    combined["recipient"] = "all"
    capture = parse_sse_body(event(hidden) + event(combined) + event(final) + "data: [DONE]\n\n")
    assert capture.text == "Found two"
    assert len(capture.tool_calls) == 1
    assert capture.tool_calls[0]["connector"] == "Gmail"
    assert capture.tool_calls[0]["status"] == "completed"
    assert "private thought" not in str(capture)


def test_ambiguous_branches_never_expose_tool_data() -> None:
    body = event({
        "id": "call", "author": {"role": "assistant"}, "recipient": "api_tool.call_tool",
        "content": {"parts": [json.dumps({"path": "/foo/execute", "args": {"q": "secret"}})]},
    })
    body += event({
        "id": "final-1", "author": {"role": "assistant"}, "recipient": "all",
        "content": {"content_type": "text", "parts": ["first"]},
    })
    body += event({
        "id": "final-2", "author": {"role": "assistant"}, "recipient": "all",
        "content": {"content_type": "text", "parts": ["second"]},
    })
    capture = parse_sse_body(body)
    assert capture == CaptureResult("sse", "unknown", "", None, None, None)


def test_legacy_text_only_runs_return_empty_tool_array(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "legacy.sqlite3")
    store.ensure_queued("legacy", "Hello", now=1)
    detail = store.detail("legacy")
    assert detail is not None
    assert detail["tool_calls"] == []


def test_manual_reply_tool_calls_survive_local_turn_retrieval(tmp_path: Path) -> None:
    path = tmp_path / "replies.sqlite3"
    store = ResponseStore(path)
    store.ensure_queued("send", "Initial", now=10)
    assert store.accept("send", "100:owner", deadline=100, now=11)
    assert store.write("send", "100:owner", CaptureResult(
        "sse", "complete", "Initial answer", "chat", "first-answer", "parent",
    ), now=12)
    replies = ManualReplyStore(path)
    reply_id = "reply-1234567890-ab"
    assert replies.prepare("send", ReplyIntent(reply_id, "chat", "first-answer", "Follow up"), now=13)
    assert replies.claim(reply_id, "100:reply", deadline=100, now=14)
    assert replies.accepted(reply_id, "100:reply", conversation_id="chat",
                            parent_id="first-answer", message_id="reply-answer", now=15)
    calls: tuple[dict[str, object], ...] = ({
        "id": "tool-1", "connector": "GitHub", "action": "lookup", "status": "completed",
        "arguments": "{}", "result": "one", "error": "",
    },)
    assert replies.observe(reply_id, "100:reply", CaptureResult(
        "sse", "complete", "Follow-up answer", "chat", "reply-answer", "first-answer",
        tool_calls=calls,
    ), now=16)
    turns = replies.turns("send")
    assert turns is not None and len(turns) == 2
    assert turns[1]["tool_calls"] == list(calls)
    assert turns[1]["assistant_text"] == "Follow-up answer"
