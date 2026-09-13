from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prompta.core import (
    Prompta,
    PromptaConfig,
    PromptJob,
    RateLimitBackoff,
    RateLimitError,
    SendVerificationError,
    add_job,
    clear_jobs,
    load_jobs,
    parse_retry_after,
    remove_job,
    set_job_paused,
)


class FakeDriver:
    def __init__(
        self,
        prompt: str,
        initial_composer: str = "",
        *,
        committed: bool = True,
        capture_status: int = 200,
        expose_user_message: bool = True,
        route_after_send: bool = True,
    ) -> None:
        self.prompt = prompt
        self.committed = committed
        self.expose_user_message = expose_user_message
        self.route_after_send = route_after_send
        self.is_connected = True
        self.context = "context-1"
        self.typed = initial_composer
        self.sent = False
        self.clear_composer_calls = 0
        self.capture: dict[str, Any] = {
            "request_id": "request-1" if capture_status else "",
            "status": capture_status,
            "response_started": bool(capture_status),
            "completed": False,
            "fetch_error": "",
        }
        self.navigated: list[str] = []

    async def navigate(self, url: str) -> None:
        self.navigated.append(url)

    async def wait_for_composer(self) -> None:
        return None

    async def dom_state(self) -> dict[str, object]:
        if self.sent:
            return {
                "composer_text": "",
                "last_user_text": self.prompt if self.expose_user_message else "",
                "last_user_id": "message-1" if self.expose_user_message else "",
                "rate_limit_text": "",
            }
        return {
            "composer_text": self.typed,
            "last_user_text": "",
            "last_user_id": "",
            "rate_limit_text": "",
        }

    async def arm_page_send_probe(self) -> None:
        return None

    def arm_send_capture(self) -> dict[str, Any]:
        return self.capture

    async def type_message(self, text: str) -> None:
        self.typed = text

    async def clear_composer(self) -> None:
        self.clear_composer_calls += 1
        self.typed = ""

    async def click_send(self) -> None:
        self.sent = True
        self.typed = ""

    async def page_send_probe(self) -> dict[str, object]:
        return {
            "message_id": "message-1",
            "response_status": int(self.capture["status"]),
            "committed": self.committed,
        }

    def captured_send_response(self, capture: dict[str, Any]) -> tuple[str, int] | None:
        status = int(capture["status"])
        if capture["request_id"] and capture["response_started"] and 200 <= status < 400:
            return str(capture["request_id"]), status
        return None

    async def eval(self, expression: str) -> str:
        assert expression == "location.pathname"
        if self.sent and self.route_after_send:
            return "/c/new-chat"
        return "/"

    def clear_send_capture(self, capture: dict[str, Any]) -> None:
        return None

    async def clear_page_send_probe(self) -> dict[str, object]:
        return {}

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_send_once_always_starts_from_new_chat(tmp_path: Path) -> None:
    prompt = "PROMPTA TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta._ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt)

    assert conversation_id == "new-chat"
    assert fake.navigated == ["https://chatgpt.com/"]
    assert fake.sent is True
    assert fake.clear_composer_calls == 0


@pytest.mark.asyncio
async def test_send_once_accepts_visible_user_message_without_transport_confirmation(tmp_path: Path) -> None:
    prompt = "PROMPTA TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt, committed=False, capture_status=0)
    prompta.driver = cast(Any, fake)
    prompta._ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt)

    assert conversation_id == "new-chat"


@pytest.mark.asyncio
async def test_send_once_requires_dom_or_transport_confirmation(tmp_path: Path) -> None:
    prompt = "PROMPTA TEST"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            send_timeout_seconds=0.01,
        ),
        "ws://unused",
    )
    fake = FakeDriver(
        prompt,
        committed=False,
        capture_status=0,
        expose_user_message=False,
        route_after_send=False,
    )
    prompta.driver = cast(Any, fake)
    prompta._ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(SendVerificationError, match="could not prove"):
        await prompta.send_once(prompt)


@pytest.mark.asyncio
async def test_send_once_accepts_new_conversation_route_as_confirmation(tmp_path: Path) -> None:
    prompt = "PROMPTA TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt, committed=False, capture_status=0, expose_user_message=False)
    prompta.driver = cast(Any, fake)
    prompta._ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt)

    assert conversation_id == "new-chat"


@pytest.mark.asyncio
async def test_send_once_clears_stale_dedicated_composer(tmp_path: Path) -> None:
    prompt = "PROMPTA TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt, initial_composer="stale draft from previous failed attempt")
    prompta.driver = cast(Any, fake)
    prompta._ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt)

    assert conversation_id == "new-chat"
    assert fake.clear_composer_calls == 1
    assert fake.sent is True


@pytest.mark.asyncio
async def test_high_effort_is_selected_and_verified(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    driver = MagicMock()
    driver.context = "context-1"
    driver.eval = AsyncMock(return_value="2")
    driver._call = AsyncMock()
    prompta._effort_trigger_info = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"text": "Medium", "x": 10.0, "y": 20.0},
            {"text": "High", "x": 10.0, "y": 20.0},
        ]
    )
    prompta._high_effort_slider_point = AsyncMock(  # type: ignore[method-assign]
        return_value={"x": 30.0, "y": 40.0}
    )
    prompta._pointer_click = AsyncMock()  # type: ignore[method-assign]

    await prompta._ensure_high_effort(driver)

    assert prompta._pointer_click.await_count == 2
    assert driver._call.await_count == 2


def test_named_jobs_round_trip(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    add_job(jobs_path, "flux", "Continue Flux", 1800)
    add_job(jobs_path, "tv", "Continue TV", 1800)
    add_job(jobs_path, "immediate", "Run immediately", 0)
    add_job(jobs_path, "daily", "Daily check", daily_at="07:00")
    jobs = load_jobs(jobs_path)
    assert set(jobs) == {"flux", "tv", "immediate", "daily"}
    assert jobs["flux"].interval_seconds == 1800
    assert jobs["immediate"].interval_seconds == 0
    assert jobs["daily"].daily_at == "07:00"
    remove_job(jobs_path, "tv")
    assert set(load_jobs(jobs_path)) == {"flux", "immediate", "daily"}
    clear_jobs(jobs_path)
    assert load_jobs(jobs_path) == {}


def test_daily_job_rejects_invalid_time(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HH:MM"):
        add_job(tmp_path / "jobs.json", "daily", "Daily check", daily_at="7am")


def test_daily_job_initial_schedule_uses_exact_local_time(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    job = PromptJob("daily", "Daily check", daily_at="07:00")
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    now = datetime(2026, 9, 12, 6, 30).timestamp()

    prompta._ensure_initial_schedules([job], now)

    assert prompta.due_in(job, now=now) == pytest.approx(30 * 60)


@pytest.mark.asyncio
async def test_daily_job_success_reschedules_for_next_local_day(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    job = PromptJob("daily", "Daily check", daily_at="07:00")
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]
    sent_at = datetime(2026, 9, 12, 7, 0).timestamp()
    next_day = datetime(2026, 9, 13, 7, 0).timestamp()

    with patch("prompta.core.time.time", return_value=sent_at):
        assert await prompta._run_job(job, now=sent_at) is True

    assert prompta.due_in(job, now=sent_at) == pytest.approx(next_day - sent_at)


def test_due_in_uses_persisted_last_send(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"jobs": {"flux": {"last_sent_at": 1000.0}}}))
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    assert prompta.due_in(PromptJob("flux", "same", 1800), now=1900.0) == 900.0
    assert prompta.due_in(PromptJob("flux", "changed", 1800), now=1900.0) == 900.0


def test_pause_state_round_trip(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    state_path = tmp_path / "state.json"
    add_job(jobs_path, "flux", "same")

    assert set_job_paused(jobs_path, state_path, "flux", True) is True
    assert json.loads(state_path.read_text())["jobs"]["flux"]["paused"] is True
    assert set_job_paused(jobs_path, state_path, "flux", False) is True
    assert json.loads(state_path.read_text())["jobs"]["flux"]["paused"] is False
    assert set_job_paused(jobs_path, state_path, "missing", True) is False


@pytest.mark.asyncio
async def test_paused_job_is_not_run(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"jobs": {"flux": {"paused": True}}}))
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]

    assert await prompta._run_job(PromptJob("flux", "same"), now=1000.0) is False
    assert prompta.send_once.await_count == 0


def test_due_in_uses_uncertain_send_to_prevent_duplicate_retry(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"jobs": {"flux": {"last_uncertain_send_at": 1000.0}}}))
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )

    assert prompta.due_in(PromptJob("flux", "same", 1800), now=1300.0) == 1500.0


@pytest.mark.asyncio
async def test_uncertain_send_is_persisted_instead_of_retried_rapidly(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(side_effect=SendVerificationError("uncertain"))  # type: ignore[method-assign]
    job = PromptJob("github", "bug hunt", 1800)

    with patch("prompta.core.time.time", return_value=1000.0):
        assert await prompta._run_job(job, now=1000.0) is False

    assert prompta.due_in(job, now=1001.0) == 1799.0


@pytest.mark.asyncio
async def test_rate_limit_backoff_is_account_wide_persisted_and_exponential(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(side_effect=RateLimitError("limited", retry_after=0))  # type: ignore[method-assign]
    first_job = PromptJob("flux", "continue flux", 1800)
    second_job = PromptJob("other", "continue other", 1800)

    with patch("prompta.core.random.uniform", return_value=0.0):
        await prompta._run_job(first_job, now=1000.0)
        first = prompta._global_backoff.remaining()
        assert first > 0

        await prompta._run_job(second_job, now=1000.0)
        assert prompta.send_once.await_count == 1

        restarted = Prompta(
            PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
            "ws://unused",
        )
        restarted.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]
        await restarted._run_job(second_job, now=1000.0)
        assert restarted.send_once.await_count == 0

        prompta._global_backoff.blocked_until = 0.0
        prompta._update_scheduler_state({"last_attempt_at": 0.0})
        await prompta._run_job(first_job, now=1061.0)
        second = prompta._global_backoff.remaining()

    assert second >= first * 2 - 1


@pytest.mark.asyncio
async def test_generic_failure_cooldown_survives_restart(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    job = PromptJob("flux", "continue flux", 1800)
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(side_effect=RuntimeError("browser broke"))  # type: ignore[method-assign]

    with patch("prompta.core.time.time", return_value=1000.0):
        await prompta._run_job(job, now=1000.0)

    restarted = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    restarted.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]
    await restarted._run_job(job, now=1100.0)
    assert restarted.send_once.await_count == 0

    await restarted._run_job(job, now=1301.0)
    assert restarted.send_once.await_count == 1


@pytest.mark.asyncio
async def test_send_attempts_are_spaced_across_jobs_and_restarts(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    first_job = PromptJob("one", "first", 1800)
    second_job = PromptJob("two", "second", 1800)
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]

    with patch("prompta.core.time.time", return_value=1000.0):
        assert await prompta._run_job(first_job, now=1000.0) is True

    restarted = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    restarted.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]
    assert await restarted._run_job(second_job, now=1030.0) is False
    assert restarted.send_once.await_count == 0

    assert await restarted._run_job(second_job, now=1299.0) is False
    with patch("prompta.core.time.time", return_value=1301.0):
        assert await restarted._run_job(second_job, now=1301.0) is True
    assert restarted.send_once.await_count == 1


def test_initial_schedules_are_randomised_and_persisted(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    jobs = [PromptJob("one", "first", 1800), PromptJob("two", "second", 1800)]
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )

    with patch("prompta.core.random.uniform", side_effect=[120.0, 900.0]):
        prompta._ensure_initial_schedules(jobs, 1000.0)

    assert prompta.due_in(jobs[0], now=1000.0) == 120.0
    assert prompta.due_in(jobs[1], now=1000.0) == 900.0

    restarted = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    with patch("prompta.core.random.uniform") as random_uniform:
        restarted._ensure_initial_schedules(jobs, 1100.0)
    random_uniform.assert_not_called()
    assert restarted.due_in(jobs[0], now=1100.0) == 20.0
    assert restarted.due_in(jobs[1], now=1100.0) == 800.0


@pytest.mark.asyncio
async def test_success_persists_recurring_jitter(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    job = PromptJob("flux", "continue", 1800)
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]

    with (
        patch("prompta.core.time.time", return_value=1000.0),
        patch("prompta.core.random.uniform", return_value=240.0),
    ):
        assert await prompta._run_job(job, now=1000.0) is True

    assert prompta.due_in(job, now=1001.0) == 2039.0


def test_backoff_round_trip() -> None:
    backoff = RateLimitBackoff()
    with patch("prompta.core.random.uniform", return_value=0.0):
        backoff.record(120, now=100.0)
    snapshot = backoff.snapshot(now=100.0, wall_time=1000.0)
    restored = RateLimitBackoff()
    restored.restore(snapshot, now=200.0, wall_time=1000.0)
    assert restored.attempts == 1
    assert restored.remaining(now=200.0) == 300.0


def test_backoff_resets_escalation_after_quiet_period() -> None:
    backoff = RateLimitBackoff()
    with patch("prompta.core.random.uniform", return_value=0.0):
        first = backoff.record(0, now=100.0)
        backoff.blocked_until = 0.0
        second = backoff.record(0, now=200.0)
        backoff.blocked_until = 0.0
        reset = backoff.record(0, now=2200.0)
    assert second == first * 2
    assert reset == first


def test_retry_after_parser() -> None:
    assert parse_retry_after("Try again in 30 seconds") == 30
    assert parse_retry_after("Please wait 2 minutes") == 120
    assert parse_retry_after("Try again in 1 hour") == 3600
    assert parse_retry_after("Wait a few minutes") == 300
