"""SQLite-backed passive cache for Prompta ChatGPT conversations."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CACHE_PATH = Path.home() / ".local" / "state" / "prompta" / "chats.sqlite3"
_SEEDED_PROMPT_KEY = "__prompta_prompt__"

logger = logging.getLogger(__name__)


@dataclass
class ActiveConversation:
    conversation_id: str
    context_id: str
    job_name: str
    prompt: str
    last_digest: str = ""
    idle_polls: int = 0
    settled_at: float = 0.0
    last_live_snapshot_at: float = 0.0


class ChatCache:
    """Small WAL-mode database designed for one writer and concurrent UI readers."""

    def __init__(self, path: Path = DEFAULT_CACHE_PATH) -> None:
        self.path = path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        if self._database_header_is_invalid():
            archived = self._quarantine_corrupt_database()
            logger.error(
                "Prompta cache header was invalid; archived it at %s and created a fresh cache",
                archived,
            )
        self.connection = self._open_connection()
        try:
            self._configure_connection()
            self._migrate()
        except sqlite3.DatabaseError as error:
            try:
                self.connection.close()
            except sqlite3.Error:
                pass
            if not self._is_corruption_error(error):
                raise
            archived = self._quarantine_corrupt_database()
            logger.error(
                "Prompta cache was corrupt; archived it at %s and created a fresh cache",
                archived,
            )
            self.connection = self._open_connection()
            self._configure_connection()
            self._migrate()

    def _database_header_is_invalid(self) -> bool:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return False
        with self.path.open("rb") as database:
            return database.read(16) != b"SQLite format 3\x00"

    def _open_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        os.chmod(self.path, 0o600)
        connection.row_factory = sqlite3.Row
        return connection

    def _configure_connection(self) -> None:
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")

    @staticmethod
    def _is_corruption_error(exc: sqlite3.DatabaseError) -> bool:
        error_code = getattr(exc, "sqlite_errorcode", None)
        if isinstance(error_code, int) and (error_code & 0xFF) in {
            sqlite3.SQLITE_CORRUPT,
            sqlite3.SQLITE_NOTADB,
        }:
            return True
        message = str(exc).casefold()
        return any(
            marker in message
            for marker in (
                "database disk image is malformed",
                "file is not a database",
                "database corruption",
            )
        )

    def _quarantine_corrupt_database(self) -> Path:
        timestamp = int(time.time())
        quarantine = self.path.with_name(f"{self.path.name}.corrupt-{timestamp}")
        sequence = 0
        while any(
            candidate.exists()
            for candidate in (
                quarantine,
                Path(f"{quarantine}-wal"),
                Path(f"{quarantine}-shm"),
            )
        ):
            sequence += 1
            quarantine = self.path.with_name(
                f"{self.path.name}.corrupt-{timestamp}-{sequence}"
            )

        for suffix in ("", "-wal", "-shm"):
            source = Path(f"{self.path}{suffix}")
            if source.exists():
                source.replace(Path(f"{quarantine}{suffix}"))
        return quarantine

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

            CREATE TRIGGER IF NOT EXISTS messages_remove_superseded_transient_after_insert
            AFTER INSERT ON messages
            WHEN NEW.role = 'assistant'
            BEGIN
                DELETE FROM messages
                WHERE rowid IN (
                    SELECT transient.rowid
                    FROM messages transient
                    WHERE transient.conversation_id = NEW.conversation_id
                      AND transient.role = 'assistant'
                      AND transient.message_key LIKE '__prompta_live_assistant_%'
                      AND EXISTS (
                          SELECT 1
                          FROM messages canonical
                          WHERE canonical.conversation_id = transient.conversation_id
                            AND canonical.role = 'assistant'
                            AND canonical.message_key NOT LIKE '__prompta_live_assistant_%'
                            AND canonical.message_key NOT LIKE 'request-placeholder-%'
                            AND canonical.ordinal > COALESCE((
                                SELECT MAX(previous_user.ordinal)
                                FROM messages previous_user
                                WHERE previous_user.conversation_id = transient.conversation_id
                                  AND previous_user.role = 'user'
                                  AND previous_user.ordinal < transient.ordinal
                            ), -1)
                            AND canonical.ordinal < COALESCE((
                                SELECT MIN(next_user.ordinal)
                                FROM messages next_user
                                WHERE next_user.conversation_id = transient.conversation_id
                                  AND next_user.role = 'user'
                                  AND next_user.ordinal > transient.ordinal
                            ), 2147483647)
                      )
                );
            END;
            """
        )
        self.connection.execute(
            """
            DELETE FROM messages
            WHERE message_key LIKE 'request-placeholder-%'
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
        self.connection.execute(
            """
            DELETE FROM messages
            WHERE message_key = ?
              AND EXISTS (
                SELECT 1
                FROM messages actual
                WHERE actual.conversation_id = messages.conversation_id
                  AND actual.role = 'user'
                  AND actual.message_key != ?
              )
            """,
            (_SEEDED_PROMPT_KEY, _SEEDED_PROMPT_KEY),
        )
        self._remove_superseded_transient_assistants()
        self.connection.commit()

    def _remove_superseded_transient_assistants(
        self,
        conversation_id: str | None = None,
    ) -> int:
        parameters: tuple[Any, ...] = ()
        conversation_filter = ""
        if conversation_id is not None:
            conversation_filter = "AND transient.conversation_id = ?"
            parameters = (conversation_id,)
        cursor = self.connection.execute(
            f"""
            DELETE FROM messages
            WHERE rowid IN (
                SELECT transient.rowid
                FROM messages transient
                WHERE transient.role = 'assistant'
                  {conversation_filter}
                  AND (
                    (
                      transient.status = 'streaming'
                      AND EXISTS (
                        SELECT 1
                        FROM messages canonical
                        WHERE canonical.conversation_id = transient.conversation_id
                          AND canonical.role = 'assistant'
                          AND canonical.status = 'complete'
                          AND canonical.rowid != transient.rowid
                          AND canonical.ordinal = transient.ordinal
                      )
                    )
                    OR (
                      transient.message_key LIKE '__prompta_live_assistant_%'
                      AND EXISTS (
                        SELECT 1
                        FROM messages canonical
                        WHERE canonical.conversation_id = transient.conversation_id
                          AND canonical.role = 'assistant'
                          AND canonical.message_key NOT LIKE '__prompta_live_assistant_%'
                          AND canonical.message_key NOT LIKE 'request-placeholder-%'
                          AND canonical.ordinal > COALESCE((
                              SELECT MAX(previous_user.ordinal)
                              FROM messages previous_user
                              WHERE previous_user.conversation_id = transient.conversation_id
                                AND previous_user.role = 'user'
                                AND previous_user.ordinal < transient.ordinal
                          ), -1)
                          AND canonical.ordinal < COALESCE((
                              SELECT MIN(next_user.ordinal)
                              FROM messages next_user
                              WHERE next_user.conversation_id = transient.conversation_id
                                AND next_user.role = 'user'
                                AND next_user.ordinal > transient.ordinal
                          ), 2147483647)
                      )
                    )
                  )
            )
            """,
            parameters,
        )
        return cursor.rowcount

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
            SELECT id, job_name, prompt, url, status
            FROM conversations
            WHERE id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown cached conversation: {conversation_id}")
        return dict(row)

    def status(self, conversation_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT status FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        return str(row["status"]) if row is not None else None

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
            if role == "assistant" and message_key.startswith("request-placeholder-"):
                continue
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

        # ChatGPT virtualizes older turns. A DOM snapshot can begin at the first
        # cached message while still omitting a stable message in the middle.
        # Treat that as partial; otherwise snapshot indexes can reuse occupied
        # ordinals and make legitimate messages render as duplicates. The one
        # safe exception is a stale assistant sibling within a user turn that
        # still has another canonical assistant represented in the snapshot.
        # Older Prompta extractors could persist multiple assistant DOM nodes
        # from one ChatGPT agent turn; a corrected full snapshot should be able
        # to collapse those rows without preserving the stale sibling forever.
        superseded_stable_keys: set[str] = set()
        if snapshot_is_full and existing_history:
            unmatched_incoming = list(incoming)
            stable_existing = [
                row
                for row in existing_history
                if str(row["status"]) == "complete"
                and not str(row["message_key"]).startswith("__prompta_live_assistant_")
                and not str(row["message_key"]).startswith("request-placeholder-")
            ]
            matched_stable_keys: set[str] = set()
            missing_stable: list[dict[str, Any]] = []
            for existing in stable_existing:
                existing_key = str(existing["message_key"])
                existing_role = str(existing["role"])
                existing_content = str(existing["content"] or "").strip()
                match_index = next(
                    (
                        index
                        for index, (_, role, content, key) in enumerate(unmatched_incoming)
                        if key == existing_key
                    ),
                    -1,
                )
                if match_index < 0:
                    match_index = next(
                        (
                            index
                            for index, (_, role, content, _) in enumerate(unmatched_incoming)
                            if role == existing_role and content.strip() == existing_content
                        ),
                        -1,
                    )
                if match_index < 0:
                    missing_stable.append(existing)
                    continue
                matched_stable_keys.add(existing_key)
                unmatched_incoming.pop(match_index)

            stable_users = [
                row for row in stable_existing if str(row["role"]) == "user"
            ]
            for missing in missing_stable:
                if str(missing["role"]) != "assistant":
                    snapshot_is_full = False
                    break
                missing_ordinal = int(missing["ordinal"])
                previous_user_ordinal = max(
                    (
                        int(row["ordinal"])
                        for row in stable_users
                        if int(row["ordinal"]) < missing_ordinal
                    ),
                    default=-1,
                )
                next_user_ordinal = min(
                    (
                        int(row["ordinal"])
                        for row in stable_users
                        if int(row["ordinal"]) > missing_ordinal
                    ),
                    default=2_147_483_647,
                )
                matched_assistant_sibling = any(
                    str(row["role"]) == "assistant"
                    and str(row["message_key"]) in matched_stable_keys
                    and previous_user_ordinal
                    < int(row["ordinal"])
                    < next_user_ordinal
                    for row in stable_existing
                )
                if not matched_assistant_sibling:
                    snapshot_is_full = False
                    break
                superseded_stable_keys.add(str(missing["message_key"]))

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
                SET title = ?,
                    status = CASE
                        WHEN ? THEN 'complete'
                        WHEN status = 'complete' THEN 'complete'
                        ELSE 'active'
                    END,
                    updated_at = ?,
                    completed_at = CASE
                        WHEN ? THEN ?
                        WHEN status = 'complete' THEN completed_at
                        ELSE NULL
                    END,
                    url = CASE WHEN ? != '' THEN ? ELSE url END
                WHERE id = ?
                """,
                (
                    str(snapshot.get("title") or ""),
                    int(complete),
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

            if snapshot_is_full and superseded_stable_keys:
                self.connection.executemany(
                    """
                    DELETE FROM messages
                    WHERE conversation_id = ?
                      AND message_key = ?
                    """,
                    [
                        (conversation_id, message_key)
                        for message_key in sorted(superseded_stable_keys)
                    ],
                )

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
                      AND (
                        message_key LIKE '__prompta_live_assistant_%'
                        OR message_key LIKE 'request-placeholder-%'
                      )
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

            self._remove_superseded_transient_assistants(conversation_id)

    def recoverable_conversations(
        self,
        *,
        interrupted_after: float,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return conversations whose live capture should be reattached after restart."""

        rows = self.connection.execute(
            """
            SELECT c.id, c.job_name, c.prompt, c.url, c.status,
                   c.created_at, c.updated_at, c.completed_at
            FROM conversations AS c
            WHERE c.status = 'active'
               OR (
                    c.status = 'interrupted'
                    AND c.updated_at >= ?
                    AND EXISTS (
                        SELECT 1
                        FROM messages AS m
                        WHERE m.conversation_id = c.id
                          AND m.status = 'streaming'
                    )
               )
            ORDER BY c.updated_at DESC
            LIMIT ?
            """,
            (interrupted_after, max(1, limit)),
        ).fetchall()
        return [dict(row) for row in rows]

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
            ORDER BY ordinal, created_at, rowid
            """,
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.connection.close()
