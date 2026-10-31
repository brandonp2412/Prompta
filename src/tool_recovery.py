"""Persist tool headings from an explicitly requested, verified exact-chat read."""

from __future__ import annotations

import time

from sqlalchemy import select, update

from .response_capture import CaptureResult
from .response_store import ResponseStore, merge_tool_calls, results


def recover_completed_tool_summaries(
    store: ResponseStore, send_id: str, capture: CaptureResult,
    *, now: float | None = None,
) -> bool:
    """Merge tools only after paced UI recovery verifies the prompt and route.

    This function never navigates or submits. Callers must obtain read admission
    and verify the original prompt before passing a normalized DOM capture.
    A completed row's exact final branch must match; text and state stay intact.
    """
    if (
        capture.source != "dom" or capture.status != "complete"
        or not capture.conversation_id or not capture.message_id
        or not capture.tool_calls
    ):
        return False
    at = time.time() if now is None else now
    with store.engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        predicates = (
            results.c.send_id == send_id,
            results.c.status == "completed",
            results.c.capture_owner == "",
            results.c.conversation_id == capture.conversation_id,
            results.c.message_id == capture.message_id,
        )
        row = connection.execute(select(results.c.tool_calls_json).where(*predicates)).one_or_none()
        if row is None:
            return False
        merged = merge_tool_calls(row[0], capture.tool_calls)
        if merged != row[0]:
            connection.execute(update(results).where(*predicates).values(
                tool_calls_json=merged, updated_at=at,
            ))
    return True
