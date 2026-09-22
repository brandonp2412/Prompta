from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_FENCE = chr(96) * 3


def _json_load(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _event_key(event: dict[str, Any], index: int) -> str:
    del index
    message_id = str(event.get("id") or "").strip()
    if message_id:
        return message_id
    payload = json.dumps(event, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"event-{digest}"


def _source_time(event: dict[str, Any]) -> float | None:
    value = event.get("create_time")
    if value is None or isinstance(value, bool):
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    return timestamp if timestamp > 0 else None


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


def _result_value(event: dict[str, Any]) -> Any:
    text = event.get("text")
    parsed = _json_load(text)
    if isinstance(parsed, dict) and set(parsed) == {"text"}:
        nested = _json_load(parsed.get("text"))
        return nested if nested is not None else parsed.get("text")
    if parsed is not None:
        return parsed
    parts = event.get("parts")
    if isinstance(parts, list) and parts:
        first = parts[0]
        if isinstance(first, str):
            nested = _json_load(first)
            return nested if nested is not None else first
        return first
    if isinstance(text, str) and text.strip():
        return text
    return None


def _tool_call_key(call: dict[str, Any], index: int) -> str:
    source_key = str(call.get("source_event_key") or "").strip()
    if source_key:
        return f"tool-{source_key}"
    stable = json.dumps(
        {
            "connector": call.get("connector"),
            "action": call.get("action"),
            "created_at": call.get("created_at"),
            "ordinal": index,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return "tool-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]


def tool_calls_from_source_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    connector_hint = ""
    reasoning_title_hint = ""

    for index, raw in enumerate(events):
        if not isinstance(raw, dict):
            continue
        reasoning_title = str(raw.get("reasoning_title") or "").strip()
        if reasoning_title:
            reasoning_title_hint = reasoning_title
        connector_name = str(raw.get("connector_name") or "").strip()
        if connector_name:
            connector_hint = connector_name

        parsed = _json_load(raw.get("text"))
        if not isinstance(parsed, dict) or not (
            parsed.get("type") == "mcpToolCall" or parsed.get("appContext")
        ):
            continue
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
        call = {
            "connector": connector,
            "action": action,
            "summary": reasoning_title or reasoning_title_hint,
            "created_at": _source_time(raw),
            "arguments": parsed.get("arguments"),
            "status": str(parsed.get("status") or "completed"),
            "duration_ms": parsed.get("durationMs"),
            "error": parsed.get("error"),
            "result": parsed.get("result"),
            "source_event_key": _event_key(raw, index),
            "result_event_key": "",
        }
        call["call_key"] = _tool_call_key(call, len(calls))
        calls.append(call)

    if calls:
        for ordinal, call in enumerate(calls):
            call["ordinal"] = ordinal
        return calls

    invocations: list[dict[str, Any]] = []
    pending: list[int] = []
    connector_hint = ""
    reasoning_title_hint = ""
    for index, raw in enumerate(events):
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
            call = {
                "connector": _connector_from_path(path) or connector_hint,
                "action": _action_from_path(path),
                "summary": reasoning_title or reasoning_title_hint,
                "created_at": _source_time(raw),
                "arguments": args,
                "status": "running",
                "duration_ms": None,
                "error": None,
                "result": None,
                "source_event_key": _event_key(raw, index),
                "result_event_key": "",
            }
            call["call_key"] = _tool_call_key(call, len(invocations))
            invocations.append(call)
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
        for pending_index in reversed(pending):
            candidate = invocations[pending_index]
            if not action or not candidate.get("action") or candidate.get("action") == action:
                match_index = pending_index
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
            call["created_at"] = _source_time(raw)
        call["result_event_key"] = _event_key(raw, index)
        result = _result_value(raw)
        if result is not None:
            call["result"] = result

    for ordinal, call in enumerate(invocations):
        call["ordinal"] = ordinal
    return invocations


def _bounded(value: Any, limit: int = 12000) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        encoded = str(value)
    if len(encoded) <= limit:
        return value
    return encoded[: limit - 1] + "…"


def format_tool_block(call: dict[str, Any]) -> str:
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
        detail["arguments"] = _bounded(call["arguments"])
    status = str(call.get("status") or "").strip()
    if status:
        detail["status"] = status
    duration = call.get("duration_ms")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
        detail["duration_ms"] = duration
    if call.get("error") is not None:
        detail["error"] = _bounded(call["error"], 6000)
    if call.get("result") is not None:
        detail["result"] = _bounded(call["result"], 12000)
    body = json.dumps(detail, indent=2, ensure_ascii=False) if detail else "Called tool"
    return _FENCE + "tool:" + label + chr(10) + body + chr(10) + _FENCE


def _visible_text(event: dict[str, Any]) -> str:
    parts = event.get("parts")
    if isinstance(parts, list):
        visible = [part for part in parts if isinstance(part, str) and part.strip()]
        if visible:
            return "\n".join(visible).strip()
    return str(event.get("text") or "").strip()


def message_parts_from_source_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = [(index, event) for index, event in enumerate(events) if isinstance(event, dict)]
    indexed.sort(
        key=lambda item: (
            _source_time(item[1]) if _source_time(item[1]) is not None else float("inf"),
            item[0],
        )
    )
    calls = tool_calls_from_source_events([event for _, event in indexed])
    calls_by_source = {
        str(call.get("source_event_key") or ""): call
        for call in calls
        if str(call.get("source_event_key") or "")
    }
    parts: list[dict[str, Any]] = []
    final_parts: list[dict[str, Any]] = []

    for source_index, event in indexed:
        event_key = _event_key(event, source_index)
        role = str(event.get("role") or "")
        recipient = str(event.get("recipient") or "")
        content_type = str(event.get("content_type") or "")
        reasoning_title = str(event.get("reasoning_title") or "").strip()
        created_at = _source_time(event)
        if (
            role == "assistant"
            and recipient in {"", "all"}
            and content_type in {"text", "multimodal_text"}
        ):
            visible = _visible_text(event)
            if visible and not re.fullmatch(
                r"message delivery timed out\.?\s*please try again\.?",
                visible,
                flags=re.IGNORECASE,
            ):
                end_turn = event.get("end_turn")
                kind = (
                    "final_text"
                    if end_turn is True
                    else ("reasoning" if reasoning_title else "assistant_text")
                )
                part = {
                    "part_key": event_key,
                    "kind": kind,
                    "title": reasoning_title,
                    "content": visible,
                    "source_created_at": created_at,
                    "source_event_key": event_key,
                    "end_turn": end_turn if isinstance(end_turn, bool) else None,
                }
                if kind == "final_text":
                    final_parts.append(part)
                else:
                    parts.append(part)

        call = calls_by_source.get(event_key)
        if call is not None:
            parts.append(
                {
                    "part_key": str(call.get("call_key") or event_key),
                    "kind": "tool_call",
                    "title": str(call.get("summary") or ""),
                    "content": format_tool_block(call),
                    "source_created_at": call.get("created_at"),
                    "source_event_key": event_key,
                    "tool_call_key": call.get("call_key"),
                    "end_turn": None,
                }
            )

    parts.extend(final_parts)
    for ordinal, part in enumerate(parts):
        part["ordinal"] = ordinal
    return parts


def rendered_content_from_parts(parts: list[dict[str, Any]]) -> str:
    ordered = sorted(
        (part for part in parts if isinstance(part, dict)),
        key=lambda part: int(part.get("ordinal") or 0),
    )
    return (
        (chr(10) * 2)
        .join(
            str(part.get("content") or "").strip()
            for part in ordered
            if str(part.get("content") or "").strip()
        )
        .strip()
    )


def source_event_type(event: dict[str, Any]) -> str:
    role = str(event.get("role") or "")
    recipient = str(event.get("recipient") or "")
    if recipient == "api_tool.call_tool":
        return "tool_call"
    if role == "tool":
        return "tool_result"
    if role == "assistant" and recipient in {"", "all"}:
        if event.get("end_turn") is True:
            return "final_text"
        if str(event.get("reasoning_title") or "").strip():
            return "reasoning"
        return "assistant_text"
    return str(event.get("content_type") or role or "event")


def stable_event_key(event: dict[str, Any], index: int) -> str:
    payload = json.dumps(event, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    message_id = str(event.get("id") or "").strip()
    base = message_id or f"event-{index}"
    return f"{base}:{digest}"
