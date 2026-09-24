from __future__ import annotations

import json
import sqlite3
from typing import Any

from .structured_capture import (
    message_parts_from_source_events,
    ordered_source_events,
    source_event_type,
    stable_event_key,
    tool_calls_from_source_events,
)
from .ui_noise import strip_assistant_ui_noise


def _meaningful_dom_prose(event: dict[str, Any]) -> bool:
    if not str(event.get("id") or "").endswith(":dom-prose"):
        return False
    parts = event.get("parts")
    if not isinstance(parts, list):
        return False
    prose = "\n\n".join(str(part).strip() for part in parts if str(part).strip())
    return bool(strip_assistant_ui_noise(prose))


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
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS source_events_message_ordinal_idx
            ON source_events(conversation_id, message_key, ordinal);

        CREATE INDEX IF NOT EXISTS source_events_message_observed_idx
            ON source_events(conversation_id, message_key, observed_at);

        CREATE INDEX IF NOT EXISTS source_events_conversation_source_created_idx
            ON source_events(conversation_id, source_created_at DESC);

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

        -- tool_calls rows are replaced during transcript refreshes, so diff rows
        -- share their stable identity without a cascading foreign key to tool_calls.
        CREATE TABLE IF NOT EXISTS tool_call_diffs (
            conversation_id TEXT NOT NULL,
            message_key TEXT NOT NULL,
            call_key TEXT NOT NULL,
            before_tree_id TEXT,
            after_tree_id TEXT,
            patch_text TEXT NOT NULL DEFAULT '',
            changed_file_count INTEGER NOT NULL DEFAULT 0
                CHECK (changed_file_count >= 0),
            additions INTEGER NOT NULL DEFAULT 0 CHECK (additions >= 0),
            deletions INTEGER NOT NULL DEFAULT 0 CHECK (deletions >= 0),
            truncated INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0, 1)),
            repository_root TEXT NOT NULL DEFAULT '',
            worktree_path TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (conversation_id, message_key, call_key),
            FOREIGN KEY (conversation_id, message_key)
                REFERENCES messages(conversation_id, message_key) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS conversation_state_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            observed_at REAL NOT NULL,
            status TEXT NOT NULL,
            streaming INTEGER,
            complete INTEGER,
            transient INTEGER,
            failed INTEGER,
            turn_ended INTEGER,
            detail_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS conversation_state_events_conversation_idx
            ON conversation_state_events(conversation_id, observed_at, id);

        CREATE TABLE IF NOT EXISTS message_versions (
            conversation_id TEXT NOT NULL,
            message_key TEXT NOT NULL,
            version INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            observed_at REAL NOT NULL,
            PRIMARY KEY (conversation_id, message_key, version),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        """
    )
    columns = {
        str(row["name"]) for row in connection.execute("PRAGMA table_info(messages)").fetchall()
    }
    if "source_created_at" not in columns:
        connection.execute("ALTER TABLE messages ADD COLUMN source_created_at REAL")
    if "activity_at" not in columns:
        connection.execute("ALTER TABLE messages ADD COLUMN activity_at REAL")
    connection.execute("UPDATE messages SET activity_at = created_at WHERE activity_at IS NULL")


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


def upsert_tool_call_diff(
    connection: sqlite3.Connection,
    *,
    conversation_id: str,
    message_key: str,
    call_key: str,
    before_tree_id: str | None,
    after_tree_id: str | None,
    patch_text: str,
    changed_file_count: int,
    additions: int,
    deletions: int,
    truncated: bool,
    repository_root: str,
    worktree_path: str,
    observed_at: float,
) -> None:
    if changed_file_count < 0 or additions < 0 or deletions < 0:
        raise ValueError("diff summary counts must be non-negative")
    connection.execute(
        """
        INSERT INTO tool_call_diffs (
            conversation_id, message_key, call_key, before_tree_id, after_tree_id,
            patch_text, changed_file_count, additions, deletions, truncated,
            repository_root, worktree_path, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(conversation_id, message_key, call_key) DO UPDATE SET
            before_tree_id = excluded.before_tree_id,
            after_tree_id = excluded.after_tree_id,
            patch_text = excluded.patch_text,
            changed_file_count = excluded.changed_file_count,
            additions = excluded.additions,
            deletions = excluded.deletions,
            truncated = excluded.truncated,
            repository_root = excluded.repository_root,
            worktree_path = excluded.worktree_path,
            updated_at = excluded.updated_at
        """,
        (
            conversation_id,
            message_key,
            call_key,
            before_tree_id,
            after_tree_id,
            patch_text,
            changed_file_count,
            additions,
            deletions,
            int(truncated),
            repository_root,
            worktree_path,
            observed_at,
            observed_at,
        ),
    )


def record_conversation_state(
    connection: sqlite3.Connection,
    *,
    conversation_id: str,
    status: str,
    observed_at: float,
    activity: dict[str, Any] | None = None,
) -> None:
    detail = dict(activity) if isinstance(activity, dict) else {}

    def bool_value(name: str) -> int | None:
        value = detail.get(name)
        return int(value) if isinstance(value, bool) else None

    values = (
        status,
        bool_value("streaming"),
        bool_value("complete"),
        bool_value("transient"),
        bool_value("failed"),
        bool_value("turn_ended"),
        _json(detail) or "{}",
    )
    latest = connection.execute(
        """
        SELECT status, streaming, complete, transient, failed, turn_ended, detail_json
        FROM conversation_state_events
        WHERE conversation_id = ?
        ORDER BY observed_at DESC, id DESC
        LIMIT 1
        """,
        (conversation_id,),
    ).fetchone()
    if latest is not None and tuple(latest) == values:
        return
    connection.execute(
        """
        INSERT INTO conversation_state_events (
            conversation_id, observed_at, status, streaming, complete,
            transient, failed, turn_ended, detail_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (conversation_id, observed_at, *values),
    )


def _canonicalize_source_event_order(
    connection: sqlite3.Connection,
    *,
    conversation_id: str,
    message_key: str,
) -> None:
    rows = connection.execute(
        """
        SELECT rowid, event_key, raw_json, observed_at
        FROM source_events
        WHERE conversation_id = ? AND message_key = ?
        ORDER BY observed_at, rowid
        """,
        (conversation_id, message_key),
    ).fetchall()
    parsed: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        try:
            event = json.loads(str(row["raw_json"] or "{}"))
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        parsed.append((str(row["event_key"]), event))

    event_key_by_object = {id(event): event_key for event_key, event in parsed}
    ordered = ordered_source_events([event for _, event in parsed])
    connection.executemany(
        """
        UPDATE source_events
        SET ordinal = ?
        WHERE conversation_id = ? AND message_key = ? AND event_key = ?
        """,
        [
            (ordinal, conversation_id, message_key, event_key_by_object[id(event)])
            for ordinal, event in enumerate(ordered)
        ],
    )


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

    retained_text_events: dict[str, dict[str, Any]] = {}
    for row in connection.execute(
        """
        SELECT event_key, raw_json
        FROM source_events
        WHERE conversation_id = ?
          AND message_key = ?
          AND role = 'assistant'
          AND recipient IN ('', 'all')
          AND content_type IN ('text', 'multimodal_text')
        ORDER BY observed_at, rowid
        """,
        (conversation_id, message_key),
    ).fetchall():
        event_key = str(row[0] or "")
        try:
            retained = json.loads(str(row[1] or "{}"))
        except json.JSONDecodeError:
            continue
        if not isinstance(retained, dict):
            continue
        identity = str(retained.get("id") or "").strip() or event_key
        retained_text_events[identity] = retained

    incoming_text_identities: set[str] = set()
    for index, event in enumerate(events):
        role = str(event.get("role") or "")
        recipient = str(event.get("recipient") or "")
        content_type = str(event.get("content_type") or "")
        if (
            role == "assistant"
            and recipient in {"", "all"}
            and content_type in {"text", "multimodal_text"}
        ):
            identity = str(event.get("id") or "").strip() or stable_event_key(event, index)
            incoming_text_identities.add(identity)

    derived_events = list(events)
    derived_events.extend(
        retained
        for identity, retained in retained_text_events.items()
        if identity not in incoming_text_identities
    )
    parts = message_parts_from_source_events(derived_events)
    calls = tool_calls_from_source_events(events)

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
        if created_at is not None and not isinstance(created_at, bool):
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
            ON CONFLICT(conversation_id, message_key, event_key) DO UPDATE SET
                ordinal = excluded.ordinal,
                event_type = excluded.event_type,
                role = excluded.role,
                recipient = excluded.recipient,
                content_type = excluded.content_type,
                text = excluded.text,
                reasoning_title = excluded.reasoning_title,
                source_created_at = COALESCE(excluded.source_created_at, source_events.source_created_at),
                end_turn = COALESCE(excluded.end_turn, source_events.end_turn),
                model_slug = CASE
                    WHEN excluded.model_slug != '' THEN excluded.model_slug
                    ELSE source_events.model_slug
                END,
                raw_json = excluded.raw_json,
                observed_at = excluded.observed_at
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

    _canonicalize_source_event_order(
        connection,
        conversation_id=conversation_id,
        message_key=message_key,
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
            ON CONFLICT(conversation_id, message_key, part_key) DO UPDATE SET
                ordinal = excluded.ordinal,
                kind = excluded.kind,
                title = excluded.title,
                content = excluded.content,
                source_created_at = excluded.source_created_at,
                source_event_key = excluded.source_event_key,
                tool_call_key = excluded.tool_call_key,
                end_turn = excluded.end_turn,
                metadata_json = excluded.metadata_json
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
            SET source_created_at = CASE
                WHEN source_created_at IS NULL OR ? < source_created_at THEN ?
                ELSE source_created_at
            END
            WHERE conversation_id = ? AND message_key = ?
            """,
            (
                min(source_times),
                min(source_times),
                conversation_id,
                message_key,
            ),
        )


def promote_structured_capture(
    connection: sqlite3.Connection,
    *,
    conversation_id: str,
    transient_message_key: str,
    durable_message_key: str,
    incoming_events: list[dict[str, Any]],
    observed_at: float,
) -> None:
    """Carry structured tool/prose capture from a live DOM key to its durable message id."""
    inherited_events: list[dict[str, Any]] = []
    latest_dom_prose: dict[str, Any] | None = None
    latest_dom_observed_at = float("-inf")
    for row in connection.execute(
        """
        SELECT raw_json, observed_at
        FROM source_events
        WHERE conversation_id = ? AND message_key = ?
        ORDER BY ordinal, observed_at, rowid
        """,
        (conversation_id, transient_message_key),
    ).fetchall():
        try:
            event = json.loads(str(row[0] or "{}"))
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if str(event.get("id") or "").endswith(":dom-prose"):
            observed = float(row[1] or 0.0)
            if _meaningful_dom_prose(event) and observed >= latest_dom_observed_at:
                latest_dom_prose = event
                latest_dom_observed_at = observed
            continue
        inherited_events.append(event)

    incoming_has_dom_prose = any(
        _meaningful_dom_prose(event) for event in incoming_events if isinstance(event, dict)
    )
    if latest_dom_prose is not None and not incoming_has_dom_prose:
        inherited_events.append(latest_dom_prose)

    merged_by_key: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for index, event in enumerate([*inherited_events, *incoming_events]):
        if not isinstance(event, dict):
            continue
        event_key = stable_event_key(event, index)
        if event_key not in merged_by_key:
            ordered_keys.append(event_key)
        merged_by_key[event_key] = event
    merged_events = [merged_by_key[event_key] for event_key in ordered_keys]

    if merged_events:
        persist_structured_capture(
            connection,
            conversation_id=conversation_id,
            message_key=durable_message_key,
            source_events=merged_events,
            observed_at=observed_at,
        )
    else:
        for table in ("message_parts", "tool_calls"):
            connection.execute(
                f"""
                UPDATE {table}
                SET message_key = ?
                WHERE conversation_id = ? AND message_key = ?
                """,
                (durable_message_key, conversation_id, transient_message_key),
            )

    for table in ("source_events", "message_parts", "tool_calls"):
        connection.execute(
            f"DELETE FROM {table} WHERE conversation_id = ? AND message_key = ?",
            (conversation_id, transient_message_key),
        )
