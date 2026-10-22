from __future__ import annotations

import os
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

OWNED_WINDOW_PREFIX = "prompta:"
MAX_OWNED_TAB_AGE_SECONDS = 45 * 60
OWNED_TAB_LEDGER = Path.home() / ".local/state/prompta/owned-tabs.sqlite3"


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


def _tab_ledger(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=2.0)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS owned_tabs (target_id TEXT PRIMARY KEY, opened_at REAL NOT NULL)"
    )
    return connection


def record_owned_tab(target_id: str, opened_at: float, path: Path = OWNED_TAB_LEDGER) -> None:
    with closing(_tab_ledger(path)) as connection, connection:
        connection.execute(
            "INSERT INTO owned_tabs (target_id, opened_at) VALUES (?, ?) "
            "ON CONFLICT(target_id) DO UPDATE SET opened_at = min(opened_at, excluded.opened_at)",
            (target_id, opened_at),
        )


def owned_tab_records(path: Path = OWNED_TAB_LEDGER) -> dict[str, float]:
    if not path.exists():
        return {}
    with closing(_tab_ledger(path)) as connection, connection:
        return {
            target: float(opened_at)
            for target, opened_at in connection.execute(
                "SELECT target_id, opened_at FROM owned_tabs"
            )
        }


def forget_owned_tabs(target_ids: set[str], path: Path = OWNED_TAB_LEDGER) -> None:
    if not target_ids or not path.exists():
        return
    with closing(_tab_ledger(path)) as connection, connection:
        connection.executemany(
            "DELETE FROM owned_tabs WHERE target_id = ?", ((target_id,) for target_id in target_ids)
        )
