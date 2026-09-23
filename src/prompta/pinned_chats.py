from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from pathlib import Path

from .metadata_store import (
    UI_METADATA_DB,
    import_recorded,
    metadata_connection,
    record_import,
)


class PinnedChatStore:
    """Persist UI pin state independently of any one browser profile."""

    _LIMIT = 500
    _LEGACY_IMPORT = "ui-pinned-chats-json"

    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / UI_METADATA_DB
        self.legacy_path = state_dir / "ui-pinned-chats.json"
        self.lock = threading.Lock()
        self._migrate()
        self._import_legacy_json()
        self._initialized, self._ids = self._load()

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

    def _migrate(self) -> None:
        with metadata_connection(self.path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pinned_chat_state (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    initialized INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pinned_chats (
                    chat_id TEXT PRIMARY KEY,
                    position INTEGER NOT NULL UNIQUE
                );
                """
            )

    def _import_legacy_json(self) -> None:
        try:
            payload = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        raw_ids = payload.get("ids")
        if not isinstance(raw_ids, list):
            return

        ids = self._normalize(raw_ids)
        imported = False
        with metadata_connection(self.path) as connection:
            if not import_recorded(connection, self._LEGACY_IMPORT):
                state = connection.execute(
                    "SELECT initialized FROM pinned_chat_state WHERE singleton = 1"
                ).fetchone()
                if state is None:
                    connection.execute(
                        """
                        INSERT INTO pinned_chat_state(singleton, initialized)
                        VALUES (1, 1)
                        """
                    )
                    connection.executemany(
                        """
                        INSERT INTO pinned_chats(chat_id, position)
                        VALUES (?, ?)
                        """,
                        [(chat_id, position) for position, chat_id in enumerate(ids)],
                    )
                record_import(connection, self._LEGACY_IMPORT)
            imported = import_recorded(connection, self._LEGACY_IMPORT)
        if imported:
            try:
                self.legacy_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _load(self) -> tuple[bool, list[str]]:
        with metadata_connection(self.path) as connection:
            state = connection.execute(
                "SELECT initialized FROM pinned_chat_state WHERE singleton = 1"
            ).fetchone()
            rows = connection.execute(
                "SELECT chat_id FROM pinned_chats ORDER BY position"
            ).fetchall()
        initialized = bool(state["initialized"]) if state is not None else False
        return initialized, [str(row["chat_id"]) for row in rows]

    def _write_locked(self) -> None:
        with metadata_connection(self.path) as connection:
            connection.execute(
                """
                INSERT INTO pinned_chat_state(singleton, initialized)
                VALUES (1, ?)
                ON CONFLICT(singleton) DO UPDATE SET initialized = excluded.initialized
                """,
                (int(self._initialized),),
            )
            connection.execute("DELETE FROM pinned_chats")
            connection.executemany(
                """
                INSERT INTO pinned_chats(chat_id, position)
                VALUES (?, ?)
                """,
                [(chat_id, position) for position, chat_id in enumerate(self._ids)],
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
