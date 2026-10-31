"""Bounded, redacted tool-call summaries from an already observed owned POST stream.

Never capture analysis/reasoning or make independent ChatGPT requests.
"""

from __future__ import annotations

import json
import re
from typing import Final

_MAX_TOOLS: Final = 128
_PRIVATE_KEYS: Final = re.compile(
    r"(?:token|secret|password|cookie|authorization|api.?key|credential|session.?key)", re.I
)


def _record(value: object) -> dict[str, object]:
    return {k: v for k, v in value.items() if isinstance(k, str)} if isinstance(value, dict) else {}


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _decode(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def _redact(value: object, depth: int = 0) -> object:
    if depth >= 8:
        return "[nested value omitted]"
    if isinstance(value, dict):
        return {
            k: "[redacted]" if _PRIVATE_KEYS.search(k) else _redact(v, depth + 1)
            for k, v in value.items() if isinstance(k, str)
        }
    if isinstance(value, list):
        return [_redact(item, depth + 1) for item in value[:64]]
    return value


def _display(value: object, limit: int = 6000) -> str:
    if value is None or value == "":
        return ""
    decoded = _decode(value)
    if isinstance(decoded, str) and (
        decoded.lstrip().startswith("{") or re.match(r'^\s*\[\s*(?:[\[{"]|$)', decoded)
    ):
        # Incomplete streamed JSON cannot be field-redacted safely yet.
        return "[structured payload pending]"
    safe = _redact(decoded)
    if isinstance(safe, str):
        result = safe
    else:
        try:
            result = json.dumps(safe, indent=2, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return "[unavailable]"
    return result if len(result) <= limit else result[:limit] + "\n… (truncated)"


def _name_from_path(value: object) -> str:
    path = _text(value)
    return path.rstrip("/").rsplit("/", 1)[-1] if path else ""


def normalize_dom_tool_calls(value: object) -> tuple[dict[str, object], ...]:
    """Accept only bounded, visible tool labels; never DOM details or thoughts."""
    if not isinstance(value, list):
        return ()
    calls: list[dict[str, object]] = []
    for candidate in value[:_MAX_TOOLS]:
        item = _record(candidate)
        label = _text(item.get("action")).strip()
        if not label or re.search(r"thought|reasoning|analysis|thinking", label, re.I):
            continue
        label = re.sub(r"https?://\S+|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", "[redacted]", label, flags=re.I)
        label = " ".join(label.split())[:120]
        if not label:
            continue
        status = _text(item.get("status"))
        if status not in ("running", "completed", "error", "observed"):
            status = "observed"
        calls.append({
            "id": f"dom-tool-{len(calls)}", "connector": "", "action": label,
            "status": status, "arguments": "", "result": "", "error": "",
        })
    return tuple(calls)


class ToolEventCollector:
    """Deduplicates invocation snapshots and pairs tool results without recording thoughts."""

    def __init__(self) -> None:
        self._calls: dict[str, dict[str, object]] = {}
        self._pending: list[str] = []
        self._results: dict[str, str] = {}
        self._recipients: dict[str, str] = {}

    def observe(self, message: dict[str, object]) -> bool:
        author = _record(message.get("author"))
        role = _text(author.get("role"))
        recipient = _text(message.get("recipient"))
        metadata = _record(message.get("metadata"))
        if metadata.get("is_visually_hidden_from_conversation") is True:
            return False
        if role == "tool":
            self._result(message)
            return True
        if role != "assistant":
            return False
        content = _record(message.get("content"))
        parts = content.get("parts")
        first = parts[0] if isinstance(parts, list) and parts else content.get("text")
        parsed = _record(_decode(first))
        if set(parsed) == {"text"}:
            nested = _record(_decode(parsed["text"]))
            if nested:
                parsed = nested
        app = _record(parsed.get("appContext"))
        invoked = _record(message.get("invoked_resource"))
        path = parsed.get("path")
        action = (
            _text(app.get("actionName")) or _name_from_path(path)
            or _text(parsed.get("tool")).rsplit(".", 1)[-1]
            or recipient.rsplit(".", 1)[-1]
        )
        is_call = (
            parsed.get("type") == "mcpToolCall" or bool(app)
            or (recipient == "api_tool.call_tool" and bool(path))
            or ("arguments" in parsed and bool(action))
            or (recipient not in ("", "all") and isinstance(first, str)
                and content.get("content_type") in ("text", "code"))
        )
        if not is_call or not action or (recipient in ("", "all") and not (
            parsed.get("type") == "mcpToolCall" or bool(app)
        )):
            return False
        identifier = _text(message.get("id")) or f"tool-{len(self._calls)}"
        existing = self._calls.get(identifier)
        if existing is None and len(self._calls) >= _MAX_TOOLS:
            return True
        connector = (
            _text(app.get("appName")) or _text(invoked.get("app_name"))
            or _text(author.get("name")) or _text(parsed.get("tool")).split(".", 1)[0]
            or (_text(path).strip("/").split("/", 1)[0] if path else "")
        )
        if connector.startswith(("asdk_app_", "plugin_", "link_")):
            connector = ""
        if not connector or connector == action:
            connector = recipient.split(".", 1)[0].replace("api_tool", "Tool")
        arguments = parsed.get("arguments", parsed.get("args", parsed or first))
        status = _text(parsed.get("status")) or "running"
        if status not in ("running", "completed", "error", "observed"):
            status = "running"
        result = parsed.get("result")
        if result is not None and status == "running":
            status = "completed"
        if existing is not None and existing.get("status") in ("completed", "error") and status == "running":
            # Replayed invocation snapshots cannot reopen a finished tool.
            status = str(existing["status"])
        entry: dict[str, object] = {
            "id": identifier, "connector": connector[:100], "action": action[:120],
            "status": status[:30], "arguments": _display(arguments),
            "result": _display(result), "error": _display(parsed.get("error"), 2000),
        }
        if existing is not None:
            for field in ("arguments", "result", "error"):
                if not entry[field]:
                    entry[field] = existing[field]
        self._calls[identifier] = entry
        self._recipients[identifier] = recipient
        if status == "running" and identifier not in self._pending:
            self._pending.append(identifier)
        if status != "running" and identifier in self._pending:
            self._pending.remove(identifier)
        return True

    def _result(self, message: dict[str, object]) -> None:
        result_id = _text(message.get("id"))
        known = self._results.get(result_id) if result_id else None
        if not self._pending and known is None:
            return
        invoked = _record(message.get("invoked_resource"))
        action = (_name_from_path(invoked.get("resource_uri"))
                  or _text(_record(message.get("author")).get("name"))).rsplit(".", 1)[-1]
        metadata = _record(message.get("metadata"))
        target = _text(metadata.get("tool_call_id"))
        if target in self._pending:
            action = _text(self._calls[target].get("action"))
        author_name = _text(_record(message.get("author")).get("name"))
        matching = [key for key in self._pending if (
            not action or self._calls[key]["action"] == action
            or (author_name and (self._recipients.get(key) == author_name
                                 or self._recipients.get(key, "").split(".", 1)[0] == author_name))
        )]
        if not matching and known is None:
            return
        key = known or (target if target in matching else matching[0])
        if result_id and len(self._results) < _MAX_TOOLS:
            self._results[result_id] = key
        entry = self._calls[key]
        content = _record(message.get("content"))
        parts = content.get("parts")
        value = parts[0] if isinstance(parts, list) and parts else content.get("text")
        entry["result"] = _display(value)
        entry["status"] = "error" if _record(message.get("metadata")).get("is_error") is True else "completed"
        if key in self._pending:
            self._pending.remove(key)

    def snapshot(self) -> tuple[dict[str, object], ...]:
        return tuple(dict(call) for call in self._calls.values())
