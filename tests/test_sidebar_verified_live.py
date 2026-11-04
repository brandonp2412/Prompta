"""Sidebar follows a verified live follow-up, not an orphaned capture lease."""

from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import select, update

from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.reply_tables import replies as reply_table
from prompta.response_capture import CaptureResult, normalize_dom_snapshot
from prompta.response_store import ResponseStore
from prompta.response_tables import results as result_table

CONVERSATION = "12345678-1234-4123-8123-123456789abc"
ORIGINAL = "11111111-1111-4111-8111-111111111111"
FOLLOWUP = "remux-followup"


def _interrupted_chain(tmp_path: Path) -> tuple[ResponseStore, ManualReplyStore]:
    path = tmp_path / "results.sqlite3"
    responses = ResponseStore(path)
    replies = ManualReplyStore(path)
    responses.ensure_queued("remux", "Original prompt", now=10)
    assert responses.accept("remux", "123:original", deadline=200, now=11)
    assert responses.write(
        "remux", "123:original",
        CaptureResult("sse", "complete", "Original finished answer", CONVERSATION, ORIGINAL, None),
        now=12,
    )
    # The earlier worker was interrupted locally, although ChatGPT finished it.
    with responses.engine.begin() as connection:
        connection.execute(update(result_table).where(result_table.c.send_id == "remux").values(
            status="interrupted",
        ))
    intent = ReplyIntent(FOLLOWUP, CONVERSATION, ORIGINAL, "Increase server timeout")
    assert replies.prepare("remux", intent, now=13)["status"] == "prepared"
    assert replies.claim(FOLLOWUP, "123:reply", deadline=200, now=14)
    assert replies.finish(FOLLOWUP, "123:reply", now=15)
    return responses, replies


def test_verified_running_followup_overrides_old_interruption_and_expires(tmp_path: Path) -> None:
    responses, replies = _interrupted_chain(tmp_path)
    assert responses.page(status="needs_attention")["total"] == 1
    now = time.time()
    assert replies.recover_historical_reply(
        FOLLOWUP,
        CaptureResult(
            "dom", "unknown", "", CONVERSATION, None, ORIGINAL,
            observer_id="fallback-turn-1:1:assistant",
            tool_calls=({"action": "Used Tool", "status": "running"},),
            verified_generating=True,
        ),
        now=now,
    )
    # Browser evidence changes only the display, never the durable capture claim.
    with replies.engine.connect() as connection:
        assert connection.execute(select(reply_table.c.status).where(
            reply_table.c.reply_id == FOLLOWUP,
        )).scalar_one() == "interrupted"
    saved = replies.get(FOLLOWUP)
    turns = replies.turns("remux")
    assert saved is not None and saved["status"] == "generating"
    assert turns is not None and turns[-1]["status"] == "generating"
    assert responses.page(status="needs_attention")["total"] == 0
    items = responses.page()["items"]
    replies.annotate_response_markers(items)
    assert items[0]["status"] == "generating"
    assert items[0]["needs_attention"] is False

    # A dead orphan cannot remain 'Generating' after the verified signal ages out.
    with replies.engine.begin() as connection:
        connection.execute(update(reply_table).where(reply_table.c.reply_id == FOLLOWUP).values(
            live_observed_at=now - 901,
        ))
    expired = replies.get(FOLLOWUP)
    assert expired is not None and expired["status"] == "interrupted"
    assert responses.page(status="needs_attention")["total"] == 1


def test_finished_followup_clears_sidebar_attention_from_old_original(tmp_path: Path) -> None:
    responses, replies = _interrupted_chain(tmp_path)
    assert replies.recover_historical_reply(
        FOLLOWUP,
        CaptureResult(
            "dom", "complete", "Longer warmup timeout committed", CONVERSATION,
            "22222222-2222-4222-8222-222222222222", ORIGINAL, "reply-unit",
        ),
        now=25,
    )
    assert responses.page(status="needs_attention")["total"] == 0
    items = responses.page()["items"]
    replies.annotate_response_markers(items)
    assert items[0]["status"] == "completed"
    assert items[0]["needs_attention"] is False


def test_queued_followup_is_distinguished_from_queued_fresh_chat(tmp_path: Path) -> None:
    responses = ResponseStore(tmp_path / "results.sqlite3")
    replies = ManualReplyStore(responses.path)
    responses.ensure_queued("pending-chat", "Original prompt", now=10)

    fresh = responses.page()["items"]
    replies.annotate_response_markers(fresh)
    assert fresh[0]["status"] == "queued"
    assert fresh[0]["queued_followup"] is False

    saved = replies.queue_followup("pending-chat", "queued-followup-12345678", "Continue", now=11)
    assert saved["status"] == "queued"
    queued = responses.page()["items"]
    replies.annotate_response_markers(queued)
    assert queued[0]["status"] == "queued"
    assert queued[0]["queued_followup"] is True
    assert queued[0]["needs_attention"] is False

    with replies.engine.begin() as connection:
        connection.execute(update(reply_table).where(
            reply_table.c.reply_id == "queued-followup-12345678",
        ).values(status="completed"))
    completed = responses.page()["items"]
    replies.annotate_response_markers(completed)
    assert completed[0]["queued_followup"] is False


def test_dom_live_signal_requires_explicit_generating_state() -> None:
    payload = {
        "message_id": "fallback-turn-1:1:assistant",
        "pathname": "/c/" + CONVERSATION,
        "verified_parent_id": ORIGINAL,
        "text": "Still checking",
        "complete": False,
    }
    assert normalize_dom_snapshot(payload).verified_generating is False
    assert normalize_dom_snapshot({**payload, "generating": True}).verified_generating is True
    assert normalize_dom_snapshot({**payload, "generating": True, "complete": True}).verified_generating is False


def test_recovered_original_is_generating_until_observation_expires(tmp_path: Path) -> None:
    responses = ResponseStore(tmp_path / "results.sqlite3")
    replies = ManualReplyStore(responses.path)
    responses.ensure_queued("original-live", "Original prompt", now=10)
    assert responses.accept("original-live", "123:original", deadline=200, now=11)
    with responses.engine.begin() as connection:
        connection.execute(update(result_table).where(
            result_table.c.send_id == "original-live",
        ).values(status="interrupted", conversation_id=CONVERSATION, capture_owner=""))
    now = time.time()
    capture = CaptureResult(
        "dom", "partial", "Implementing the patch", CONVERSATION, None, None,
        observer_id="fallback-turn-0:activity:assistant", verified_generating=True,
    )
    assert responses.recover_historical_response("original-live", capture, now=now)
    items = responses.page()["items"]
    replies.annotate_response_markers(items)
    assert items[0]["status"] == "generating"
    assert items[0]["needs_attention"] is False
    detail = responses.detail("original-live")
    assert detail is not None
    replies.annotate_response_markers([detail])
    assert detail["status"] == "generating"
    turns = replies.turns("original-live")
    assert turns is not None and turns[0]["status"] == "generating"
    assert responses.page(status="needs_attention")["total"] == 0
    # A virtualized snapshot can be shorter without making a verified active
    # capture fail or truncating the saved progress.
    assert responses.recover_historical_response(
        "original-live",
        CaptureResult("dom", "partial", "Short live update", CONVERSATION, None, None,
                      observer_id="fallback-turn-0:activity:assistant", verified_generating=True),
    )
    saved = responses.get("original-live")
    assert saved is not None and saved["assistant_text"] == "Implementing the patch"
    # Keep recovery eligible while the visible status reflects live capture.
    assert responses.next_history_recovery(priority_ids=("original-live",)) is not None
    with responses.engine.begin() as connection:
        connection.execute(update(result_table).where(
            result_table.c.send_id == "original-live",
        ).values(live_observed_at=now - 901))
    items = responses.page()["items"]
    replies.annotate_response_markers(items)
    assert items[0]["status"] == "interrupted"
    assert responses.page(status="needs_attention")["total"] == 1
    # Reading old partial text without active generation cannot restore live status.
    assert responses.recover_historical_response(
        "original-live",
        CaptureResult("dom", "partial", "Implementing the patch", CONVERSATION, None, None,
                      observer_id="fallback-turn-0:activity:assistant"),
    )
    items = responses.page()["items"]
    replies.annotate_response_markers(items)
    assert items[0]["status"] == "interrupted"
