from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prompta.cache import ActiveConversation, ChatCache
from prompta.core import (
    Prompta,
    PromptaConfig,
    PromptJob,
    RateLimitBackoff,
    RateLimitError,
    SendVerificationError,
    _daemon_is_running,
    _parser,
    _run,
    _send_direct,
    _send_once_via_control,
    _send_reply_via_control,
    _start_control_server,
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

    async def new_tab(self, url: str = "https://chatgpt.com/") -> str:
        self.context = "context-new"
        self.navigated.append(url)
        return self.context

    async def close_context(self, context: str) -> None:
        return None

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
    prompta._ensure_high_effort.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_scheduled_send_requires_high_effort(tmp_path: Path) -> None:
    prompt = "PROMPTA SCHEDULED TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta._ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    assert await prompta.send_once(prompt, job_name="scheduled-job") == "new-chat"

    prompta._ensure_high_effort.assert_awaited_once_with(fake)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_send_once_accepts_visible_user_message_without_transport_confirmation(
    tmp_path: Path,
) -> None:
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
async def test_send_once_ignores_provisional_web_route_until_durable_id(tmp_path: Path) -> None:
    prompt = "PROMPTA TEST"

    class ProvisionalRouteDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__(prompt, committed=False, capture_status=0)
            self.route_reads = 0

        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            if not self.sent:
                return "/"
            self.route_reads += 1
            if self.route_reads < 3:
                return "/c/WEB:temporary"
            return "/c/durable-chat"

    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
            send_timeout_seconds=1.0,
        ),
        "ws://unused",
    )
    fake = ProvisionalRouteDriver()
    prompta.driver = cast(Any, fake)
    prompta._ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt)

    assert conversation_id == "durable-chat"
    assert fake.route_reads >= 3
    assert prompta.cache.metadata(conversation_id)["url"] == "https://chatgpt.com/c/durable-chat"
    prompta.cache.close()


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
async def test_send_reply_reuses_retained_conversation_tab(tmp_path: Path) -> None:
    prompt = "Continue from the UI"
    conversation_id = "existing-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class ReplyFakeDriver(FakeDriver):
        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return f"/c/{conversation_id}"

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-1"
            return {
                "title": "Existing chat",
                "path": f"/c/{conversation_id}",
                "streaming": True,
                "messages": [
                    {"id": "u1", "role": "user", "content": prompt},
                ],
            }

    fake = ReplyFakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta._ensure_high_effort = AsyncMock()  # type: ignore[method-assign]
    prompta.cache.start(
        conversation_id,
        context_id="context-1",
        job_name="kite",
        prompt="Original prompt",
    )
    prompta._active_conversations["context-1"] = ActiveConversation(
        conversation_id=conversation_id,
        context_id="context-1",
        job_name="kite",
        prompt="Original prompt",
        settled_at=1.0,
    )

    result = await prompta.send_reply(conversation_id, prompt)

    assert result == conversation_id
    assert fake.navigated == []
    assert fake.sent is True
    assert prompta._active_conversations["context-1"].settled_at == 0.0
    assert prompta.cache.recent_conversations()[0]["status"] == "active"
    await prompta.close()


@pytest.mark.asyncio
async def test_send_reply_recovers_history_link_after_deep_link_redirect(
    tmp_path: Path,
) -> None:
    prompt = "Continue from the UI"
    conversation_id = "WEB:legacy-chat"
    current_path = "/c/permanent-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class LegacyReplyFakeDriver(FakeDriver):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.path = "/"
            self.history_activations: list[str] = []

        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return self.path

        async def activate_history_link(self, path: str) -> bool:
            self.history_activations.append(path)
            self.path = path
            return True

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            return {
                "title": "Legacy chat",
                "path": current_path,
                "streaming": True,
                "messages": [
                    {"id": "u2", "role": "user", "content": prompt},
                ],
            }

    fake = LegacyReplyFakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta._ensure_high_effort = AsyncMock()  # type: ignore[method-assign]
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="",
        prompt="Original prompt",
    )
    with prompta.cache.connection:
        prompta.cache.connection.execute(
            "UPDATE conversations SET url = ? WHERE id = ?",
            (f"https://chatgpt.com{current_path}", conversation_id),
        )

    result = await prompta.send_reply(conversation_id, prompt)

    assert result == conversation_id
    assert fake.navigated == [f"https://chatgpt.com{current_path}"]
    assert fake.history_activations == [current_path]
    assert fake.sent is True
    await prompta.close()


@pytest.mark.asyncio
async def test_send_reply_recovers_when_deep_link_has_no_composer(tmp_path: Path) -> None:
    prompt = "Continue from the UI"
    conversation_id = "WEB:legacy-chat"
    current_path = "/c/permanent-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class MissingComposerReplyFakeDriver(FakeDriver):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.path = "/"
            self.wait_calls = 0
            self.history_activations: list[str] = []

        async def wait_for_composer(self) -> None:
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise RuntimeError("ChatGPT composer did not become ready")

        async def navigate(self, url: str) -> None:
            self.navigated.append(url)
            self.path = "/"

        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return self.path

        async def activate_history_link(self, path: str) -> bool:
            self.history_activations.append(path)
            self.path = path
            return True

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            return {
                "title": "Legacy chat",
                "path": current_path,
                "streaming": True,
                "messages": [
                    {"id": "u3", "role": "user", "content": prompt},
                ],
            }

    fake = MissingComposerReplyFakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta._ensure_high_effort = AsyncMock()  # type: ignore[method-assign]
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="",
        prompt="Original prompt",
    )
    with prompta.cache.connection:
        prompta.cache.connection.execute(
            "UPDATE conversations SET url = ? WHERE id = ?",
            (f"https://chatgpt.com{current_path}", conversation_id),
        )

    result = await prompta.send_reply(conversation_id, prompt)

    assert result == conversation_id
    assert fake.navigated == [
        f"https://chatgpt.com{current_path}",
        "https://chatgpt.com/",
    ]
    assert fake.history_activations == [current_path]
    assert fake.wait_calls == 3
    assert fake.sent is True
    await prompta.close()


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


def test_daemon_check_does_not_create_lock_file(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"

    assert _daemon_is_running(state_path) is False
    assert not (tmp_path / "daemon.lock").exists()


@pytest.mark.asyncio
async def test_send_direct_waits_for_cached_response_and_stops_firefox(tmp_path: Path) -> None:
    process = MagicMock()
    process.returncode = None
    process.wait = AsyncMock(return_value=0)
    prompta = MagicMock()
    prompta.send_once = AsyncMock(return_value="chat-direct")
    prompta.wait_for_cached_response = AsyncMock(return_value=True)
    prompta.close = AsyncMock()

    with (
        patch("prompta.core._spawn_firefox", AsyncMock(return_value=process)),
        patch("prompta.core.Prompta", return_value=prompta),
    ):
        result = await _send_direct(
            tmp_path / "state.json",
            tmp_path / "chats.sqlite3",
            "Hello",
        )

    assert result == "chat-direct"
    prompta.send_once.assert_awaited_once_with("Hello")
    prompta.wait_for_cached_response.assert_awaited_once_with("chat-direct")
    prompta.close.assert_awaited_once()
    process.terminate.assert_called_once()


def test_named_jobs_round_trip(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    add_job(jobs_path, "flux", "Continue Flux", 1800)
    add_job(jobs_path, "tv", "Continue TV", 1800)
    add_job(jobs_path, "immediate", "Run immediately", 0)
    add_job(jobs_path, "exact", "Run exactly", 1800, exact_interval=True)
    add_job(jobs_path, "daily", "Daily check", daily_at="07:00")
    jobs = load_jobs(jobs_path)
    assert set(jobs) == {"flux", "tv", "immediate", "exact", "daily"}
    assert jobs["flux"].interval_seconds == 1800
    assert jobs["immediate"].interval_seconds == 0
    assert jobs["exact"].exact_interval is True
    assert jobs["daily"].daily_at == "07:00"
    remove_job(jobs_path, "tv")
    assert set(load_jobs(jobs_path)) == {"flux", "immediate", "exact", "daily"}
    clear_jobs(jobs_path)
    assert load_jobs(jobs_path) == {}


def test_daily_job_rejects_invalid_time(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HH:MM"):
        add_job(tmp_path / "jobs.json", "daily", "Daily check", daily_at="7am")


def test_exact_interval_has_no_recurring_jitter() -> None:
    with patch("prompta.core.random.uniform", return_value=300.0):
        assert Prompta._next_delay(PromptJob("exact", "run", 1800, exact_interval=True)) == 1800


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


def test_ls_alias_parses_as_list_command() -> None:
    args = _parser().parse_args(["ls"])

    assert args.command == "ls"
    assert hasattr(args, "jobs_file")
    assert hasattr(args, "state")


def test_once_command_parses_as_non_scheduled_prompt() -> None:
    args = _parser().parse_args(["once", "Do exactly one thing", "--bidi-url", "ws://test"])

    assert args.command == "once"
    assert args.prompt == "Do exactly one thing"
    assert args.bidi_url == "ws://test"
    assert not hasattr(args, "jobs_file")


@pytest.mark.asyncio
async def test_once_command_sends_exactly_once_without_scheduler(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _parser().parse_args(["once", "Do exactly one thing", "--bidi-url", "ws://test"])

    with (
        patch.object(Prompta, "send_once", AsyncMock(return_value="conversation-123")) as send_once,
        patch.object(
            Prompta,
            "wait_for_cached_response",
            AsyncMock(return_value=True),
        ) as wait_for_cached_response,
        patch.object(Prompta, "run", AsyncMock()) as run,
        patch.object(Prompta, "close", AsyncMock()),
    ):
        await _run(args)

    send_once.assert_awaited_once_with("Do exactly one thing")
    wait_for_cached_response.assert_awaited_once_with("conversation-123")
    run.assert_not_awaited()
    output = capsys.readouterr().out
    assert "One-shot" in output
    assert "conversation conversation-123" in output
    assert "assistant response complete" in output


@pytest.mark.asyncio
async def test_control_socket_routes_one_shot_through_scheduler(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=state_path,
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation-via-daemon")  # type: ignore[method-assign]
    server, socket_path = await _start_control_server(prompta, state_path)
    try:
        client = asyncio.create_task(_send_once_via_control(state_path, "Do one thing"))
        for _ in range(100):
            if not prompta._once_requests.empty():
                break
            await asyncio.sleep(0.01)
        assert not prompta._once_requests.empty()
        await prompta._drain_once_requests()
        assert await client == "conversation-via-daemon"
        prompta.send_once.assert_awaited_once_with("Do one thing")  # type: ignore[attr-defined]
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)
        prompta.cache.close()


@pytest.mark.asyncio
async def test_control_socket_routes_reply_through_scheduler(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=state_path,
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.send_reply = AsyncMock(return_value="existing-chat")  # type: ignore[method-assign]
    server, socket_path = await _start_control_server(prompta, state_path)
    try:
        client = asyncio.create_task(
            _send_reply_via_control(state_path, "existing-chat", "Continue here")
        )
        for _ in range(100):
            if not prompta._reply_requests.empty():
                break
            await asyncio.sleep(0.01)
        assert not prompta._reply_requests.empty()
        await prompta._drain_reply_requests()
        assert await client == "existing-chat"
        prompta.send_reply.assert_awaited_once_with("existing-chat", "Continue here")  # type: ignore[attr-defined]
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)
        prompta.cache.close()


@pytest.mark.asyncio
async def test_once_uses_running_scheduler_without_spawning_firefox(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _parser().parse_args(["once", "Do exactly one thing"])
    with (
        patch("prompta.core._daemon_is_running", return_value=True),
        patch(
            "prompta.core._send_once_via_control",
            AsyncMock(return_value="conversation-queued"),
        ) as send_via_control,
        patch(
            "prompta.core._wait_for_cache_completion",
            AsyncMock(return_value=True),
        ) as wait_for_cache,
        patch("prompta.core._spawn_firefox", AsyncMock()) as spawn_firefox,
    ):
        await _run(args)

    send_via_control.assert_awaited_once_with(args.state, "Do exactly one thing")
    wait_for_cache.assert_awaited_once_with(args.cache, "conversation-queued")
    spawn_firefox.assert_not_awaited()
    output = capsys.readouterr().out
    assert "conversation conversation-queued" in output
    assert "assistant response complete" in output


@pytest.mark.asyncio
async def test_poll_active_conversations_reconnects_before_cache_capture(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.cache.start(
        "conversation-123",
        context_id="context-1",
        job_name="",
        prompt="Do exactly one thing",
    )
    prompta._active_conversations["context-1"] = ActiveConversation(
        conversation_id="conversation-123",
        context_id="context-1",
        job_name="",
        prompt="Do exactly one thing",
    )

    driver = MagicMock()
    driver.is_connected = False

    async def connect() -> None:
        driver.is_connected = True

    driver.connect = AsyncMock(side_effect=connect)
    driver.conversation_snapshot = AsyncMock(
        return_value={
            "title": "Recovered chat",
            "messages": [
                {
                    "id": "user-1",
                    "role": "user",
                    "content": "Do exactly one thing",
                    "status": "complete",
                },
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": "Done",
                    "status": "complete",
                },
            ],
            "streaming": False,
        }
    )
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()

    driver.connect.assert_awaited_once()
    driver.conversation_snapshot.assert_awaited_once_with("context-1")
    assert [message["content"] for message in prompta.cache.messages("conversation-123")] == [
        "Do exactly one thing",
        "Done",
    ]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_wait_for_cached_response_polls_until_conversation_completes(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta._active_conversations["context-1"] = ActiveConversation(
        conversation_id="conversation-123",
        context_id="context-1",
        job_name="",
        prompt="Do exactly one thing",
    )

    async def complete_on_poll() -> None:
        prompta._active_conversations.clear()

    prompta._poll_active_conversations = AsyncMock(side_effect=complete_on_poll)  # type: ignore[method-assign]

    assert await prompta.wait_for_cached_response("conversation-123", timeout_seconds=1) is True
    prompta._poll_active_conversations.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_run_does_not_abort_just_because_driver_disconnected(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    driver = MagicMock()
    driver.is_connected = False
    prompta.driver = cast(Any, driver)
    prompta._poll_active_conversations = AsyncMock()  # type: ignore[method-assign]
    prompta._drain_reply_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]
    prompta._drain_once_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]
    prompta.read_jobs = MagicMock(return_value={})  # type: ignore[method-assign]

    await prompta.run(once=True)

    prompta._poll_active_conversations.assert_awaited_once()  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_close_preserves_completed_retained_conversation(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.cache.start(
        "conversation-123",
        context_id="context-1",
        job_name="",
        prompt="Do work",
    )
    active = ActiveConversation(
        conversation_id="conversation-123",
        context_id="context-1",
        job_name="",
        prompt="Do work",
        settled_at=1.0,
    )
    prompta._active_conversations["context-1"] = active

    driver = MagicMock()
    driver.conversation_snapshot = AsyncMock(
        return_value={
            "title": "Completed",
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": "Done"},
            ],
            "streaming": False,
        }
    )
    driver.close = AsyncMock()
    prompta.driver = cast(Any, driver)

    await prompta.close()

    cache = ChatCache(tmp_path / "chats.sqlite3")
    conversation = cache.recent_conversations()[0]
    cache.close()
    assert conversation["status"] == "complete"


@pytest.mark.asyncio
async def test_scheduler_once_waits_for_started_conversation_cache(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    job = PromptJob("e2e", "Do one thing", interval_seconds=0, exact_interval=True)
    prompta.read_jobs = MagicMock(return_value={"e2e": job})  # type: ignore[method-assign]
    prompta._ensure_initial_schedules = MagicMock()  # type: ignore[method-assign]

    async def start_conversation(*args: Any, **kwargs: Any) -> bool:
        prompta._active_conversations["context-1"] = ActiveConversation(
            conversation_id="conversation-123",
            context_id="context-1",
            job_name="e2e",
            prompt=job.prompt,
        )
        return True

    prompta._run_job = AsyncMock(side_effect=start_conversation)  # type: ignore[method-assign]
    prompta.wait_for_cached_response = AsyncMock(return_value=True)  # type: ignore[method-assign]

    await prompta.run(once=True)

    prompta.wait_for_cached_response.assert_awaited_once_with("conversation-123")  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_one_shot_waits_for_stream_and_persists_messages_end_to_end(tmp_path: Path) -> None:
    prompt = "Reply with exactly PROMPTA_CACHE_E2E_OK and nothing else."
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class StreamingFakeDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__(prompt)
            self.snapshot_calls = 0

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            self.snapshot_calls += 1
            messages: list[dict[str, str]] = [{"id": "u1", "role": "user", "content": prompt}]
            streaming = self.snapshot_calls < 3
            if self.snapshot_calls >= 2:
                messages.append(
                    {
                        "id": "a1",
                        "role": "assistant",
                        "content": "PROMPTA_CACHE_E2E_OK",
                    }
                )
            return {
                "title": "Prompta cache E2E",
                "path": "/c/new-chat",
                "streaming": streaming,
                "messages": messages,
            }

    fake = StreamingFakeDriver()
    prompta.driver = cast(Any, fake)
    prompta._ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    with patch("prompta.core.asyncio.sleep", AsyncMock()):
        conversation_id = await prompta.send_once(prompt)
        completed = await prompta.wait_for_cached_response(
            conversation_id,
            timeout_seconds=5,
        )

    assert completed is True
    rows = prompta.cache.recent_conversations()
    messages = prompta.cache.messages(conversation_id)
    assert rows[0]["status"] == "complete"
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "PROMPTA_CACHE_E2E_OK"
    assert messages[-1]["status"] == "complete"
    assert fake.snapshot_calls >= 6
    await prompta.close()
