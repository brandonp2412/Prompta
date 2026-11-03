"""Passive tool summaries from the already-issued POST SSE on one owned browser tab.

CDP delivers streamed chunks while a fetch response is still open. No requests,
history access, raw frame storage, or transcript/analysis capture occurs here.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import codecs
from collections.abc import Callable
from dataclasses import dataclass, field

from patchright.async_api import CDPSession, Page
from patchright.async_api import Error as PatchrightError

from .response_capture import CaptureResult, SseResponseAccumulator
from .tool_call_store import deserialize_tool_calls, merge_tool_calls
from .tool_events import ToolEventCollector, summarize_stream_tool_calls

_MAX_STREAM_BYTES = 4 * 1024 * 1024


@dataclass
class _Stream:
    parser: SseResponseAccumulator
    decoder: codecs.IncrementalDecoder = field(
        default_factory=lambda: codecs.getincrementaldecoder("utf-8")("replace")
    )
    pending: list[str] = field(default_factory=list)
    armed: bool = False
    finished: bool = False
    received: int = 0
    published_events: int = 0


class OwnedToolStream:
    """Observe only the current owned-tab POSTs; publish metadata, never payloads."""

    def __init__(
        self,
        session: CDPSession,
        is_active: Callable[[], bool],
        is_send_endpoint: Callable[[str], bool],
        publish: Callable[[CaptureResult], None],
    ) -> None:
        self.session = session
        self.is_active = is_active
        self.is_send_endpoint = is_send_endpoint
        self.publish = publish
        self.streams: dict[str, _Stream] = {}
        self.tasks: set[asyncio.Task[None]] = set()
        self.calls_json = "[]"
        self.collector = ToolEventCollector()
        self.conversation_id: str | None = None
        self.stopped = False

    @classmethod
    async def attach(
        cls,
        page: Page,
        is_active: Callable[[], bool],
        is_send_endpoint: Callable[[str], bool],
        publish: Callable[[CaptureResult], None],
    ) -> OwnedToolStream:
        session = await page.context.new_cdp_session(page)
        observer = cls(session, is_active, is_send_endpoint, publish)
        session.on("Network.requestWillBeSent", observer.on_request)
        session.on("Network.responseReceived", observer.on_response)
        session.on("Network.dataReceived", observer.on_data)
        session.on("Network.loadingFinished", observer.on_finished)
        session.on("Network.loadingFailed", observer.on_finished)
        try:
            await session.send("Network.enable")
        except Exception:
            await session.detach()
            raise
        return observer

    def on_request(self, event: dict[str, object]) -> None:
        request = event.get("request")
        if self.stopped or not self.is_active() or not isinstance(request, dict):
            return
        method = request.get("method")
        url = request.get("url")
        identity = event.get("requestId")
        if (
            method == "POST" and isinstance(url, str) and self.is_send_endpoint(url)
            and isinstance(identity, str) and identity
        ):
            self.streams[identity] = _Stream(SseResponseAccumulator(self.collector))

    def on_response(self, event: dict[str, object]) -> None:
        identity = event.get("requestId")
        if not isinstance(identity, str) or identity not in self.streams:
            return
        response = event.get("response")
        if not isinstance(response, dict):
            self.streams.pop(identity, None)
            return
        status = response.get("status")
        mime = response.get("mimeType")
        if (
            not isinstance(status, (float, int)) or not 200 <= status < 300
            or not isinstance(mime, str) or "text/event-stream" not in mime.casefold()
        ):
            self.streams.pop(identity, None)
            return
        task = asyncio.create_task(self.arm(identity))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def arm(self, identity: str) -> None:
        try:
            result = await self.session.send(
                "Network.streamResourceContent", {"requestId": identity}
            )
        except (PatchrightError, RuntimeError):
            self.streams.pop(identity, None)
            return
        stream = self.streams.get(identity)
        if stream is None or self.stopped:
            return
        buffered = result.get("bufferedData")
        if isinstance(buffered, str):
            self.feed(stream, buffered)
        stream.armed = True
        for chunk in stream.pending:
            self.feed(stream, chunk)
        stream.pending.clear()
        if stream.finished:
            self.flush(identity)

    def on_data(self, event: dict[str, object]) -> None:
        identity = event.get("requestId")
        if not isinstance(identity, str):
            return
        stream = self.streams.get(identity)
        chunk = event.get("data")
        if stream is None or not isinstance(chunk, str) or not self.is_active():
            return
        if stream.armed:
            self.feed(stream, chunk)
        elif sum(len(item) for item in stream.pending) + len(chunk) <= _MAX_STREAM_BYTES * 2:
            stream.pending.append(chunk)

    def feed(self, stream: _Stream, encoded: str) -> None:
        if stream.received >= _MAX_STREAM_BYTES:
            return
        try:
            chunk = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            return
        stream.received += len(chunk)
        if stream.received > _MAX_STREAM_BYTES:
            return
        stream.parser.feed(stream.decoder.decode(chunk))
        self.snapshot(stream)

    def snapshot(self, stream: _Stream) -> None:
        result = stream.parser.snapshot()
        if stream.parser.progress_events == stream.published_events:
            return
        stream.published_events = stream.parser.progress_events
        if result.stream_error:
            self.publish(result)
            return
        if not result.tool_calls:
            self.publish(CaptureResult("sse", "unknown", "", result.conversation_id, None, None, verified_generating=True))
            return
        conversation = result.conversation_id
        if conversation and self.conversation_id and conversation != self.conversation_id:
            return
        if conversation:
            self.conversation_id = conversation
        safe = summarize_stream_tool_calls(result.tool_calls)
        merged = merge_tool_calls(self.calls_json, safe)
        if merged == self.calls_json:
            self.publish(CaptureResult("sse", "unknown", "", conversation, None, None, verified_generating=True))
            return
        self.calls_json = merged
        self.publish(CaptureResult(
            "sse", "unknown", "", self.conversation_id, None, None,
            tool_calls=tuple(deserialize_tool_calls(merged)),
        ))

    def on_finished(self, event: dict[str, object]) -> None:
        identity = event.get("requestId")
        if not isinstance(identity, str):
            return
        stream = self.streams.get(identity)
        if stream is not None:
            stream.finished = True
            if stream.armed:
                self.flush(identity)

    def flush(self, identity: str) -> None:
        stream = self.streams.pop(identity, None)
        if stream is not None:
            stream.parser.feed(stream.decoder.decode(b"", final=True))
            stream.parser.finish()
            self.snapshot(stream)

    async def stop(self) -> None:
        self.stopped = True
        self.streams.clear()
        for task in tuple(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.session.detach()
