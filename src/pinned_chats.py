from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from .persistence import connect_sqlite, read_legacy_json, remove_legacy_json


def normalize_pinned_ids(values: Iterable[object], *, limit: int = 500) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for value in values:
        chat_id = str(value or "").strip()
        if not chat_id or chat_id in seen:
            continue
        seen.add(chat_id)
        ids.append(chat_id)
        if len(ids) >= limit:
            break
    return ids


def seed_pinned_state(
    initialized: bool,
    current_ids: list[str],
    values: Iterable[object],
    *,
    limit: int = 500,
) -> tuple[bool, list[str], bool]:
    if initialized:
        return initialized, list(current_ids), False
    return True, normalize_pinned_ids(values, limit=limit), True


def set_pinned_state(
    initialized: bool,
    current_ids: list[str],
    chat_id: str,
    pinned: bool,
) -> tuple[bool, list[str], bool]:
    normalized = str(chat_id or "").strip()
    if not normalized:
        raise ValueError("Chat id is required")

    ids = list(current_ids)
    changed = False
    if pinned:
        if normalized not in ids:
            ids.append(normalized)
            changed = True
    elif normalized in ids:
        ids.remove(normalized)
        changed = True

    return True, ids, changed or not initialized


def promote_pinned_state(
    initialized: bool,
    current_ids: list[str],
    previous_id: str,
    next_id: str,
) -> tuple[bool, list[str], bool]:
    previous = str(previous_id or "").strip()
    next_value = str(next_id or "").strip()
    if not previous or not next_value:
        raise ValueError("Both previous and next chat ids are required")

    ids = list(current_ids)
    if previous not in ids or previous == next_value:
        return initialized, ids, False

    previous_index = ids.index(previous)
    ids.remove(previous)
    if next_value not in ids:
        ids.insert(previous_index, next_value)
    return True, ids, True


class PinnedChatStore:
    """Persist UI pin state in SQLite independently of any one browser profile."""

    _LIMIT = 500

    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "ui-pinned-chats.sqlite3"
        self.legacy_path = state_dir / "ui-pinned-chats.json"
        self.lock = threading.Lock()
        self._initialize()
        self._migrate_legacy()
        self._initialized, self._ids = self._load()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pinned_chats (
                    position INTEGER PRIMARY KEY,
                    chat_id TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS pinned_chat_metadata (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                );
                """
            )

    @classmethod
    def _normalize(cls, values: Iterable[object]) -> list[str]:
        return normalize_pinned_ids(values, limit=cls._LIMIT)

    def _migrate_legacy(self) -> None:
        payload = read_legacy_json(self.legacy_path)
        if payload is None:
            return
        raw_ids = payload.get("ids") if isinstance(payload, dict) else None
        ids = self._normalize(raw_ids if isinstance(raw_ids, list) else [])
        with self._connect() as connection:
            initialized = connection.execute(
                "SELECT value FROM pinned_chat_metadata WHERE key = 'initialized'"
            ).fetchone()
            if initialized is None:
                connection.executemany(
                    "INSERT INTO pinned_chats(position, chat_id) VALUES (?, ?)",
                    list(enumerate(ids)),
                )
                connection.execute(
                    "INSERT INTO pinned_chat_metadata(key, value) VALUES ('initialized', 1)"
                )
        remove_legacy_json(self.legacy_path)

    def _load(self) -> tuple[bool, list[str]]:
        with self._connect() as connection:
            initialized = connection.execute(
                "SELECT value FROM pinned_chat_metadata WHERE key = 'initialized'"
            ).fetchone()
            rows = connection.execute(
                "SELECT chat_id FROM pinned_chats ORDER BY position"
            ).fetchall()
        return initialized is not None and bool(initialized["value"]), [
            str(row["chat_id"]) for row in rows
        ]

    def _write_locked(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM pinned_chats")
            connection.executemany(
                "INSERT INTO pinned_chats(position, chat_id) VALUES (?, ?)",
                list(enumerate(self._ids)),
            )
            connection.execute(
                """
                INSERT INTO pinned_chat_metadata(key, value)
                VALUES ('initialized', 1)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return {"initialized": self._initialized, "ids": list(self._ids)}

    def seed(self, values: Iterable[object]) -> dict[str, object]:
        with self.lock:
            initialized, ids, should_write = seed_pinned_state(
                self._initialized,
                self._ids,
                values,
                limit=self._LIMIT,
            )
            self._initialized = initialized
            self._ids = ids
            if should_write:
                self._write_locked()
            return {"initialized": self._initialized, "ids": list(self._ids)}

    def set_pinned(self, chat_id: str, pinned: bool) -> dict[str, object]:
        with self.lock:
            initialized, ids, should_write = set_pinned_state(
                self._initialized,
                self._ids,
                chat_id,
                pinned,
            )
            self._initialized = initialized
            self._ids = ids
            if should_write:
                self._write_locked()
            return {"initialized": self._initialized, "ids": list(self._ids)}

    def promote(self, previous_id: str, next_id: str) -> dict[str, object]:
        with self.lock:
            initialized, ids, should_write = promote_pinned_state(
                self._initialized,
                self._ids,
                previous_id,
                next_id,
            )
            self._initialized = initialized
            self._ids = ids
            if should_write:
                self._write_locked()
            return {"initialized": self._initialized, "ids": list(self._ids)}
