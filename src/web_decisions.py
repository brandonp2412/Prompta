from __future__ import annotations

import math
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs


def query_limit(
    query: dict[str, list[str]],
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        value = int(query.get("limit", [str(default)])[0])
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def parse_query(raw_query: str) -> dict[str, list[str]]:
    return parse_qs(raw_query)


def schedule_every_request(payload: dict[str, Any]) -> tuple[str, float]:
    prompt = str(payload.get("prompt") or "").strip()
    try:
        interval_minutes = float(str(payload.get("interval_minutes") or ""))
    except (TypeError, ValueError):
        interval_minutes = 0.0
    if not prompt:
        raise ValueError("Schedule prompt is empty")
    if not math.isfinite(interval_minutes) or interval_minutes <= 0:
        raise ValueError("Schedule interval must be a finite value greater than zero")
    return prompt, interval_minutes


def schedule_at_request(payload: dict[str, Any], *, now: float) -> tuple[str, float]:
    prompt = str(payload.get("prompt") or "").strip()
    try:
        run_at_epoch = float(str(payload.get("run_at_epoch") or ""))
    except (TypeError, ValueError):
        run_at_epoch = 0.0
    if not prompt:
        raise ValueError("Schedule prompt is empty")
    if not math.isfinite(run_at_epoch) or run_at_epoch <= now:
        raise ValueError("Schedule time must be a finite timestamp in the future")
    return prompt, run_at_epoch


def schedule_response(result: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
    status = HTTPStatus.CREATED if result.get("created") is not False else HTTPStatus.OK
    return status, {"ok": True, **result}


def one_time_schedule_response(result: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
    return HTTPStatus.CREATED, {"ok": True, **result}


def required_boolean(
    payload: dict[str, Any],
    key: str,
    *,
    error: str,
) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(error)
    return value


def pin_seed_ids(payload: dict[str, Any]) -> list[object]:
    values = payload.get("ids")
    if not isinstance(values, list):
        raise ValueError("Expected ids to be a list")
    return values


def pin_update_request(payload: dict[str, Any]) -> tuple[str, bool]:
    chat_id = str(payload.get("id") or "").strip()
    pinned = required_boolean(
        payload,
        "pinned",
        error="Expected pinned to be a boolean",
    )
    return chat_id, pinned


def pin_promote_request(payload: dict[str, Any]) -> tuple[str, str]:
    return (
        str(payload.get("from") or "").strip(),
        str(payload.get("to") or "").strip(),
    )


def resource_id(path: str, prefix: str, suffix: str = "") -> str | None:
    if not path.startswith(prefix):
        return None
    if suffix and not path.endswith(suffix):
        return None
    end = -len(suffix) if suffix else None
    return path[len(prefix) : end].strip("/")


def send_operation(*, reply: bool, track_response: bool) -> str:
    if reply:
        return "reply_tracked" if track_response else "reply"
    return "once_tracked" if track_response else "once"
