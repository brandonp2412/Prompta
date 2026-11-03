from __future__ import annotations

import os
import sqlite3
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import event, inspect, update

from prompta.browser_ownership import (
    MAX_OWNED_TAB_AGE_SECONDS,
    owned_tab_records,
    record_owned_tab,
    touch_owned_tab,
)
from prompta.reply_contracts import ManualReplyStore, ReplyConflict, ReplyIntent
from prompta.response_capture import CaptureResult

CONVERSATION = "conversation-1234567890"
PARENT = "assistant-1234567890"
REPLY_ID = "reply-1234567890123"
MESSAGE = "assistant-2222222222"


def seed(tmp_path: Path) -> ManualReplyStore:
    store = ManualReplyStore(tmp_path / "private" / "chat-results.sqlite3")
    results = store.responses
    results.ensure_queued("run", "Initial private prompt", now=100)
    assert results.accept("run", "10:initial", deadline=300, now=101)
    assert results.write("run", "10:initial", CaptureResult(
        "sse", "complete", "Initial private answer", CONVERSATION, PARENT, "user-1234567890123"
    ), now=102)
    return store


def intent(reply_id: str = REPLY_ID, parent_id: str = PARENT, text: str = "Manual reply") -> ReplyIntent:
    return ReplyIntent(reply_id, CONVERSATION, parent_id, text)


def test_deploy_reply_recovers_without_releasing_chat_slot(tmp_path: Path) -> None:
    store = seed(tmp_path)
    store.prepare("run", intent(), now=150)
    assert store.claim(REPLY_ID, "999999999:dead", deadline=10000, now=151)
    assert store.accepted(
        REPLY_ID, "999999999:dead", conversation_id=CONVERSATION,
        parent_id=PARENT, message_id=MESSAGE, now=152,
    )
    store.responses.prepare_deployment_recovery((), (REPLY_ID,), now=160)
    assert store.recover_orphans(now=161) == 0
    assert store.responses.active_capture_send_ids(now=1059) == {"run"}
    candidate = store.next_history_reply_recovery(now=161)
    assert candidate is not None and candidate["reply_id"] == REPLY_ID
    assert store.observe_history_loaded(REPLY_ID, CONVERSATION, PARENT, now=900)
    assert store.recover_orphans(now=1060) == 0
    assert store.recover_historical_reply(
        REPLY_ID, CaptureResult(
            "dom", "partial", "", CONVERSATION, MESSAGE, PARENT, verified_generating=True,
        ), now=1000,
    )
    assert store.recover_orphans(now=1060) == 0
    assert store.responses.active_capture_send_ids(now=1899) == {"run"}
    assert store.recover_orphans(now=1900) == 1
    assert store.responses.active_capture_send_ids(now=1900) == set()


def test_migration_permissions_and_explicit_intent_validation(tmp_path: Path) -> None:
    from prompta.response_store import ResponseStore

    path = tmp_path / "private" / "chat-results.sqlite3"
    ResponseStore(path)  # old schema: migration must preserve it
    store = seed(tmp_path)
    assert "job_responses" in inspect(store.engine).get_table_names()
    assert "manual_reply_turns" in inspect(store.engine).get_table_names()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    with pytest.raises(ValueError):
        ReplyIntent.parse({"reply_id": REPLY_ID, "conversation_id": CONVERSATION,
                           "parent_id": PARENT, "text": "", "extra": "surprise"})
    with pytest.raises(ValueError):
        ReplyIntent.parse({"reply_id": REPLY_ID, "conversation_id": CONVERSATION,
                           "parent_id": PARENT, "text": ""})
    assert store.turns("absent") is None


def test_early_followups_wait_for_verified_parent_and_dispatch_in_order(tmp_path: Path) -> None:
    store = ManualReplyStore(tmp_path / "private" / "chat-results.sqlite3")
    store.responses.ensure_queued("run", "Original question", now=100)
    first = "queued-1111111111111111"
    second = "queued-2222222222222222"
    assert store.queue_followup("run", first, "One more question", now=101)["status"] == "queued"
    assert store.queue_followup("run", second, "And a second", now=102)["status"] == "queued"
    assert store.queue_followup("run", first, "One more question", now=103)["reply_id"] == first
    with pytest.raises(ReplyConflict, match="Idempotency"):
        store.queue_followup("run", first, "Different text")
    assert store.next_queued_intent(now=103) is None
    assert [turn["status"] for turn in store.turns("run") or []] == ["queued", "queued", "queued"]

    assert store.responses.accept("run", "10:initial", deadline=300, now=104)
    assert store.next_queued_intent(now=105) is None
    assert store.responses.write("run", "10:initial", CaptureResult(
        "sse", "complete", "Initial answer", CONVERSATION, PARENT, "user-1234567890123",
    ), now=106)
    ready = store.next_queued_intent(now=107)
    assert ready == ("run", ReplyIntent(first, CONVERSATION, PARENT, "One more question"))
    assert store.next_queued_intent(exclude={first}, now=108) is None
    # Restart after preparing, but before claiming the browser send: safe to resume.
    restored = ManualReplyStore(store.responses.path)
    assert restored.next_queued_intent(now=109) == ready
    assert restored.claim(first, "123:worker", deadline=300, now=110)
    assert restored.accepted(
        first, "123:worker", conversation_id=CONVERSATION, parent_id=PARENT,
        message_id=MESSAGE, now=111,
    )
    assert restored.observe(first, "123:worker", CaptureResult(
        "sse", "complete", "First follow-up answer", CONVERSATION, MESSAGE, PARENT,
    ), now=112)
    assert restored.next_queued_intent(now=113) == (
        "run", ReplyIntent(second, CONVERSATION, MESSAGE, "And a second"),
    )
    assert [turn["user_text"] for turn in restored.turns("run") or []] == [
        "Original question", "One more question", "And a second",
    ]


def test_reply_work_duration_excludes_queue_and_preserves_first_acceptance(tmp_path: Path) -> None:
    store = seed(tmp_path)
    store.prepare("run", intent(), now=150)
    assert store.claim(REPLY_ID, "123:reply", deadline=400, now=190)
    assert store.acknowledge_submission(
        REPLY_ID, "123:reply", conversation_id=CONVERSATION, parent_id=PARENT, now=200,
    )
    assert store.accepted(
        REPLY_ID, "123:reply", conversation_id=CONVERSATION, parent_id=PARENT,
        message_id=MESSAGE, now=205,
    )
    assert store.observe(REPLY_ID, "123:reply", CaptureResult(
        "sse", "complete", "Finished answer", CONVERSATION, MESSAGE, PARENT,
    ), now=267)
    latest = (store.turns("run") or [])[-1]
    assert latest["status"] == "completed"
    assert latest["created_at"] == 150
    assert latest["accepted_at"] == 200
    assert latest["finished_at"] == 267
    assert latest["updated_at"] == 267


def test_queued_dispatch_scans_many_blocked_chats_in_two_selects(tmp_path: Path) -> None:
    store = seed(tmp_path)
    for index in range(12):
        send_id = f"missing-parent-{index}"
        store.responses.ensure_queued(send_id, "Original question", now=100 + index)
        assert store.responses.accept(send_id, f"{index}:initial", deadline=300, now=120 + index)
        assert store.responses.write(
            send_id, f"{index}:initial",
            CaptureResult(
                "dom", "complete", "Answer with missing identity", CONVERSATION,
                None, None, "rendered:assistant",
            ), now=140 + index,
        )
        store.queue_followup(
            send_id, f"blocked-followup-{index:016d}", "Continue", now=200 + index,
        )
    ready_id = "ready-followup-111111111"
    store.queue_followup("run", ready_id, "Ready to send", now=300)

    selects: list[str] = []

    def count_select(connection, cursor, statement, parameters, context, executemany) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(store.engine, "before_cursor_execute", count_select)
    try:
        ready = store.next_queued_intent(now=400)
    finally:
        event.remove(store.engine, "before_cursor_execute", count_select)

    assert ready == ("run", ReplyIntent(ready_id, CONVERSATION, PARENT, "Ready to send"))
    assert len(selects) == 2  # One read-only lineage check, then one under the writer lock.
    for index in range(12):
        blocked = store.get(f"blocked-followup-{index:016d}")
        assert blocked is not None
        assert blocked["status"] == "queued"


def test_blocked_queued_reply_scan_does_not_wait_for_a_writer(tmp_path: Path) -> None:
    store = ManualReplyStore(tmp_path / "private" / "chat-results.sqlite3")
    store.responses.ensure_queued("awaiting-parent", "Question", now=100)
    store.queue_followup("awaiting-parent", "queued-1111111111111111", "Continue", now=101)

    # An unrelated delivery/database write can be in progress every time
    # the one-second queue pump wakes up. Blocked parents are read-only.
    writer = sqlite3.connect(store.responses.path, timeout=0.1, isolation_level=None)
    try:
        writer.execute("BEGIN IMMEDIATE")
        assert store.next_queued_intent(now=102) is None
    finally:
        writer.rollback()
        writer.close()

    queued = store.get("queued-1111111111111111")
    assert queued is not None and queued["status"] == "queued"


def test_queued_reply_with_unresolved_predecessor_never_takes_writer_lock(
    tmp_path: Path,
) -> None:
    store = seed(tmp_path)
    first = "queued-first-111111111111"
    second = "queued-second-22222222222"
    store.queue_followup("run", first, "First follow-up", now=200)
    store.queue_followup("run", second, "Second follow-up", now=201)
    ready = store.next_queued_intent(now=202)
    assert ready == ("run", ReplyIntent(first, CONVERSATION, PARENT, "First follow-up"))
    assert store.claim(first, "active:worker", deadline=400, now=203)

    # The first follow-up is in flight. An unrelated writer must never
    # stall the one-second pump while the second waits for its answer.
    writer = sqlite3.connect(store.responses.path, timeout=0.1, isolation_level=None)
    try:
        writer.execute("BEGIN IMMEDIATE")
        assert store.next_queued_intent(now=204) is None
        assert store.next_queued_intent(exclude={second}, now=204) is None
    finally:
        writer.rollback()
        writer.close()

    queued = store.get(second)
    assert queued is not None and queued["status"] == "queued"


def test_explicit_queue_pump_waits_for_first_answer_and_serializes_followups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prompta.manual_reply_dispatch import ManualReplyDispatcher

    store = ManualReplyStore(tmp_path / "private" / "chat-results.sqlite3")
    store.responses.ensure_queued("run", "Initial prompt", now=100)
    first = "queued-pump-111111111111"
    second = "queued-pump-222222222222"
    store.queue_followup("run", first, "First", now=101)
    store.queue_followup("run", second, "Second", now=102)
    dispatcher = ManualReplyDispatcher(store, tmp_path / "state.sqlite3")
    submitted: list[ReplyIntent] = []

    def fake_submit(send_id: str, submission: ReplyIntent) -> dict[str, object]:
        assert send_id == "run"
        assert store.claim(submission.reply_id, "123:worker", deadline=400, now=110)
        submitted.append(submission)
        return {"status": "dispatching"}

    monkeypatch.setattr(dispatcher, "submit", fake_submit)
    dispatcher.pump_queued()
    assert submitted == []

    assert store.responses.accept("run", "10:initial", deadline=400, now=103)
    assert store.responses.write("run", "10:initial", CaptureResult(
        "sse", "complete", "Initial answer", CONVERSATION, PARENT, "user-1234567890123",
    ), now=104)
    dispatcher.pump_queued()
    assert submitted == [ReplyIntent(first, CONVERSATION, PARENT, "First")]
    dispatcher.pump_queued()
    assert len(submitted) == 1
    assert store.accepted(
        first, "123:worker", conversation_id=CONVERSATION,
        parent_id=PARENT, message_id=MESSAGE, now=112,
    )
    assert store.observe(first, "123:worker", CaptureResult(
        "sse", "complete", "First answer", CONVERSATION, MESSAGE, PARENT,
    ), now=113)
    dispatcher.pump_queued()
    assert submitted[-1] == ReplyIntent(second, CONVERSATION, MESSAGE, "Second")


def test_queued_reply_pump_respects_active_dispatch_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prompta.manual_reply_dispatch import ManualReplyDispatcher

    store = ManualReplyStore(tmp_path / "private" / "chat-results.sqlite3")
    for index in range(3):
        send_id = f"capacity-run-{index}"
        store.responses.ensure_queued(send_id, "Private prompt", now=100 + index)
        assert store.responses.accept(send_id, "initial", deadline=200, now=110 + index)
        assert store.responses.write(send_id, "initial", CaptureResult(
            "sse", "complete", "Initial answer", CONVERSATION, PARENT, "initial-user",
        ), now=120 + index)
        store.queue_followup(
            send_id, f"capacity-reply-{index}-00000000", "Explicit queued reply", now=130 + index,
        )

    dispatcher = ManualReplyDispatcher(store, tmp_path / "state.sqlite3")
    started: list[str] = []

    def fake_submit(send_id: str, submission: ReplyIntent) -> dict[str, object]:
        now = time.time()
        assert store.claim(submission.reply_id, "worker", deadline=now + 120, now=now)
        dispatcher._active.add(submission.reply_id)
        started.append(send_id)
        return {"status": "dispatching"}

    monkeypatch.setattr(dispatcher, "submit", fake_submit)
    dispatcher.pump_queued()
    assert len(started) == 2
    dispatcher.pump_queued()
    assert len(started) == 2

    dispatcher._active.remove("capacity-reply-0-00000000")
    dispatcher.pump_queued()
    assert len(started) == 3
    assert len(set(started)) == 3


def test_exact_branch_idempotency_and_concurrent_intents(tmp_path: Path) -> None:
    store = seed(tmp_path)
    with pytest.raises(ReplyConflict, match="different"):
        store.prepare("run", intent(parent_id="assistant-wrong-123456789"), now=200)
    candidates = [intent("reply-00000000000000" + str(i)) for i in range(6)]

    def attempt(candidate: ReplyIntent) -> str:
        try:
            return str(store.prepare("run", candidate, now=200)["reply_id"])
        except ReplyConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, candidates))
    assert results.count("conflict") == 5
    winner = next(result for result in results if result != "conflict")
    winning_intent = next(candidate for candidate in candidates if candidate.reply_id == winner)
    assert store.prepare("run", winning_intent, now=210)["reply_id"] == winner
    with pytest.raises(ReplyConflict, match="Idempotency"):
        store.prepare("run", intent(winner, text="Changed message"), now=210)
    assert len(store.turns("run") or []) == 2
    turns = store.turns("run")
    assert turns is not None and turns[1]["status"] == "prepared"


def test_single_claim_proven_branch_terminal_and_second_turn(tmp_path: Path) -> None:
    store = seed(tmp_path)
    assert store.prepare("run", intent(), now=200)["status"] == "prepared"
    owner = f"{os.getpid()}:manual"
    assert store.claim(REPLY_ID, owner, deadline=400, now=201)
    assert not store.claim(REPLY_ID, owner, deadline=400, now=202)
    assert not store.accepted(REPLY_ID, "other", conversation_id=CONVERSATION,
                              parent_id=PARENT, message_id=MESSAGE, now=203)
    assert not store.accepted(REPLY_ID, owner, conversation_id="wrong", parent_id=PARENT,
                              message_id=MESSAGE, now=203)
    assert store.accepted(REPLY_ID, owner, conversation_id=CONVERSATION,
                          parent_id=PARENT, message_id=MESSAGE, now=203)
    assert not store.observe(REPLY_ID, owner, CaptureResult(
        "dom", "complete", "Wrong branch", CONVERSATION, "wrong", PARENT
    ), now=204)
    assert store.observe(REPLY_ID, owner, CaptureResult(
        "dom", "partial", "Partial reply", CONVERSATION, MESSAGE, PARENT
    ), now=205)
    assert not store.observe(REPLY_ID, owner, CaptureResult(
        "dom", "partial", "Short", CONVERSATION, MESSAGE, PARENT
    ), now=206)
    assert store.observe(REPLY_ID, owner, CaptureResult(
        "sse", "complete", "Complete reply", CONVERSATION, MESSAGE, PARENT
    ), now=207)
    assert not store.observe(REPLY_ID, owner, CaptureResult(
        "sse", "complete", "Changed answer", CONVERSATION, MESSAGE, PARENT
    ), now=208)
    assert store.prepare("run", intent("reply-99999999999999", MESSAGE), now=209)["status"] == "prepared"
    turns = store.turns("run")
    assert turns is not None
    assert turns[1]["assistant_text"] == "Complete reply"
    assert turns[2]["parent_id"] == MESSAGE
    assert store.recover_orphans(now=999) == 0


def test_verified_submission_is_not_unknown_when_generation_interrupts(tmp_path: Path) -> None:
    store = seed(tmp_path)
    assert store.prepare("run", intent(), now=200)["status"] == "prepared"
    owner = f"{os.getpid()}:submitted"
    assert store.claim(REPLY_ID, owner, deadline=400, now=201)
    assert not store.acknowledge_submission(
        REPLY_ID, "wrong-owner", conversation_id=CONVERSATION, parent_id=PARENT, now=202,
    )
    assert not store.acknowledge_submission(
        REPLY_ID, owner, conversation_id="wrong", parent_id=PARENT, now=202,
    )
    assert store.acknowledge_submission(
        REPLY_ID, owner, conversation_id=CONVERSATION, parent_id=PARENT, now=202,
    )
    turns = store.turns("run")
    assert turns is not None and turns[-1]["status"] == "accepted"
    assert turns[-1]["message_id"] == ""
    assert not store.acknowledge_submission(
        REPLY_ID, owner, conversation_id=CONVERSATION, parent_id=PARENT, now=203,
    )
    assert store.finish(REPLY_ID, owner, uncertain=True, now=204)
    turns = store.turns("run")
    assert turns is not None and turns[-1]["status"] == "interrupted"
    assert not store.claim(REPLY_ID, owner, deadline=500, now=205)


def test_verified_submission_can_bind_a_later_assistant_message(tmp_path: Path) -> None:
    store = seed(tmp_path)
    store.prepare("run", intent(), now=200)
    owner = f"{os.getpid()}:submitted"
    assert store.claim(REPLY_ID, owner, deadline=400, now=201)
    assert store.acknowledge_submission(
        REPLY_ID, owner, conversation_id=CONVERSATION, parent_id=PARENT, now=202,
    )
    assert store.accepted(
        REPLY_ID, owner, conversation_id=CONVERSATION,
        parent_id=PARENT, message_id=MESSAGE, now=203,
    )
    assert store.observe(REPLY_ID, owner, CaptureResult(
        "dom", "complete", "Final reply", CONVERSATION, MESSAGE, None,
    ), now=204)
    turns = store.turns("run")
    assert turns is not None and turns[-1]["status"] == "completed"
    assert turns[-1]["assistant_text"] == "Final reply"


def test_reply_retains_commentary_after_final_dom_reindexes_text(tmp_path: Path) -> None:
    store = seed(tmp_path)
    store.prepare("run", intent(), now=200)
    owner = f"{os.getpid()}:commentary"
    assert store.claim(REPLY_ID, owner, deadline=400, now=201)
    assert store.acknowledge_submission(
        REPLY_ID, owner, conversation_id=CONVERSATION, parent_id=PARENT, now=202,
    )
    assert store.accepted(
        REPLY_ID, owner, conversation_id=CONVERSATION,
        parent_id=PARENT, message_id=MESSAGE, now=203,
    )
    assert store.observe(REPLY_ID, owner, CaptureResult(
        "dom", "partial", "OPENING", CONVERSATION, MESSAGE, None,
        display_blocks=({"kind": "text", "id": "text-0", "text": "OPENING"},),
    ), now=204)
    assert store.observe(REPLY_ID, owner, CaptureResult(
        "dom", "complete", "FINISH", CONVERSATION, MESSAGE, None,
        display_blocks=({"kind": "text", "id": "text-0", "text": "FINISH"},),
    ), now=205)
    turns = store.turns("run")
    assert turns is not None and turns[-1]["status"] == "completed"
    assert turns[-1]["assistant_text"] == "OPENING\n\nFINISH"
    assert turns[-1]["display_blocks"] == [
        {"kind": "text", "id": "text-0", "text": "OPENING"},
        {"kind": "text", "id": "text-1", "text": "FINISH"},
    ]


def test_ambiguous_claim_crash_and_partial_recovery_never_resend(tmp_path: Path) -> None:
    store = seed(tmp_path)
    store.prepare("run", intent(), now=200)
    assert store.claim(REPLY_ID, "99999999:dead", deadline=400, now=201)
    assert store.recover_orphans(now=202) == 1
    turns = store.turns("run")
    assert turns is not None and turns[1]["status"] == "outcome_unknown"
    assert not store.claim(REPLY_ID, "other", deadline=500, now=203)
    with pytest.raises(ReplyConflict, match="unresolved"):
        store.prepare("run", intent("reply-99999999999999"), now=204)
    restored = ManualReplyStore(store.responses.path).turns("run")
    assert restored is not None and restored[1]["status"] == "outcome_unknown"


def test_reply_orphan_probe_does_not_hold_a_sqlite_writer_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = seed(tmp_path)
    store.prepare("run", intent(), now=200)
    assert store.claim(REPLY_ID, "99999999:dead", deadline=400, now=201)

    def dead_worker(pid: int, signal: int) -> None:
        assert (pid, signal) == (99999999, 0)
        # A concurrent store write must succeed during the process-liveness
        # probe, not wait on an open orphan-recovery transaction.
        store.responses.ensure_queued("unrelated", "Concurrent prompt", now=202)
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", dead_worker)
    assert store.recover_orphans(now=202) == 1
    assert store.responses.get("unrelated") is not None
    turns = store.turns("run")
    assert turns is not None and turns[-1]["status"] == "outcome_unknown"
    assert not store.claim(REPLY_ID, "new:owner", deadline=500, now=203)


def test_reply_orphan_recovery_preserves_live_accepted_leases(tmp_path: Path) -> None:
    store = seed(tmp_path)
    store.prepare("run", intent(), now=200)
    owner = f"{os.getpid()}:live"
    assert store.claim(REPLY_ID, owner, deadline=400, now=201)
    assert store.acknowledge_submission(
        REPLY_ID, owner, conversation_id=CONVERSATION, parent_id=PARENT, now=202,
    )
    assert store.recover_orphans(now=203) == 0
    turns = store.turns("run")
    assert turns is not None and turns[-1]["status"] == "accepted"
    assert store.recover_orphans(now=401) == 1
    turns = store.turns("run")
    assert turns is not None and turns[-1]["status"] == "interrupted"


def test_capture_deadline_extends_only_verified_live_owner(tmp_path: Path) -> None:
    from prompta.response_store import ResponseStore

    store = ResponseStore(tmp_path / "results.sqlite3")
    store.ensure_queued("test", "prompt", now=100)
    assert store.accept("test", "10:owner", deadline=200, now=101)
    assert not store.renew_capture_deadline("test", "other", deadline=300, now=102)
    assert store.renew_capture_deadline("test", "10:owner", deadline=300, now=102)
    assert not store.renew_capture_deadline("test", "10:owner", deadline=250, now=103)
    assert store.write("test", "10:owner", CaptureResult(
        "dom", "partial", "Partial", CONVERSATION, PARENT, "user-1234567890123"
    ), now=250)
    assert not store.renew_capture_deadline("test", "10:owner", deadline=400, now=301)


def test_verified_idle_lease_legacy_migration_and_no_resurrection(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "tabs.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE owned_tabs (target_id TEXT PRIMARY KEY, opened_at REAL NOT NULL)")
        conn.execute("INSERT INTO owned_tabs VALUES ('legacy', 100)")
    assert owned_tab_records(path) == {"legacy": 100}
    record_owned_tab("owned", 200, path)
    record_owned_tab("owned", 230, path)  # polling/navigation must not refresh activity
    assert owned_tab_records(path)["owned"] == 200
    assert touch_owned_tab("owned", 210, path)
    assert owned_tab_records(path)["owned"] == 210
    assert not touch_owned_tab("owned", 209, path)
    assert not touch_owned_tab("missing", 300, path)
    assert not touch_owned_tab("owned", 210 + MAX_OWNED_TAB_AGE_SECONDS + 1, path)
    assert owned_tab_records(path)["owned"] == 210


def test_original_parent_recovery_requires_exact_saved_answer_and_is_one_time(
    tmp_path: Path,
) -> None:
    original = ManualReplyStore(tmp_path / "recover.sqlite3")
    original.responses.ensure_queued("run", "Original prompt", now=10)
    assert original.responses.accept("run", "test:owner", deadline=100, now=11)
    conversation = "00000000-0000-4000-8000-000000000001"
    message = "00000000-0000-4000-8000-000000000002"
    assert original.responses.write(
        "run", "test:owner",
        CaptureResult("dom", "complete", "Original answer", conversation,
                      None, None, "rendered:assistant"), now=12,
    )
    assert not original.recover_original_parent("run", conversation, message, "Wrong answer")
    assert not original.recover_original_parent("run", message, message, "Original answer")
    assert not original.recover_original_parent("run", conversation, "not-an-id", "Original answer")
    assert original.recover_original_parent("run", conversation, message, "Original answer")
    saved_turns = original.turns("run")
    assert saved_turns is not None and saved_turns[0]["message_id"] == message
    assert not original.recover_original_parent("run", conversation, message, "Original answer")
    prepared = original.prepare(
        "run", ReplyIntent("reply-1234567890123", conversation, message, "Follow-up")
    )
    assert prepared["status"] == "prepared"


def test_accepted_post_dom_answer_preserves_unknown_response_parent(
    tmp_path: Path,
) -> None:
    store = seed(tmp_path)
    assert store.prepare("run", intent(), now=200)["status"] == "prepared"
    owner = f"{os.getpid()}:dom"
    assert store.claim(REPLY_ID, owner, deadline=400, now=201)
    assert store.accepted(
        REPLY_ID, owner, conversation_id=CONVERSATION,
        parent_id=PARENT, message_id=MESSAGE, response_parent_id="", now=202,
    )
    assert not store.observe(
        REPLY_ID, owner, CaptureResult("sse", "complete", "SSE without parent",
                                       CONVERSATION, MESSAGE, None), now=203,
    )
    assert not store.observe(
        REPLY_ID, owner, CaptureResult("dom", "complete", "Wrong answer",
                                       CONVERSATION, "different-message", None), now=203,
    )
    assert store.observe(
        REPLY_ID, owner, CaptureResult("dom", "complete", "DOM verified answer",
                                       CONVERSATION, MESSAGE, None, "unit:assistant"),
        now=204,
    )
    turns = store.turns("run")
    assert turns is not None and turns[-1]["status"] == "completed"


def test_terminal_original_capture_with_verified_parent_can_continue(tmp_path: Path) -> None:
    for status in ("interrupted", "unavailable"):
        store = seed(tmp_path / status)
        with store.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE job_responses SET status = ? WHERE send_id = 'run'", (status,),
            )
        prepared = store.prepare("run", intent(), now=200)
        assert prepared["status"] == "prepared"


def test_interrupted_verified_manual_reply_can_continue_without_duplicate(tmp_path: Path) -> None:
    store = seed(tmp_path)
    store.prepare("run", intent(), now=200)
    owner = f"{os.getpid()}:interrupted"
    assert store.claim(REPLY_ID, owner, deadline=400, now=201)
    assert store.accepted(
        REPLY_ID, owner, conversation_id=CONVERSATION,
        parent_id=PARENT, message_id=MESSAGE, now=202,
    )
    assert store.finish(REPLY_ID, owner, uncertain=True, now=203)
    next_intent = intent("reply-99999999999999", MESSAGE, "Later follow-up")
    assert store.prepare("run", next_intent, now=204)["status"] == "prepared"
    with pytest.raises(ReplyConflict, match="unresolved"):
        store.prepare("run", intent("reply-88888888888888", MESSAGE), now=205)


def test_manual_tip_recovery_after_uncertain_send(tmp_path: Path) -> None:
    store = ManualReplyStore(tmp_path / "recover-tip.sqlite3")
    conversation = "00000000-0000-4000-8000-000000000001"
    original_id = "00000000-0000-4000-8000-000000000002"
    recovered_id = "00000000-0000-4000-8000-000000000003"
    store.responses.ensure_queued("run", "Original", now=100)
    assert store.responses.accept("run", "test:owner", deadline=300, now=101)
    assert store.responses.write(
        "run", "test:owner", CaptureResult(
            "sse", "complete", "Initial answer", conversation, original_id,
            "00000000-0000-4000-8000-000000000004",
        ), now=102,
    )
    reply = ReplyIntent(REPLY_ID, conversation, original_id, "Follow-up")
    store.prepare("run", reply, now=200)
    assert store.claim(REPLY_ID, "99999999:dead", deadline=400, now=201)
    assert store.recover_orphans(now=202) == 1
    assert not store.recover_reply_parent(
        "run", REPLY_ID, conversation, original_id,
        "Wrong user", "", recovered_id,
    )
    assert not store.recover_reply_parent(
        "run", REPLY_ID, conversation, original_id,
        "Follow-up", "", original_id,
    )
    assert store.recover_reply_parent(
        "run", REPLY_ID, conversation, original_id,
        "Follow-up", "", recovered_id,
    )
    assert not store.recover_reply_parent(
        "run", REPLY_ID, conversation, original_id,
        "Follow-up", "", recovered_id,
    )
    saved = store.turns("run")
    assert saved is not None
    assert saved[-1]["status"] == "interrupted"
    assert saved[-1]["message_id"] == recovered_id
    assert store.prepare(
        "run", ReplyIntent("reply-99999999999999", conversation, recovered_id, "Continue"),
        now=205,
    )["status"] == "prepared"


def test_queued_reply_authorizes_background_original_parent_recovery(tmp_path: Path) -> None:
    store = ManualReplyStore(tmp_path / "queued-revival.sqlite3")
    conversation = "00000000-0000-4000-8000-000000000001"
    parent = "00000000-0000-4000-8000-000000000002"
    reply_id = "queued-revival-1111111111"
    store.responses.ensure_queued("run", "Original prompt", now=10)
    assert store.responses.accept("run", "test:owner", deadline=100, now=11)
    assert store.responses.write(
        "run", "test:owner",
        CaptureResult("dom", "complete", "Original answer", conversation,
                      None, None, "rendered:assistant"), now=12,
    )
    assert store.queue_followup("run", reply_id, "Revive and continue", now=13)["status"] == "queued"
    assert store.queued_recovery_candidates() == ["run"]
    assert store.next_queued_intent() is None
    assert not store.recover_original_parent("run", conversation, parent, "Wrong answer")
    assert store.recover_original_parent("run", conversation, parent, "Original answer")
    assert store.queued_recovery_candidates() == []
    assert store.next_queued_intent() == (
        "run", ReplyIntent(reply_id, conversation, parent, "Revive and continue"),
    )


def test_queued_recovery_scan_batches_state_reads(tmp_path: Path) -> None:
    """The one-second queue pump must not perform a transcript query per chat."""
    store = ManualReplyStore(tmp_path / "queued-batch.sqlite3")
    conversation = "00000000-0000-4000-8000-000000000001"
    for index in range(6):
        send_id = f"chat-{index}"
        store.responses.ensure_queued(send_id, "Original", now=10 + index)
        assert store.responses.accept(send_id, "test:owner", deadline=100, now=20 + index)
        assert store.responses.write(
            send_id, "test:owner",
            CaptureResult("dom", "complete", "Answer", conversation,
                          None, None, "rendered:assistant"),
            now=30 + index,
        )
        store.queue_followup(send_id, f"queued-{index}-11111111111", "Continue", now=40 + index)

    statements: list[str] = []

    def count_select(
        _connection: object, _cursor: object, statement: str,
        _parameters: object, _context: object, _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(store.engine, "before_cursor_execute", count_select)
    try:
        assert store.queued_recovery_candidates() == [
            f"chat-{index}" for index in reversed(range(6))
        ]
    finally:
        event.remove(store.engine, "before_cursor_execute", count_select)
    assert len(statements) == 2


def test_queued_reply_recovers_uncertain_manual_tip_without_resending_it(tmp_path: Path) -> None:
    store = ManualReplyStore(tmp_path / "queued-tip-revival.sqlite3")
    conversation = "00000000-0000-4000-8000-000000000001"
    original_id = "00000000-0000-4000-8000-000000000002"
    recovered_id = "00000000-0000-4000-8000-000000000003"
    store.responses.ensure_queued("run", "Original", now=10)
    assert store.responses.accept("run", "test:owner", deadline=200, now=11)
    assert store.responses.write(
        "run", "test:owner",
        CaptureResult("sse", "complete", "Answer", conversation,
                      original_id, "00000000-0000-4000-8000-000000000004"), now=12,
    )
    previous = ReplyIntent("uncertain-reply-11111111", conversation, original_id, "Before revival")
    store.prepare("run", previous, now=13)
    assert store.claim(previous.reply_id, "dead:worker", deadline=20, now=14)
    assert store.recover_orphans(now=30) == 1
    queued_id = "queued-revival-2222222222"
    assert store.queue_followup("run", queued_id, "Next request", now=31)["status"] == "queued"
    from prompta.reply_tables import replies

    # A just-observed interrupted answer is still generating, so do not
    # launch a competing history read until the observation expires.
    with store.engine.begin() as connection:
        connection.execute(update(replies).where(
            replies.c.reply_id == previous.reply_id,
        ).values(live_observed_at=time.time()))
    assert store.queued_recovery_candidates() == []
    with store.engine.begin() as connection:
        connection.execute(update(replies).where(
            replies.c.reply_id == previous.reply_id,
        ).values(live_observed_at=0))
    assert store.queued_recovery_candidates() == ["run"]
    assert store.recover_reply_parent(
        "run", previous.reply_id, conversation, original_id, "Before revival", "", recovered_id,
    )
    assert store.next_queued_intent() == (
        "run", ReplyIntent(queued_id, conversation, recovered_id, "Next request"),
    )


def test_queued_reply_pump_recovers_missing_parent_in_background(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    from prompta.manual_reply_dispatch import ManualReplyDispatcher

    store = ManualReplyStore(tmp_path / "queued-worker.sqlite3")
    conversation = "00000000-0000-4000-8000-000000000001"
    parent = "00000000-0000-4000-8000-000000000002"
    store.responses.ensure_queued("run", "Original", now=10)
    assert store.responses.accept("run", "test:owner", deadline=100, now=11)
    assert store.responses.write(
        "run", "test:owner", CaptureResult(
            "dom", "complete", "Answer", conversation, None, None, "rendered:assistant",
        ), now=12,
    )
    queued_id = "queued-worker-1111111111"
    store.queue_followup("run", queued_id, "Continue", now=13)
    dispatcher = ManualReplyDispatcher(store, tmp_path / "state.sqlite3")
    verified = threading.Event()
    release = threading.Event()
    dispatched: list[ReplyIntent] = []

    def recover(send_id: str) -> dict[str, str]:
        assert send_id == "run"
        verified.set()
        assert release.wait(2)
        assert store.recover_original_parent(send_id, conversation, parent, "Answer")
        return {"message_id": parent}

    def submit(send_id: str, intent: ReplyIntent) -> dict[str, object]:
        assert send_id == "run"
        dispatched.append(intent)
        return {"status": "prepared"}

    monkeypatch.setattr(dispatcher, "recover", recover)
    monkeypatch.setattr(dispatcher, "submit", submit)
    dispatcher.pump_queued()
    assert verified.wait(2)
    assert not dispatched  # The branch must be verified before any send.
    release.set()
    for _ in range(100):
        if not dispatcher._recovery_scheduled:
            break
        time.sleep(0.01)
    dispatcher.pump_queued()
    assert dispatched == [ReplyIntent(queued_id, conversation, parent, "Continue")]


def test_queued_recovery_shares_history_account_pacing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prompta.manual_reply_dispatch import ManualReplyDispatcher
    from prompta.response_store import HISTORY_READ_INTERVAL_SECONDS

    store = ManualReplyStore(tmp_path / "queued-pacing.sqlite3")
    conversation = "00000000-0000-4000-8000-000000000001"
    store.responses.ensure_queued("run", "Original", now=10)
    assert store.responses.accept("run", "test:owner", deadline=100, now=11)
    assert store.responses.write(
        "run", "test:owner", CaptureResult(
            "dom", "complete", "Answer", conversation, None, None, "rendered:assistant",
        ), now=12,
    )
    store.queue_followup("run", "queued-pacing-111111111", "Continue", now=13)
    assert store.queued_recovery_candidates() == ["run"]
    assert store.responses.reserve_history_recovery_global_slot(
        now=time.time(), interval=HISTORY_READ_INTERVAL_SECONDS,
    )

    dispatcher = ManualReplyDispatcher(store, tmp_path / "state.sqlite3")
    recovered: list[str] = []
    monkeypatch.setattr(dispatcher, "recover", lambda send_id: recovered.append(send_id))
    scanner = store.queued_recovery_candidates
    monkeypatch.setattr(store, "queued_recovery_candidates", lambda: pytest.fail(
        "Do not scan queued transcripts while account recovery is paced",
    ))
    dispatcher.pump_queued()
    monkeypatch.setattr(store, "queued_recovery_candidates", scanner)
    assert recovered == []
    assert not dispatcher._recovery_scheduled

    restarted = ManualReplyDispatcher(store, tmp_path / "state.sqlite3")
    with pytest.raises(ReplyConflict, match="account read pacing"):
        restarted.recover("run")
    assert store.queued_recovery_candidates() == ["run"]


def test_queued_recovery_prioritizes_pins_then_rotates_failed_chats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prompta.manual_reply_dispatch import ManualReplyDispatcher

    store = ManualReplyStore(tmp_path / "queued-priority.sqlite3")
    conversation = "00000000-0000-4000-8000-000000000001"
    for name, created in [("pinned", 10), ("recent", 20)]:
        store.responses.ensure_queued(name, "Original", now=created)
        assert store.responses.accept(name, "test:owner", deadline=100, now=created + 1)
        assert store.responses.write(
            name, "test:owner", CaptureResult(
                "dom", "complete", "Answer", conversation, None, None, "rendered:assistant",
            ), now=created + 2,
        )
        store.queue_followup(name, f"{name}-queued-111111111", "Continue", now=created + 3)
    assert store.responses.set_local_pin("pinned", pinned=True)
    assert store.queued_recovery_candidates() == ["pinned", "recent"]

    dispatcher = ManualReplyDispatcher(store, tmp_path / "state.sqlite3")
    recovered: list[str] = []
    monkeypatch.setattr(dispatcher, "recover", lambda send_id: recovered.append(send_id))
    for expected in ("pinned", "recent"):
        dispatcher.pump_queued()
        for _ in range(100):
            if not dispatcher._recovery_scheduled:
                break
            time.sleep(0.01)
        assert recovered[-1:] == [expected]
    assert recovered == ["pinned", "recent"]


def test_queued_recovery_does_not_rescan_while_a_probe_is_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prompta.manual_reply_dispatch import ManualReplyDispatcher

    store = ManualReplyStore(tmp_path / "queued-priority.sqlite3")
    dispatcher = ManualReplyDispatcher(store, tmp_path / "state.sqlite3")
    dispatcher._recovery_scheduled.add("already-recovering")

    def unexpected_scan() -> list[str]:
        raise AssertionError("A running recovery must not rescan the queued transcript")

    monkeypatch.setattr(store, "queued_recovery_candidates", unexpected_scan)
    dispatcher._schedule_queued_parent_recovery()
