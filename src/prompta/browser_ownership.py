from __future__ import annotations

import time
import uuid

OWNED_WINDOW_PREFIX = "prompta:"


def new_owned_window_marker(*, now: float | None = None) -> str:
    stamp = int(time.time() if now is None else now)
    return f"{OWNED_WINDOW_PREFIX}{stamp}:{uuid.uuid4().hex}"


def owned_window_started_at(value: object) -> int | None:
    if not isinstance(value, str) or not value.startswith(OWNED_WINDOW_PREFIX):
        return None
    stamp = value[len(OWNED_WINDOW_PREFIX) :].split(":", 1)[0]
    try:
        return int(stamp)
    except ValueError:
        return None
