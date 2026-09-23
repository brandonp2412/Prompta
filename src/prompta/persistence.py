from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

STATE_DIR = Path.home() / ".local" / "state" / "prompta"
DEFAULT_RUNTIME_PATH = STATE_DIR / "runtime.sqlite3"
LEGACY_JOBS_PATH = Path.home() / ".config" / "prompta" / "jobs.json"
LEGACY_STATE_PATH = STATE_DIR / "state.json"

_SQLITE_HEADER = b"SQLite format 3\x00"


def is_sqlite_file(path: Path) -> bool:
    target = path.expanduser()
    try:
        with target.open("rb") as handle:
            return handle.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER
    except FileNotFoundError:
        return False
    except OSError:
        return False


def read_legacy_json(path: Path) -> Any | None:
    target = path.expanduser()
    if not target.is_file() or is_sqlite_file(target):
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def connect_sqlite(path: Path, *, timeout: float = 5.0) -> sqlite3.Connection:
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=timeout)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(f"PRAGMA busy_timeout={max(1, int(timeout * 1000))}")
    return connection


def remove_legacy_json(path: Path) -> None:
    target = path.expanduser()
    if target.is_file() and not is_sqlite_file(target):
        target.unlink(missing_ok=True)
