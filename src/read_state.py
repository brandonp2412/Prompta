from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


class ConversationReadState:
    """Persist per-conversation read markers shared by every Prompta UI client."""

    def __init__(
        self,
        state_dir: Path,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = state_dir / "ui-conversation-state.sqlite3"
        self.clock = clock
        self.lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self.lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS read_state (
                    conversation_id TEXT PRIMARY KEY,
                    read_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value REAL NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO metadata(key, value) VALUES ('initialized_at', ?)",
                (float(self.clock()),),
            )

    def mark_read(self, conversation_id: str) -> dict[str, object]:
        chat_id = str(conversation_id or "").strip()
        if not chat_id:
            raise ValueError("Conversation id is required")

        read_at = float(self.clock())
        with self.lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO read_state(conversation_id, read_at)
                VALUES (?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET read_at = excluded.read_at
                """,
                (chat_id, read_at),
            )
        return {"ok": True, "id": chat_id, "read_at": read_at}

    def mark_all_read(self) -> dict[str, object]:
        read_at = float(self.clock())
        with self.lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO metadata(key, value)
                VALUES ('all_read_at', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (read_at,),
            )
        return {"ok": True, "read_at": read_at}

    def decorate(self, conversations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = [dict(chat) for chat in conversations]
        ids = [str(chat.get("id") or "").strip() for chat in rows]
        ids = [chat_id for chat_id in ids if chat_id]

        with self.lock, self._connect() as connection:
            baseline_row = connection.execute(
                "SELECT MAX(value) AS value FROM metadata WHERE key IN ('initialized_at', 'all_read_at')"
            ).fetchone()
            baseline_value = baseline_row["value"] if baseline_row is not None else None
            baseline = float(baseline_value if baseline_value is not None else self.clock())
            read_at: dict[str, float] = {}
            if ids:
                placeholders = ", ".join("?" for _ in ids)
                for row in connection.execute(
                    f"SELECT conversation_id, read_at FROM read_state WHERE conversation_id IN ({placeholders})",
                    ids,
                ):
                    read_at[str(row["conversation_id"])] = float(row["read_at"])

        for chat in rows:
            chat_id = str(chat.get("id") or "").strip()
            try:
                last_assistant_at = float(chat.get("last_assistant_at") or 0.0)
            except (TypeError, ValueError):
                last_assistant_at = 0.0
            chat["unread"] = last_assistant_at > max(baseline, read_at.get(chat_id, baseline))

        return rows
