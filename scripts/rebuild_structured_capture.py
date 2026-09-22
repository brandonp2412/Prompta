#!/usr/bin/env python3
"""Rebuild derived structured chat rows from preserved source events."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from prompta.structured_capture import (
    message_parts_from_source_events,
    tool_calls_from_source_events,
)

DEFAULT_CACHE = Path.home() / ".local/state/prompta/chats.sqlite3"


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        raw = json.loads(str(row["raw_json"] or "{}"))
    except json.JSONDecodeError:
        raw = {}
    event = dict(raw) if isinstance(raw, dict) else {}
    # Persisted event keys include a digest even when several source events share one ChatGPT message id.
    # Use that unique key while rebuilding so derived part/tool keys cannot collide.
    event["id"] = str(row["event_key"] or "")
    event.setdefault("role", str(row["role"] or ""))
    event.setdefault("recipient", str(row["recipient"] or ""))
    event.setdefault("content_type", str(row["content_type"] or ""))
    if not event.get("text") and row["text"]:
        event["text"] = str(row["text"])
    if not event.get("reasoning_title") and row["reasoning_title"]:
        event["reasoning_title"] = str(row["reasoning_title"])
    if event.get("create_time") is None and row["source_created_at"] is not None:
        event["create_time"] = row["source_created_at"]
    if event.get("end_turn") is None and row["end_turn"] is not None:
        event["end_turn"] = bool(row["end_turn"])
    if not event.get("model_slug") and row["model_slug"]:
        event["model_slug"] = str(row["model_slug"])
    return event


def _replace_derived_rows(
    connection: sqlite3.Connection,
    conversation_id: str,
    message_key: str,
    events: list[dict[str, Any]],
) -> tuple[int, int, int]:
    parts = message_parts_from_source_events(events)
    calls = tool_calls_from_source_events(events)

    connection.execute(
        "DELETE FROM message_parts WHERE conversation_id = ? AND message_key = ?",
        (conversation_id, message_key),
    )
    connection.execute(
        "DELETE FROM tool_calls WHERE conversation_id = ? AND message_key = ?",
        (conversation_id, message_key),
    )

    text_parts = 0
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
        if str(part.get("kind") or "") in {"assistant_text", "final_text", "reasoning"}:
            text_parts += 1

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

    return len(parts), text_parts, len(calls)


def rebuild(cache_path: Path) -> tuple[int, int, int, int]:
    connection = sqlite3.connect(cache_path)
    connection.row_factory = sqlite3.Row
    rebuilt = 0
    part_count = 0
    text_part_count = 0
    call_count = 0
    try:
        groups = connection.execute(
            """
            SELECT conversation_id, message_key
            FROM source_events
            GROUP BY conversation_id, message_key
            """
        ).fetchall()
        with connection:
            for group in groups:
                conversation_id = str(group["conversation_id"])
                message_key = str(group["message_key"])
                rows = connection.execute(
                    """
                    SELECT event_key, ordinal, role, recipient, content_type, text,
                           reasoning_title, source_created_at, end_turn, model_slug, raw_json
                    FROM source_events
                    WHERE conversation_id = ? AND message_key = ?
                    ORDER BY ordinal
                    """,
                    (conversation_id, message_key),
                ).fetchall()
                events = [_event_from_row(row) for row in rows]
                parts, text_parts, calls = _replace_derived_rows(
                    connection,
                    conversation_id,
                    message_key,
                    events,
                )
                rebuilt += 1
                part_count += parts
                text_part_count += text_parts
                call_count += calls
    finally:
        connection.close()
    return rebuilt, part_count, text_part_count, call_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    rebuilt, parts, text_parts, calls = rebuild(args.cache)
    print(f"rebuilt_messages={rebuilt} parts={parts} text_parts={text_parts} tool_calls={calls}")


if __name__ == "__main__":
    main()
