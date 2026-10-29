"""End-to-end tool events: owned POST -> capture -> private SQLite -> local turns."""

import json
from collections.abc import Mapping
from pathlib import Path

from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.response_capture import CaptureResult, normalize_dom_snapshot, parse_sse_body
from prompta.response_store import ResponseStore, merge_tool_calls
from prompta.strict_types import string_object_dict


def event(message: Mapping[str, object]) -> str:
    return "data: " + json.dumps({"conversation_id": "chat-1", "message": message}) + "\n\n"


def test_stream_tool_evidence_replaces_dom_summary_without_duplicates() -> None:
    dom: tuple[dict[str, object], ...] = (
        {"id": "dom-tool-0", "connector": "", "action": "Used search", "status": "observed"},
    )
    stream: tuple[dict[str, object], ...] = (
        {"id": "invoke-1", "connector": "Search", "action": "find", "status": "completed", "result": "Two hits"},
    )
    recovered = merge_tool_calls("[]", dom)
    upgraded = merge_tool_calls(recovered, stream)
    assert len(json.loads(upgraded)) == 1
    assert json.loads(upgraded)[0]["id"] == "invoke-1"
    assert merge_tool_calls(upgraded, dom) == upgraded


def test_dom_tool_summaries_are_bounded_redacted_and_survive_interrupted_recovery(tmp_path: Path) -> None:
    conversation = "12345678-1234-4123-8123-123456789abc"
    payload = {
        "message_id": "assistant-unit", "pathname": f"/c/{conversation}",
        "text": "", "complete": False,
        "tool_calls": [
            {"action": "Used Nox Python for https://private.example/path", "status": "completed", "result": "private"},
            {"action": "Thinking about private task", "status": "running"},
        ],
    }
    partial = normalize_dom_snapshot(payload)
    assert partial.status == "unknown"
    assert len(partial.tool_calls) == 1
    assert "private.example" not in str(partial.tool_calls)
    assert "private" not in str(partial.tool_calls)
    assert partial.tool_calls[0]["action"] == "Used Nox Python for [redacted]"
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    store.ensure_queued("manual-tools", "Original prompt", now=10)
    assert store.accept("manual-tools", "123:owner", deadline=100, now=11)
    assert store.bind_conversation_route("manual-tools", "123:owner", f"/c/{conversation}", now=12)
    assert store.finish("manual-tools", "123:owner", "interrupted", now=100)
    assert store.recover_historical_response("manual-tools", partial, now=110)
    recovered = store.detail("manual-tools")
    assert recovered is not None
    assert recovered["status"] == "interrupted"
    assert recovered["tool_calls"] == list(partial.tool_calls)
    payload["text"] = "The answer"
    payload["complete"] = True
    assert store.recover_historical_response("manual-tools", normalize_dom_snapshot(payload), now=111)
    completed = store.detail("manual-tools")
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["assistant_text"] == "The answer"
    assert completed["tool_calls"] == list(partial.tool_calls)


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


def test_tool_only_stream_before_final_text_is_preserved(tmp_path: Path) -> None:
    """A completed tool POST can have no assistant text until a later DOM answer."""
    store = ResponseStore(tmp_path / "tool-first.sqlite3")
    store.ensure_queued("tool-first", "Look up the weather", now=10)
    assert store.accept("tool-first", "100:owned", deadline=100, now=11)
    running: tuple[dict[str, object], ...] = ({
        "id": "call-1", "connector": "Weather", "action": "lookup",
        "status": "running", "arguments": '{"city":"Auckland"}', "result": "", "error": "",
    },)
    assert store.write("tool-first", "100:owned", CaptureResult(
        "sse", "unknown", "", "conversation-1", None, None, tool_calls=running,
    ), now=12)
    before = store.detail("tool-first")
    assert before is not None
    assert before["status"] == "accepted"
    assert before["assistant_text"] == ""
    assert before["tool_calls"] == list(running)

    completed: tuple[dict[str, object], ...] = ({
        **running[0], "status": "completed", "result": '{"temp_c":18}',
    }, {"id": "call-2", "connector": "Weather", "action": "units",
        "status": "completed", "arguments": "{}", "result": "metric", "error": ""})
    assert store.write("tool-first", "100:owned", CaptureResult(
        "sse", "unknown", "", "conversation-1", None, None, tool_calls=completed,
    ), now=13)
    assert store.write("tool-first", "100:owned", CaptureResult(
        "dom", "complete", "It is 18 °C.", "conversation-1", "answer-1", "parent-1",
    ), now=14)
    detail = store.detail("tool-first")
    assert detail is not None
    assert detail["status"] == "completed"
    calls = detail["tool_calls"]
    assert isinstance(calls, list)
    assert len(calls) == 2
    first_call, second_call = string_object_dict(calls[0]), string_object_dict(calls[1])
    assert first_call is not None and second_call is not None
    assert first_call["status"] == "completed"
    assert first_call["result"] == '{"temp_c":18}'
    assert second_call["action"] == "units"
    assert detail["assistant_text"] == "It is 18 °C."


def test_later_partial_tool_snapshot_cannot_erase_completed_result(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "merge.sqlite3")
    store.ensure_queued("merge", "Check", now=1)
    assert store.accept("merge", "100:owned", deadline=90, now=2)
    completed: tuple[dict[str, object], ...] = ({
        "id": "same", "connector": "GitHub", "action": "search", "status": "completed",
        "arguments": '{"repo":"project"}', "result": '{"count":2}', "error": "",
    },)
    assert store.write("merge", "100:owned", CaptureResult(
        "sse", "unknown", "", None, None, None, tool_calls=completed,
    ), now=3)
    stale: tuple[dict[str, object], ...] = ({
        "id": "same", "connector": "GitHub", "action": "search", "status": "running",
        "arguments": "", "result": "", "error": "",
    },)
    assert store.write("merge", "100:owned", CaptureResult(
        "sse", "unknown", "", None, None, None, tool_calls=stale,
    ), now=4)
    detail = store.detail("merge")
    assert detail is not None
    calls = detail["tool_calls"]
    assert isinstance(calls, list)
    first_call = string_object_dict(calls[0])
    assert first_call is not None
    assert first_call["status"] == "completed"
    assert first_call["result"] == '{"count":2}'
