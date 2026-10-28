"""Pure, bounded, passive parsing of one owned ChatGPT conversation POST response.

No HTTP client, browser navigation, history endpoint, logging, or persistence lives here.
The caller feeds only bytes already observed on its own submitted POST.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

CaptureStatus = Literal[
    "complete", "partial", "timeout", "approval_wait", "rate_limited", "interrupted", "unknown"
]
CaptureSource = Literal["sse", "dom"]
StopReason = Literal["timeout", "approval_wait", "rate_limited", "interrupted", "unknown"]

_MAX_SSE_CHARACTERS = 4 * 1024 * 1024
_MAX_ANSWER_CHARACTERS = 2 * 1024 * 1024
_PART_PATH = re.compile(r"^/message/content/parts/(\d+)$")


@dataclass(frozen=True, slots=True)
class CaptureResult:
    source: CaptureSource
    status: CaptureStatus
    text: str
    conversation_id: str | None
    message_id: str | None
    parent_id: str | None
    observer_id: str | None = None


def conversation_id_from_path(path: object) -> str | None:
    """Validate the new conversation route on this one owned tab."""
    if not isinstance(path, str):
        return None
    match = re.fullmatch(r"/(?:g/[^/]+/)?c/([0-9a-fA-F-]{36})", path)
    if match is None:
        return None
    try:
        identity = UUID(match.group(1))
    except ValueError:
        return None
    return str(identity) if str(identity) == match.group(1).lower() else None


def _record(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {key: child for key, child in value.items() if isinstance(key, str)}


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _part_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return _string(_record(value).get("text")) or ""


def _message_parts(message: dict[str, object]) -> list[str]:
    content = _record(message.get("content"))
    parts = content.get("parts")
    if isinstance(parts, list):
        return [_part_text(part) for part in parts]
    text = _string(content.get("text"))
    return [text] if text is not None else []


def _is_final_assistant(message: dict[str, object]) -> bool:
    if _record(message.get("author")).get("role") != "assistant":
        return False
    if message.get("recipient") not in (None, "all"):
        return False
    metadata = _record(message.get("metadata"))
    if message.get("channel") not in (None, "final"):
        return False
    if metadata.get("channel") not in (None, "final"):
        return False
    if metadata.get("message_type") in ("analysis", "thought", "reasoning_recap"):
        return False
    if metadata.get("is_visually_hidden_from_conversation") is True:
        return False
    if _record(message.get("content")).get("content_type") != "text":
        return False
    return True


def _message_complete(message: dict[str, object]) -> bool:
    return (
        message.get("status") == "finished_successfully"
        or message.get("end_turn") is True
        or _record(message.get("metadata")).get("is_complete") is True
    )


class SseResponseAccumulator:
    """Decode one POST stream, rejecting ambiguous branch/identity changes."""

    def __init__(self) -> None:
        self._line_buffer = ""
        self._data_lines: list[str] = []
        self._parts: list[str] = []
        self._last_part = 0
        self._conversation_id: str | None = None
        self._message_id: str | None = None
        self._parent_id: str | None = None
        self._tracking = False
        self._seen_final = False
        self._complete = False
        self._ambiguous = False
        self._overflow = False
        self._received = 0

    def feed(self, chunk: str) -> None:
        if not chunk or self._overflow:
            return
        remaining = _MAX_SSE_CHARACTERS - self._received
        self._received += len(chunk)
        if len(chunk) > remaining:
            self._overflow = True
            chunk = chunk[:remaining]
        self._line_buffer += chunk
        while (index := self._line_buffer.find("\n")) >= 0:
            line = self._line_buffer[:index].removesuffix("\r")
            self._line_buffer = self._line_buffer[index + 1 :]
            self._handle_line(line)

    def finish(self) -> None:
        if self._line_buffer:
            self._handle_line(self._line_buffer.removesuffix("\r"))
            self._line_buffer = ""
        self._flush_event()

    def _handle_line(self, line: str) -> None:
        if not line:
            self._flush_event()
        elif line.startswith("data:"):
            self._data_lines.append(line[5:].removeprefix(" "))

    def _flush_event(self) -> None:
        if not self._data_lines:
            return
        payload = "\n".join(self._data_lines)
        self._data_lines.clear()
        if payload == "[DONE]":
            self._complete = True
            return
        try:
            event: object = json.loads(payload)
        except (ValueError, TypeError):
            return
        self._consume(_record(event))

    def _bind_identity(self, conversation_id: object, parent_id: object) -> None:
        candidate = _string(conversation_id)
        if candidate is not None:
            if self._conversation_id is not None and self._conversation_id != candidate:
                self._ambiguous = True
            else:
                self._conversation_id = candidate
        parent = _string(parent_id)
        if parent is not None:
            if self._parent_id is not None and self._parent_id != parent:
                self._ambiguous = True
            else:
                self._parent_id = parent

    def _consume_message(
        self,
        message: dict[str, object],
        conversation_id: object,
        parent_id: object,
    ) -> None:
        if not _is_final_assistant(message):
            self._tracking = False
            return
        # Tool/thought nodes can have different parents within one stream;
        # branch identity belongs only to the captured final assistant node.
        self._bind_identity(conversation_id, parent_id)
        candidate = _string(message.get("id"))
        if self._seen_final and candidate != self._message_id:
            # Different final ids on the same POST may be alternate branches.
            self._ambiguous = True
            self._tracking = False
            return
        if self._ambiguous:
            return
        self._seen_final = True
        self._tracking = True
        self._message_id = candidate
        parts = _message_parts(message)
        if len("\n".join(parts)) >= len("\n".join(self._parts)):
            self._parts = parts
            self._last_part = max(0, len(parts) - 1)
        if _message_complete(message):
            self._complete = True

    def _patch(self, patch: dict[str, object]) -> None:
        if not self._tracking or self._ambiguous:
            return
        path = _string(patch.get("p"))
        operation = patch.get("o")
        value = patch.get("v")
        if path in ("/message/status", "/message/end_turn"):
            if (path == "/message/status" and value == "finished_successfully") or (
                path == "/message/end_turn" and value is True
            ):
                self._complete = True
            return
        if path is None:
            index = self._last_part
        else:
            match = _PART_PATH.fullmatch(path)
            if match is None:
                return
            index = int(match.group(1))
        if index > 16 or not isinstance(value, str):
            return
        while len(self._parts) <= index:
            self._parts.append("")
        if operation in (None, "append"):
            self._parts[index] += value
        elif operation in ("replace", "add"):
            self._parts[index] = value
        else:
            return
        self._last_part = index

    def _consume(self, event: dict[str, object]) -> None:
        if not event:
            return
        if event.get("type") == "message_stream_complete":
            self._bind_identity(event.get("conversation_id"), event.get("parent_id"))
            self._complete = True
            return
        message = _record(event.get("message"))
        if message:
            self._consume_message(
                message, event.get("conversation_id"), event.get("parent_id")
            )
            return
        operation = event.get("o")
        value = event.get("v")
        wrapped = _record(value)
        nested = _record(wrapped.get("message"))
        if nested:
            self._consume_message(
                nested,
                wrapped.get("conversation_id") or event.get("conversation_id"),
                wrapped.get("parent_id") or event.get("parent_id"),
            )
            return
        if operation in ("add", "replace") and event.get("p") == "/message" and wrapped:
            self._consume_message(
                wrapped, event.get("conversation_id"), event.get("parent_id")
            )
            return
        if isinstance(value, list) and operation in (None, "patch"):
            for item in value:
                self._patch(_record(item))
        else:
            self._patch(event)

    def snapshot(self, *, stop_reason: StopReason | None = None) -> CaptureResult:
        if self._ambiguous:
            return CaptureResult("sse", "unknown", "", None, None, None)
        text = "\n".join(part for part in self._parts if part).strip()
        if len(text) > _MAX_ANSWER_CHARACTERS:
            text = text[:_MAX_ANSWER_CHARACTERS]
            self._overflow = True
        status: CaptureStatus
        if stop_reason is not None and stop_reason != "unknown":
            status = stop_reason
        elif self._complete and self._seen_final and text and not self._overflow:
            status = "complete"
        elif text:
            status = "partial"
        else:
            status = "unknown"
        return CaptureResult(
            "sse", status, text, self._conversation_id, self._message_id, self._parent_id
        )


def parse_sse_body(body: str, *, stop_reason: StopReason | None = None) -> CaptureResult:
    accumulator = SseResponseAccumulator()
    accumulator.feed(body)
    accumulator.finish()
    return accumulator.snapshot(stop_reason=stop_reason)


def normalize_dom_snapshot(
    payload: object, *, stop_reason: StopReason | None = None
) -> CaptureResult:
    """Normalize one observer snapshot; never infer completion from text stability alone."""
    record = _record(payload)
    identity = _string(record.get("message_id"))
    if not identity or record.get("ambiguous") is True:
        return CaptureResult("dom", "unknown", "", None, None, None)
    original_text = _string(record.get("text")) or ""
    truncated = len(original_text) > _MAX_ANSWER_CHARACTERS
    text = original_text[:_MAX_ANSWER_CHARACTERS].strip()
    if stop_reason is not None and stop_reason != "unknown":
        status: CaptureStatus = stop_reason
    elif record.get("complete") is True and text and not truncated:
        status = "complete"
    elif text:
        status = "partial"
    else:
        status = "unknown"
    # The modern assistant unit key is an observer identity, not a backend message ID.
    # Only the single unambiguous backend ID may become a manual-reply parent.
    branch_id = (
        _string(record.get("branch_message_id"))
        if "branch_message_id" in record
        else identity  # Legacy synthetic observer fixtures.
    )
    if "branch_message_id" in record and branch_id is not None:
        try:
            branch_id = str(UUID(branch_id)) if str(UUID(branch_id)) == branch_id.lower() else None
        except ValueError:
            branch_id = None
    return CaptureResult(
        "dom", status, text, conversation_id_from_path(record.get("pathname")),
        branch_id, None, identity,
    )
