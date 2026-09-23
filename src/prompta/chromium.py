"""Read-only Chromium/CDP enrichment for structured ChatGPT tool calls."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

import websockets

from .browser_script_loader import render_browser_script
from .chatgpt_dom import ASSISTANT_MESSAGE_SELECTOR, MESSAGE_ROLE_SELECTOR, TURN_SELECTOR
from .ui_noise import is_assistant_ui_noise

logger = logging.getLogger(__name__)

_DEFAULT_CDP_URL = "http://127.0.0.1:9222"
_FENCE = chr(96) * 3
_TOOL_BLOCK_RE = re.compile(
    r"^ {0,3}"
    + re.escape(_FENCE)
    + r"(?:tool|tool-call|function|function-call)(?::[^\n\x60]*)?\r?\n"
    + r"[\s\S]*?^ {0,3}"
    + re.escape(_FENCE)
    + r"[ \t]*\r?$",
    re.IGNORECASE | re.MULTILINE,
)
_REACT_TOOL_SCRIPT = render_browser_script(
    "react_tool_messages.js",
    ASSISTANT_SELECTOR=ASSISTANT_MESSAGE_SELECTOR,
    MESSAGE_ROLE_SELECTOR=MESSAGE_ROLE_SELECTOR,
    TURN_SELECTOR=TURN_SELECTOR,
)


def _json_load(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _action_from_path(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    parts = [part for part in value.split("/") if part]
    return parts[-1] if parts else ""


def _connector_from_path(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    parts = [part for part in value.split("/") if part]
    if not parts:
        return ""
    first = parts[0]
    if first.startswith(("asdk_app_", "plugin_", "link_")):
        return ""
    return first


def _bounded(value: Any, limit: int = 6000) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        encoded = str(value)
    if len(encoded) <= limit:
        return value
    return encoded[: limit - 1] + "…"


def _result_value(message: dict[str, Any]) -> Any:
    text = message.get("text")
    parsed = _json_load(text)
    if isinstance(parsed, dict) and set(parsed) == {"text"}:
        nested = _json_load(parsed.get("text"))
        return nested if nested is not None else parsed.get("text")
    if parsed is not None:
        return parsed
    parts = message.get("parts")
    if isinstance(parts, list) and parts:
        first = parts[0]
        if isinstance(first, str):
            nested = _json_load(first)
            return nested if nested is not None else first
        return first
    if isinstance(text, str) and text.strip():
        return text
    return None


def tool_blocks_from_messages(messages: list[dict[str, Any]]) -> list[str]:
    """Convert sanitized ChatGPT React messages into Prompta tool fences."""

    calls: list[dict[str, Any]] = []
    completed_wrapper_count = 0
    connector_hint = ""

    reasoning_title_hint = ""
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        reasoning_title = str(raw.get("reasoning_title") or "").strip()
        if reasoning_title:
            reasoning_title_hint = reasoning_title
        connector_name = str(raw.get("connector_name") or "").strip()
        if connector_name:
            connector_hint = connector_name

        text = str(raw.get("text") or "")
        parsed = _json_load(text)
        if isinstance(parsed, dict) and (
            parsed.get("type") == "mcpToolCall" or parsed.get("appContext")
        ):
            app_context = parsed.get("appContext")
            if not isinstance(app_context, dict):
                app_context = {}
            tool_name = str(parsed.get("tool") or "")
            action = str(app_context.get("actionName") or "")
            if not action and tool_name:
                action = tool_name.rsplit(".", 1)[-1]
            invoked = raw.get("invoked_resource")
            if not isinstance(invoked, dict):
                invoked = {}
            connector = str(
                app_context.get("appName") or invoked.get("app_name") or connector_hint
            ).strip()
            calls.append(
                {
                    "connector": connector,
                    "action": action,
                    "summary": reasoning_title or reasoning_title_hint,
                    "created_at": raw.get("create_time"),
                    "arguments": parsed.get("arguments"),
                    "status": str(parsed.get("status") or "completed"),
                    "duration_ms": parsed.get("durationMs"),
                    "error": parsed.get("error"),
                    "result": parsed.get("result"),
                }
            )
            completed_wrapper_count += 1

    if completed_wrapper_count:
        pending_invocations: list[dict[str, Any]] = []
        for raw in messages:
            if not isinstance(raw, dict) or str(raw.get("recipient") or "") != "api_tool.call_tool":
                continue
            parsed = _json_load(raw.get("text"))
            if not isinstance(parsed, dict):
                continue
            pending_invocations.append(
                {
                    "action": _action_from_path(parsed.get("path")),
                    "created_at": raw.get("create_time"),
                }
            )

        for call in calls:
            call_action = str(call.get("action") or "")
            match_index = next(
                (
                    index
                    for index, invocation in enumerate(pending_invocations)
                    if not call_action
                    or not invocation.get("action")
                    or invocation.get("action") == call_action
                ),
                None,
            )
            if match_index is None:
                continue
            invocation = pending_invocations.pop(match_index)
            created_at = invocation.get("created_at")
            if (
                isinstance(created_at, (int, float))
                and not isinstance(created_at, bool)
                and created_at > 0
            ):
                call["created_at"] = created_at

        return [_format_tool_block(call) for call in calls]

    invocations: list[dict[str, Any]] = []
    pending: list[int] = []
    reasoning_title_hint = ""
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        reasoning_title = str(raw.get("reasoning_title") or "").strip()
        if reasoning_title:
            reasoning_title_hint = reasoning_title
        connector_name = str(raw.get("connector_name") or "").strip()
        if connector_name:
            connector_hint = connector_name

        recipient = str(raw.get("recipient") or "")
        text = str(raw.get("text") or "")
        if recipient == "api_tool.call_tool":
            parsed = _json_load(text)
            if not isinstance(parsed, dict):
                parsed = {}
            payload = _json_load(raw.get("connector_tool_payload"))
            path = parsed.get("path")
            args = parsed.get("args")
            if args is None and isinstance(payload, dict):
                if "args" in payload:
                    args = payload.get("args")
                elif "path" not in payload:
                    args = payload
            invocations.append(
                {
                    "connector": _connector_from_path(path) or connector_hint,
                    "action": _action_from_path(path),
                    "summary": reasoning_title or reasoning_title_hint,
                    "created_at": raw.get("create_time"),
                    "arguments": args,
                    "status": "running",
                    "duration_ms": None,
                    "error": None,
                    "result": None,
                    "path": path,
                }
            )
            pending.append(len(invocations) - 1)
            continue

        if str(raw.get("role") or "") != "tool":
            continue
        invoked = raw.get("invoked_resource")
        if not isinstance(invoked, dict):
            invoked = {}
        resource_uri = invoked.get("resource_uri")
        action = _action_from_path(resource_uri)
        connector = str(invoked.get("app_name") or connector_hint).strip()
        match_index: int | None = None
        for index in reversed(pending):
            candidate = invocations[index]
            if not action or not candidate.get("action") or candidate.get("action") == action:
                match_index = index
                break
        if match_index is None:
            continue
        pending.remove(match_index)
        call = invocations[match_index]
        if connector:
            call["connector"] = connector
        if action:
            call["action"] = action
        call["status"] = "completed"
        if call.get("created_at") is None:
            call["created_at"] = raw.get("create_time")
        result = _result_value(raw)
        if result is not None:
            call["result"] = result

    return [_format_tool_block(call) for call in invocations]


def _format_tool_block(call: dict[str, Any]) -> str:
    connector = str(call.get("connector") or "").strip()
    action = str(call.get("action") or "").strip()
    label = " · ".join(part for part in (connector, action) if part) or "tool"
    detail: dict[str, Any] = {}
    summary = str(call.get("summary") or "").strip()
    if summary:
        detail["summary"] = summary
    created_at = call.get("created_at")
    if isinstance(created_at, (int, float)) and not isinstance(created_at, bool) and created_at > 0:
        detail["created_at"] = created_at
    if call.get("arguments") is not None:
        detail["arguments"] = _bounded(call["arguments"], 12000)
    status = str(call.get("status") or "").strip()
    if status:
        detail["status"] = status
    duration = call.get("duration_ms")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
        detail["duration_ms"] = duration
    if call.get("error"):
        detail["error"] = _bounded(call["error"])
    if call.get("result") is not None:
        detail["result"] = _bounded(call["result"])
    body = json.dumps(detail, indent=2, ensure_ascii=False) if detail else "Called tool"
    return _FENCE + "tool:" + label + chr(10) + body + chr(10) + _FENCE


def _message_create_time(message: dict[str, Any]) -> float:
    value = message.get("create_time")
    return float(value) if isinstance(value, (int, float)) else float("inf")


def _tool_block_create_time(block: str) -> float | None:
    lines = str(block or "").splitlines()
    if len(lines) < 3:
        return None
    payload = _json_load(chr(10).join(lines[1:-1]))
    if not isinstance(payload, dict):
        return None
    value = payload.get("created_at")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    return float(value)


def ordered_assistant_content_from_messages(messages: list[dict[str, Any]]) -> str:
    """Build the latest assistant turn from React messages in event order."""

    ordered = sorted(
        (message for message in messages if isinstance(message, dict)),
        key=_message_create_time,
    )
    blocks = tool_blocks_from_messages(ordered)
    completed_wrappers = any(
        isinstance(parsed := _json_load(message.get("text")), dict)
        and (
            parsed.get("type") == "mcpToolCall"
            or parsed.get("appContext")
            or parsed.get("arguments") is not None
        )
        for message in ordered
    )

    text_entries: list[tuple[int, dict[str, Any], str]] = []
    for index, message in enumerate(ordered):
        role = str(message.get("role") or "")
        recipient = str(message.get("recipient") or "")
        content_type = str(message.get("content_type") or "")
        if (
            role != "assistant"
            or recipient not in {"", "all"}
            or content_type not in {"text", "multimodal_text"}
        ):
            continue
        raw_parts = message.get("parts")
        visible_parts = (
            [part for part in raw_parts if isinstance(part, str) and part.strip()]
            if isinstance(raw_parts, list)
            else []
        )
        visible = (
            chr(10).join(visible_parts) if visible_parts else str(message.get("text") or "")
        ).strip()
        if not visible or is_assistant_ui_noise(visible):
            continue
        text_entries.append((index, message, visible))

    final_text: str | None = None
    if text_entries and text_entries[-1][1].get("end_turn") is True:
        _, _, final_text = text_entries.pop()

    timeline: list[tuple[float, int, str]] = [
        (_message_create_time(message), index * 2, visible)
        for index, message, visible in text_entries
    ]

    tool_sources: list[tuple[int, dict[str, Any]]] = []
    for index, message in enumerate(ordered):
        parsed = _json_load(message.get("text"))
        wrapper = isinstance(parsed, dict) and (
            parsed.get("type") == "mcpToolCall"
            or parsed.get("appContext")
            or parsed.get("arguments") is not None
        )
        invocation = str(message.get("recipient") or "") == "api_tool.call_tool"
        if (completed_wrappers and wrapper) or (not completed_wrappers and invocation):
            tool_sources.append((index, message))

    for tool_index, block in enumerate(blocks):
        if tool_index < len(tool_sources):
            source_index, source_message = tool_sources[tool_index]
            fallback_time = _message_create_time(source_message)
            order_index = source_index * 2 + 1
        else:
            fallback_time = float("inf")
            order_index = len(ordered) * 2 + tool_index
        created_at = _tool_block_create_time(block)
        timeline.append(
            (
                created_at if created_at is not None else fallback_time,
                order_index,
                block,
            )
        )

    timeline.sort(key=lambda entry: (entry[0], entry[1]))
    parts = [content for _, _, content in timeline if content]
    if final_text:
        parts.append(final_text)
    return (chr(10) * 2).join(parts).strip()


def preserves_non_tool_text(source: str, candidate: str) -> bool:
    """Return whether candidate keeps all visible non-tool assistant text."""

    source_text = re.sub(r"\s+", " ", _TOOL_BLOCK_RE.sub("", str(source or ""))).strip()
    if not source_text:
        return True
    candidate_text = re.sub(r"\s+", " ", _TOOL_BLOCK_RE.sub("", str(candidate or ""))).strip()
    return source_text in candidate_text


def finalize_completed_assistant_content(content: str) -> str:
    """Keep the last completed assistant prose after every tool call.

    ChatGPT can collapse a long tool timeline in the DOM. When Prompta has more
    structured tool blocks than visible tool rows, the fallback DOM merge may
    append those hidden blocks after the final answer. On a completed turn,
    move only the last non-tool segment that is sandwiched between tool blocks
    to the end. Already-correct content and tool-only turns are unchanged.
    """

    source = str(content or "")
    matches = list(_TOOL_BLOCK_RE.finditer(source))
    if len(matches) < 2:
        return source
    if source[matches[-1].end() :].strip():
        return source

    final_gap: tuple[int, int, str] | None = None
    for previous, current in zip(matches, matches[1:]):
        gap = source[previous.end() : current.start()]
        if gap.strip():
            final_gap = (previous.end(), current.start(), gap)
    if final_gap is None:
        return source

    start, end, prose = final_gap
    before = source[:start].rstrip()
    after = source[end:].strip()
    final_prose = prose.strip()
    return (chr(10) * 2).join(part for part in (before, after, final_prose) if part).strip()


def merge_tool_blocks(content: str, blocks: list[str]) -> str:
    if not blocks:
        return content
    source = str(content or "")
    matches = list(_TOOL_BLOCK_RE.finditer(source))
    if not matches:
        return (chr(10) * 2).join(part for part in [source.strip(), *blocks] if part).strip()

    parts: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        parts.append(source[cursor : match.start()])
        parts.append(blocks[index] if index < len(blocks) else match.group(0))
        cursor = match.end()
    parts.append(source[cursor:])
    merged = "".join(parts).strip()
    if len(blocks) > len(matches):
        merged = (chr(10) * 2).join([merged, *blocks[len(matches) :]]).strip()
    return merged


class ChromiumToolEnricher:
    """Use an authenticated local Chromium CDP endpoint for read-only enrichment."""

    def __init__(self, endpoint: str | None = None, *, timeout_seconds: float = 8.0) -> None:
        self.endpoint = (
            endpoint or os.getenv("PROMPTA_CHROMIUM_CDP_URL") or _DEFAULT_CDP_URL
        ).rstrip("/")
        self.timeout_seconds = max(1.0, timeout_seconds)

    async def enrichment(self, url: str) -> tuple[list[str], str]:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname != "chatgpt.com":
            return [], ""
        created_target = False
        target: dict[str, Any] | None = None
        try:
            targets = await asyncio.to_thread(self._http_json, "/json/list")
            if isinstance(targets, list):
                target = next(
                    (
                        item
                        for item in targets
                        if isinstance(item, dict)
                        and item.get("type") == "page"
                        and str(item.get("url") or "").rstrip("/") == url.rstrip("/")
                    ),
                    None,
                )
            if target is None:
                target = await asyncio.to_thread(
                    self._http_json,
                    f"/json/new?{quote(url, safe='')}",
                    "PUT",
                )
                created_target = True
            if not isinstance(target, dict):
                return [], ""
            websocket_url = str(target.get("webSocketDebuggerUrl") or "")
            if not websocket_url:
                return [], ""
            messages = await self._react_messages(websocket_url)
            blocks = tool_blocks_from_messages(messages)
            return blocks, ordered_assistant_content_from_messages(messages)
        except Exception as exc:
            logger.debug("Chromium tool enrichment unavailable for %s: %s", url, exc)
            return [], ""
        finally:
            if created_target and isinstance(target, dict) and target.get("id"):
                try:
                    await asyncio.to_thread(
                        self._http_json,
                        f"/json/close/{target['id']}",
                    )
                except Exception:
                    logger.debug("Could not close Chromium enrichment tab", exc_info=True)

    async def tool_blocks(self, url: str) -> list[str]:
        blocks, _ = await self.enrichment(url)
        return blocks

    def _http_json(self, path: str, method: str = "GET") -> Any:
        request = Request(f"{self.endpoint}{path}", method=method)
        with urlopen(request, timeout=min(3.0, self.timeout_seconds)) as response:
            payload = response.read()
        return json.loads(payload) if payload else {}

    async def _react_messages(self, websocket_url: str) -> list[dict[str, Any]]:
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        async with websockets.connect(
            websocket_url,
            max_size=16 * 1024 * 1024,
            ping_interval=None,
            open_timeout=min(3.0, self.timeout_seconds),
        ) as websocket:
            request_id = 0

            async def call(
                method: str,
                params: dict[str, Any] | None = None,
            ) -> dict[str, Any]:
                nonlocal request_id
                request_id += 1
                current_id = request_id
                await websocket.send(
                    json.dumps({"id": current_id, "method": method, "params": params or {}})
                )
                while True:
                    remaining = max(
                        0.1,
                        deadline - asyncio.get_running_loop().time(),
                    )
                    message = json.loads(
                        await asyncio.wait_for(websocket.recv(), timeout=remaining)
                    )
                    if message.get("id") == current_id:
                        return message

            await call("Runtime.enable")
            latest: list[dict[str, Any]] = []
            while asyncio.get_running_loop().time() < deadline:
                response = await call(
                    "Runtime.evaluate",
                    {"expression": _REACT_TOOL_SCRIPT, "returnByValue": True},
                )
                value = response.get("result", {}).get("result", {}).get("value", {})
                if isinstance(value, dict):
                    messages = value.get("messages")
                    if isinstance(messages, list):
                        latest = [item for item in messages if isinstance(item, dict)]
                    if value.get("ready") and latest:
                        blocks = tool_blocks_from_messages(latest)
                        if blocks and not any('"status": "running"' in block for block in blocks):
                            return latest
                await asyncio.sleep(0.35)
            return latest
