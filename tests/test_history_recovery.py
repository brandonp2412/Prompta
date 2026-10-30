from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import prompta.history_recovery as history_recovery
from prompta.delivery_worker import DeliveryAdmission
from prompta.history_recovery import (
    HistoryRecovery,
    _read_backoff_remaining,
    _record_read_rate_limit,
)
from prompta.playwright_driver import BrowserSecurityChallengeError, PlaywrightDriver
from prompta.rate_limit import RateLimitError
from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from prompta.scheduler_runtime import SchedulerRuntime

CONVERSATION = "12345678-1234-4123-8123-123456789abc"


def _expired(store: ResponseStore, send_id: str = "manual-1") -> None:
    store.ensure_queued(send_id, "Original prompt", now=10)
    assert store.accept(send_id, "123:owner", deadline=100, now=11)
    assert store.bind_conversation_route(send_id, "123:owner", "/c/" + CONVERSATION, now=12)
    assert store.finish(send_id, "123:owner", "interrupted", now=100)


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
    assert store.next_history_recovery(now=200) is None
    candidate = store.next_history_recovery(now=201)
    assert candidate is not None and candidate["attempt_count"] == 1
    store.schedule_history_recovery("manual-1", now=201, next_attempt_at=401)
    candidate = store.next_history_recovery(now=401)
    assert candidate is not None and candidate["attempt_count"] == 2


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
        "dom", "unknown", "", CONVERSATION, None, None, "turn",
        tool_calls=({"id": "dom-tool-0", "connector": "", "action": "Used search", "status": "observed"},),
    )
    assert store.recover_historical_response("manual-1", tool_only, now=112.5)
    saved = store.detail("manual-1")
    assert saved is not None and saved["assistant_text"] == "Still working"
    calls = saved["tool_calls"]
    assert isinstance(calls, list) and len(calls) == 1
    complete = CaptureResult("dom", "complete", "Finished response", CONVERSATION, None, None, "turn")
    assert store.recover_historical_response("manual-1", complete, now=113)
    row = store.get("manual-1")
    assert row is not None and row["status"] == "completed"
    assert row["source"] == "history_dom" and row["assistant_text"] == "Finished response"
    assert not store.recover_historical_response("manual-1", complete, now=114)
    assert store.next_history_recovery(now=999) is None


class FakeHistoryDriver:
    def __init__(
        self, *, rate_limited: bool = False, challenge: bool = False,
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

    async def eval(self, expression: str) -> object:
        assert CONVERSATION in expression and "Original prompt" in expression
        return {
            "verified": True, "ambiguous": False,
            "message_id": "turn", "branch_message_id": "",
            "pathname": "/c/" + CONVERSATION,
            "text": "Recovered from existing chat", "complete": True,
        }

    async def close(self) -> None:
        self.closed = True


def test_transient_ambiguous_dom_does_not_discard_same_tab_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)

    class HydratingDriver(FakeHistoryDriver):
        def __init__(self) -> None:
            super().__init__()
            self.probes = 0

        async def eval(self, expression: str) -> object:
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
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


def test_read_only_recovery_restores_uncertain_explicit_reply_without_resending(tmp_path: Path) -> None:
    path = tmp_path / "chat-results.sqlite3"
    responses = ResponseStore(path)
    original_id = "87654321-4321-4321-8321-123456789abc"
    responses.ensure_queued("manual-original", "Original prompt", now=10)
    assert responses.accept("manual-original", "123:owner", deadline=300, now=11)
    assert responses.write("manual-original", "123:owner", CaptureResult(
        "sse", "complete", "Original answer", CONVERSATION, original_id, None,
    ), now=12)
    replies = ManualReplyStore(path)
    intent = ReplyIntent("reply-123456789abcdef", CONVERSATION, original_id, "Follow up")
    assert replies.prepare("manual-original", intent, now=13)["status"] == "prepared"
    assert replies.claim(intent.reply_id, "123:reply", deadline=300, now=14)
    assert replies.finish(intent.reply_id, "123:reply", uncertain=True, now=15)
    before = replies.get(intent.reply_id)
    assert before is not None and before["status"] == "outcome_unknown"

    class ReplyDriver(FakeHistoryDriver):
        async def eval(self, expression: str) -> object:
            assert "Follow up" in expression and original_id in expression
            return {
                "verified": True, "ambiguous": False,
                "message_id": "reply-unit", "branch_message_id": "11111111-1111-4111-8111-111111111111",
                "verified_parent_id": original_id, "pathname": "/c/" + CONVERSATION,
                "text": "Recovered follow-up", "complete": True,
                "tool_calls": [{"action": "Used Nox Python", "status": "completed"}],
            }

    driver = ReplyDriver()
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert HistoryRecovery(responses, runtime, lambda: driver).recover_once(now=20)
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
    assert DeliveryAdmission(runtime, resource_admission=lambda: (True, ""))(
        manual=True
    ) == (True, "", 0.0)
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
    assert store.history_recovery_global_pace_remaining(now=151) == 89
    second_driver = FakeHistoryDriver()
    restarted_worker = HistoryRecovery(
        ResponseStore(tmp_path / "chat-results.sqlite3"), runtime, lambda: second_driver,
    )
    assert not restarted_worker.recover_once(now=151)
    assert second_driver.visited == []
    assert restarted_worker.recover_once(now=240)
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
    assert PlaywrightDriver._is_history_read_rate_limit(429, "GET", url)
    assert not PlaywrightDriver._is_history_read_rate_limit(200, "GET", url)
    assert not PlaywrightDriver._is_history_read_rate_limit(429, "POST", url)
    assert not PlaywrightDriver._is_history_read_rate_limit(
        429, "GET", "https://chatgpt.com/backend-api/pins?item_type=conversation"
    )
    assert not PlaywrightDriver._is_history_read_rate_limit(
        429, "GET", "https://example.com/backend-api/conversations/" + CONVERSATION
    )
    driver = PlaywrightDriver(profile=tmp_path / "chrome-profile")
    assert not driver.history_rate_limited()
    driver._observe_history_read_response(429, "GET", url)
    assert driver.history_rate_limited()


def test_conversation_http_429_stops_recovery_and_persists_backoff(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)
    driver = FakeHistoryDriver(http_limited=True)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert not HistoryRecovery(store, runtime, lambda: driver).recover_once(now=150)
    assert driver.closed and runtime.read_backoff_remaining() >= 299
    restarted = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert restarted.read_backoff_remaining() > 0
    row = store.get("manual-1")
    assert row is not None and row["status"] == "interrupted"
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


def test_pinned_recovery_does_not_bypass_per_chat_backoff(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store, "manual-unpinned")
    _expired(store, "manual-pinned")
    assert store.set_local_pin("manual-pinned", pinned=True)
    store.schedule_history_recovery("manual-pinned", now=100, next_attempt_at=500)
    assert store.next_history_recovery(now=150, pinned_only=True) is None

    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert HistoryRecovery(store, runtime, FakeHistoryDriver).recover_once(now=150)
    recovered = store.get("manual-unpinned")
    waiting = store.get("manual-pinned")
    assert recovered is not None and recovered["status"] == "completed"
    assert waiting is not None and waiting["status"] == "interrupted"
