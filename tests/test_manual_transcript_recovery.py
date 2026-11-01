"""Explicit transcript recovery reuses the paced read-only worker, never send paths."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from test_history_recovery import FakeHistoryDriver, _expired
from web_results_support import get, post_json, server

from prompta.history_recovery import HistoryRecovery
from prompta.reply_contracts import ReplyIntent
from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from prompta.scheduler_runtime import SchedulerRuntime

CONVERSATION = "12345678-1234-4123-8123-123456789abc"


def test_manual_recovery_endpoint_persists_one_request_without_resending(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        store = app.results
        _expired(store, "interrupted-chat")
        store.schedule_history_recovery(
            "interrupted-chat", now=100, next_attempt_at=9000,
        )
        assert post_json(port, "/api/results/interrupted-chat/manual-recover", {}) == (
            202, {"ok": True, "pending": 1},
        )
        assert post_json(port, "/api/results/interrupted-chat/manual-recover", {}) == (
            202, {"ok": True, "pending": 1},
        )
        assert store.pending_manual_recovery_requests() == ["interrupted-chat"]
        assert ResponseStore(store.path).manual_recovery_pending("interrupted-chat") == 1
        detail = get(port, "/api/results/interrupted-chat")[1]
        assert detail["manual_recovery_pending"] == 1
        assert store.next_history_recovery(now=8999) is None  # Never bypass per-chat pacing.
        assert app.queue.get("interrupted-chat") is None  # No fresh-send queue mutation.

        store.ensure_queued("unverified", "Private text", now=100)
        assert store.accept("unverified", "123:owner", deadline=200, now=101)
        assert store.finish("unverified", "123:owner", "interrupted", now=200)
        assert post_json(port, "/api/results/unverified/manual-recover", {})[0] == 409
        assert post_json(port, "/api/results/not-found/manual-recover", {})[0] == 404


def test_manual_recovery_targets_verified_uncertain_followup_only(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        store = app.results
        store.ensure_queued("reply-run", "Private original prompt", now=10)
        assert store.accept("reply-run", "123:owner", deadline=100, now=11)
        original_id = "11111111-1111-4111-8111-111111111111"
        assert store.write(
            "reply-run", "123:owner",
            CaptureResult("sse", "complete", "Full original answer", CONVERSATION, original_id, None),
            now=12,
        )
        intent = ReplyIntent("uncertain-followup", CONVERSATION, original_id, "Private follow-up")
        assert app.replies.prepare("reply-run", intent, now=13)["status"] == "prepared"
        assert app.replies.claim(intent.reply_id, "123:reply", deadline=100, now=14)
        assert app.replies.finish(intent.reply_id, "123:reply", uncertain=True, now=15)
        assert post_json(port, "/api/results/reply-run/manual-recover", {}) == (
            202, {"ok": True, "pending": 1},
        )
        assert store.pending_manual_recovery_requests() == ["reply:uncertain-followup"]
        original = store.get("reply-run")
        assert original is not None and original["status"] == "completed"
        followup = app.replies.get(intent.reply_id)
        assert followup is not None and followup["status"] == "outcome_unknown"


def test_requested_chat_is_next_when_due_and_is_consumed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "older-requested")
    _expired(store, "newer-backlog")
    store.schedule_history_recovery("older-requested", now=100, next_attempt_at=500)
    assert store.queue_manual_recovery("older-requested", ["older-requested"], now=101) == 1
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, FakeHistoryDriver)
    seen: list[str] = []

    async def read(_conversation_id: str, _prompt: str) -> CaptureResult:
        seen.append("read")
        return CaptureResult("dom", "complete", "Recovered", CONVERSATION, None, None, "observer")

    monkeypatch.setattr(worker, "_read_original_response", read)
    assert worker.recover_once(now=150)  # The request is still under backoff.
    newer = store.get("newer-backlog")
    older = store.get("older-requested")
    assert newer is not None and newer["status"] == "completed"
    assert older is not None and older["status"] == "interrupted"
    assert store.manual_recovery_pending("older-requested") == 1
    assert not worker.recover_once(now=151)  # 90-second global pace.
    assert worker.recover_once(now=500)
    recovered = store.get("older-requested")
    assert recovered is not None and recovered["status"] == "completed"
    assert store.manual_recovery_pending("older-requested") == 0
    assert seen == ["read", "read"]


@pytest.mark.parametrize("width,height", [(360, 800), (390, 844), (412, 915), (1440, 900)])
def test_recovery_button_lives_after_transcript_and_survives_reload(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (app, port):
        _expired(app.results, "broken-ui")
        with sync_playwright() as patchright:
            browser = patchright.chromium.launch(
                headless=True,
                executable_path=os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"),
            )
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(f"http://127.0.0.1:{port}/?view=chats&run=broken-ui")
                button = page.get_by_role("button", name="Recover chat")
                expect(button).to_be_visible()
                assert page.locator(".chat-detail-content > .chat-manual-recovery").count() == 1
                button.click()
                expect(page.get_by_role("button", name="Recovery queued")).to_be_disabled()
                assert app.results.manual_recovery_pending("broken-ui") == 1
                page.reload()
                expect(page.get_by_role("button", name="Recovery queued")).to_be_disabled()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            finally:
                browser.close()
