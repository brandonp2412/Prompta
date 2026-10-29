from __future__ import annotations

from pathlib import Path

from prompta.history_recovery import HistoryRecovery
from prompta.playwright_driver import BrowserSecurityChallengeError
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
    complete = CaptureResult("dom", "complete", "Finished response", CONVERSATION, None, None, "turn")
    assert store.recover_historical_response("manual-1", complete, now=113)
    row = store.get("manual-1")
    assert row is not None and row["status"] == "completed"
    assert row["source"] == "history_dom" and row["assistant_text"] == "Finished response"
    assert not store.recover_historical_response("manual-1", complete, now=114)
    assert store.next_history_recovery(now=999) is None


class FakeHistoryDriver:
    def __init__(self, *, rate_limited: bool = False, challenge: bool = False) -> None:
        self.context = "owned"
        self.rate_limited = rate_limited
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


def test_rate_limit_stops_recovery_and_preserves_retry_state(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _expired(store)
    driver = FakeHistoryDriver(rate_limited=True)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, lambda: driver)
    assert not worker.recover_once(now=150)
    assert driver.closed and runtime.global_backoff_remaining() > 0
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
