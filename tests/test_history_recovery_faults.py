"""Fault-injected read-only recovery with no ChatGPT send surface."""

from pathlib import Path

from prompta.history_recovery import HistoryRecovery
from prompta.patchright_driver import BrowserSecurityChallengeError
from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from prompta.scheduler_runtime import SchedulerRuntime

CONVERSATION = "12345678-1234-4123-8123-123456789abc"


class OwnedReadDriver:
    context = "isolated"

    def __init__(
        self, *, text: str = "", complete: bool = False,
        limit: str = "", challenge: bool = False,
    ) -> None:
        self.text = text
        self.complete = complete
        self.limit = limit
        self.challenge = challenge
        self.visited: list[str] = []
        self.closed = False

    async def connect(self) -> None:
        self.visited.append("connect")

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        assert context == self.context
        assert url == "https://chatgpt.com/c/" + CONVERSATION
        self.visited.append(url)
        if self.challenge:
            raise BrowserSecurityChallengeError("Protected page")

    async def dom_state(self) -> dict[str, object]:
        return {"rate_limit_text": self.limit}

    async def eval(self, expression: str) -> object:
        assert CONVERSATION in expression and "Original prompt" in expression
        return {
            "verified": True,
            "ambiguous": False,
            "message_id": "turn",
            "branch_message_id": "",
            "pathname": "/c/" + CONVERSATION,
            "text": self.text,
            "complete": self.complete,
        }

    async def close(self) -> None:
        self.closed = True


def expired_partial(store: ResponseStore) -> None:
    store.ensure_queued("run", "Original prompt", now=10)
    assert store.accept("run", "123:owner", deadline=100, now=11)
    assert store.write(
        "run", "123:owner",
        CaptureResult("dom", "partial", "Saved partial", CONVERSATION, "turn", None),
        now=12,
    )
    assert store.finish("run", "123:owner", "interrupted", now=100)


def test_fault_injected_partial_then_final_is_read_only_and_reconciled(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "results.sqlite3")
    expired_partial(store)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    drivers = [
        OwnedReadDriver(text="Saved partial plus more", complete=False),
        OwnedReadDriver(text="Saved partial plus more and final", complete=True),
    ]
    used: list[OwnedReadDriver] = []

    def factory() -> OwnedReadDriver:
        driver = drivers[len(used)]
        used.append(driver)
        return driver

    worker = HistoryRecovery(store, runtime, factory)
    assert not worker.recover_once(now=150)
    pending = store.detail("run")
    assert pending is not None
    assert pending["status"] == "interrupted"
    assert pending["assistant_text"] == "Saved partial plus more"
    assert pending["recovery"] == {
        "attempt_count": 1,
        "last_attempt_at": 150,
        "next_attempt_at": 0,
        "eligible": True,
        "state": "pending",
    }
    assert not worker.recover_once(now=239)
    assert len(used) == 1
    assert worker.recover_once(now=240)
    completed = store.detail("run")
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["assistant_text"] == "Saved partial plus more and final"
    assert "recovery" not in completed
    metrics = store.recovery_metrics(now=241)
    assert metrics["recovered_completed"] == 1
    assert metrics["partial_text_saved"] == 0
    assert metrics["recoverable"] == 0
    assert len(used) == 2
    assert all(driver.closed and driver.visited == [
        "connect", "https://chatgpt.com/c/" + CONVERSATION,
    ] for driver in used)


def test_http_429_honors_account_backoff_without_blocking_one_chat(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite3"
    store = ResponseStore(path)
    expired_partial(store)
    runtime_path = tmp_path / "runtime.sqlite3"
    runtime = SchedulerRuntime(runtime_path, tmp_path / "jobs.json")
    driver = OwnedReadDriver(limit="Try again in 12 minutes")
    assert not HistoryRecovery(store, runtime, lambda: driver).recover_once(now=150)
    assert driver.closed
    pending = ResponseStore(path).detail("run")
    assert pending is not None
    assert pending["status"] == "interrupted"
    assert pending["assistant_text"] == "Saved partial"
    recovery = pending["recovery"]
    assert isinstance(recovery, dict)
    next_attempt = recovery.get("next_attempt_at")
    assert isinstance(next_attempt, (int, float))
    assert next_attempt == 0
    assert ResponseStore(path).next_history_recovery(now=150 + 11 * 60) is not None
    assert SchedulerRuntime(runtime_path, tmp_path / "jobs.json").read_backoff_remaining() > 0


def test_cloudflare_failures_are_bounded_without_falsely_completing(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite3"
    store = ResponseStore(path)
    expired_partial(store)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    drivers: list[OwnedReadDriver] = []

    def factory() -> OwnedReadDriver:
        driver = OwnedReadDriver(challenge=True)
        drivers.append(driver)
        return driver

    worker = HistoryRecovery(store, runtime, factory)
    attempt_at = 150.0
    for index, expected_delay in enumerate((1800, 3600, 7200, 14400, 14400), 1):
        assert not worker.recover_once(now=attempt_at)
        assert store.history_recovery_security_pause_remaining(now=attempt_at) == expected_delay
        assert not worker.recover_once(now=attempt_at + 89)
        assert len(drivers) == index
        attempt_at += expected_delay
    assert store.history_recovery_security_failures(now=attempt_at) == 5
    assert all(driver.closed and len(driver.visited) == 2 for driver in drivers)
    saved = store.get("run")
    assert saved is not None and saved["status"] == "interrupted"
    # A full day without a challenge resets the escalation window.
    after_reset = attempt_at + 24 * 3600
    assert not worker.recover_once(now=after_reset)
    assert store.history_recovery_security_failures(now=after_reset) == 1
    assert 1800 <= store.history_recovery_security_pause_remaining(now=after_reset) <= 3600


def test_genuinely_unavailable_without_owned_route_is_never_probed(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "results.sqlite3")
    store.ensure_queued("run", "Original prompt", now=10)
    assert store.accept("run", "123:owner", deadline=100, now=11)
    assert store.finish("run", "123:owner", "unavailable", now=100)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")

    def forbidden_driver() -> OwnedReadDriver:
        raise AssertionError("A chat without a verified Prompta route cannot be opened")

    assert not HistoryRecovery(store, runtime, forbidden_driver).recover_once(now=150)
    detail = store.detail("run")
    assert detail is not None
    assert detail["status"] == "unavailable"
    assert detail["recovery"] == {
        "attempt_count": 0,
        "last_attempt_at": 0,
        "next_attempt_at": 0,
        "eligible": False,
        "state": "identity_required",
    }
    assert detail["assistant_text"] == ""
    assert store.recovery_metrics(now=151)["missing_verified_identity"] == 1
