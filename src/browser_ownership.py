from __future__ import annotations

import os
import time
import uuid

OWNED_WINDOW_PREFIX = "prompta:"


def new_page_owner_id() -> str:
    return f"{os.getpid()}-{uuid.uuid4().hex}"


def new_owned_window_marker(
    *,
    now: float | None = None,
    prefix: str = OWNED_WINDOW_PREFIX,
    owner_id: str | None = None,
) -> str:
    stamp = int(time.time() if now is None else now)
    owner = owner_id or new_page_owner_id()
    return f"{prefix}{stamp}:{owner}:{uuid.uuid4().hex}"


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


def owned_window_owner_id(
    value: object,
    *,
    prefix: str = OWNED_WINDOW_PREFIX,
) -> str | None:
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    parts = value[len(prefix) :].split(":")
    if len(parts) < 3:
        return None
    owner_id = parts[1].strip()
    return owner_id or None


def owned_window_owner_alive(owner_id: str) -> bool:
    pid_text = owner_id.split("-", 1)[0]
    try:
        pid = int(pid_text)
    except ValueError:
        return True
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
