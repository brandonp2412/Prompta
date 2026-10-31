"""Actual CDP event ordering, cross-POST tools, lease storage, and privacy."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from patchright.async_api import CDPSession

from prompta.owned_tool_stream import OwnedToolStream
from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore


def frame(message: Mapping[str, object], conversation: str = "chat-1") -> bytes:
    return ("data: " + json.dumps({
        "conversation_id": conversation, "message": message,
    }) + "\n\n").encode()


def encoded(chunk: bytes) -> str:
    return base64.b64encode(chunk).decode("ascii")


@pytest.mark.asyncio
async def test_streamed_tool_call_and_result_across_owned_posts_persist_redacted_payload(
    tmp_path: Path,
) -> None:
    session = Mock(spec=CDPSession)
    session.send = AsyncMock(return_value={"bufferedData": ""})
    updates: list[CaptureResult] = []
    stream = OwnedToolStream(
        session, lambda: True,
        lambda url: url == "https://chatgpt.com/backend-api/conversation",
        updates.append,
    )
    call = {
        "id": "call-1", "author": {"role": "assistant"},
        "recipient": "api_tool.call_tool",
        "content": {"content_type": "text", "parts": [json.dumps({
            "type": "mcpToolCall",
            "tool": "search.lookup",
            "arguments": {"query": "PRIVATE_SEARCH", "password": "PRIVATE_SECRET"},
        })]},
    }
    result = {
        "id": "result-1", "author": {"role": "tool", "name": "search"},
        "metadata": {"tool_call_id": "call-1"},
        "content": {"content_type": "text", "parts": ["PRIVATE_RESULT"]},
    }
    # Network chunks may arrive before streamResourceContent resolves.
    stream.on_request({"requestId": "post-1", "request": {
        "method": "POST", "url": "https://chatgpt.com/backend-api/conversation",
    }})
    stream.on_response({"requestId": "post-1", "response": {
        "status": 200, "mimeType": "text/event-stream",
    }})
    await asyncio.gather(*stream.tasks)
    payload = frame(call)
    stream.on_data({"requestId": "post-1", "data": encoded(payload[:34])})
    stream.on_data({"requestId": "post-1", "data": encoded(payload[34:])})
    assert updates[-1].tool_calls[0]["status"] == "running"
    assert "PRIVATE_SEARCH" in str(updates)
    assert "PRIVATE_SECRET" not in str(updates)
    stream.on_finished({"requestId": "post-1"})

    # The second POST is a connector continuation, not a second prompt.
    stream.on_request({"requestId": "post-2", "request": {
        "method": "POST", "url": "https://chatgpt.com/backend-api/conversation",
    }})
    stream.on_response({"requestId": "post-2", "response": {
        "status": 200, "mimeType": "text/event-stream",
    }})
    await asyncio.gather(*stream.tasks)
    stream.on_data({"requestId": "post-2", "data": encoded(frame(result))})
    assert len(updates[-1].tool_calls) == 1
    assert updates[-1].tool_calls[0]["status"] == "completed"
    assert "PRIVATE_RESULT" in str(updates)

    store = ResponseStore(tmp_path / "results.sqlite3")
    store.ensure_queued("owned", "Tool canary", now=1)
    assert store.accept("owned", "owner", deadline=100, now=2)
    assert store.write("owned", "owner", updates[-1], now=3)
    record = store.detail("owned")
    assert record is not None
    assert record["tool_calls"] == list(updates[-1].tool_calls)
    assert record["assistant_text"] == ""
    assert record["status"] == "accepted"
    assert "PRIVATE_SECRET" not in str(record["tool_calls"])
    assert "PRIVATE_RESULT" in str(record["tool_calls"])
    await stream.stop()


def test_incomplete_tool_snapshot_survives_store_reopen_and_interruption(tmp_path: Path) -> None:
    path = tmp_path / "durable-restart.sqlite3"
    first = ResponseStore(path)
    first.ensure_queued("owned-incomplete", "Tool canary", now=1)
    assert first.accept("owned-incomplete", "owner", deadline=100, now=2)
    tools: tuple[dict[str, object], ...] = ({
        "id": "tool-call-1", "connector": "web", "action": "search",
        "status": "running", "arguments": "", "result": "", "error": "",
    },)
    assert first.write(
        "owned-incomplete", "owner",
        CaptureResult("sse", "unknown", "", "owned-chat", None, None, tool_calls=tools),
        now=3,
    )
    # A restarted service has no memory of the original SSE yet retains only
    # durable redacted metadata; it must not re-dispatch anything.
    reopened = ResponseStore(path)
    before = reopened.detail("owned-incomplete")
    assert before is not None
    assert before["tool_calls"] == list(tools)
    assert reopened.finish("owned-incomplete", "owner", "interrupted", now=4)
    after = ResponseStore(path).detail("owned-incomplete")
    assert after is not None
    assert after["status"] == "interrupted"
    assert after["tool_calls"] == list(tools)


@pytest.mark.asyncio
async def test_incomplete_event_and_non_sse_response_do_not_publish_data() -> None:
    session = Mock(spec=CDPSession)
    session.send = AsyncMock(return_value={"bufferedData": ""})
    updates: list[CaptureResult] = []
    stream = OwnedToolStream(
        session, lambda: True, lambda _url: True, updates.append,
    )
    stream.on_request({"requestId": "non-sse", "request": {"method": "POST", "url": "/api"}})
    stream.on_response({"requestId": "non-sse", "response": {
        "status": 200, "mimeType": "application/json",
    }})
    assert "non-sse" not in stream.streams
    stream.on_request({"requestId": "partial", "request": {"method": "POST", "url": "/api"}})
    stream.on_response({"requestId": "partial", "response": {
        "status": 200, "mimeType": "text/event-stream",
    }})
    await asyncio.gather(*stream.tasks)
    payload = frame({
        "id": "call-2", "author": {"role": "assistant"},
        "recipient": "api_tool.call_tool",
        "content": {"content_type": "text", "parts": [json.dumps({
            "type": "mcpToolCall", "tool": "calendar.lookup",
            "arguments": {"api_key": "PRIVATE_KEY"},
        })]},
    })
    stream.on_data({"requestId": "partial", "data": encoded(payload[:-2])})
    assert not updates
    stream.on_data({"requestId": "partial", "data": encoded(payload[-2:])})
    assert len(updates) == 1
    assert updates[0].tool_calls[0]["status"] == "running"
    assert "PRIVATE_KEY" not in str(updates)
    await stream.stop()
