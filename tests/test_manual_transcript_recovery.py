"""Explicit transcript recovery reuses the paced read-only worker, never send paths."""

from __future__ import annotations

import os
import time
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


def _status(store: ResponseStore, send_id: str) -> object:
    row = store.get(send_id)
    assert row is not None
    return row["status"]


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
        assert store.next_history_recovery(now=8999) is not None  # No per-chat gate.
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
        # The live server runs orphan recovery concurrently: a 1970-era
        # deadline or a dead test PID would let it steal this dispatch lease.
        owner = f"{os.getpid()}:reply"
        claim_at = time.time()
        assert app.replies.claim(
            intent.reply_id, owner, deadline=claim_at + 100, now=claim_at,
        )
        assert app.replies.finish(
            intent.reply_id, owner, uncertain=True, now=claim_at + 1,
        )
        assert post_json(port, "/api/results/reply-run/manual-recover", {}) == (
            202, {"ok": True, "pending": 1},
        )
        assert store.pending_manual_recovery_requests() == ["reply:uncertain-followup"]
        original = store.get("reply-run")
        assert original is not None and original["status"] == "completed"
        followup = app.replies.get(intent.reply_id)
        assert followup is not None and followup["status"] == "outcome_unknown"


def test_requested_chat_is_next_without_local_delay_and_is_consumed_once(
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
    assert worker.recover_once(now=150)  # Explicit request has no local delay.
    newer = store.get("newer-backlog")
    older = store.get("older-requested")
    assert older is not None and older["status"] == "completed"
    assert newer is not None and newer["status"] == "interrupted"
    assert store.manual_recovery_pending("older-requested") == 0
    assert not worker.recover_once(now=239)  # The sole account-wide gate.
    assert worker.recover_once(now=240)
    recovered = store.get("newer-backlog")
    assert recovered is not None and recovered["status"] == "completed"
    assert seen == ["read", "read"]


def test_explicit_requests_get_slots_amid_permanently_eligible_pinned_backlog(
    tmp_path: Path,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    for send_id in ("requested-first", "requested-second", "pinned-old", "pinned-new"):
        _expired(store, send_id)
    assert store.set_local_pin("pinned-old", pinned=True)
    assert store.set_local_pin("pinned-new", pinned=True)
    assert store.queue_manual_recovery("requested-first", ["requested-first"], now=101) == 1
    assert store.queue_manual_recovery("requested-second", ["requested-second"], now=102) == 1
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, FakeHistoryDriver)

    # New manual requests each get a first attempt before repeated pinned probes;
    # one of every three slots remains available to automatic recovery.
    assert worker.recover_once(now=150)
    assert _status(store, "requested-first") == "completed"
    assert store.manual_recovery_pending("requested-first") == 0
    assert worker.recover_once(now=240)
    assert sum(_status(store, pinned) == "completed"
               for pinned in ("pinned-old", "pinned-new")) == 1
    assert worker.recover_once(now=330)
    assert _status(store, "requested-second") == "completed"
    assert store.manual_recovery_pending("requested-second") == 0
    assert worker.recover_once(now=420)
    assert _status(store, "pinned-old") == "completed"
    assert _status(store, "pinned-new") == "completed"
    assert store.history_recovery_global_attempt_count() == 4


def test_pinned_probe_consumes_matching_manual_request_even_when_not_selected(
    tmp_path: Path,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "pinned-target")
    assert store.set_local_pin("pinned-target", pinned=True)
    assert store.queue_manual_recovery("pinned-target", ["pinned-target"], now=100) == 1
    # The first slot was already used by another process; the next is pinned-first.
    assert store.reserve_history_recovery_global_slot(now=10, interval=90)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, FakeHistoryDriver)
    assert worker.recover_once(now=150)
    assert _status(store, "pinned-target") == "completed"
    assert store.manual_recovery_pending("pinned-target") == 0


def test_failed_requested_probe_remains_queued_for_eventual_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "incomplete-target")
    assert store.queue_manual_recovery("incomplete-target", ["incomplete-target"], now=100) == 1
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, FakeHistoryDriver)

    async def no_response(_conversation_id: str, _prompt: str) -> None:
        return None

    monkeypatch.setattr(worker, "_read_original_response", no_response)
    assert not worker.recover_once(now=150)
    assert _status(store, "incomplete-target") == "interrupted"
    assert store.manual_recovery_pending("incomplete-target") == 1
    assert store.history_recovery_global_attempt_count() == 1

    async def recovered(_conversation_id: str, _prompt: str) -> CaptureResult:
        return CaptureResult("dom", "complete", "Recovered", CONVERSATION, None, None, "observer")

    monkeypatch.setattr(worker, "_read_original_response", recovered)
    assert not worker.recover_once(now=239)
    assert worker.recover_once(now=240)
    assert _status(store, "incomplete-target") == "completed"
    assert store.manual_recovery_pending("incomplete-target") == 0


def test_manual_request_survives_temporary_live_capture(
    tmp_path: Path,
) -> None:
    from sqlalchemy import update

    from prompta.response_tables import results

    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "temporarily-live")
    store.queue_manual_recovery("temporarily-live", ["temporarily-live"], now=100)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, FakeHistoryDriver)

    # A surviving capture may temporarily own the turn after the request is
    # queued. That is not evidence that its answer has been recovered.
    with store.engine.begin() as connection:
        connection.execute(update(results).where(
            results.c.send_id == "temporarily-live",
        ).values(status="generating", capture_owner="123:live", capture_deadline=500))
    assert not worker.recover_once(now=150)
    assert store.manual_recovery_pending("temporarily-live") == 1

    with store.engine.begin() as connection:
        connection.execute(update(results).where(
            results.c.send_id == "temporarily-live",
        ).values(status="interrupted", capture_owner=""))
    assert worker.recover_once(now=240)
    assert _status(store, "temporarily-live") == "completed"
    assert store.manual_recovery_pending("temporarily-live") == 0


def test_failed_requested_probe_moves_behind_other_manual_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "first")
    _expired(store, "second")
    store.queue_manual_recovery("first", ["first"], now=100)
    store.queue_manual_recovery("second", ["second"], now=101)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, FakeHistoryDriver)
    attempts: list[str] = []

    async def read(_conversation_id: str, prompt: str) -> CaptureResult | None:
        attempts.append(prompt)
        if len(attempts) == 1:
            return None
        return CaptureResult("dom", "complete", "Recovered", CONVERSATION, None, None, "observer")

    monkeypatch.setattr(worker, "_read_original_response", read)
    assert not worker.recover_once(now=150)
    assert store.pending_manual_recovery_requests() == ["second", "first"]
    assert worker.recover_once(now=240)
    assert store.pending_manual_recovery_requests() == ["first"]
    assert _status(store, "first") == "interrupted"
    assert _status(store, "second") == "completed"


def test_new_manual_request_precedes_repeated_older_failure(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "older-failure")
    _expired(store, "fresh-request")
    store.queue_manual_recovery("older-failure", ["older-failure"], now=100)
    store.schedule_history_recovery("older-failure", now=101)
    store.queue_manual_recovery("fresh-request", ["fresh-request"], now=102)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, FakeHistoryDriver)

    assert worker.recover_once(now=150)
    assert _status(store, "fresh-request") == "completed"
    assert _status(store, "older-failure") == "interrupted"
    assert store.pending_manual_recovery_requests() == ["older-failure"]


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
                assert button.locator("svg[aria-hidden='true']").count() == 1
                assert page.locator(".chat-detail-content > .chat-manual-recovery").count() == 1
                button.click()
                expect(page.get_by_role("button", name="Recovery queued")).to_be_disabled()
                assert app.results.manual_recovery_pending("broken-ui") == 1
                page.reload()
                expect(page.get_by_role("button", name="Recovery queued")).to_be_disabled()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            finally:
                browser.close()


def test_recovery_button_hidden_while_chat_is_working(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        for status in ("queued", "accepted", "generating", "completed"):
            send_id = f"working-{status}"
            app.results.ensure_queued(send_id, "Working chat", now=10)
            if status != "queued":
                assert app.results.accept(send_id, "123:owner", deadline=100, now=11)
                assert app.results.bind_conversation_route(
                    send_id, "123:owner", "/c/" + CONVERSATION, now=12,
                )
            if status in ("generating", "completed"):
                capture = CaptureResult(
                    "sse", "partial" if status == "generating" else "complete",
                    "Assistant is responding" if status == "generating" else "Complete response",
                    CONVERSATION, "11111111-1111-4111-8111-111111111111", None,
                )
                assert app.results.write(send_id, "123:owner", capture, now=13)
                saved = app.results.get(send_id)
                assert saved is not None and saved["status"] == status

        with sync_playwright() as patchright:
            browser = patchright.chromium.launch(
                headless=True,
                executable_path=os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"),
            )
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                for status in ("queued", "accepted", "generating", "completed"):
                    page.goto(f"http://127.0.0.1:{port}/?view=chats&run=working-{status}")
                    expect(page.locator(".chat-detail-content")).to_be_visible()
                    expect(page.locator(".chat-manual-recovery")).to_have_count(0)
            finally:
                browser.close()
