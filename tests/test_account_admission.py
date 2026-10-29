from __future__ import annotations

from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

from prompta.delivery_worker import DeliveryAdmission
from prompta.rate_limit import (
    RateLimitBackoff,
    RateLimitError,
    captured_retry_after,
    parse_retry_after_header,
)
from prompta.scheduler_runtime import SchedulerRuntime


def test_read_throttle_durable_without_blocking_dispatch(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    reader = SchedulerRuntime(path, path)
    dispatcher = SchedulerRuntime(path, path)
    assert (
        300
        <= reader.record_read_rate_limit(RateLimitError("Too many requests", retry_after=60))
        <= 330
    )
    status = dispatcher.read_admission_status()
    assert status["blocked"] is True
    assert status["reason"] == "Too many requests"
    assert status["attempts"] == 1
    assert dispatcher.account_admission_status()["blocked"] is False
    admission = DeliveryAdmission(dispatcher, resource_admission=lambda: (True, ""))
    assert admission(manual=True) == (True, "", 0.0)

    dispatcher.update_account_state(
        {
            "rate_limit_backoff": {
                "attempts": 2,
                "blocked_until_epoch": 9999999999,
                "last_limited_at_epoch": 9999999990,
            }
        }
    )
    assert admission(manual=True) == (True, "", 0.0)
    dispatcher.clear_read_rate_limit()
    assert reader.read_backoff_remaining() == 0
    assert reader.read_admission_status()["blocked"] is False


def test_read_backoff_grows_and_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    reader = SchedulerRuntime(path, path)
    assert 300 <= reader.record_read_rate_limit(RateLimitError(retry_after=0)) <= 330
    restarted = SchedulerRuntime(path, path)
    assert 600 <= restarted.record_read_rate_limit(RateLimitError(retry_after=0)) <= 660
    assert restarted.record_read_rate_limit(RateLimitError(retry_after=1200)) >= 1200
    assert SchedulerRuntime(path, path).read_admission_status()["attempts"] == 3


def test_read_delay_honors_exponential_cap_and_longer_server_header() -> None:
    backoff = RateLimitBackoff()
    delays = [backoff.record(0, now=100 + i) for i in range(6)]
    assert 300 <= delays[0] <= 330
    assert 600 <= delays[1] <= 660
    assert delays[5] >= 1800
    backoff.reset()
    assert backoff.record(3600, now=200) >= 3600


def test_retry_after_header_seconds_dates_and_ms() -> None:
    date = format_datetime(datetime.fromtimestamp(1_000_600, tz=UTC), usegmt=True)
    assert parse_retry_after_header("900") == 900
    assert parse_retry_after_header(date, now=1_000_000) == 600
    assert parse_retry_after_header("invalid") == 0
    assert parse_retry_after_header("9" * 5000) == 0
    assert captured_retry_after({"retry_after": "60", "retry_after_ms": "900000"}) == 900
    assert captured_retry_after({"retry_after_ms": "NaN"}) == 0
    assert captured_retry_after({}) == 0


def test_success_resets_only_an_expired_read_cooldown(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    reader = SchedulerRuntime(path, path)
    reader.record_read_rate_limit(RateLimitError())
    reader.record_read_success()
    assert reader.read_admission_status()["attempts"] == 1

    import time

    now = time.time()
    reader.update_account_state(
        {
            "read_rate_limit_backoff": {
                "attempts": 1,
                "blocked_until_epoch": now - 1,
                "last_limited_at_epoch": now - 360,
            }
        }
    )
    reader.record_read_success()
    assert reader.read_admission_status()["attempts"] == 0


def test_fresh_chat_sender_ignores_read_cooldown(tmp_path: Path, monkeypatch) -> None:
    from prompta.delivery_browser import BrowserDeliverySender

    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", connector_approval=False)
    sender.runtime.record_read_rate_limit(RateLimitError("Too many requests"))
    accepted: list[str] = []

    async def fake_send(message: str, **_kwargs: object) -> None:
        accepted.append(message)

    monkeypatch.setattr(sender, "_send_browser", fake_send)
    sender("New chat")
    assert accepted == ["New chat"]
