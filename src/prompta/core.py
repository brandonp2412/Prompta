"""Periodic fresh-chat scheduler for Prompta."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import logging
import os
import random as random
import sqlite3
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .browser_session import BrowserSession
from .cache import DEFAULT_CACHE_PATH, ActiveConversation, ChatCache
from .control_server import (
    ControlDeferredError,
)
from .control_server import (
    _acquire_daemon_lock as _acquire_daemon_lock,
)
from .control_server import (
    _control_socket_path as _control_socket_path,
)
from .control_server import (
    _daemon_is_running as _daemon_is_running,
)
from .control_server import (
    _open_control_connection as _open_control_connection,
)
from .control_server import (
    _start_control_server as _start_control_server,
)
from .conversation_actions import ConversationActions
from .conversation_actions import SendVerificationError as SendVerificationError
from .conversation_tracker import RESTART_RECOVERY_RETRY_SECONDS, ConversationTracker
from .jobs import (
    DEFAULT_INTERVAL_SECONDS as DEFAULT_INTERVAL_SECONDS,
)
from .jobs import (
    PromptJob,
    _normalise_daily_at,
    add_job,
    clear_jobs,
    load_jobs,
    remove_job,
)
from .playwright_driver import PlaywrightDriver
from .rate_limit import (
    DEFAULT_RETRY_AFTER,
    RateLimitBackoff,
    RateLimitError,
)
from .rate_limit import (
    parse_retry_after as parse_retry_after,
)
from .resource_pressure import ResourceAdmission
from .scheduler_execution import SchedulerExecution
from .scheduler_runtime import SchedulerRuntime

logger = logging.getLogger(__name__)

_RESTART_RECOVERY_MESSAGE_TIMEOUT_SECONDS = 15.0

BrowserDriver = PlaywrightDriver
DriverFactory = Callable[[], BrowserDriver]

DEFAULT_JOBS_PATH = Path.home() / ".config" / "prompta" / "jobs.json"
DEFAULT_STATE_PATH = Path.home() / ".local" / "state" / "prompta" / "state.json"
DEFAULT_CHROME_PROFILE = Path.home() / ".local" / "state" / "prompta" / "chrome-profile"
_CONTROL_CONNECT_TIMEOUT_SECONDS = 30.0
_CONTROL_SEND_TIMEOUT_SECONDS = 2 * 60 * 60.0 + 5 * 60.0
_CONTROL_RESTART_POLL_SECONDS = 0.1
_BROWSER_RESTART_REQUIRED_SUFFIX = "browser restart required"
_SEND_CONFIRM_TIMEOUT_SECONDS = 20.0
_SEND_CONFIRM_POLL_SECONDS = 0.2
_EFFORT_CONTROL_TIMEOUT_SECONDS = 20.0
_IDLE_POLL_SECONDS = 1.0
_CACHE_COMPLETION_TIMEOUT_SECONDS = 2 * 60 * 60.0
_FAILURE_RETRY_SECONDS = 300.0
_MIN_SEND_GAP_SECONDS = 5 * 60.0
_INITIAL_DELAY_CAP_SECONDS = 30 * 60.0
_RECURRING_JITTER_FRACTION = 0.20
_RECURRING_JITTER_CAP_SECONDS = 5 * 60.0


@dataclass(frozen=True)
class PromptaConfig:
    jobs_file: Path = DEFAULT_JOBS_PATH
    state_path: Path = DEFAULT_STATE_PATH
    cache_path: Path | None = None
    send_timeout_seconds: float = _SEND_CONFIRM_TIMEOUT_SECONDS


class Prompta:
    def __init__(
        self,
        config: PromptaConfig,
        browser_url: str,
        *,
        driver_factory: DriverFactory | None = None,
        resource_admission: Callable[[], tuple[bool, str]] | None = None,
    ) -> None:
        self.config = config
        self.browser = BrowserSession(browser_url, driver_factory)
        cache_path = config.cache_path
        if cache_path is None:
            cache_path = (
                DEFAULT_CACHE_PATH
                if config.jobs_file == DEFAULT_JOBS_PATH and config.state_path == DEFAULT_STATE_PATH
                else config.jobs_file.expanduser().parent / "chats.sqlite3"
            )
        self.cache = ChatCache(cache_path)
        self.conversations = ConversationTracker(
            self.cache,
            ensure_driver=lambda: self._ensure_driver(),
            ensure_route=lambda driver, expected_path, **kwargs: self._ensure_conversation_route(
                driver,
                expected_path,
                **kwargs,
            ),
            current_driver=lambda: self.driver,
            recovery_message_timeout_seconds=lambda: _RESTART_RECOVERY_MESSAGE_TIMEOUT_SECONDS,
        )
        self._active_conversations = self.conversations.active
        self.actions = ConversationActions(
            self.cache,
            self._active_conversations,
            config.send_timeout_seconds,
            ensure_driver=lambda: self._ensure_driver(),
            ensure_high_effort=lambda driver: self._ensure_high_effort(driver),
            ensure_route=lambda driver, expected_path, **kwargs: self._ensure_conversation_route(
                driver,
                expected_path,
                **kwargs,
            ),
            enrich_completed_tool_calls=lambda conversation_id, snapshot, **kwargs: (
                self._enrich_completed_tool_calls(
                    conversation_id,
                    snapshot,
                    **kwargs,
                )
            ),
            wait_for_cached_response=lambda conversation_id, **kwargs: (
                self.wait_for_cached_response(
                    conversation_id,
                    **kwargs,
                )
            ),
        )
        self.scheduler = SchedulerRuntime(config.state_path, config.jobs_file)
        self._backoffs = self.scheduler.backoffs
        self._global_backoff = self.scheduler.global_backoff
        self._failure_retry_until = self.scheduler.failure_retry_until
        self.scheduler_execution = SchedulerExecution(
            self.scheduler,
            self._active_conversations,
            config.jobs_file,
            send_once=lambda prompt, **kwargs: self.send_once(prompt, **kwargs),
            send_reply=lambda conversation_id, prompt, **kwargs: self.send_reply(
                conversation_id,
                prompt,
                **kwargs,
            ),
            sync_conversation=lambda conversation_id: self.sync_conversation(conversation_id),
            interrupt_active=lambda: self._interrupt_active_conversations(),
            current_driver=lambda: self.driver,
            set_driver=lambda value: setattr(self, "driver", value),
            conversation_complete=lambda conversation_id: (
                self.cache.status(conversation_id) == "complete"
            ),
            resource_admission=resource_admission,
        )
        self._once_requests = self.scheduler_execution.once_requests
        self._reply_requests = self.scheduler_execution.reply_requests
        self._sync_requests = self.scheduler_execution.sync_requests

    @property
    def tool_enricher(self):
        return self.conversations.tool_enricher

    @property
    def driver(self) -> BrowserDriver | None:
        return self.browser.driver

    @driver.setter
    def driver(self, value: BrowserDriver | None) -> None:
        self.browser.driver = value

    @property
    def _next_recovery_retry_at(self) -> float:
        return self.conversations.next_recovery_retry_at

    @_next_recovery_retry_at.setter
    def _next_recovery_retry_at(self, value: float) -> None:
        self.conversations.next_recovery_retry_at = value

    @staticmethod
    def _normalise(text: str) -> str:
        return " ".join(text.split()).strip()

    @staticmethod
    def _prompt_hash(prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()

    def _load_state(self) -> dict[str, Any]:
        return self.scheduler.load_state()

    def _write_state(self, state: dict[str, Any]) -> None:
        self.scheduler.write_state(state)

    def _job_state(self, name: str) -> dict[str, Any]:
        return self.scheduler.job_state(name)

    def _update_job_state(self, name: str, updates: dict[str, Any]) -> None:
        self.scheduler.update_job_state(name, updates)

    def _scheduler_state(self) -> dict[str, Any]:
        return self.scheduler.scheduler_state()

    def _update_scheduler_state(self, updates: dict[str, Any]) -> None:
        self.scheduler.update_scheduler_state(updates)

    def _persist_backoff(self, name: str, backoff: RateLimitBackoff) -> None:
        self.scheduler.persist_backoff(name, backoff)

    def _persist_global_backoff(self) -> None:
        self.scheduler.persist_global_backoff()

    def _record_global_rate_limit(self, exc: RateLimitError) -> float:
        return self.scheduler.record_global_rate_limit(exc)

    def _send_gap_remaining(self, now: float) -> float:
        return self.scheduler.send_gap_remaining(now)

    def _ensure_initial_schedules(self, jobs: list[PromptJob], now: float) -> None:
        self.scheduler.ensure_initial_schedules(jobs, now)

    @staticmethod
    def _next_delay(job: PromptJob) -> float:
        return SchedulerRuntime.next_delay(job)

    def _failure_retry_remaining(self, name: str, now: float) -> float:
        return self.scheduler.failure_retry_remaining(name, now)

    def _mark_failure(self, name: str, message: str, *, retry_until: float | None = None) -> None:
        self.scheduler.mark_failure(name, message, retry_until=retry_until)

    def read_jobs(self) -> dict[str, PromptJob]:
        return self.scheduler.read_jobs()

    def due_in(self, job: PromptJob, now: float | None = None) -> float:
        return self.scheduler.due_in(job, now)

    async def _ensure_driver(self) -> BrowserDriver:
        return await self.browser.ensure_driver()

    async def _ensure_conversation_route(
        self,
        driver: BrowserDriver,
        expected_path: str,
        *,
        context: str | None = None,
    ) -> None:
        await self.browser.ensure_conversation_route(
            driver,
            expected_path,
            context=context,
        )

    async def _pointer_click(self, driver: BrowserDriver, x: float, y: float) -> None:
        await self.browser.pointer_click(driver, x, y)

    async def _effort_trigger_info(
        self,
        driver: BrowserDriver,
        *,
        timeout: float = _EFFORT_CONTROL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        return await self.browser.effort_trigger_info(driver, timeout=timeout)

    async def _ensure_high_effort(self, driver: BrowserDriver) -> None:
        await self.browser.ensure_high_effort(
            driver,
            effort_trigger_info=lambda target: self._effort_trigger_info(target),
            pointer_click=lambda target, x, y: self._pointer_click(target, x, y),
        )

    async def send_once(
        self,
        prompt: str,
        job_name: str = "once",
        *,
        attachments: list[str] | None = None,
    ) -> str:
        return await self.actions.send_once(prompt, job_name=job_name, attachments=attachments)

    async def recover_cached_conversations(self, *, limit: int = 50) -> int:
        try:
            return await self.conversations.recover_cached_conversations(limit=limit)
        except Exception:
            self._next_recovery_retry_at = time.monotonic() + RESTART_RECOVERY_RETRY_SECONDS
            logger.exception("Prompta cached recovery failed; retrying later")
            return 0

    async def _retry_cached_recovery_if_due(self) -> bool:
        """Retry one transiently failed restart recovery without recycling the daemon."""

        if time.monotonic() < self._next_recovery_retry_at:
            return False
        self._next_recovery_retry_at = time.monotonic() + RESTART_RECOVERY_RETRY_SECONDS
        recovered = await self.recover_cached_conversations(limit=1)
        if recovered:
            logger.info(
                "Prompta recovered %d live conversation(s) after deferred retry",
                recovered,
            )
            return True
        return False

    async def sync_conversation(self, conversation_id: str) -> int:
        return await self.actions.sync_conversation(conversation_id)

    async def send_reply(
        self,
        conversation_id: str,
        prompt: str,
        *,
        attachments: list[str] | None = None,
    ) -> str:
        return await self.actions.send_reply(
            conversation_id,
            prompt,
            attachments=attachments,
        )

    async def _run_job(self, job: PromptJob, *, now: float) -> bool:
        return await self.scheduler_execution.run_job(job, now=now)

    def _interrupt_active_conversations(self) -> None:
        for active in self._active_conversations.values():
            self.cache.mark_interrupted(active.conversation_id)
        self._active_conversations.clear()

    @staticmethod
    def _apply_structured_tool_blocks(
        snapshot: dict[str, Any],
        blocks: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        return ConversationTracker.apply_structured_tool_blocks(snapshot, blocks)

    async def _enrich_completed_tool_calls(
        self,
        conversation_id: str,
        snapshot: dict[str, Any],
        *,
        active: ActiveConversation | None = None,
    ) -> dict[str, Any]:
        return await self.conversations.enrich_completed_tool_calls(
            conversation_id,
            snapshot,
            active=active,
        )

    async def stop_conversation(self, conversation_id: str) -> str:
        return await self.actions.stop_conversation(conversation_id)

    async def _poll_active_conversations(self) -> None:
        await self.conversations.poll_active_conversations()

    async def wait_for_cached_response(
        self,
        conversation_id: str,
        *,
        timeout_seconds: float = _CACHE_COMPLETION_TIMEOUT_SECONDS,
    ) -> bool:
        """Keep passively caching one conversation until the assistant response is complete."""

        deadline = asyncio.get_running_loop().time() + max(1.0, timeout_seconds)
        while any(
            active.conversation_id == conversation_id
            for active in self._active_conversations.values()
        ):
            await self._poll_active_conversations()
            matching = next(
                (
                    active
                    for active in self._active_conversations.values()
                    if active.conversation_id == conversation_id
                ),
                None,
            )
            if matching is None:
                return self.cache.status(conversation_id) != "interrupted"
            if matching.settled_at > 0:
                return True
            if asyncio.get_running_loop().time() >= deadline:
                logger.warning(
                    "Prompta cache completion timed out conversation=%s after %.0fs",
                    conversation_id,
                    timeout_seconds,
                )
                return False
            await asyncio.sleep(_IDLE_POLL_SECONDS)
        return self.cache.status(conversation_id) != "interrupted"

    async def _drain_once_requests(self) -> bool:
        return await self.scheduler_execution.drain_once_requests()

    def _reply_target_is_busy(self, conversation_id: str) -> bool:
        return self.scheduler_execution.reply_target_is_busy(conversation_id)

    async def _drain_reply_requests(self) -> bool:
        return await self.scheduler_execution.drain_reply_requests()

    async def _drain_sync_requests(self) -> bool:
        return await self.scheduler_execution.drain_sync_requests()

    async def _release_driver_if_idle(self) -> None:
        # Keep one browser session for the daemon lifetime. Reusing the resident
        # driver avoids unnecessary session churn and preserves the authenticated profile.
        return

    async def run(self, *, once: bool = False) -> None:
        while True:
            # UI sends are latency-sensitive. Drain them before browser/cache
            # maintenance so a slow active-conversation poll cannot starve new
            # messages for minutes.
            did_work = await self._drain_reply_requests()
            did_work = await self._drain_once_requests() or did_work
            did_work = await self._drain_sync_requests() or did_work

            # Dispatch due scheduled work before cache maintenance. A stale
            # recovered browser tab can block or poison browser calls, but it
            # must not starve unrelated scheduled jobs indefinitely.
            jobs = self.read_jobs()
            if jobs:
                now = time.time()
                scheduled_jobs = list(jobs.values())
                self._ensure_initial_schedules(scheduled_jobs, now)
                for job in scheduled_jobs:
                    if await self._run_job(job, now=now):
                        did_work = True
                    if self._global_backoff.remaining() > 0:
                        break
                if once:
                    for active in list(self._active_conversations.values()):
                        await self.wait_for_cached_response(active.conversation_id)
                    return

            did_work = await self._retry_cached_recovery_if_due() or did_work
            await self._poll_active_conversations()
            if self.driver is not None and self.driver.needs_browser_restart is True:
                raise RuntimeError(
                    "Browser session was lost; restarting Prompta to recycle browser"
                )

            if not jobs:
                await self._release_driver_if_idle()
                if once:
                    return
                await asyncio.sleep(_IDLE_POLL_SECONDS)
                continue

            await self._release_driver_if_idle()
            await asyncio.sleep(_IDLE_POLL_SECONDS if did_work else 1.0)

    async def close(self) -> None:
        driver = self.driver
        if driver is not None:
            poisoned = getattr(driver, "needs_browser_restart", False) is True
            for context, active in list(self._active_conversations.items()):
                complete = active.settled_at > 0
                if not poisoned:
                    try:
                        snapshot = await driver.conversation_snapshot(context)
                        messages = snapshot.get("messages")
                        if not isinstance(messages, list):
                            messages = []
                        last_message = messages[-1] if messages else None
                        has_assistant = (
                            isinstance(last_message, dict)
                            and str(last_message.get("role") or "") == "assistant"
                            and bool(str(last_message.get("content") or "").strip())
                        )
                        complete = complete or (
                            has_assistant and not bool(snapshot.get("streaming"))
                        )
                        self.cache.write_snapshot(
                            active.conversation_id,
                            snapshot,
                            complete=complete,
                        )
                    except Exception:
                        logger.debug("Could not flush Prompta cache during shutdown", exc_info=True)
                if not complete:
                    logger.info(
                        "Prompta preserving live conversation=%s for restart recovery",
                        active.conversation_id,
                    )
            self._active_conversations.clear()
            await driver.close()
            self.driver = None
        self.cache.close()


def set_job_paused(path: Path, state_path: Path, name: str, paused: bool) -> bool:
    """Set a job's paused state and return whether the job exists."""
    jobs = load_jobs(path)
    if name not in jobs:
        return False
    prompta = Prompta(PromptaConfig(jobs_file=path, state_path=state_path), "")
    prompta._update_job_state(name, {"paused": paused})
    return True


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "now"
    total_minutes = max(1, int(seconds / 60 + 0.5))
    days, remainder = divmod(total_minutes, 60 * 24)
    hours, minutes = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h" if hours else f"{days}d"
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m"


def _format_next_due(prompta: Prompta, job: PromptJob, now: float | None = None) -> str:
    current = time.time() if now is None else now
    remaining = prompta.due_in(job, current)
    when = datetime.fromtimestamp(current + remaining).astimezone().strftime("%Y-%m-%d %H:%M")
    return f"now ({when})" if remaining <= 0 else f"in {_format_duration(remaining)} ({when})"


def _job_status(prompta: Prompta, job: PromptJob) -> tuple[str, str]:
    state = prompta._job_state(job.name)
    if state.get("paused") is True:
        return "Ⅱ", "paused"
    status = str(state.get("status") or "pending")
    message = str(state.get("status_message") or "").casefold()
    if "rate limit" in message or "rate-limited" in message:
        return "⏳", "rate-limited"
    if status == "failing":
        return "✗", "failing"
    if status == "healthy":
        return "●", "healthy"
    backoff = state.get("rate_limit_backoff")
    try:
        backoff_attempts = int(backoff.get("attempts") or 0) if isinstance(backoff, dict) else 0
    except (TypeError, ValueError):
        backoff_attempts = 0
    if state.get("last_uncertain_send_at") or backoff_attempts > 0:
        return "✗", "failing"
    if state.get("last_sent_at"):
        return "●", "healthy"
    return "○", "pending"


def _prompt_preview(prompt: str, width: int = 52) -> str:
    single_line = " ".join(prompt.split())
    return single_line if len(single_line) <= width else single_line[: width - 1].rstrip() + "…"


def _uses_color(stream: Any = None) -> bool:
    stream = sys.stdout if stream is None else stream
    return bool(
        os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM") != "dumb"
        and getattr(stream, "isatty", lambda: False)()
    )


def _paint(text: str, code: str, *, stream: Any = None) -> str:
    return f"\033[{code}m{text}\033[0m" if _uses_color(stream) else text


def _status_text(status: str) -> str:
    code = {
        "healthy": "1;32",
        "failing": "1;31",
        "rate-limited": "1;33",
        "paused": "1;33",
        "pending": "2",
    }.get(status, "0")
    return _paint(status, code)


def _print_notice(icon: str, title: str, detail: str = "", *, tone: str = "36") -> None:
    marker = _paint(icon, f"1;{tone}")
    heading = _paint(title, "1")
    suffix = f"  {_paint(detail, '2')}" if detail else ""
    print(f"{marker} {heading}{suffix}")


def _print_job_table(prompta: Prompta, jobs: dict[str, PromptJob]) -> None:
    if not jobs:
        _print_notice("○", "No jobs configured", "Add one with `prompta add …`", tone="33")
        return
    rows: list[tuple[str, str, str, str, str]] = []
    for job in jobs.values():
        icon, status = _job_status(prompta, job)
        rows.append(
            (icon, status, job.name, _format_next_due(prompta, job), _prompt_preview(job.prompt))
        )
    headers = ("", "STATUS", "NAME", "NEXT DUE", "PROMPT")
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    line = "┼".join("─" * (width + 2) for width in widths)
    top = "╭" + line.replace("┼", "┬") + "╮"
    middle = "├" + line + "┤"
    bottom = "╰" + line.replace("┼", "┴") + "╯"

    print(
        f"{_paint('Prompta', '1;36')}  {_paint(f'{len(rows)} job' + ('s' if len(rows) != 1 else ''), '2')}"
    )
    print(top)
    print("│" + "│".join(f" {header.ljust(widths[i])} " for i, header in enumerate(headers)) + "│")
    print(middle)
    for icon, status, name, due, prompt in rows:
        values = (icon, status, name, due, prompt)
        rendered = []
        for i, value in enumerate(values):
            shown = _status_text(value) if i == 1 else value
            rendered.append(f" {shown}{' ' * (widths[i] - len(value))} ")
        print("│" + "│".join(rendered) + "│")
    print(bottom)


async def _wait_for_scheduler_restart(state_path: Path) -> None:
    """Wait for the poisoned scheduler process to release and then reacquire its daemon lock."""

    deadline = asyncio.get_running_loop().time() + _CONTROL_CONNECT_TIMEOUT_SECONDS
    saw_stopped = False
    while asyncio.get_running_loop().time() < deadline:
        running = _daemon_is_running(state_path)
        if not running:
            saw_stopped = True
        elif saw_stopped:
            return
        await asyncio.sleep(_CONTROL_RESTART_POLL_SECONDS)
    raise RuntimeError(
        "Prompta scheduler did not restart after the browser session became poisoned"
    )


async def _control_send_request(
    state_path: Path,
    request: dict[str, Any],
    *,
    rejected_message: str,
) -> dict[str, Any]:
    reader, writer = await _open_control_connection(state_path)
    try:
        writer.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
        await writer.drain()
        raw = await asyncio.wait_for(
            reader.readline(),
            timeout=_CONTROL_SEND_TIMEOUT_SECONDS,
        )
    finally:
        writer.close()
        await writer.wait_closed()
    if not raw:
        raise RuntimeError("Prompta scheduler closed the control connection without a response")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        error = str(payload.get("error") or rejected_message)
        error_type = str(payload.get("error_type") or "") if isinstance(payload, dict) else ""
        if error_type == "rate_limit":
            raise RateLimitError(
                error, retry_after=int(payload.get("retry_after") or DEFAULT_RETRY_AFTER)
            )
        if error_type == "deferred":
            raise ControlDeferredError(error, retry_after=float(payload.get("retry_after") or 2.0))
        raise RuntimeError(error)
    return payload


async def _control_send_request_with_restart_retry(
    state_path: Path,
    request: dict[str, Any],
    *,
    rejected_message: str,
) -> dict[str, Any]:
    try:
        return await _control_send_request(
            state_path,
            request,
            rejected_message=rejected_message,
        )
    except RuntimeError as exc:
        if _BROWSER_RESTART_REQUIRED_SUFFIX not in str(exc).lower():
            raise
    logger.info(
        "Prompta control send hit a poisoned browser session; waiting for scheduler restart"
    )
    await _wait_for_scheduler_restart(state_path)
    return await _control_send_request(
        state_path,
        request,
        rejected_message=rejected_message,
    )


async def _send_once_via_control(
    state_path: Path,
    prompt: str,
    attachments: list[str] | None = None,
) -> str:
    payload = await _control_send_request_with_restart_retry(
        state_path,
        {"op": "once", "prompt": prompt, "attachments": attachments or []},
        rejected_message="Prompta scheduler rejected one-shot request",
    )
    conversation_id = str(payload.get("conversation_id") or "")
    if not conversation_id:
        raise RuntimeError("Prompta scheduler returned an empty conversation id")
    return conversation_id


async def _send_reply_via_control(
    state_path: Path,
    conversation_id: str,
    prompt: str,
    attachments: list[str] | None = None,
    *,
    defer_if_busy: bool = False,
) -> str:
    payload = await _control_send_request_with_restart_retry(
        state_path,
        {
            "op": "reply",
            "conversation_id": conversation_id,
            "prompt": prompt,
            "attachments": attachments or [],
            "defer_if_busy": defer_if_busy,
        },
        rejected_message="Prompta scheduler rejected reply",
    )
    result = str(payload.get("conversation_id") or "")
    if not result:
        raise RuntimeError("Prompta scheduler returned an empty conversation id")
    return result


async def _stop_via_control(state_path: Path, conversation_id: str) -> str:
    path = _control_socket_path(state_path)
    try:
        reader, writer = await asyncio.open_unix_connection(str(path))
    except OSError as exc:
        raise RuntimeError(f"Prompta scheduler control socket is unavailable: {path}") from exc
    try:
        writer.write(
            (
                json.dumps(
                    {"op": "stop", "conversation_id": conversation_id},
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")
        )
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), timeout=10.0)
    finally:
        writer.close()
        await writer.wait_closed()
    if not raw:
        raise RuntimeError("Prompta scheduler closed the control connection without a response")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError(str(payload.get("error") or "Prompta scheduler rejected stop request"))
    result = str(payload.get("conversation_id") or "")
    if not result:
        raise RuntimeError("Prompta scheduler returned an empty conversation id")
    return result


async def _sync_via_control(state_path: Path, conversation_id: str) -> int:
    reader, writer = await _open_control_connection(state_path)
    try:
        writer.write(
            (
                json.dumps(
                    {"op": "sync", "conversation_id": conversation_id},
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")
        )
        await writer.drain()
        raw = await asyncio.wait_for(
            reader.readline(),
            timeout=_CONTROL_SEND_TIMEOUT_SECONDS,
        )
    finally:
        writer.close()
        await writer.wait_closed()
    if not raw:
        raise RuntimeError("Prompta scheduler closed the control connection without a response")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError(str(payload.get("error") or "Prompta scheduler rejected sync"))
    message_count = payload.get("message_count")
    if not isinstance(message_count, int) or message_count < 0:
        raise RuntimeError("Prompta scheduler returned an invalid message count")
    return message_count


async def _wait_for_cache_completion(
    cache_path: Path,
    conversation_id: str,
    *,
    timeout_seconds: float = _CACHE_COMPLETION_TIMEOUT_SECONDS,
) -> bool:
    deadline = asyncio.get_running_loop().time() + max(1.0, timeout_seconds)
    expanded = cache_path.expanduser()
    while asyncio.get_running_loop().time() < deadline:
        if expanded.exists():
            try:
                connection = sqlite3.connect(expanded, timeout=1.0)
                try:
                    row = connection.execute(
                        "SELECT status FROM conversations WHERE id = ?",
                        (conversation_id,),
                    ).fetchone()
                finally:
                    connection.close()
            except sqlite3.Error:
                row = None
            if row is not None:
                status = str(row[0] or "")
                if status == "complete":
                    return True
                if status == "interrupted":
                    return False
        await asyncio.sleep(_IDLE_POLL_SECONDS)
    return False


def _add_browser_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--send-timeout-seconds", type=float, default=_SEND_CONFIRM_TIMEOUT_SECONDS)
    parser.add_argument(
        "--direct-browser",
        action="store_true",
        help="Bypass a running Prompta daemon and use this command's browser backend directly",
    )
    parser.add_argument(
        "--browser",
        choices=("chrome",),
        default="chrome",
    )
    parser.add_argument(
        "--chrome-profile",
        type=Path,
        default=Path(os.environ.get("PROMPTA_CHROME_PROFILE", str(DEFAULT_CHROME_PROFILE))),
    )
    parser.add_argument(
        "--chrome-path",
        default=os.environ.get("PROMPTA_CHROME_PATH", "/usr/bin/chromium"),
    )
    parser.add_argument(
        "--chrome-debugger-address",
        default=os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS"),
        help="Attach Playwright to an existing Chromium-family browser CDP address",
    )
    parser.add_argument(
        "--flaresolverr-url",
        default=os.environ.get("PROMPTA_FLARESOLVERR_URL"),
        help="FlareSolverr endpoint used to recover Cloudflare-blocked ChatGPT pages",
    )
    parser.add_argument(
        "--chrome-auth-timeout-seconds",
        type=float,
        default=float(os.environ.get("PROMPTA_CHROME_AUTH_TIMEOUT_SECONDS", "30")),
        help="How long Playwright may wait for a ChatGPT login before failing",
    )
    parser.add_argument(
        "--chrome-headed",
        action="store_true",
        help="Run Chromium with a visible window (useful for the first ChatGPT login)",
    )


def _playwright_driver_factory(args: argparse.Namespace) -> DriverFactory:
    profile = args.chrome_profile.expanduser().resolve()
    chrome_path = str(args.chrome_path)
    headless = not bool(args.chrome_headed)

    def factory() -> BrowserDriver:
        return PlaywrightDriver(
            profile=profile,
            chrome_path=chrome_path,
            headless=headless,
            auth_timeout_seconds=max(0.1, float(args.chrome_auth_timeout_seconds)),
            debugger_address=args.chrome_debugger_address,
            flaresolverr_url=args.flaresolverr_url,
        )

    return factory


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send prompts into fresh ChatGPT chats, once or on a schedule"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_parser = subparsers.add_parser("add", aliases=["push"], help="Add or replace a named job")
    add_parser.add_argument("name")
    add_parser.add_argument("prompt")
    schedule_group = add_parser.add_mutually_exclusive_group()
    schedule_group.add_argument("--interval-minutes", type=float)
    schedule_group.add_argument("--daily-at", metavar="HH:MM")
    add_parser.add_argument(
        "--exact-interval",
        action="store_true",
        help="Run interval jobs without recurrence jitter",
    )
    add_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    remove_parser = subparsers.add_parser("remove", aliases=["rm"], help="Remove a named job")
    remove_parser.add_argument("name")
    remove_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    show_parser = subparsers.add_parser("show", help="Show one named job")
    show_parser.add_argument("name")
    show_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    show_parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    list_parser = subparsers.add_parser("list", aliases=["ls"], help="List configured jobs")
    list_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    list_parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    clear_parser = subparsers.add_parser("clear", aliases=["cls"], help="Remove all jobs")
    clear_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    for command, help_text in (("pause", "Pause a named job"), ("resume", "Resume a named job")):
        job_parser = subparsers.add_parser(command, help=help_text)
        job_parser.add_argument("name")
        job_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
        job_parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    once_parser = subparsers.add_parser(
        "once", help="Send one prompt immediately without creating a repeating job"
    )
    once_parser.add_argument("prompt")
    _add_browser_arguments(once_parser)
    reply_parser = subparsers.add_parser(
        "reply", help="Send a message into an existing cached conversation"
    )
    reply_parser.add_argument("conversation_id")
    reply_parser.add_argument("prompt")
    _add_browser_arguments(reply_parser)
    sync_parser = subparsers.add_parser(
        "sync", help="Refresh one cached conversation from ChatGPT without sending"
    )
    sync_parser.add_argument("conversation_id")
    _add_browser_arguments(sync_parser)
    run_parser = subparsers.add_parser("run", help="Run the scheduler")
    run_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    _add_browser_arguments(run_parser)
    run_parser.add_argument(
        "--once",
        action="store_true",
        help="Run one scheduler pass over currently due jobs, then exit",
    )
    return parser


async def _run(args: argparse.Namespace) -> None:
    if args.command == "once":
        _print_notice("◆", "One-shot", _prompt_preview(args.prompt, 72))
        if not args.direct_browser and _daemon_is_running(args.state):
            conversation_id = await _send_once_via_control(args.state, args.prompt)
            _print_notice("✓", "Sent", f"conversation {conversation_id}", tone="32")
            _print_notice("…", "Waiting", "assistant response", tone="36")
            if await _wait_for_cache_completion(args.cache, conversation_id):
                _print_notice("✓", "Cached", "assistant response complete", tone="32")
            return
    elif args.command == "reply":
        _print_notice("◆", "Reply", _prompt_preview(args.prompt, 72))
        if not args.direct_browser and _daemon_is_running(args.state):
            conversation_id = await _send_reply_via_control(
                args.state,
                args.conversation_id,
                args.prompt,
            )
            _print_notice("✓", "Sent", f"conversation {conversation_id}", tone="32")
            return
    elif args.command == "sync":
        if not args.direct_browser and _daemon_is_running(args.state):
            message_count = await _sync_via_control(args.state, args.conversation_id)
            _print_notice(
                "✓",
                "Synced",
                f"conversation {args.conversation_id} ({message_count} messages)",
                tone="32",
            )
            return

    daemon_lock: Any = None
    control_server: asyncio.AbstractServer | None = None
    control_path: Path | None = None
    prompta: Prompta | None = None

    if args.command == "run":
        daemon_lock = _acquire_daemon_lock(args.state)

    try:
        driver_factory = _playwright_driver_factory(args)

        prompta = Prompta(
            PromptaConfig(
                jobs_file=getattr(args, "jobs_file", DEFAULT_JOBS_PATH),
                state_path=args.state,
                cache_path=args.cache,
                send_timeout_seconds=max(1.0, args.send_timeout_seconds),
            ),
            "",
            driver_factory=driver_factory,
            resource_admission=ResourceAdmission() if args.command == "run" else None,
        )
        if args.command == "run":
            # Publish the control socket before browser/cache recovery. The daemon lock is
            # already held at this point, so UI sends otherwise see a running scheduler
            # but can race a potentially slow recovery and fail before the socket exists.
            control_server, control_path = await _start_control_server(prompta, args.state)
            recovered = await prompta.recover_cached_conversations()
            if recovered:
                logger.info("Prompta recovered %d live conversation(s) after restart", recovered)

        if args.command == "once":
            conversation_id = await prompta.send_once(args.prompt)
            _print_notice("✓", "Sent", f"conversation {conversation_id}", tone="32")
            _print_notice("…", "Waiting", "assistant response", tone="36")
            if await prompta.wait_for_cached_response(conversation_id):
                _print_notice("✓", "Cached", "assistant response complete", tone="32")
        elif args.command == "reply":
            conversation_id = await prompta.send_reply(args.conversation_id, args.prompt)
            _print_notice("✓", "Sent", f"conversation {conversation_id}", tone="32")
            _print_notice("…", "Waiting", "assistant response", tone="36")
            if await prompta.wait_for_cached_response(conversation_id):
                _print_notice("✓", "Cached", "assistant response complete", tone="32")
        elif args.command == "sync":
            message_count = await prompta.sync_conversation(args.conversation_id)
            _print_notice(
                "✓",
                "Synced",
                f"conversation {args.conversation_id} ({message_count} messages)",
                tone="32",
            )
        else:
            await prompta.run(once=args.once)
    finally:
        if control_server is not None:
            control_server.close()
            await control_server.wait_closed()
        if control_path is not None:
            try:
                control_path.unlink()
            except FileNotFoundError:
                pass
        if prompta is not None:
            await prompta.close()
        if daemon_lock is not None:
            fcntl.flock(daemon_lock.fileno(), fcntl.LOCK_UN)
            daemon_lock.close()


class _TerminalLogFormatter(logging.Formatter):
    _tones = {
        logging.DEBUG: ("·", "2"),
        logging.INFO: ("›", "36"),
        logging.WARNING: ("!", "33"),
        logging.ERROR: ("×", "31"),
        logging.CRITICAL: ("×", "1;31"),
    }

    def format(self, record: logging.LogRecord) -> str:
        icon, tone = self._tones.get(record.levelno, ("›", "0"))
        timestamp = datetime.fromtimestamp(record.created).astimezone().strftime("%H:%M:%S")
        message = record.getMessage().removeprefix("Prompta ").removeprefix("prompta ")
        rendered = f"{_paint(icon, tone, stream=sys.stderr)} {_paint(timestamp, '2', stream=sys.stderr)} {message}"
        if record.exc_info:
            rendered += "\n" + self.formatException(record.exc_info)
        return rendered


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_TerminalLogFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def main() -> None:
    args = _parser().parse_args()
    _configure_logging()
    if args.command in {"add", "push"}:
        interval_minutes = (
            DEFAULT_INTERVAL_SECONDS / 60.0
            if args.interval_minutes is None
            else args.interval_minutes
        )
        add_job(
            args.jobs_file,
            args.name,
            args.prompt,
            max(0.0, interval_minutes * 60.0),
            args.daily_at,
            args.exact_interval,
        )
        if args.daily_at is not None:
            detail = f"daily at {_normalise_daily_at(args.daily_at)} local time"
        else:
            detail = f"every {_format_duration(interval_minutes * 60)}"
            if args.exact_interval:
                detail += " exactly"
        _print_notice("✓", f"Saved {args.name}", detail, tone="32")
        return
    if args.command in {"remove", "rm"}:
        existed = args.name in load_jobs(args.jobs_file)
        remove_job(args.jobs_file, args.name)
        if existed:
            _print_notice("✓", f"Removed {args.name}", tone="32")
        else:
            _print_notice("○", f"No job named {args.name}", tone="33")
        return
    if args.command == "show":
        job = load_jobs(args.jobs_file).get(args.name)
        if job is None:
            raise SystemExit(f"No Prompta job named {args.name!r}")
        prompta = Prompta(PromptaConfig(jobs_file=args.jobs_file, state_path=args.state), "")
        icon, status = _job_status(prompta, job)
        state = prompta._job_state(job.name)
        print(f"{icon} {_paint(job.name, '1')}  {_status_text(status)}")
        print(_paint("─" * max(24, len(job.name) + len(status) + 4), "2"))
        if job.daily_at is not None:
            print(f"{_paint('Schedule', '2')}  daily at {job.daily_at} local time")
        else:
            interval = _format_duration(job.interval_seconds)
            if job.exact_interval:
                interval += " exactly"
            print(f"{_paint('Interval', '2')}  {interval}")
        print(f"{_paint('Next due', '2')}  {_format_next_due(prompta, job)}")
        if state.get("status_message"):
            print(f"{_paint('Issue', '2')}     {_paint(str(state['status_message']), '31')}")
        print(f"{_paint('Prompt', '2')}    {job.prompt}")
        return
    if args.command in {"list", "ls"}:
        prompta = Prompta(PromptaConfig(jobs_file=args.jobs_file, state_path=args.state), "")
        _print_job_table(prompta, load_jobs(args.jobs_file))
        return
    if args.command in {"clear", "cls"}:
        count = len(load_jobs(args.jobs_file))
        clear_jobs(args.jobs_file)
        _print_notice("✓", f"Cleared {count} job{'s' if count != 1 else ''}", tone="32")
        return
    if args.command in {"pause", "resume"}:
        jobs = load_jobs(args.jobs_file)
        if args.name not in jobs:
            raise SystemExit(f"No Prompta job named {args.name!r}")
        paused = args.command == "pause"
        set_job_paused(args.jobs_file, args.state, args.name, paused)
        _print_notice(
            "Ⅱ" if paused else "▶",
            f"{'Paused' if paused else 'Resumed'} {args.name}",
            tone="33" if paused else "32",
        )
        return
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
