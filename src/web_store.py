from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .cache import DEFAULT_CACHE_PATH, _dom_prose_text, strip_delivery_timeout_noise
from .chromium import preserves_non_tool_text
from .preview import compact_sidebar_preview
from .stream_order import (
    compact_prose_observation,
    has_stream_order_inversion,
    observed_prose_blocks,
    recover_stream_order_from_observations,
    stabilize_streaming_content,
)
from .structured_capture import has_completed_final_text, rendered_content_from_parts


def _attach_transient_dom_prose_observations(
    messages: list[dict[str, Any]],
    observations_by_message: dict[str, list[tuple[float, str]]],
    source_ranges_by_message: dict[str, tuple[float, float]],
) -> None:
    """Attach legacy live-assistant prose observations to their durable turn."""

    durable_assistant_keys = [
        str(message.get("message_key") or "")
        for message in messages
        if str(message.get("role") or "") == "assistant"
        and not str(message.get("message_key") or "").startswith("__prompta_live_assistant_")
    ]
    durable_keys = set(durable_assistant_keys)
    for transient_key, observations in list(observations_by_message.items()):
        if transient_key in durable_keys or not transient_key.startswith(
            "__prompta_live_assistant_"
        ):
            continue
        transient_range = source_ranges_by_message.get(transient_key)
        if transient_range is None:
            continue
        transient_start, transient_end = transient_range
        candidates: list[tuple[float, str]] = []
        for durable_key in durable_assistant_keys:
            durable_range = source_ranges_by_message.get(durable_key)
            if durable_range is None:
                continue
            durable_start, durable_end = durable_range
            overlap = min(transient_end, durable_end) - max(transient_start, durable_start)
            if overlap >= 0:
                candidates.append((overlap, durable_key))
        if not candidates:
            continue
        candidates.sort(reverse=True)
        best_overlap, best_key = candidates[0]
        if len(candidates) > 1 and candidates[1][0] == best_overlap:
            continue
        existing = observations_by_message.setdefault(best_key, [])
        existing.extend(observations)
        existing.sort(key=lambda item: item[0])


def _merge_tool_parts_with_dom_prose(
    parts: list[dict[str, Any]],
    observations: list[tuple[float, str]],
    *,
    message_key: str,
) -> list[dict[str, Any]] | None:
    """Recover renderable prose/tool interleaving when only tool parts survived."""

    has_tool = any(str(part.get("kind") or "") == "tool_call" for part in parts)
    has_text = any(
        str(part.get("kind") or "") in {"assistant_text", "final_text", "reasoning"}
        and bool(str(part.get("content") or "").strip())
        for part in parts
    )
    if not has_tool or has_text:
        return None

    prose_blocks = observed_prose_blocks(observations)
    if not prose_blocks:
        return None

    timeline: list[tuple[float, int, int, dict[str, Any]]] = []
    for index, part in enumerate(parts):
        timestamp = part.get("source_created_at")
        try:
            sort_time = float(timestamp) if timestamp is not None else float("inf")
        except (TypeError, ValueError):
            sort_time = float("inf")
        timeline.append((sort_time, 1, index, dict(part)))

    for index, (observed_at, content) in enumerate(prose_blocks):
        timeline.append(
            (
                observed_at,
                0,
                index,
                {
                    "message_key": message_key,
                    "part_key": f"recovered-dom-prose-{index}",
                    "ordinal": 0,
                    "kind": "assistant_text",
                    "title": "",
                    "content": content,
                    "source_created_at": observed_at,
                    "source_event_key": "",
                    "tool_call_key": "",
                    "end_turn": None,
                    "metadata": {"recovered_from": "dom-prose"},
                },
            )
        )

    timeline.sort(key=lambda item: (item[0], item[1], item[2]))
    merged: list[dict[str, Any]] = []
    for ordinal, (_, _, _, part) in enumerate(timeline):
        part["ordinal"] = ordinal
        merged.append(part)
    return merged


class ReadOnlyChatStore:
    """Open fresh read-only data sources for each web request."""

    def __init__(
        self,
        path: Path = DEFAULT_CACHE_PATH,
        log_path: Path | None = None,
        journal_unit: str = "prompta-ui.service",
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

    def conversations(
        self,
        *,
        limit: int = 200,
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

        parameters.append(max(1, min(limit, 500)) + (len(included_ids) if not search else 0))

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
                        LIMIT ?
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

    def conversation(
        self,
        conversation_id: str,
        *,
        include_state_events: bool = True,
    ) -> dict[str, Any] | None:
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
                tool_call_diffs = (
                    connection.execute(
                        """
                        SELECT message_key, call_key, before_tree_id, after_tree_id,
                               patch_text, changed_file_count, additions, deletions,
                               truncated, repository_root, worktree_path,
                               created_at, updated_at
                        FROM tool_call_diffs
                        WHERE conversation_id = ?
                        """,
                        (conversation_id,),
                    ).fetchall()
                    if "tool_call_diffs" in tables
                    else []
                )
                source_event_counts = (
                    connection.execute(
                        """
                        SELECT message_key, COUNT(*) AS event_count,
                               MIN(source_created_at) AS earliest_source_created_at,
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
                    if include_state_events and "conversation_state_events" in tables
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
        diffs_by_call = {
            (str(row["message_key"]), str(row["call_key"])): dict(row) for row in tool_call_diffs
        }
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
            diff = diffs_by_call.get((str(call["message_key"]), str(call["call_key"])))
            if diff is not None:
                diff.pop("message_key", None)
                diff.pop("call_key", None)
                diff["truncated"] = bool(diff.get("truncated"))
                call["code_diff"] = diff
            calls_by_message.setdefault(str(call["message_key"]), []).append(call)
        event_count_by_message = {
            str(row["message_key"]): int(row["event_count"] or 0) for row in source_event_counts
        }
        latest_source_time_by_message = {
            str(row["message_key"]): float(row["latest_source_created_at"])
            for row in source_event_counts
            if row["latest_source_created_at"] is not None
        }
        source_ranges_by_message = {
            str(row["message_key"]): (
                float(row["earliest_source_created_at"]),
                float(row["latest_source_created_at"]),
            )
            for row in source_event_counts
            if row["earliest_source_created_at"] is not None
            and row["latest_source_created_at"] is not None
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
        _attach_transient_dom_prose_observations(
            message_payloads,
            dom_prose_by_message,
            source_ranges_by_message,
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
            message["parts_renderable"] = False
            message["tool_calls"] = calls_by_message.get(message_key, [])
            message["source_event_count"] = event_count_by_message.get(message_key, 0)
            message["display_at"] = latest_source_time_by_message.get(
                message_key, message.get("created_at")
            )
            message["version_count"] = version_count_by_message.get(message_key, 0)
            dom_observations = [
                (observed_at, cleaned)
                for observed_at, prose in dom_prose_by_message.get(message_key, [])
                if (cleaned := compact_prose_observation(strip_delivery_timeout_noise(prose)))
            ]
            use_structured_content = historical or str(message.get("status") or "") == "complete"
            if use_structured_content and str(message.get("role") or "") == "assistant":
                recovered_parts = _merge_tool_parts_with_dom_prose(
                    structured_parts,
                    dom_observations,
                    message_key=message_key,
                )
                if recovered_parts is not None:
                    structured_parts = recovered_parts
                    message["parts"] = structured_parts
                    message["content"] = rendered_content_from_parts(structured_parts)
                    message["parts_renderable"] = True

            if str(message.get("role") or "") == "assistant" and dom_observations:
                latest_dom_prose = dom_observations[-1][1]
                current_content = str(message.get("content") or "")
                if latest_dom_prose and not preserves_non_tool_text(
                    latest_dom_prose,
                    current_content,
                ):
                    recovered_content = stabilize_streaming_content(
                        latest_dom_prose,
                        current_content,
                    )
                    if has_stream_order_inversion(recovered_content, dom_observations):
                        recovered_content = recover_stream_order_from_observations(
                            recovered_content,
                            dom_observations,
                        )
                    message["content"] = recovered_content

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
                    message["parts_renderable"] = True
            if use_structured_content:
                canonical_text_observations = [
                    (
                        float(part["source_created_at"]),
                        str(part.get("content") or ""),
                    )
                    for part in structured_parts
                    if str(part.get("kind") or "")
                    in {
                        "assistant_text",
                        "final_text",
                        "reasoning",
                    }
                    and part.get("source_created_at") is not None
                    and str(part.get("content") or "").strip()
                ]
                observations = [
                    *canonical_text_observations,
                    *dom_prose_by_message.get(message_key, []),
                ]
                content = str(message.get("content") or "")
                if (
                    not message["parts_renderable"]
                    and observations
                    and has_stream_order_inversion(content, observations)
                ):
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
