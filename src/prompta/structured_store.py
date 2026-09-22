from __future__ import annotations

import json
import sqlite3
from typing import Any

from .structured_capture import (
    message_parts_from_source_events,
    source_event_type,
    stable_event_key,
    tool_calls_from_source_events,
)


def migrate_structured_capture(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_events (
            conversation_id TEXT NOT NULL,
            message_key TEXT NOT NULL,
            event_key TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            event_type TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT '',
            recipient TEXT NOT NULL DEFAULT '',
            content_type TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            reasoning_title TEXT NOT NULL DEFAULT '',
            source_created_at REAL,
            end_turn INTEGER,
            model_slug TEXT NOT NULL DEFAULT '',
            raw_json TEXT NOT NULL,
            observed_at REAL NOT NULL,
            PRIMARY KEY (conversation_id, message_key, event_key),
            FOREIGN KEY (conversation_id, message_key)
                REFERENCES messages(conversation_id, message_key) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS source_events_message_ordinal_idx
            ON source_events(conversation_id, message_key, ordinal);

        CREATE TABLE IF NOT EXISTS message_parts (
            conversation_id TEXT NOT NULL,
            message_key TEXT NOT NULL,
            part_key TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            source_created_at REAL,
            source_event_key TEXT NOT NULL DEFAULT '',
            tool_call_key TEXT NOT NULL DEFAULT '',
            end_turn INTEGER,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (conversation_id, message_key, part_key),
            FOREIGN KEY (conversation_id, message_key)
                REFERENCES messages(conversation_id, message_key) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS message_parts_message_ordinal_idx
            ON message_parts(conversation_id, message_key, ordinal);

        CREATE TABLE IF NOT EXISTS tool_calls (
            conversation_id TEXT NOT NULL,
            message_key TEXT NOT NULL,
            call_key TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            connector TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            arguments_json TEXT,
            status TEXT NOT NULL DEFAULT '',
            result_json TEXT,
            error_json TEXT,
            duration_ms REAL,
            source_created_at REAL,
            source_event_key TEXT NOT NULL DEFAULT '',
            result_event_key TEXT NOT NULL DEFAULT '',
            raw_json TEXT NOT NULL,
            PRIMARY KEY (conversation_id, message_key, call_key),
            FOREIGN KEY (conversation_id, message_key)
                REFERENCES messages(conversation_id, message_key) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS tool_calls_message_ordinal_idx
            ON tool_calls(conversation_id, message_key, ordinal);

        CREATE TABLE IF NOT EXISTS message_versions (
            conversation_id TEXT NOT NULL,
            message_key TEXT NOT NULL,
            version INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            observed_at REAL NOT NULL,
            PRIMARY KEY (conversation_id, message_key, version),
            FOREIGN KEY (conversation_id, message_key)
                REFERENCES messages(conversation_id, message_key) ON DELETE CASCADE
        );
        """
    )
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(messages)").fetchall()
    }
    if "source_created_at" not in columns:
        connection.execute("ALTER TABLE messages ADD COLUMN source_created_at REAL")


def record_message_version(
    connection: sqlite3.Connection,
    *,
    conversation_id: str,
    message_key: str,
    role: str,
    content: str,
    status: str,
    observed_at: float,
    previous: dict[str, Any] | None,
) -> None:
    should_record = previous is None
    if previous is not None:
        previous_status = str(previous.get("status") or "")
        previous_content = str(previous.get("content") or "")
        previous_role = str(previous.get("role") or "")
        should_record = (
            previous_role != role
            or (
                previous_status == "complete"
                and (previous_content != content or status != previous_status)
            )
            or (previous_status == "streaming" and status == "complete")
        )
    if not should_record:
        return
    row = connection.execute(
        """
        SELECT COALESCE(MAX(version), -1) + 1 AS next_version
        FROM message_versions
        WHERE conversation_id = ? AND message_key = ?
        """,
        (conversation_id, message_key),
    ).fetchone()
    version = int(row["next_version"] if row is not None else 0)
    connection.execute(
        """
        INSERT INTO message_versions (
            conversation_id, message_key, version, role, content, status, observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            conversation_id,
            message_key,
            version,
            role,
            content,
            status,
            observed_at,
        ),
    )


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def persist_structured_capture(
    connection: sqlite3.Connection,
    *,
    conversation_id: str,
    message_key: str,
    source_events: list[dict[str, Any]],
    observed_at: float,
) -> None:
    if not source_events:
        return
    events = [event for event in source_events if isinstance(event, dict)]
    if not events:
        return

    parts = message_parts_from_source_events(events)
    calls = tool_calls_from_source_events(events)

    connection.execute(
        "DELETE FROM source_events WHERE conversation_id = ? AND message_key = ?",
        (conversation_id, message_key),
    )
    connection.execute(
        "DELETE FROM message_parts WHERE conversation_id = ? AND message_key = ?",
        (conversation_id, message_key),
    )
    connection.execute(
        "DELETE FROM tool_calls WHERE conversation_id = ? AND message_key = ?",
        (conversation_id, message_key),
    )

    source_times: list[float] = []
    for ordinal, event in enumerate(events):
        created_at = event.get("create_time")
        source_created_at: float | None = None
        if not isinstance(created_at, bool):
            try:
                numeric = float(created_at)
            except (TypeError, ValueError):
                numeric = 0.0
            if numeric > 0:
                source_created_at = numeric
                source_times.append(numeric)
        end_turn = event.get("end_turn")
        connection.execute(
            """
            INSERT INTO source_events (
                conversation_id, message_key, event_key, ordinal, event_type,
                role, recipient, content_type, text, reasoning_title,
                source_created_at, end_turn, model_slug, raw_json, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                message_key,
                stable_event_key(event, ordinal),
                ordinal,
                source_event_type(event),
                str(event.get("role") or ""),
                str(event.get("recipient") or ""),
                str(event.get("content_type") or ""),
                str(event.get("text") or ""),
                str(event.get("reasoning_title") or ""),
                source_created_at,
                int(end_turn) if isinstance(end_turn, bool) else None,
                str(event.get("model_slug") or ""),
                _json(event) or "{}",
                observed_at,
            ),
        )

    for part in parts:
        end_turn = part.get("end_turn")
        metadata = {
            key: value
            for key, value in part.items()
            if key
            not in {
                "part_key",
                "ordinal",
                "kind",
                "title",
                "content",
                "source_created_at",
                "source_event_key",
                "tool_call_key",
                "end_turn",
            }
        }
        connection.execute(
            """
            INSERT INTO message_parts (
                conversation_id, message_key, part_key, ordinal, kind, title,
                content, source_created_at, source_event_key, tool_call_key,
                end_turn, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                message_key,
                str(part.get("part_key") or f"part-{part.get('ordinal', 0)}"),
                int(part.get("ordinal") or 0),
                str(part.get("kind") or ""),
                str(part.get("title") or ""),
                str(part.get("content") or ""),
                part.get("source_created_at"),
                str(part.get("source_event_key") or ""),
                str(part.get("tool_call_key") or ""),
                int(end_turn) if isinstance(end_turn, bool) else None,
                _json(metadata) or "{}",
            ),
        )

    for call in calls:
        connection.execute(
            """
            INSERT INTO tool_calls (
                conversation_id, message_key, call_key, ordinal, connector, action,
                summary, arguments_json, status, result_json, error_json, duration_ms,
                source_created_at, source_event_key, result_event_key, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                message_key,
                str(call.get("call_key") or f"tool-{call.get('ordinal', 0)}"),
                int(call.get("ordinal") or 0),
                str(call.get("connector") or ""),
                str(call.get("action") or ""),
                str(call.get("summary") or ""),
                _json(call.get("arguments")),
                str(call.get("status") or ""),
                _json(call.get("result")),
                _json(call.get("error")),
                call.get("duration_ms"),
                call.get("created_at"),
                str(call.get("source_event_key") or ""),
                str(call.get("result_event_key") or ""),
                _json(call) or "{}",
            ),
        )

    if source_times:
        connection.execute(
            """
            UPDATE messages
            SET source_created_at = COALESCE(source_created_at, ?)
            WHERE conversation_id = ? AND message_key = ?
            """,
            (min(source_times), conversation_id, message_key),
        )
