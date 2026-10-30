from __future__ import annotations

import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import inspect

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
