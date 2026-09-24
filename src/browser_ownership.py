from __future__ import annotations

import time
import uuid

OWNED_WINDOW_PREFIX = "prompta:"


def new_owned_window_marker(
    *,
    now: float | None = None,
    prefix: str = OWNED_WINDOW_PREFIX,
) -> str:
    stamp = int(time.time() if now is None else now)
    return f"{prefix}{stamp}:{uuid.uuid4().hex}"


def owned_window_started_at(
    value: object,
    *,
    prefix: str = OWNED_WINDOW_PREFIX,
) -> int | None:
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    stamp = value[len(prefix) :].split(":", 1)[0]
    try:
        return int(stamp)
    except ValueError:
        return None
