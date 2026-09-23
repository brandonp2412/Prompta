from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from .persistence import connect_sqlite, read_legacy_json, remove_legacy_json


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
        ids: list[str] = []
        seen: set[str] = set()
        for value in values:
            chat_id = str(value or "").strip()
            if not chat_id or chat_id in seen:
                continue
            seen.add(chat_id)
            ids.append(chat_id)
            if len(ids) >= cls._LIMIT:
                break
        return ids

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
            if not self._initialized:
                self._ids = self._normalize(values)
                self._initialized = True
                self._write_locked()
            return {"initialized": self._initialized, "ids": list(self._ids)}

    def set_pinned(self, chat_id: str, pinned: bool) -> dict[str, object]:
        normalized = str(chat_id or "").strip()
        if not normalized:
            raise ValueError("Chat id is required")

        with self.lock:
            changed = False
            if pinned:
                if normalized not in self._ids:
                    self._ids.append(normalized)
                    changed = True
            elif normalized in self._ids:
                self._ids.remove(normalized)
                changed = True

            if changed or not self._initialized:
                self._initialized = True
                self._write_locked()

            return {"initialized": self._initialized, "ids": list(self._ids)}

    def promote(self, previous_id: str, next_id: str) -> dict[str, object]:
        previous = str(previous_id or "").strip()
        next_value = str(next_id or "").strip()
        if not previous or not next_value:
            raise ValueError("Both previous and next chat ids are required")

        with self.lock:
            if previous in self._ids and previous != next_value:
                previous_index = self._ids.index(previous)
                self._ids.remove(previous)
                if next_value not in self._ids:
                    self._ids.insert(previous_index, next_value)
                self._initialized = True
                self._write_locked()

            return {"initialized": self._initialized, "ids": list(self._ids)}
