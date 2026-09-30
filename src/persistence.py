from __future__ import annotations

import sqlite3
from pathlib import Path

STATE_DIR = Path.home() / ".local" / "state" / "prompta"
DEFAULT_RUNTIME_PATH = STATE_DIR / "runtime.sqlite3"


def connect_sqlite(path: Path, *, timeout: float = 5.0) -> sqlite3.Connection:
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=timeout)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(f"PRAGMA busy_timeout={max(1, int(timeout * 1000))}")
    return connection
