from __future__ import annotations

import re
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .cache import DEFAULT_CACHE_PATH

_SIDEBAR_PREVIEW_LIMIT = 1024
_SIDEBAR_TOOL_BLOCK_RE = re.compile(
    r"^ {0,3}```(?:tool|tool-call|function|function-call)(?::[^\n\x60]*)?\r?\n"
    r"[\s\S]*?^ {0,3}```[ \t]*\r?$",
    re.IGNORECASE | re.MULTILINE,
)


def _compact_sidebar_preview(value: Any) -> str:
    compact = " ".join(_SIDEBAR_TOOL_BLOCK_RE.sub(" ", str(value or "")).split())
    return compact[:_SIDEBAR_PREVIEW_LIMIT]


class ReadOnlyChatStore:
    """Open fresh read-only data sources for each web request."""

    def __init__(
        self,
        path: Path = DEFAULT_CACHE_PATH,
        log_path: Path | None = None,
        journal_unit: str = "prompta.service",
    ) -> None:
        self.path = path.expanduser()
        self.log_path = (
            log_path.expanduser()
            if log_path is not None
            else self.path.with_name("prompta-nox.log")
        )
        self.journal_unit = journal_unit.strip()

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        connection = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=2.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=2000")
        return connection

    def conversations(self, *, limit: int = 200, query: str = "") -> list[dict[str, Any]]:
        search = query.strip()
        where = ""
        parameters: list[Any] = []
        if search:
            where = """
                WHERE c.title COLLATE NOCASE LIKE ? ESCAPE '!'
                   OR c.job_name COLLATE NOCASE LIKE ? ESCAPE '!'
                   OR c.prompt COLLATE NOCASE LIKE ? ESCAPE '!'
                   OR EXISTS (
                        SELECT 1 FROM messages sm
                        WHERE sm.conversation_id = c.id
                          AND sm.message_key NOT LIKE 'request-placeholder-%'
                          AND sm.content COLLATE NOCASE LIKE ? ESCAPE '!'
                    )
            """
            escaped = search.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            needle = f"%{escaped}%"
            parameters.extend([needle, needle, needle, needle])
        parameters.append(max(1, min(limit, 500)))
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        c.id,
                        c.job_name,
                        c.prompt,
                        c.url,
                        c.title,
                        c.status,
                        c.created_at,
                        c.updated_at,
                        c.completed_at,
                        COALESCE(
                            (
                                SELECT MAX(m.created_at) FROM messages m
                                WHERE m.conversation_id = c.id
                                  AND m.message_key NOT LIKE 'request-placeholder-%'
                            ),
                            c.created_at
                        ) AS last_message_at,
                        COALESCE(
                            (
                                SELECT m.content FROM messages m
                                WHERE m.conversation_id = c.id
                                  AND m.message_key NOT LIKE 'request-placeholder-%'
                                ORDER BY m.ordinal DESC LIMIT 1
                            ),
                            NULLIF(c.prompt, '')
                        ) AS preview,
                        CASE
                            WHEN EXISTS (
                                SELECT 1 FROM messages m
                                WHERE m.conversation_id = c.id
                                  AND m.message_key NOT LIKE 'request-placeholder-%'
                            )
                            THEN (
                                SELECT COUNT(*) FROM messages m
                                WHERE m.conversation_id = c.id
                                  AND m.message_key NOT LIKE 'request-placeholder-%'
                            )
                            WHEN TRIM(c.prompt) <> '' THEN 1
                            ELSE 0
                        END AS message_count
                    FROM conversations c
                    {where}
                    ORDER BY
                        CASE c.status WHEN 'active' THEN 0 ELSE 1 END,
                        c.updated_at DESC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()
        except (FileNotFoundError, sqlite3.DatabaseError):
            return []
        result = []
        for row in rows:
            payload = dict(row)
            payload["preview"] = _compact_sidebar_preview(payload.get("preview"))
            result.append(payload)
        return result

    def conversation(self, conversation_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                conversation = connection.execute(
                    """
                    SELECT id, job_name, prompt, url, title, status,
                           created_at, updated_at, completed_at
                    FROM conversations
                    WHERE id = ?
                    """,
                    (conversation_id,),
                ).fetchone()
                if conversation is None:
                    return None
                messages = connection.execute(
                    """
                    SELECT message_key, ordinal, role, content, status,
                           created_at, updated_at
                    FROM messages
                    WHERE conversation_id = ?
                      AND message_key NOT LIKE 'request-placeholder-%'
                    ORDER BY ordinal
                    """,
                    (conversation_id,),
                ).fetchall()
        except (FileNotFoundError, sqlite3.DatabaseError):
            return None
        payload = dict(conversation)
        message_payloads = [dict(message) for message in messages]
        if payload.get("status") != "active":
            for message in message_payloads:
                message["status"] = "complete"
        prompt = str(payload.get("prompt") or "")
        if not message_payloads and prompt.strip():
            message_payloads = [
                {
                    "message_key": "__prompta_prompt__",
                    "ordinal": 0,
                    "role": "user",
                    "content": prompt,
                    "status": "complete",
                    "created_at": payload["created_at"],
                    "updated_at": payload["updated_at"],
                }
            ]
        payload["messages"] = message_payloads
        return payload

    def logs(self, *, limit: int = 500) -> dict[str, Any]:
        bounded_limit = max(1, min(limit, 2000))
        file_payload: dict[str, Any] | None = None
        if self.log_path.is_file():
            try:
                text = self.log_path.read_text(errors="replace")
                updated_at = self.log_path.stat().st_mtime
            except OSError:
                pass
            else:
                file_payload = {
                    "exists": True,
                    "lines": text.splitlines()[-bounded_limit:],
                    "updated_at": updated_at,
                    "source": "file",
                }

        if not self.journal_unit:
            return file_payload or {
                "exists": False,
                "lines": [],
                "updated_at": None,
                "source": "none",
            }

        try:
            completed = subprocess.run(
                [
                    "journalctl",
                    "--user",
                    "-u",
                    self.journal_unit,
                    "-n",
                    str(bounded_limit),
                    "--no-pager",
                    "--output=short-iso",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=2.0,
            )
        except (OSError, subprocess.SubprocessError):
            return file_payload or {
                "exists": False,
                "lines": [],
                "updated_at": None,
                "source": "none",
            }

        lines = (
            [
                line
                for line in completed.stdout.splitlines()
                if line.strip() and line.strip() != "-- No entries --"
            ]
            if completed.returncode == 0
            else []
        )
        if not lines:
            return file_payload or {
                "exists": False,
                "lines": [],
                "updated_at": None,
                "source": "none",
            }
        updated_at = None
        try:
            updated_at = datetime.fromisoformat(lines[-1].split(maxsplit=1)[0]).timestamp()
        except (ValueError, IndexError):
            pass
        return {
            "exists": True,
            "lines": lines[-bounded_limit:],
            "updated_at": updated_at,
            "source": "journal",
        }

    def stats(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"exists": False, "total": 0, "active": 0}
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active
                    FROM conversations
                    """
                ).fetchone()
        except (FileNotFoundError, sqlite3.Error):
            return {"exists": False, "total": 0, "active": 0}
        return {
            "exists": True,
            "total": int(row["total"] or 0),
            "active": int(row["active"] or 0),
        }

    def change_token(self) -> str:
        """Cheap token that changes when SQLite/WAL or synced logs change."""
        parts: list[str] = []
        targets = (
            self.path,
            Path(f"{self.path}-wal"),
            self.log_path,
        )
        for target in targets:
            try:
                stat = target.stat()
            except OSError:
                parts.append("0:0")
                continue
            parts.append(f"{stat.st_mtime_ns}:{stat.st_size}")
        return "|".join(parts)

    def event_fingerprint(self) -> str:
        """Compatibility token for older SSE consumers."""
        return self.change_token()
