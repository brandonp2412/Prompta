from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from patchright.async_api import Error as PatchrightError
from sqlalchemy import update

import prompta.history_recovery as history_recovery
from prompta.delivery_worker import DeliveryAdmission
from prompta.history_recovery import (
    HistoryRecovery,
    _network_recovery_turn,
    _read_backoff_remaining,
    _record_read_rate_limit,
)
from prompta.patchright_driver import BrowserSecurityChallengeError, PatchrightDriver
from prompta.rate_limit import RateLimitError
from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore, history_recovery_attempts
from prompta.scheduler_runtime import SchedulerRuntime

CONVERSATION = "12345678-1234-4123-8123-123456789abc"


def _expired(store: ResponseStore, send_id: str = "manual-1") -> None:
    store.ensure_queued(send_id, "Original prompt", now=10)
    assert store.accept(send_id, "123:owner", deadline=100, now=11)
    assert store.bind_conversation_route(send_id, "123:owner", "/c/" + CONVERSATION, now=12)
    assert store.finish(send_id, "123:owner", "interrupted", now=100)


def test_deployed_capture_is_recovered_before_older_backlog_without_resending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "deployment-capture")
    _expired(store, "ordinary-newer")
    (tmp_path / "deployment-interrupted.json").write_text(
        json.dumps(
            {
                "priority": {"job_responses": ["deployment-capture"], "manual_reply_turns": []},
            }
        )
    )
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, FakeHistoryDriver, approval_enabled=False)
    observed: list[str] = []

    async def read(conversation_id: str, original_prompt: str) -> CaptureResult:
        assert conversation_id == CONVERSATION
        observed.append(original_prompt)
        return CaptureResult(
            "dom", "complete", "Recovered existing answer", CONVERSATION, None, None, "turn"
        )

    # Both use the same prompt in this fixture; only the exact persisted ID
    # chosen by the store can transition to completed.
    monkeypatch.setattr(worker, "_read_original_response", read)
    assert worker.recover_once(now=150)
    assert observed == ["Original prompt"]
    recovered = store.get("deployment-capture")
    pending = store.get("ordinary-newer")
    assert recovered is not None and recovered["status"] == "completed"
    assert pending is not None and pending["status"] == "interrupted"
    assert not worker.recover_once(now=151)  # account-wide five-minute slot


def test_recent_interruption_is_not_starved_by_previous_deploy_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    conversations = {
        "previous-deploy": "12345678-1234-4123-8123-123456789abd",
        "recent-interruption": "12345678-1234-4123-8123-123456789abe",
    }
    for stamp, (send_id, conversation) in zip((10.0, 40.0), conversations.items()):
        store.ensure_queued(send_id, send_id + " prompt", now=stamp)
        assert store.accept(send_id, "123:owner", deadline=100, now=stamp + 1)
        assert store.bind_conversation_route(
            send_id, "123:owner", "/c/" + conversation, now=stamp + 2,
        )
        assert store.finish(send_id, "123:owner", "interrupted", now=100)
    (tmp_path / "deployment-interrupted.json").write_text(json.dumps({
        "priority": {"job_responses": ["previous-deploy"], "manual_reply_turns": []},
    }))
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, FakeHistoryDriver, approval_enabled=False)

    async def read(conversation_id: str, original_prompt: str) -> CaptureResult:
        return CaptureResult(
            "dom", "complete", "Verified answer", conversation_id, None, None, "turn",
        )

    monkeypatch.setattr(worker, "_read_original_response", read)
    assert worker.recover_once(now=150)
    recent = store.get("recent-interruption")
    old = store.get("previous-deploy")
    assert recent is not None and recent["status"] == "completed"
    assert recent["assistant_text"] == "Verified answer"
    assert old is not None and old["status"] == "interrupted"
    assert not worker.recover_once(now=151)  # Neither chat can monopolize the slot.


def test_newest_pinned_chat_beats_older_pinned_retry_and_newer_deploy_priority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    conversations = {
        "older-pinned": "12345678-1234-4123-8123-123456789abd",
        "newer-pinned": "12345678-1234-4123-8123-123456789abe",
        "newest-unpinned": "12345678-1234-4123-8123-123456789abf",
    }
    for at, (send_id, conversation) in enumerate(conversations.items(), start=10):
        stamp = float(at * 10)
        store.ensure_queued(send_id, send_id + " prompt", now=stamp)
        assert store.accept(send_id, "123:owner", deadline=200, now=stamp + 1)
        assert store.bind_conversation_route(
            send_id,
            "123:owner",
            "/c/" + conversation,
            now=stamp + 2,
        )
        assert store.finish(send_id, "123:owner", "interrupted", now=100)
    assert store.set_local_pin("older-pinned", pinned=True)
    assert store.set_local_pin("newer-pinned", pinned=True)
    store.schedule_history_recovery("older-pinned", now=110, next_attempt_at=9000)
    store.schedule_history_recovery("newer-pinned", now=110, next_attempt_at=125)
    (tmp_path / "deployment-interrupted.json").write_text(
        json.dumps(
            {
                "priority": {"job_responses": ["newest-unpinned"], "manual_reply_turns": []},
            }
        )
    )
    newest_pinned = store.next_history_recovery(now=150, pinned_only=True)
    assert newest_pinned is not None and newest_pinned["send_id"] == "newer-pinned"

    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, FakeHistoryDriver)
    observed: list[str] = []

    async def read(conversation_id: str, original_prompt: str) -> CaptureResult:
        observed.append(original_prompt)
        return CaptureResult(
            "dom",
            "complete",
            "Recovered pinned answer",
            conversation_id,
            None,
            None,
            "turn",
        )

    monkeypatch.setattr(worker, "_read_original_response", read)
    assert worker.recover_once(now=150)
    assert observed == ["newer-pinned prompt"]
    newer = store.get("newer-pinned")
    assert newer is not None and newer["status"] == "completed"
    for still_waiting in ("older-pinned", "newest-unpinned"):
        row = store.get(still_waiting)
        assert row is not None and row["status"] == "interrupted"


def test_deployment_priority_ignores_legacy_per_chat_deadline(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "deployment-capture")
    _expired(store, "ordinary-newer")
    store.schedule_history_recovery("deployment-capture", now=100, next_attempt_at=500)
    # Simulate a row written by the pre-deploy per-chat backoff scheduler.
    with store.engine.begin() as connection:
        connection.execute(
            update(history_recovery_attempts)
            .where(history_recovery_attempts.c.send_id == "deployment-capture")
            .values(next_attempt_at=9000)
        )
    candidate = store.next_history_recovery(now=150, priority_ids=["deployment-capture"])
    assert candidate is not None and candidate["send_id"] == "deployment-capture"
    assert candidate["attempt_count"] == 1


def test_only_verified_incomplete_conversations_are_recovery_candidates(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    store.ensure_queued("no-route", "prompt", now=10)
    assert store.accept("no-route", "123:owner", deadline=100, now=11)
    assert store.finish("no-route", "123:owner", "interrupted", now=100)
    _expired(store)
    candidate = store.next_history_recovery(now=101)
    assert candidate is not None and candidate["send_id"] == "manual-1"
    assert candidate["conversation_id"] == CONVERSATION
    store.schedule_history_recovery("manual-1", now=101, next_attempt_at=201)
    candidate = store.next_history_recovery(now=101)
    assert candidate is not None and candidate["attempt_count"] == 1
    store.schedule_history_recovery("manual-1", now=201, next_attempt_at=401)
    candidate = store.next_history_recovery(now=201)
    assert candidate is not None and candidate["attempt_count"] == 2


@pytest.mark.parametrize("attempts", [0, 1, 6, 8, 30])
def test_repeated_failed_reads_wait_only_for_global_slot_without_resending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attempts: int,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)
    for _ in range(attempts):
        store.schedule_history_recovery("manual-1", now=100, next_attempt_at=9000)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, FakeHistoryDriver)
    reads: list[bool] = []

    async def missing_response(_conversation_id: str, _prompt: str) -> None:
        reads.append(True)
        return None

    monkeypatch.setattr(worker, "_read_original_response", missing_response)
    assert not worker.recover_once(now=150)
    record = store.detail("manual-1")
    assert record is not None and record["status"] == "interrupted"
    candidate = store.next_history_recovery(now=151)
    assert candidate is not None and candidate["send_id"] == "manual-1"
    assert candidate["attempt_count"] == attempts + 1
    assert not worker.recover_once(now=449)  # The account's five-minute slot is locked.
    assert len(reads) == 1
    assert not worker.recover_once(now=450)
    assert len(reads) == 2


def test_recovery_metrics_are_private_aggregate_and_respect_backoff(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "verified")
    store.ensure_queued("unverified", "Sensitive prompt", now=10)
    assert store.accept("unverified", "123:owner", deadline=100, now=11)
    assert store.finish("unverified", "123:owner", "interrupted", now=100)
    store.ensure_queued("active", "Still streaming", now=10)
    assert store.accept("active", "123:owner", deadline=200, now=11)
    store.schedule_history_recovery("verified", next_attempt_at=180, now=100)
    store.schedule_history_recovery("__global_pacing__", next_attempt_at=160, now=100)
    store.schedule_history_recovery("__security_pause__", next_attempt_at=210, now=100)

    metrics = store.recovery_metrics(now=150)
    assert metrics == {
        "active_captures": 1,
        "stale_capture_leases": 0,
        "recoverable": 1,
        "ready_for_read_only_probe": 1,
        "missing_verified_identity": 1,
        "partial_text_saved": 0,
        "waiting_per_chat_backoff": 0,
        "recovered_completed": 0,
        "attention_chats": 2,
        "security_pause_seconds": 60,
        "global_pace_seconds": 10,
    }
    assert store.recovery_metrics(now=220)["ready_for_read_only_probe"] == 1
    assert store.recovery_metrics(now=220)["stale_capture_leases"] == 1
    assert "Sensitive prompt" not in str(metrics)


def test_recovery_never_overwrites_completed_or_crosses_branches(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)
    wrong = CaptureResult("dom", "complete", "Wrong chat", "wrong-id", None, None, "turn")
    assert not store.recover_historical_response("manual-1", wrong, now=110)
    partial = CaptureResult("dom", "partial", "Still working", CONVERSATION, None, None, "turn")
    assert store.recover_historical_response("manual-1", partial, now=111)
    row = store.get("manual-1")
    assert row is not None and row["status"] == "interrupted"
    assert row["assistant_text"] == "Still working"
    shorter = CaptureResult("dom", "partial", "Tiny", CONVERSATION, None, None, "turn")
    assert not store.recover_historical_response("manual-1", shorter, now=112)
    tool_only = CaptureResult(
        "dom",
        "unknown",
        "",
        CONVERSATION,
        None,
        None,
        "turn",
        tool_calls=(
            {"id": "dom-tool-0", "connector": "", "action": "Used search", "status": "observed"},
        ),
    )
    assert store.recover_historical_response("manual-1", tool_only, now=112.5)
    saved = store.detail("manual-1")
    assert saved is not None and saved["assistant_text"] == "Still working"
    calls = saved["tool_calls"]
    assert isinstance(calls, list) and len(calls) == 1
    complete = CaptureResult(
        "dom", "complete", "Finished response", CONVERSATION, None, None, "turn"
    )
    assert store.recover_historical_response("manual-1", complete, now=113)
    row = store.get("manual-1")
    assert row is not None and row["status"] == "completed"
    assert row["source"] == "history_dom" and row["assistant_text"] == "Finished response"
    assert not store.recover_historical_response("manual-1", complete, now=114)
    assert store.next_history_recovery(now=999) is None


class FakeHistoryDriver:
    def __init__(
        self,
        *,
        rate_limited: bool = False,
        challenge: bool = False,
        http_limited: bool = False,
    ) -> None:
        self.context = "owned"
        self.rate_limited = rate_limited
        self.http_limited = http_limited
        self.challenge = challenge
        self.visited: list[str] = []
        self.closed = False

    async def connect(self) -> None:
        self.visited.append("connect")

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        assert context == self.context
        self.visited.append(url)
        if self.challenge:
            raise BrowserSecurityChallengeError("Protected page")

    async def dom_state(self) -> dict[str, object]:
        return {"rate_limit_text": "Too many requests" if self.rate_limited else ""}

    def history_rate_limited(self) -> bool:
        return self.http_limited

    async def eval(self, expression: str, *, main_world: bool = False) -> object:
        assert CONVERSATION in expression and "Original prompt" in expression
        return {
            "verified": True,
            "ambiguous": False,
            "message_id": "turn",
            "branch_message_id": "",
            "pathname": "/c/" + CONVERSATION,
            "text": "Recovered from existing chat",
            "complete": True,
        }

    async def close(self) -> None:
        self.closed = True


def test_verified_live_probe_survives_without_answer_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verified generating DOM is a usable live-state signal, not a completed answer."""
    class LiveDriver(FakeHistoryDriver):
        async def eval(self, expression: str, *, main_world: bool = False) -> object:
            assert CONVERSATION in expression
            return {
                "verified": True, "ambiguous": False,
                "message_id": "fallback-turn-0:activity:assistant",
                "pathname": "/c/" + CONVERSATION,
                "text": "", "complete": False, "generating": True,
            }

    async def no_delay(_seconds: float) -> None:
        return None

    monkeypatch.setattr(history_recovery, "_READ_PROBE_SECONDS", 0.02)
    monkeypatch.setattr(history_recovery.asyncio, "sleep", no_delay)
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, LiveDriver, approval_enabled=False)
    result = asyncio.run(worker._read_original_response(CONVERSATION, "Original prompt"))
    assert result is not None and result.status == "unknown"
    assert result.verified_generating and result.conversation_id == CONVERSATION


def test_transient_ambiguous_dom_does_not_discard_same_tab_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)

    class HydratingDriver(FakeHistoryDriver):
        def __init__(self) -> None:
            super().__init__()
            self.probes = 0

        async def eval(self, expression: str, *, main_world: bool = False) -> object:
            self.probes += 1
            if self.probes == 1:
                return {"verified": False, "ambiguous": True}
            return await super().eval(expression)

    async def no_delay(_delay: float) -> None:
        return None

    monkeypatch.setattr(history_recovery.asyncio, "sleep", no_delay)
    driver = HydratingDriver()
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert HistoryRecovery(store, runtime, lambda: driver).recover_once(now=150)
    assert driver.probes == 2 and driver.closed
    assert driver.visited == ["connect", "https://chatgpt.com/c/" + CONVERSATION]
    row = store.get("manual-1")
    assert row is not None and row["status"] == "completed"


@pytest.mark.parametrize("transient", [TimeoutError, PatchrightError])
def test_transient_dom_and_probe_timeouts_retry_same_owned_tab(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transient: type[Exception],
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)

    class SlowHydration(FakeHistoryDriver):
        def __init__(self) -> None:
            super().__init__()
            self.dom_reads = 0
            self.probes = 0

        async def dom_state(self) -> dict[str, object]:
            self.dom_reads += 1
            if self.dom_reads == 1:
                raise transient("Transient DOM wait")
            return await super().dom_state()

        async def eval(self, expression: str, *, main_world: bool = False) -> object:
            self.probes += 1
            if self.probes == 1:
                raise transient("Transient evaluation")
            return await super().eval(expression)

    async def no_delay(_delay: float) -> None:
        return None

    monkeypatch.setattr(history_recovery.asyncio, "sleep", no_delay)
    driver = SlowHydration()
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert HistoryRecovery(store, runtime, lambda: driver).recover_once(now=150)
    assert driver.dom_reads == 3 and driver.probes == 2
    assert driver.visited == ["connect", "https://chatgpt.com/c/" + CONVERSATION]
    assert driver.closed
    row = store.get("manual-1")
    assert row is not None and row["status"] == "completed"


def test_read_only_recovery_restores_exact_run_without_dispatch(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)
    driver = FakeHistoryDriver()
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, lambda: driver)
    assert worker.recover_once(now=150)
    assert driver.closed
    assert driver.visited == ["connect", "https://chatgpt.com/c/" + CONVERSATION]
    row = store.get("manual-1")
    assert row is not None and row["status"] == "completed"
    assert row["assistant_text"] == "Recovered from existing chat"


def test_cleanup_failure_does_not_discard_verified_read_only_response(
    tmp_path: Path,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)

    class CleanupFailure(FakeHistoryDriver):
        async def close(self) -> None:
            self.closed = True
            raise RuntimeError("CDP connection vanished during close")

    driver = CleanupFailure()
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert HistoryRecovery(store, runtime, lambda: driver).recover_once(now=150)
    assert driver.closed
    row = store.get("manual-1")
    assert row is not None and row["status"] == "completed"


def test_stuck_cleanup_has_a_deadline_without_losing_verified_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)

    class StuckCleanup(FakeHistoryDriver):
        async def close(self) -> None:
            await asyncio.sleep(60)

    driver = StuckCleanup()
    monkeypatch.setattr(history_recovery, "_HISTORY_CLOSE_TIMEOUT_SECONDS", 0.02)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert HistoryRecovery(store, runtime, lambda: driver).recover_once(now=150)
    row = store.get("manual-1")
    assert row is not None and row["status"] == "completed"


def test_read_only_recovery_restores_uncertain_explicit_reply_without_resending(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chat-results.sqlite3"
    responses = ResponseStore(path)
    original_id = "87654321-4321-4321-8321-123456789abc"
    responses.ensure_queued("manual-original", "Original prompt", now=10)
    assert responses.accept("manual-original", "123:owner", deadline=300, now=11)
    assert responses.write(
        "manual-original",
        "123:owner",
        CaptureResult(
            "sse",
            "complete",
            "Original answer",
            CONVERSATION,
            original_id,
            None,
        ),
        now=12,
    )
    replies = ManualReplyStore(path)
    intent = ReplyIntent("reply-123456789abcdef", CONVERSATION, original_id, "Follow up")
    assert replies.prepare("manual-original", intent, now=13)["status"] == "prepared"
    assert replies.claim(intent.reply_id, "123:reply", deadline=300, now=14)
    assert replies.finish(intent.reply_id, "123:reply", uncertain=True, now=15)
    before = replies.get(intent.reply_id)
    assert before is not None and before["status"] == "outcome_unknown"

    class ReplyDriver(FakeHistoryDriver):
        async def eval(self, expression: str, *, main_world: bool = False) -> object:
            assert "Follow up" in expression and original_id in expression
            return {
                "verified": True,
                "ambiguous": False,
                "message_id": "reply-unit",
                "branch_message_id": "11111111-1111-4111-8111-111111111111",
                "verified_parent_id": original_id,
                "pathname": "/c/" + CONVERSATION,
                "text": "Recovered follow-up",
                "complete": True,
                "tool_calls": [{"action": "Used test connector", "status": "completed"}],
            }

    driver = ReplyDriver()
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(responses, runtime, lambda: driver)
    assert not worker.recover_once(now=20, background=True)
    assert driver.visited == []
    responses.queue_manual_recovery(
        "manual-original", ["reply:" + intent.reply_id], now=20,
    )
    assert worker.recover_once(now=20, background=True)
    assert driver.visited == ["connect", "https://chatgpt.com/c/" + CONVERSATION]
    turn = replies.get(intent.reply_id)
    assert turn is not None
    assert turn["status"] == "completed" and turn["assistant_text"] == "Recovered follow-up"
    assert turn["message_id"] == "11111111-1111-4111-8111-111111111111"
    calls = turn["tool_calls"]
    assert isinstance(calls, list) and len(calls) == 1
    assert replies.next_history_reply_recovery(now=999) is None


def test_rate_limit_stops_recovery_and_preserves_retry_state(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)
    driver = FakeHistoryDriver(rate_limited=True)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, lambda: driver)
    assert not worker.recover_once(now=150)
    assert driver.closed and runtime.read_backoff_remaining() >= 299
    assert DeliveryAdmission(runtime, resource_admission=lambda: (True, ""))(manual=True) == (
        True,
        "",
        0.0,
    )
    restarted = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert restarted.read_backoff_remaining() > 0
    row = store.get("manual-1")
    assert row is not None and row["status"] == "interrupted"
    assert not worker.recover_once(now=151)
    assert driver.visited.count("connect") == 1


def test_security_challenge_uses_durable_global_pause(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)
    driver = FakeHistoryDriver(challenge=True)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, lambda: driver)
    assert not worker.recover_once(now=150)
    assert driver.closed
    assert store.history_recovery_security_pause_remaining(now=151) >= 29 * 60
    assert not worker.recover_once(now=160)
    assert driver.visited.count("connect") == 1


def test_global_pacing_survives_worker_restart(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "manual-first")
    _expired(store, "manual-second")
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    first_driver = FakeHistoryDriver()
    first_worker = HistoryRecovery(store, runtime, lambda: first_driver)
    assert first_worker.recover_once(now=150)
    assert store.history_recovery_global_pace_remaining(now=151) == 299
    second_driver = FakeHistoryDriver()
    restarted_worker = HistoryRecovery(
        ResponseStore(tmp_path / "chat-results.sqlite3"),
        runtime,
        lambda: second_driver,
    )
    assert not restarted_worker.recover_once(now=151)
    assert second_driver.visited == []
    assert restarted_worker.recover_once(now=450)
    assert second_driver.visited.count("connect") == 1


def test_read_specific_backoff_api_is_preferred_when_available() -> None:
    class NewRuntime:
        def read_backoff_remaining(self) -> float:
            return 42.0

        def record_read_rate_limit(self, exc: RateLimitError) -> float:
            return 120.0

    runtime = NewRuntime()
    assert _read_backoff_remaining(runtime) == 42.0
    assert _record_read_rate_limit(runtime, RateLimitError()) == 120.0


def test_conversation_http_429_detection_is_exact(tmp_path: Path) -> None:
    url = "https://chatgpt.com/backend-api/conversations/" + CONVERSATION + "?num_turns=10"
    assert PatchrightDriver._is_history_read_rate_limit(429, "GET", url)
    assert not PatchrightDriver._is_history_read_rate_limit(200, "GET", url)
    assert not PatchrightDriver._is_history_read_rate_limit(429, "POST", url)
    assert not PatchrightDriver._is_history_read_rate_limit(
        429, "GET", "https://chatgpt.com/backend-api/pins?item_type=conversation"
    )
    assert not PatchrightDriver._is_history_read_rate_limit(
        429, "GET", "https://example.com/backend-api/conversations/" + CONVERSATION
    )
    driver = PatchrightDriver(profile=tmp_path / "chrome-profile")
    assert not driver.history_rate_limited()
    driver._observe_history_read_response(429, "GET", url)
    assert driver.history_rate_limited()


def test_conversation_http_429_stops_recovery_and_persists_backoff(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)

    class UnloadedHistory(FakeHistoryDriver):
        async def eval(self, expression: str, *, main_world: bool = False) -> object:
            return {"verified": False, "pathname": "/c/" + CONVERSATION}

    driver = UnloadedHistory(http_limited=True)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert not HistoryRecovery(store, runtime, lambda: driver).recover_once(now=150)
    assert driver.closed and runtime.read_backoff_remaining() >= 299
    restarted = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert restarted.read_backoff_remaining() > 0
    row = store.get("manual-1")
    assert row is not None and row["status"] == "interrupted"
    assert driver.visited == ["connect", "https://chatgpt.com/c/" + CONVERSATION]


def test_verified_exact_chat_recovers_despite_background_http_429(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)
    driver = FakeHistoryDriver(http_limited=True)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")

    assert HistoryRecovery(store, runtime, lambda: driver).recover_once(now=150)
    assert driver.closed
    row = store.get("manual-1")
    assert row is not None and row["status"] == "completed"
    assert row["assistant_text"] == "Recovered from existing chat"
    assert runtime.read_backoff_remaining() == 0


def test_browser_context_error_after_429_still_persists_read_backoff(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)

    class InterruptedRead(FakeHistoryDriver):
        async def dom_state(self) -> dict[str, object]:
            raise PatchrightError("Execution context was destroyed")

    driver = InterruptedRead(http_limited=True)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert not HistoryRecovery(store, runtime, lambda: driver).recover_once(now=150)
    assert driver.closed
    assert runtime.read_backoff_remaining() >= 299
    assert driver.visited == ["connect", "https://chatgpt.com/c/" + CONVERSATION]


def test_pinned_incomplete_chat_recovers_before_unpinned_backlog(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "manual-unpinned")
    _expired(store, "manual-pinned")
    assert store.set_local_pin("manual-pinned", pinned=True)
    pinned = store.next_history_recovery(now=150, pinned_only=True)
    assert pinned is not None and pinned["send_id"] == "manual-pinned"

    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert HistoryRecovery(store, runtime, FakeHistoryDriver).recover_once(now=150)
    recovered = store.get("manual-pinned")
    waiting = store.get("manual-unpinned")
    assert recovered is not None and recovered["status"] == "completed"
    assert waiting is not None and waiting["status"] == "interrupted"


def test_pinned_recovery_ignores_legacy_per_chat_deadline(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "manual-unpinned")
    _expired(store, "manual-pinned")
    assert store.set_local_pin("manual-pinned", pinned=True)
    store.schedule_history_recovery("manual-pinned", now=100, next_attempt_at=500)
    candidate = store.next_history_recovery(now=150, pinned_only=True)
    assert candidate is not None and candidate["send_id"] == "manual-pinned"

    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert HistoryRecovery(store, runtime, FakeHistoryDriver).recover_once(now=150)
    recovered = store.get("manual-pinned")
    waiting = store.get("manual-unpinned")
    assert recovered is not None and recovered["status"] == "completed"
    assert waiting is not None and waiting["status"] == "interrupted"


@pytest.mark.parametrize("slot_number,expected", [(0, True), (1, False), (2, True)])
def test_unresponsive_owned_tab_leaves_network_history_slots(
    slot_number: int, expected: bool,
) -> None:
    assert _network_recovery_turn(
        network_read_allowed=True, manual_slot=False, pinned_target="",
        owned_target="old-orphan", slot_number=slot_number,
    ) is expected
    assert not _network_recovery_turn(
        network_read_allowed=False, manual_slot=False, pinned_target="",
        owned_target="old-orphan", slot_number=slot_number,
    )


def test_pinned_and_manual_recovery_precede_unpinned_owned_tab() -> None:
    assert _network_recovery_turn(
        network_read_allowed=True, manual_slot=False, pinned_target="new-pinned",
        owned_target="old-orphan", slot_number=1,
    )
    assert _network_recovery_turn(
        network_read_allowed=True, manual_slot=True, pinned_target="",
        owned_target="old-orphan", slot_number=1,
    )
    assert not _network_recovery_turn(
        network_read_allowed=True, manual_slot=False, pinned_target="pinned-owned",
        owned_target="pinned-owned", slot_number=0,
    )


@pytest.mark.parametrize("pinned", [False, True])
def test_background_network_recovery_requires_demand_even_for_pins(tmp_path: Path, pinned: bool) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)
    if pinned:
        assert store.set_local_pin("manual-1", pinned=True)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    driver = FakeHistoryDriver()
    worker = HistoryRecovery(store, runtime, lambda: driver)
    assert not worker.recover_once(now=150, background=True)
    assert driver.visited == []
    assert store.history_recovery_global_pace_remaining(now=150) == 0
    store.queue_manual_recovery("manual-1", ["manual-1"], now=151)
    assert worker.recover_once(now=151, background=True)
    assert driver.visited.count("connect") == 1
    assert store.pending_manual_recovery_requests() == []


def test_background_recovers_deployment_inventory_without_sweeping_backlog(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "deployed")
    _expired(store, "backlog")
    (tmp_path / "deployment-interrupted.json").write_text(json.dumps({
        "priority": {"job_responses": ["deployed"], "manual_reply_turns": []},
    }))
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    driver = FakeHistoryDriver()
    worker = HistoryRecovery(store, runtime, lambda: driver)
    assert worker.recover_once(now=150, background=True)
    assert not worker.recover_once(now=450, background=True)
    assert driver.visited.count("connect") == 1
    row = store.get("backlog")
    assert row is not None and row["status"] == "interrupted"
