"""Bounded, redacted tool-call summaries from an already observed owned POST stream.

Never capture analysis/reasoning or make independent ChatGPT requests.
"""

from __future__ import annotations

import json
import re
import time
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
            "observed_at": time.time(),
            "id": f"dom-tool-{len(calls)}", "connector": "", "action": label,
            "status": status, "arguments": "", "result": "", "error": "",
        })
    return tuple(calls)


def summarize_stream_tool_calls(
    calls: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    """Keep bounded, redacted invocation inputs and outputs for the activity viewer."""
    summaries: list[dict[str, object]] = []
    for call in calls[:_MAX_TOOLS]:
        identifier = _text(call.get("id"))[:100]
        action = _text(call.get("action"))[:120]
        if not identifier or not action:
            continue
        connector = _text(call.get("connector"))[:100]
        status = _text(call.get("status"))
        summaries.append({
            **({"observed_at": call["observed_at"]} if "observed_at" in call else {}),
            "id": identifier,
            "connector": re.sub(r"https?://\S+|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b",
                                "[redacted]", connector, flags=re.I),
            "action": re.sub(r"https?://\S+|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b",
                             "[redacted]", action, flags=re.I),
            "status": status if status in ("running", "completed", "error", "observed") else "observed",
            "arguments": _display(call.get("arguments")),
            "result": _display(call.get("result")),
            "error": _display(call.get("error"), 2000),
        })
    return tuple(summaries)


def _resource_key(value: object) -> str:
    """Match a link across readable invocation and opaque result resource paths."""
    path = _text(value).strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[-2].startswith("link_"):
        return "/".join(parts[-2:])
    return path


def _connector_name(value: object) -> str:
    """Use a real connector identity, not an opaque app ID or the assistant role."""
    name = _text(value).strip().strip("/")
    if name.startswith("mcp__codex_apps__"):
        name = name.removeprefix("mcp__codex_apps__")
    if not name or name.casefold() in {"assistant", "tool", "api_tool", "call_tool"}:
        return ""
    if name.startswith(("asdk_app_", "plugin_", "link_", "connector_")):
        return ""
    labels = {
        "glass": "Glass",
        "glass_execute_python": "Glass",
        "glass_serena": "Glass Serena",
        "nox": "Nox",
        "nox_python_mcp": "Nox Python MCP",
        "nox_serena": "Nox Serena",
        "pi": "Pi",
        "pi_python_mcp": "Pi Python MCP",
        "patchright_brave": "Patchright Brave",
    }
    return labels.get(name.casefold(), name)


class ToolEventCollector:
    """Deduplicates invocation snapshots and pairs tool results without recording thoughts."""

    def __init__(self) -> None:
        self._calls: dict[str, dict[str, object]] = {}
        self._pending: list[str] = []
        self._results: dict[str, str] = {}
        self._recipients: dict[str, str] = {}
        self._resources: dict[str, str] = {}

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
        if isinstance(first, dict) and first.get("type") == "text":
            first = first.get("text")
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
        tool_name = _text(parsed.get("tool"))
        tool_namespace = (
            tool_name.removesuffix("_" + action)
            if tool_name.startswith("mcp__codex_apps__") and tool_name.endswith("_" + action)
            else tool_name.split(".", 1)[0]
        )
        resource_path = _text(invoked.get("resource_uri")).strip("/")
        path_namespace = _text(path).strip("/").split("/", 1)[0]
        connector = next((name for candidate in (
            app.get("appName"), app.get("displayName"), app.get("name"),
            invoked.get("app_name"), invoked.get("display_name"),
            metadata.get("app_name"), tool_namespace,
            path_namespace, resource_path.split("/", 1)[0], author.get("name"),
        ) if (name := _connector_name(candidate)) and name != action), "")
        if not connector:
            connector = _connector_name(recipient.split(".", 1)[0]) or "Tool"
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
            "observed_at": existing["observed_at"] if existing is not None else time.time(),
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
        if resource := _resource_key(path):
            self._resources[identifier] = resource
        if status == "running" and identifier not in self._pending:
            self._pending.append(identifier)
        if status != "running" and identifier in self._pending:
            self._pending.remove(identifier)
        return True

    def _result(self, message: dict[str, object]) -> None:
        result_id = _text(message.get("id"))
        known = self._results.get(result_id) if result_id else None
        invoked = _record(message.get("invoked_resource"))
        action = (_name_from_path(invoked.get("resource_uri"))
                  or _text(_record(message.get("author")).get("name"))).rsplit(".", 1)[-1]
        metadata = _record(message.get("metadata"))
        target = _text(metadata.get("tool_call_id"))
        if not self._pending and known is None and target not in self._calls:
            return
        if target in self._calls:
            action = _text(self._calls[target].get("action"))
        resource_key = _resource_key(invoked.get("resource_uri"))
        same_resource = [key for key in self._pending if (
            resource_key and self._resources.get(key) == resource_key
        )]
        author_name = _text(_record(message.get("author")).get("name"))
        matching = [key for key in self._pending if (
            not action or self._calls[key]["action"] == action
            or (author_name and (self._recipients.get(key) == author_name
                                 or self._recipients.get(key, "").split(".", 1)[0] == author_name))
        )]
        if not matching and not same_resource and known is None and target not in self._calls:
            return
        if known is not None:
            key = known
        elif target in self._calls:
            key = target
        elif len(same_resource) == 1:
            key = same_resource[0]
        elif len(matching) == 1 and (
            not resource_key or not self._resources.get(matching[0])
            or self._resources[matching[0]] == resource_key
        ):
            key = matching[0]
        else:
            return
        if result_id and len(self._results) < _MAX_TOOLS:
            self._results[result_id] = key
        entry = self._calls[key]
        # Tool result messages can identify the source even when the invocation
        # used an opaque app/link path. Only upgrade the matched invocation:
        # unrelated concurrent calls may use the same action name.
        if not _connector_name(entry.get("connector")):
            resource_path = _text(invoked.get("resource_uri")).strip("/")
            connector = next((name for candidate in (
                invoked.get("app_name"), invoked.get("display_name"),
                metadata.get("app_name"), resource_path.split("/", 1)[0],
            ) if (name := _connector_name(candidate)) and name != action), "")
            if connector:
                entry["connector"] = connector[:100]
        content = _record(message.get("content"))
        parts = content.get("parts")
        value = parts[0] if isinstance(parts, list) and parts else content.get("text")
        if isinstance(value, dict) and value.get("type") == "text":
            value = value.get("text")
        entry["result"] = _display(value)
        entry["status"] = "error" if _record(message.get("metadata")).get("is_error") is True else "completed"
        if key in self._pending:
            self._pending.remove(key)

    def snapshot(self) -> tuple[dict[str, object], ...]:
        return tuple(dict(call) for call in self._calls.values())
