"""SQLite-backed passive cache for Prompta ChatGPT conversations."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CACHE_PATH = Path.home() / ".local" / "state" / "prompta" / "chats.sqlite3"
_SEEDED_PROMPT_KEY = "__prompta_prompt__"


@dataclass
class ActiveConversation:
    conversation_id: str
    context_id: str
    job_name: str
    prompt: str
    last_digest: str = ""
    idle_polls: int = 0
    settled_at: float = 0.0


class ChatCache:
    """Small WAL-mode database designed for one writer and concurrent UI readers."""

    def __init__(self, path: Path = DEFAULT_CACHE_PATH) -> None:
        self.path = path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        self.connection = sqlite3.connect(self.path)
        os.chmod(self.path, 0o600)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                job_name TEXT NOT NULL DEFAULT '',
                prompt TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL,
                browser_context_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                completed_at REAL
            );

            CREATE INDEX IF NOT EXISTS conversations_status_updated_idx
                ON conversations(status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS messages (
                conversation_id TEXT NOT NULL,
                message_key TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (conversation_id, message_key),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS messages_conversation_ordinal_idx
                ON messages(conversation_id, ordinal);
            """
        )
        self.connection.execute(
            """
            INSERT INTO messages (
                conversation_id, message_key, ordinal, role, content, status,
                created_at, updated_at
            )
            SELECT c.id, ?, 0, 'user', c.prompt, 'complete', c.created_at, c.updated_at
            FROM conversations c
            WHERE TRIM(c.prompt) <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM messages m WHERE m.conversation_id = c.id
              )
            """,
            (_SEEDED_PROMPT_KEY,),
        )
        self.connection.commit()

    def mark_orphaned_active(self) -> int:
        """Mark tabs from a previous Prompta process as interrupted after restart."""

        now = time.time()
        cursor = self.connection.execute(
            """
            UPDATE conversations
            SET status = 'interrupted', updated_at = ?, completed_at = COALESCE(completed_at, ?)
            WHERE status = 'active'
            """,
            (now, now),
        )
        self.connection.commit()
        return cursor.rowcount

    def start(
        self,
        conversation_id: str,
        *,
        context_id: str,
        job_name: str,
        prompt: str,
    ) -> None:
        now = time.time()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO conversations (
                    id, job_name, prompt, url, browser_context_id, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    job_name = excluded.job_name,
                    prompt = excluded.prompt,
                    url = excluded.url,
                    browser_context_id = excluded.browser_context_id,
                    status = 'active',
                    updated_at = excluded.updated_at,
                    completed_at = NULL
                """,
                (
                    conversation_id,
                    job_name,
                    prompt,
                    f"https://chatgpt.com/c/{conversation_id}",
                    context_id,
                    now,
                    now,
                ),
            )
            if prompt.strip():
                self.connection.execute(
                    """
                    INSERT INTO messages (
                        conversation_id, message_key, ordinal, role, content, status,
                        created_at, updated_at
                    )
                    SELECT ?, ?, 0, 'user', ?, 'complete', ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM messages WHERE conversation_id = ?
                    )
                    """,
                    (
                        conversation_id,
                        _SEEDED_PROMPT_KEY,
                        prompt,
                        now,
                        now,
                        conversation_id,
                    ),
                )

    def metadata(self, conversation_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT id, job_name, prompt, url
            FROM conversations
            WHERE id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown cached conversation: {conversation_id}")
        return dict(row)

    def resume(self, conversation_id: str, *, context_id: str) -> dict[str, Any]:
        """Mark an existing cached conversation active in a live browser context."""

        row = self.connection.execute(
            """
            SELECT id, job_name, prompt, url
            FROM conversations
            WHERE id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown cached conversation: {conversation_id}")
        now = time.time()
        with self.connection:
            self.connection.execute(
                """
                UPDATE conversations
                SET browser_context_id = ?, status = 'active', updated_at = ?, completed_at = NULL
                WHERE id = ?
                """,
                (context_id, now, conversation_id),
            )
        return dict(row)

    @staticmethod
    def digest(snapshot: dict[str, Any]) -> str:
        stable = {
            "title": str(snapshot.get("title") or ""),
            "path": str(snapshot.get("path") or ""),
            "streaming": bool(snapshot.get("streaming")),
            "messages": snapshot.get("messages") or [],
        }
        return hashlib.sha256(
            json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def mark_interrupted(self, conversation_id: str) -> None:
        now = time.time()
        self.connection.execute(
            """
            UPDATE conversations
            SET status = 'interrupted', updated_at = ?, completed_at = COALESCE(completed_at, ?)
            WHERE id = ?
            """,
            (now, now, conversation_id),
        )
        self.connection.commit()

    def write_snapshot(
        self,
        conversation_id: str,
        snapshot: dict[str, Any],
        *,
        complete: bool = False,
    ) -> None:
        now = time.time()
        messages = snapshot.get("messages")
        if not isinstance(messages, list):
            messages = []
        status = "complete" if complete else "active"
        completed_at = now if complete else None
        snapshot_path = str(snapshot.get("path") or "")
        snapshot_url = (
            f"https://chatgpt.com{snapshot_path}" if snapshot_path.startswith("/c/") else ""
        )
        existing_rows = self.connection.execute(
            """
            SELECT message_key, ordinal, role, content, status, created_at, updated_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY ordinal, created_at
            """,
            (conversation_id,),
        ).fetchall()
        existing_by_key = {str(row["message_key"]): dict(row) for row in existing_rows}
        existing_history = [
            dict(row) for row in existing_rows if str(row["message_key"]) != _SEEDED_PROMPT_KEY
        ]

        incoming: list[tuple[int, str, str, str]] = []
        for snapshot_index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "")
            content = str(message.get("content") or "")
            raw_key = str(message.get("id") or "")
            message_key = raw_key or f"{role}:{snapshot_index}"
            incoming.append((snapshot_index, role, content, message_key))

        first_incoming = incoming[0] if incoming else None
        first_existing = existing_history[0] if existing_history else None
        snapshot_is_full = first_existing is None
        if first_incoming is not None and first_existing is not None:
            _, incoming_role, incoming_content, incoming_key = first_incoming
            snapshot_is_full = incoming_key == str(first_existing["message_key"]) or (
                incoming_role == str(first_existing["role"])
                and incoming_content.strip() == str(first_existing["content"]).strip()
            )

        max_existing_ordinal = max(
            (int(row["ordinal"]) for row in existing_rows),
            default=-1,
        )
        next_partial_ordinal = max_existing_ordinal + 1
        snapshot_keys: list[str] = []
        current_by_key = dict(existing_by_key)

        with self.connection:
            self.connection.execute(
                """
                UPDATE conversations
                SET title = ?, status = ?, updated_at = ?,
                    completed_at = CASE WHEN ? THEN ? ELSE NULL END,
                    url = CASE WHEN ? != '' THEN ? ELSE url END
                WHERE id = ?
                """,
                (
                    str(snapshot.get("title") or ""),
                    status,
                    now,
                    int(complete),
                    completed_at,
                    snapshot_url,
                    snapshot_url,
                    conversation_id,
                ),
            )

            preceding_user_key = ""
            for snapshot_index, role, content, raw_message_key in incoming:
                message_key = raw_message_key
                if (
                    role == "assistant"
                    and message_key.startswith("__prompta_live_assistant_")
                    and message_key not in current_by_key
                    and preceding_user_key in current_by_key
                ):
                    preceding_user = current_by_key[preceding_user_key]
                    target_ordinal = int(preceding_user["ordinal"]) + 1
                    for candidate_key, candidate in current_by_key.items():
                        if candidate_key.startswith("__prompta_live_assistant_"):
                            continue
                        if str(candidate["role"]) != "assistant":
                            continue
                        if int(candidate["ordinal"]) != target_ordinal:
                            continue
                        candidate_content = str(candidate["content"] or "").strip()
                        incoming_content = content.strip()
                        if (
                            candidate_content
                            and incoming_content
                            and (
                                candidate_content == incoming_content
                                or candidate_content.startswith(incoming_content)
                                or incoming_content.startswith(candidate_content)
                            )
                        ):
                            message_key = candidate_key
                            break

                existing = current_by_key.get(message_key)
                if snapshot_is_full:
                    ordinal = snapshot_index
                elif existing is not None:
                    ordinal = int(existing["ordinal"])
                else:
                    ordinal = next_partial_ordinal
                    next_partial_ordinal += 1

                snapshot_keys.append(message_key)
                message_status = (
                    "streaming"
                    if not complete
                    and bool(snapshot.get("streaming"))
                    and snapshot_index == len(messages) - 1
                    and role == "assistant"
                    else "complete"
                )
                self.connection.execute(
                    """
                    INSERT INTO messages (
                        conversation_id, message_key, ordinal, role, content, status,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(conversation_id, message_key) DO UPDATE SET
                        ordinal = excluded.ordinal,
                        role = excluded.role,
                        content = excluded.content,
                        status = excluded.status,
                        updated_at = excluded.updated_at
                    """,
                    (
                        conversation_id,
                        message_key,
                        ordinal,
                        role,
                        content,
                        message_status,
                        now,
                        now,
                    ),
                )
                created_at = float(existing["created_at"]) if existing is not None else now
                current_by_key[message_key] = {
                    "message_key": message_key,
                    "ordinal": ordinal,
                    "role": role,
                    "content": content,
                    "status": message_status,
                    "created_at": created_at,
                    "updated_at": now,
                }
                if role == "user":
                    preceding_user_key = message_key

            if snapshot_keys:
                unique_keys = list(dict.fromkeys(snapshot_keys))
                snapshot_user_contents = {
                    content.strip()
                    for _, role, content, _ in incoming
                    if role == "user" and content.strip()
                }
                if snapshot_user_contents:
                    self.connection.execute(
                        """
                        DELETE FROM messages
                        WHERE conversation_id = ?
                          AND message_key = ?
                        """,
                        (conversation_id, _SEEDED_PROMPT_KEY),
                    )

                current_assistants = [
                    content.strip()
                    for _, role, content, _ in incoming
                    if role == "assistant" and content.strip()
                ]
                transient_rows = self.connection.execute(
                    """
                    SELECT message_key, content
                    FROM messages
                    WHERE conversation_id = ?
                      AND message_key LIKE '__prompta_live_assistant_%'
                    """,
                    (conversation_id,),
                ).fetchall()
                for row in transient_rows:
                    transient_key = str(row["message_key"])
                    if transient_key in unique_keys:
                        continue
                    transient_content = str(row["content"] or "").strip()
                    superseded = any(
                        candidate == transient_content
                        or candidate.startswith(transient_content)
                        or transient_content.startswith(candidate)
                        for candidate in current_assistants
                    )
                    if snapshot_is_full and (complete or superseded):
                        self.connection.execute(
                            """
                            DELETE FROM messages
                            WHERE conversation_id = ?
                              AND message_key = ?
                            """,
                            (conversation_id, transient_key),
                        )

    def recent_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, job_name, url, title, status, created_at, updated_at, completed_at
            FROM conversations
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
        return [dict(row) for row in rows]

    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT message_key, ordinal, role, content, status, created_at, updated_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY ordinal
            """,
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.connection.close()
