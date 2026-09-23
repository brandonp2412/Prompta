from __future__ import annotations

import json
import sqlite3
import subprocess
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

from .cache import DEFAULT_CACHE_PATH, _dom_prose_text, strip_delivery_timeout_noise
from .chromium import preserves_non_tool_text
from .preview import compact_sidebar_preview
from .stream_order import has_stream_order_inversion, recover_stream_order_from_observations
from .structured_capture import has_completed_final_text, rendered_content_from_parts


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
        self._conversation_cache: OrderedDict[
            str, tuple[tuple[str, float, float | None], dict[str, Any]]
        ] = OrderedDict()
        self._conversation_cache_lock = threading.Lock()
        self._conversation_cache_limit = 24

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

    def conversations(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        query: str = "",
        include_ids: list[str] | tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        search = query.strip()
        included_ids = list(
            dict.fromkeys(str(value).strip() for value in include_ids if str(value).strip())
        )[:100]
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

        include_rank = "1"
        if included_ids and not search:
            placeholders = ", ".join("?" for _ in included_ids)
            include_rank = f"CASE WHEN c.id IN ({placeholders}) THEN 0 ELSE 1 END"
            parameters.extend(included_ids)

        parameters.append(
            max(1, min(limit, 500)) + (len(included_ids) if not search and offset == 0 else 0)
        )
        parameters.append(max(0, offset))

        try:
            with self._connect() as connection:
                tables = {
                    str(row["name"])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(conversations)").fetchall()
                }
                has_preview_column = "preview" in columns
                message_columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(messages)").fetchall()
                }
                message_activity = (
                    "COALESCE(m.activity_at, m.created_at)"
                    if "activity_at" in message_columns
                    else "m.created_at"
                )
                preview_column = "c.preview," if has_preview_column else ""
                latest_message_preview = """(
                    SELECT m.content
                    FROM messages m
                    WHERE m.conversation_id = s.id
                      AND m.message_key NOT LIKE 'request-placeholder-%'
                    ORDER BY m.ordinal DESC
                    LIMIT 1
                )"""
                structured_final_preview = """
                    (
                        SELECT p.content
                        FROM message_parts p
                        JOIN messages pm
                          ON pm.conversation_id = p.conversation_id
                         AND pm.message_key = p.message_key
                        WHERE p.conversation_id = s.id
                          AND pm.role = 'assistant'
                          AND p.kind = 'final_text'
                          AND p.end_turn = 1
                          AND p.source_event_key NOT LIKE '%:dom-prose'
                          AND EXISTS (
                              SELECT 1
                              FROM source_events pe
                              WHERE pe.conversation_id = p.conversation_id
                                AND pe.message_key = p.message_key
                                AND pe.event_key LIKE '%:dom-prose:%'
                          )
                        ORDER BY pm.ordinal DESC, p.ordinal DESC
                        LIMIT 1
                    )
                """
                has_structured_preview = {"message_parts", "source_events"} <= tables
                stored_preview = "s.preview" if has_preview_column else "NULL"
                preview_expression = (
                    f"COALESCE({structured_final_preview}, {stored_preview}, "
                    f"{latest_message_preview}, NULLIF(s.prompt, ''))"
                    if has_structured_preview
                    else (
                        stored_preview
                        if has_preview_column
                        else f"COALESCE({latest_message_preview}, NULLIF(s.prompt, ''))"
                    )
                )
                rows = connection.execute(
                    f"""
                    WITH selected AS (
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
                            {preview_column}
                            {include_rank} AS include_rank
                        FROM conversations c
                        {where}
                        ORDER BY include_rank, c.created_at DESC, c.id
                        LIMIT ? OFFSET ?
                    ),
                    message_stats AS (
                        SELECT
                            m.conversation_id,
                            MAX(m.created_at) AS last_message_at,
                            MAX(CASE WHEN m.role = 'assistant' THEN {message_activity} END) AS last_assistant_at,
                            MAX(CASE WHEN m.role = 'user' THEN {message_activity} END) AS last_user_at,
                            COUNT(*) AS message_count
                        FROM messages m
                        JOIN selected s ON s.id = m.conversation_id
                        WHERE m.message_key NOT LIKE 'request-placeholder-%'
                        GROUP BY m.conversation_id
                    )
                    SELECT
                        s.id,
                        s.job_name,
                        s.prompt,
                        s.url,
                        s.title,
                        s.status,
                        s.created_at,
                        s.updated_at,
                        s.completed_at,
                        COALESCE(ms.last_message_at, s.created_at) AS last_message_at,
                        ms.last_assistant_at,
                        COALESCE(ms.last_user_at, s.created_at) AS last_user_at,
                        {preview_expression} AS preview,
                        CASE
                            WHEN COALESCE(ms.message_count, 0) > 0 THEN ms.message_count
                            WHEN TRIM(s.prompt) <> '' THEN 1
                            ELSE 0
                        END AS message_count
                    FROM selected s
                    LEFT JOIN message_stats ms ON ms.conversation_id = s.id
                    ORDER BY s.include_rank, s.created_at DESC, s.id
                    """,
                    parameters,
                ).fetchall()
        except (FileNotFoundError, sqlite3.DatabaseError):
            return []

        result = []
        fallback_payloads: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            raw_preview = payload.get("preview")
            preview = compact_sidebar_preview(raw_preview)
            payload["preview"] = preview or compact_sidebar_preview(payload.get("prompt"))
            raw_preview_text = str(raw_preview or "")
            legacy_noise = any(
                marker in raw_preview_text.casefold()
                for marker in (
                    "connection interrupted",
                    "waiting for the complete answer",
                    "a network error occurred",
                    "message delivery timed out",
                )
            )
            if has_preview_column and raw_preview and (not preview or legacy_noise):
                fallback_payloads.append(payload)
            result.append(payload)

        if fallback_payloads:
            with self._connect() as connection:
                for payload in fallback_payloads:
                    row = connection.execute(
                        """
                        SELECT content
                        FROM messages
                        WHERE conversation_id = ?
                          AND message_key NOT LIKE 'request-placeholder-%'
                        ORDER BY ordinal DESC
                        LIMIT 1
                        """,
                        (payload["id"],),
                    ).fetchone()
                    if row is None:
                        continue
                    preview = compact_sidebar_preview(row["content"])
                    if preview:
                        payload["preview"] = preview

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

                revision = (
                    str(conversation["status"] or ""),
                    float(conversation["updated_at"] or 0.0),
                    (
                        float(conversation["completed_at"])
                        if conversation["completed_at"] is not None
                        else None
                    ),
                )
                with self._conversation_cache_lock:
                    cached = self._conversation_cache.get(conversation_id)
                    if cached is not None and cached[0] == revision:
                        self._conversation_cache.move_to_end(conversation_id)
                        return cached[1]
                    if cached is not None:
                        self._conversation_cache.pop(conversation_id, None)

                tables = {
                    str(row["name"])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                message_columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(messages)").fetchall()
                }
                created_at_expression = (
                    "COALESCE(source_created_at, created_at)"
                    if "source_created_at" in message_columns
                    else "created_at"
                )
                activity_at_expression = (
                    "COALESCE(activity_at, created_at)"
                    if "activity_at" in message_columns
                    else "created_at"
                )
                messages = connection.execute(
                    f"""
                    SELECT message_key, ordinal, role, content, status,
                           {created_at_expression} AS created_at, updated_at,
                           {activity_at_expression} AS activity_at
                    FROM messages
                    WHERE conversation_id = ?
                      AND message_key NOT LIKE 'request-placeholder-%'
                    ORDER BY ordinal
                    """,
                    (conversation_id,),
                ).fetchall()
                parts = (
                    connection.execute(
                        """
                        SELECT message_key, part_key, ordinal, kind, title, content,
                               source_created_at, source_event_key, tool_call_key,
                               end_turn, metadata_json
                        FROM message_parts
                        WHERE conversation_id = ?
                        ORDER BY message_key, ordinal
                        """,
                        (conversation_id,),
                    ).fetchall()
                    if "message_parts" in tables
                    else []
                )
                tool_calls = (
                    connection.execute(
                        """
                        SELECT message_key, call_key, ordinal, connector, action,
                               summary, arguments_json, status, result_json,
                               error_json, duration_ms, source_created_at,
                               source_event_key, result_event_key
                        FROM tool_calls
                        WHERE conversation_id = ?
                        ORDER BY message_key, ordinal
                        """,
                        (conversation_id,),
                    ).fetchall()
                    if "tool_calls" in tables
                    else []
                )
                source_event_counts = (
                    connection.execute(
                        """
                        SELECT message_key, COUNT(*) AS event_count,
                               MAX(source_created_at) AS latest_source_created_at
                        FROM source_events
                        WHERE conversation_id = ?
                        GROUP BY message_key
                        """,
                        (conversation_id,),
                    ).fetchall()
                    if "source_events" in tables
                    else []
                )
                dom_prose_events = (
                    connection.execute(
                        """
                        SELECT message_key, observed_at, raw_json
                        FROM source_events
                        WHERE conversation_id = ?
                          AND event_key LIKE '%:dom-prose:%'
                        ORDER BY message_key, observed_at, rowid
                        """,
                        (conversation_id,),
                    ).fetchall()
                    if "source_events" in tables
                    else []
                )
                version_counts = (
                    connection.execute(
                        """
                        SELECT message_key, COUNT(*) AS version_count
                        FROM message_versions
                        WHERE conversation_id = ?
                        GROUP BY message_key
                        """,
                        (conversation_id,),
                    ).fetchall()
                    if "message_versions" in tables
                    else []
                )
                state_events = (
                    connection.execute(
                        """
                        SELECT observed_at, status, streaming, complete, transient,
                               failed, turn_ended, detail_json
                        FROM conversation_state_events
                        WHERE conversation_id = ?
                        ORDER BY observed_at, id
                        """,
                        (conversation_id,),
                    ).fetchall()
                    if "conversation_state_events" in tables
                    else []
                )
        except (FileNotFoundError, sqlite3.DatabaseError):
            return None
        payload = dict(conversation)
        payload["state_events"] = []
        for row in state_events:
            state_event = dict(row)
            detail_json = str(state_event.pop("detail_json", "") or "")
            try:
                state_event["detail"] = json.loads(detail_json) if detail_json else {}
            except json.JSONDecodeError:
                state_event["detail"] = {}
            for key in ("streaming", "complete", "transient", "failed", "turn_ended"):
                if state_event.get(key) is not None:
                    state_event[key] = bool(state_event[key])
            payload["state_events"].append(state_event)
        message_payloads = [dict(message) for message in messages]
        parts_by_message: dict[str, list[dict[str, Any]]] = {}
        for row in parts:
            part = dict(row)
            metadata_json = str(part.pop("metadata_json", "") or "")
            try:
                part["metadata"] = json.loads(metadata_json) if metadata_json else {}
            except json.JSONDecodeError:
                part["metadata"] = {}
            parts_by_message.setdefault(str(part["message_key"]), []).append(part)
        calls_by_message: dict[str, list[dict[str, Any]]] = {}
        for row in tool_calls:
            call = dict(row)
            for source, target in (
                ("arguments_json", "arguments"),
                ("result_json", "result"),
                ("error_json", "error"),
            ):
                encoded = call.pop(source, None)
                if encoded is None:
                    call[target] = None
                    continue
                try:
                    call[target] = json.loads(str(encoded))
                except json.JSONDecodeError:
                    call[target] = str(encoded)
            calls_by_message.setdefault(str(call["message_key"]), []).append(call)
        event_count_by_message = {
            str(row["message_key"]): int(row["event_count"] or 0) for row in source_event_counts
        }
        latest_source_time_by_message = {
            str(row["message_key"]): float(row["latest_source_created_at"])
            for row in source_event_counts
            if row["latest_source_created_at"] is not None
        }
        dom_prose_by_message: dict[str, list[tuple[float, str]]] = {}
        for row in dom_prose_events:
            try:
                event = json.loads(str(row["raw_json"] or "{}"))
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            prose = _dom_prose_text(event)
            if not prose:
                continue
            dom_prose_by_message.setdefault(str(row["message_key"]), []).append(
                (float(row["observed_at"]), prose)
            )
        version_count_by_message = {
            str(row["message_key"]): int(row["version_count"] or 0) for row in version_counts
        }
        historical = payload.get("status") != "active"
        for message in message_payloads:
            message_key = str(message.get("message_key") or "")
            structured_parts = parts_by_message.get(message_key, [])
            if str(message.get("role") or "") == "assistant":
                message["content"] = strip_delivery_timeout_noise(str(message.get("content") or ""))
                for part in structured_parts:
                    if str(part.get("kind") or "") in {
                        "assistant_text",
                        "final_text",
                        "reasoning",
                    }:
                        part["content"] = strip_delivery_timeout_noise(
                            str(part.get("content") or "")
                        )
            message["parts"] = structured_parts
            message["tool_calls"] = calls_by_message.get(message_key, [])
            message["source_event_count"] = event_count_by_message.get(message_key, 0)
            message["display_at"] = latest_source_time_by_message.get(
                message_key, message.get("created_at")
            )
            message["version_count"] = version_count_by_message.get(message_key, 0)
            use_structured_content = historical or str(message.get("status") or "") == "complete"
            if use_structured_content and structured_parts:
                structured_content = rendered_content_from_parts(structured_parts)
                canonical_content = str(message.get("content") or "")
                if structured_content and (
                    (
                        bool(dom_prose_by_message.get(message_key))
                        and has_completed_final_text(structured_parts)
                    )
                    or preserves_non_tool_text(canonical_content, structured_content)
                ):
                    message["content"] = structured_content
            if use_structured_content:
                observations = dom_prose_by_message.get(message_key, [])
                content = str(message.get("content") or "")
                if observations and has_stream_order_inversion(content, observations):
                    message["content"] = recover_stream_order_from_observations(
                        content, observations
                    )
        if historical:
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
                    "display_at": payload["created_at"],
                    "parts": [],
                    "tool_calls": [],
                    "source_event_count": 0,
                    "version_count": 0,
                }
            ]
        payload["messages"] = message_payloads
        with self._conversation_cache_lock:
            self._conversation_cache[conversation_id] = (revision, payload)
            self._conversation_cache.move_to_end(conversation_id)
            while len(self._conversation_cache) > self._conversation_cache_limit:
                self._conversation_cache.popitem(last=False)
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
        """Cheap token that changes when cached chat state changes."""
        parts: list[str] = []
        targets = (self.path, Path(f"{self.path}-wal"))
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
