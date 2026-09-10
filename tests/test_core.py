from __future__ import annotations

import json
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
    add_job,
    clear_jobs,
    load_jobs,
    parse_retry_after,
    remove_job,
)


class FakeDriver:
    def __init__(self, prompt: str, initial_composer: str = "") -> None:
        self.prompt = prompt
        self.is_connected = True
        self.context = "context-1"
        self.typed = initial_composer
        self.sent = False
        self.clear_composer_calls = 0
        self.capture: dict[str, object] = {
            "request_id": "request-1",
            "status": 200,
            "response_started": True,
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
                "last_user_text": self.prompt,
                "last_user_id": "message-1",
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

    def arm_send_capture(self) -> dict[str, object]:
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
        return {"message_id": "message-1", "response_status": 200, "committed": True}

    def captured_send_response(self, capture: dict[str, object]) -> tuple[str, int] | None:
        return ("request-1", 200)

    async def eval(self, expression: str) -> str:
        assert expression == "location.pathname"
        return "/c/new-chat"

    def clear_send_capture(self, capture: dict[str, object]) -> None:
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
    jobs = load_jobs(jobs_path)
    assert set(jobs) == {"flux", "tv"}
    assert jobs["flux"].interval_seconds == 1800
    remove_job(jobs_path, "tv")
    assert set(load_jobs(jobs_path)) == {"flux"}
    clear_jobs(jobs_path)
    assert load_jobs(jobs_path) == {}


def test_due_in_uses_persisted_last_send(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"jobs": {"flux": {"last_sent_at": 1000.0}}}))
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    assert prompta.due_in(PromptJob("flux", "same", 1800), now=1900.0) == 900.0
    assert prompta.due_in(PromptJob("flux", "changed", 1800), now=1900.0) == 900.0


@pytest.mark.asyncio
async def test_rate_limit_backoff_is_exponential_and_job_scoped(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(side_effect=RateLimitError("limited", retry_after=0))  # type: ignore[method-assign]
    job = PromptJob("flux", "continue flux", 1800)
    with patch("prompta.core.random.uniform", return_value=0.0):
        await prompta._run_job(job, now=1000.0)
        first = prompta._backoffs["flux"].remaining()
        prompta._backoffs["flux"].blocked_until = 0.0
        await prompta._run_job(job, now=1000.0)
        second = prompta._backoffs["flux"].remaining()
    assert second >= first * 2
    assert "other" not in prompta._backoffs


def test_backoff_round_trip() -> None:
    backoff = RateLimitBackoff()
    with patch("prompta.core.random.uniform", return_value=0.0):
        backoff.record(120, now=100.0)
    snapshot = backoff.snapshot(now=100.0, wall_time=1000.0)
    restored = RateLimitBackoff()
    restored.restore(snapshot, now=200.0, wall_time=1000.0)
    assert restored.attempts == 1
    assert restored.remaining(now=200.0) == 120.0


def test_retry_after_parser() -> None:
    assert parse_retry_after("Try again in 30 seconds") == 30
    assert parse_retry_after("Please wait 2 minutes") == 120
    assert parse_retry_after("Try again in 1 hour") == 3600
    assert parse_retry_after("Wait a few minutes") == 300
