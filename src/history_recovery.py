"""Throttled, exact-conversation recovery of Prompta-owned response text.

This worker never sends prompts, enumerates account history, or reads other chats.
Each browser navigation is to a durable conversation identity from our own store.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable
from uuid import UUID

from .browser_script_loader import load_browser_script
from .playwright_driver import BrowserSecurityChallengeError
from .rate_limit import RateLimitError, is_rate_limited_text
from .reply_contracts import ManualReplyStore
from .response_capture import CaptureResult, normalize_dom_snapshot
from .response_store import ResponseStore
from .scheduler_runtime import SchedulerRuntime
from .strict_types import int_value

logger = logging.getLogger(__name__)
_GLOBAL_INTERVAL_SECONDS = 90.0
_MAX_PER_CHAT_INTERVAL_SECONDS = 3600.0
_LOOKUP_TIMEOUT_SECONDS = 55.0
_HISTORY_CLOSE_TIMEOUT_SECONDS = 5.0


class HistoryDriver(Protocol):
    context: str

    async def connect(self) -> None: ...
    async def navigate(self, url: str, *, context: str | None = None) -> None: ...
    async def dom_state(self) -> dict[str, object]: ...
    async def eval(self, expression: str) -> object: ...
    async def close(self) -> None: ...


@runtime_checkable
class _HistoryRateLimitSignal(Protocol):
    def history_rate_limited(self) -> bool: ...


@runtime_checkable
class _ReadLimitAPI(Protocol):
    def read_backoff_remaining(self) -> float: ...
    def record_read_rate_limit(self, exc: RateLimitError) -> float: ...


@runtime_checkable
class _LegacyLimitAPI(Protocol):
    def global_backoff_remaining(self) -> float: ...
    def record_global_rate_limit(self, exc: RateLimitError) -> float: ...


def _read_backoff_remaining(runtime: object) -> float:
    # The account admission refactor gives read throttling its own persisted gate.
    if isinstance(runtime, _ReadLimitAPI):
        return runtime.read_backoff_remaining()
    if isinstance(runtime, _LegacyLimitAPI):
        return runtime.global_backoff_remaining()
    raise RuntimeError("Read rate-limit admission is unavailable")


def _record_read_rate_limit(runtime: object, exc: RateLimitError) -> float:
    if isinstance(runtime, _ReadLimitAPI):
        return runtime.record_read_rate_limit(exc)
    if isinstance(runtime, _LegacyLimitAPI):
        return runtime.record_global_rate_limit(exc)
    raise RuntimeError("Read rate-limit recording is unavailable")


class HistoryRecovery:
    def __init__(
        self,
        results: ResponseStore,
        runtime: SchedulerRuntime,
        driver_factory: Callable[[], HistoryDriver],
    ) -> None:
        self.results = results
        self.replies = ManualReplyStore(results.path)
        self.runtime = runtime
        self.driver_factory = driver_factory

    async def _read_original_response(
        self, conversation_id: str, original_prompt: str,
    ) -> CaptureResult | None:
        script = (
            load_browser_script("historical_response_probe.js")
            .replace("__CONVERSATION__", json.dumps(conversation_id))
            .replace("__ORIGINAL_PROMPT__", json.dumps(original_prompt))
        )
        return await self._read_probe(conversation_id, script)

    async def _read_reply_response(
        self, conversation_id: str, original_prompt: str, reply_text: str, parent_id: str,
    ) -> CaptureResult | None:
        script = (
            load_browser_script("historical_reply_probe.js")
            .replace("__CONVERSATION__", json.dumps(conversation_id))
            .replace("__ORIGINAL_PROMPT__", json.dumps(original_prompt))
            .replace("__REPLY_TEXT__", json.dumps(reply_text))
            .replace("__PARENT__", json.dumps(parent_id))
        )
        return await self._read_probe(conversation_id, script)

    async def _read_probe(self, conversation_id: str, script: str) -> CaptureResult | None:
        driver = self.driver_factory()
        try:
            await driver.connect()
            await driver.navigate(
                "https://chatgpt.com/c/" + conversation_id, context=driver.context,
            )
            deadline = asyncio.get_running_loop().time() + 25.0
            while asyncio.get_running_loop().time() < deadline:
                state = await driver.dom_state()
                if (
                    isinstance(driver, _HistoryRateLimitSignal)
                    and driver.history_rate_limited()
                ):
                    raise RateLimitError("ChatGPT conversation read returned HTTP 429")
                limit_text = str(state.get("rate_limit_text") or "")
                if is_rate_limited_text(limit_text):
                    raise RateLimitError.from_text(limit_text)
                payload = await driver.eval(script)
                if isinstance(payload, dict):
                    if payload.get("rate_limited") is True:
                        raise RateLimitError()
                    if payload.get("ambiguous") is True:
                        # Hydration and streaming can transiently render two
                        # candidate nodes. Keep observing this same permitted
                        # tab until the deadline, without navigating again.
                        await asyncio.sleep(2.0)
                        continue
                    if payload.get("verified") is True:
                        result = normalize_dom_snapshot(payload)
                        if result.conversation_id == conversation_id and (result.text or result.tool_calls):
                            return result
                await asyncio.sleep(2.0)
            return None
        finally:
            try:
                # Cleanup is best effort. A failed CDP disconnect must not
                # discard a verified response that was already read.
                await asyncio.wait_for(driver.close(), timeout=_HISTORY_CLOSE_TIMEOUT_SECONDS)
            except Exception as exc:
                logger.warning(
                    "Historical recovery browser cleanup failed error_type=%s",
                    type(exc).__name__,
                )

    def recover_once(self, *, now: float | None = None) -> bool:
        """Attempt at most one due chat; all retries are read-only and persisted."""
        at = time.time() if now is None else now
        if (
            _read_backoff_remaining(self.runtime) > 0
            or self.results.history_recovery_security_pause_remaining(now=at) > 0
            or self.results.history_recovery_global_pace_remaining(now=at) > 0
        ):
            return False
        # User-pinned, already-due chats go first, without increasing scan cadence.
        pinned = self.results.next_history_recovery(now=at, pinned_only=True)
        reply = None if pinned is not None else self.replies.next_history_reply_recovery(now=at)
        candidate = pinned or reply or self.results.next_history_recovery(now=at)
        if candidate is None:
            return False
        if not self.results.reserve_history_recovery_global_slot(
            now=at, interval=_GLOBAL_INTERVAL_SECONDS,
        ):
            return False
        reply_id = str(candidate["reply_id"]) if reply is not None else ""
        send_id = "reply:" + reply_id if reply_id else str(candidate["send_id"])
        conversation_id = str(candidate["conversation_id"])
        prompt = str(candidate["user_text"])
        attempts = int_value(candidate["attempt_count"])
        delay = min(_MAX_PER_CHAT_INTERVAL_SECONDS, 90.0 * 2 ** min(attempts, 6))
        try:
            if str(UUID(conversation_id)) != conversation_id.lower():
                logger.warning("Historical recovery skipped invalid conversation identity send_id=%s", send_id)
                delay = _MAX_PER_CHAT_INTERVAL_SECONDS
            else:
                probe = (
                    self._read_reply_response(conversation_id, str(candidate["original_prompt"]),
                                              prompt, str(candidate["parent_id"]))
                    if reply_id else self._read_original_response(conversation_id, prompt)
                )
                result = asyncio.run(asyncio.wait_for(probe, timeout=_LOOKUP_TIMEOUT_SECONDS))
                recovered = result is not None and (
                    self.replies.recover_historical_reply(reply_id, result, now=at)
                    if reply_id else self.results.recover_historical_response(send_id, result, now=at)
                )
                if recovered and result is not None:
                    if result.status == "complete":
                        self.runtime.record_read_success()
                        logger.info("Historical response recovered send_id=%s", send_id)
                        return True
        except RateLimitError as exc:
            delay = max(delay, _record_read_rate_limit(self.runtime, exc))
            logger.warning("Historical recovery paused for account rate limit")
        except BrowserSecurityChallengeError:
            delay = max(delay, 30 * 60.0)
            self.results.pause_history_recovery_security(until=at + delay, now=at)
            logger.warning("Historical recovery paused for browser security challenge")
        except Exception as exc:
            logger.warning(
                "Historical recovery will retry send_id=%s error_type=%s",
                send_id, type(exc).__name__,
            )
        self.results.schedule_history_recovery(
            send_id, now=at, next_attempt_at=at + delay,
        )
        return False


def run_history_recovery(
    results: ResponseStore,
    runtime: SchedulerRuntime,
    driver_factory: Callable[[], HistoryDriver],
    *,
    stop: threading.Event | None = None,
) -> None:
    """Background loop with a global 90-second navigation budget."""
    shutdown = stop or threading.Event()
    recovery = HistoryRecovery(results, runtime, driver_factory)
    last_checked_at = 0.0
    while not shutdown.is_set():
        try:
            current = time.monotonic()
            if current - last_checked_at >= _GLOBAL_INTERVAL_SECONDS:
                if (
                    _read_backoff_remaining(runtime) <= 0
                    and results.history_recovery_security_pause_remaining() <= 0
                    and results.history_recovery_global_pace_remaining() <= 0
                ):
                    # The global pacing clock advances for each attempted scan.
                    if (results.next_history_recovery() is not None
                            or recovery.replies.next_history_reply_recovery() is not None):
                        last_checked_at = current
                        recovery.recover_once()
        except Exception as exc:
            last_checked_at = time.monotonic()
            logger.warning("Historical recovery loop will retry error_type=%s", type(exc).__name__)
        shutdown.wait(5.0)
