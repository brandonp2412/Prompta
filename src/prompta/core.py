"""Periodic fresh-chat scheduler for Prompta."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from websockets.exceptions import ConnectionClosed

from .bidi import FirefoxBiDiDriver, wait_for_port
from .cache import DEFAULT_CACHE_PATH, ActiveConversation, ChatCache
from .chrome import ChromeDriverDriver
from .chromium import ChromiumToolEnricher, merge_tool_blocks

logger = logging.getLogger(__name__)

BrowserDriver = FirefoxBiDiDriver | ChromeDriverDriver
DriverFactory = Callable[[], BrowserDriver]

DEFAULT_INTERVAL_SECONDS = 30 * 60
DEFAULT_JOBS_PATH = Path.home() / ".config" / "prompta" / "jobs.json"
DEFAULT_STATE_PATH = Path.home() / ".local" / "state" / "prompta" / "state.json"
DEFAULT_FIREFOX_PROFILE = Path.home() / ".local" / "state" / "prompta" / "firefox-profile"
DEFAULT_FIREFOX_PORT = 9229
DEFAULT_CHROME_PROFILE = Path.home() / ".local" / "state" / "prompta" / "chrome-profile"
_CONTROL_SOCKET_NAME = "control.sock"
_DAEMON_LOCK_NAME = "daemon.lock"
_CONTROL_CONNECT_TIMEOUT_SECONDS = 30.0
_CONTROL_SEND_TIMEOUT_SECONDS = 2 * 60 * 60.0 + 5 * 60.0
_CONTROL_RESTART_POLL_SECONDS = 0.1
_BROWSER_RESTART_REQUIRED_SUFFIX = "browser restart required"
DEFAULT_RETRY_AFTER = 5 * 60
_SEND_CONFIRM_TIMEOUT_SECONDS = 20.0
_SEND_CONFIRM_POLL_SECONDS = 0.2
_EFFORT_CONTROL_TIMEOUT_SECONDS = 20.0
_IDLE_POLL_SECONDS = 1.0
_LIVE_SNAPSHOT_INTERVAL_SECONDS = 2.0
_CACHE_COMPLETION_TIMEOUT_SECONDS = 2 * 60 * 60.0
_RESTART_RECOVERY_INTERRUPTED_SECONDS = 15 * 60.0
_RESTART_RECOVERY_MESSAGE_TIMEOUT_SECONDS = 15.0
_RESTART_RECOVERY_LOAD_ATTEMPTS = 2
_RESTART_RECOVERY_RETRY_SECONDS = 60.0
_ACTIVE_TAB_RETENTION_SECONDS = 15.0
_FALLBACK_COMPLETION_POLLS = 10
_DELIVERY_FAILURE_POLLS = 3
_DELIVERY_RETRY_DISCOVERY_POLLS = 3
_DELIVERY_RETRY_MAX_ATTEMPTS = 1
_DELIVERY_RETRY_GRACE_SECONDS = 15.0
_DELIVERY_RECOVERY_MAX_ATTEMPTS = 1
_DELIVERY_RECOVERY_GRACE_SECONDS = 15.0
_TRANSIENT_FAILURE_TIMEOUT_SECONDS = 15 * 60.0
_TRANSIENT_RECOVERY_GRACE_SECONDS = 15.0
_FIREFOX_REUSE_POLL_SECONDS = 0.25
_FIREFOX_REUSE_STABILITY_CHECKS = 12
_FIREFOX_PROFILE_RELEASE_TIMEOUT_SECONDS = 30.0
_FAILURE_RETRY_SECONDS = 300.0
_MIN_SEND_GAP_SECONDS = 5 * 60.0
_INITIAL_DELAY_CAP_SECONDS = 30 * 60.0
_RECURRING_JITTER_FRACTION = 0.20
_RECURRING_JITTER_CAP_SECONDS = 5 * 60.0
_RATE_LIMIT_BACKOFF_CAP_SECONDS = 30 * 60.0
_RATE_LIMIT_RESET_SECONDS = 30 * 60.0
_RATE_LIMIT_JITTER_FRACTION = 0.10
_RATE_LIMIT_JITTER_CAP_SECONDS = 60.0


class RateLimitError(RuntimeError):
    def __init__(
        self, message: str = "ChatGPT rate limit reached", retry_after: int = DEFAULT_RETRY_AFTER
    ) -> None:
        super().__init__(message)
        self.retry_after = max(0, int(retry_after))

    @classmethod
    def from_text(cls, text: str) -> RateLimitError:
        message = text.strip() or "ChatGPT rate limit reached"
        return cls(message, retry_after=parse_retry_after(message))


class SendVerificationError(RuntimeError):
    """The send action happened, but ChatGPT did not expose enough evidence to prove its outcome."""


def parse_retry_after(text: str) -> int:
    lowered = text.casefold()
    if re.search(r"\b(?:a\s+)?few\s+(?:minutes?|mins?)\b", lowered):
        return 5 * 60
    match = re.search(r"\b(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b", lowered)
    if match is None:
        return DEFAULT_RETRY_AFTER
    value = int(match.group(1))
    unit = match.group(2)
    if unit.startswith(("hour", "hr")):
        return value * 60 * 60
    return value * 60 if unit.startswith(("min", "minute")) else value


def is_rate_limited_text(text: str) -> bool:
    lowered = " ".join(text.casefold().split())
    return any(
        phrase in lowered
        for phrase in (
            "too many requests",
            "rate limit",
            "try again in",
            "wait a few minutes",
            "you've reached the current usage cap",
            "you have reached the current usage cap",
        )
    )


class RateLimitBackoff:
    def __init__(self) -> None:
        self.attempts = 0
        self.blocked_until = 0.0
        self.last_limited_at = 0.0

    def snapshot(
        self,
        *,
        now: float | None = None,
        wall_time: float | None = None,
    ) -> dict[str, float | int]:
        now = time.monotonic() if now is None else now
        wall_time = time.time() if wall_time is None else wall_time
        remaining = self.remaining(now=now)
        limited_age = max(0.0, now - self.last_limited_at) if self.attempts else 0.0
        return {
            "attempts": self.attempts,
            "blocked_until_epoch": wall_time + remaining,
            "last_limited_at_epoch": wall_time - limited_age,
        }

    def restore(
        self,
        snapshot: dict[str, Any],
        *,
        now: float | None = None,
        wall_time: float | None = None,
    ) -> None:
        now = time.monotonic() if now is None else now
        wall_time = time.time() if wall_time is None else wall_time
        attempts = max(0, int(snapshot.get("attempts") or 0))
        blocked_until_epoch = float(snapshot.get("blocked_until_epoch") or 0.0)
        last_limited_epoch = float(snapshot.get("last_limited_at_epoch") or 0.0)
        remaining = max(0.0, blocked_until_epoch - wall_time)
        limited_age = max(0.0, wall_time - last_limited_epoch) if last_limited_epoch else 0.0
        if not attempts or (remaining <= 0 and limited_age >= _RATE_LIMIT_RESET_SECONDS):
            self.reset()
            return
        self.attempts = attempts
        self.blocked_until = now + remaining
        self.last_limited_at = now - limited_age

    def record(self, retry_after: float = 0.0, *, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        if (
            self.attempts
            and self.last_limited_at
            and now - self.last_limited_at >= _RATE_LIMIT_RESET_SECONDS
        ):
            self.reset()
        self.attempts += 1
        exponential = min(
            _RATE_LIMIT_BACKOFF_CAP_SECONDS,
            float(DEFAULT_RETRY_AFTER) * (2 ** min(self.attempts - 1, 20)),
        )
        floor = max(exponential, max(0.0, float(retry_after)))
        jitter_cap = min(_RATE_LIMIT_JITTER_CAP_SECONDS, floor * _RATE_LIMIT_JITTER_FRACTION)
        delay = floor + random.uniform(0.0, jitter_cap)
        self.last_limited_at = now
        self.blocked_until = max(self.blocked_until, now + delay)
        return max(0.0, self.blocked_until - now)

    def remaining(self, *, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        return max(0.0, self.blocked_until - now)

    def reset(self) -> None:
        self.attempts = 0
        self.blocked_until = 0.0
        self.last_limited_at = 0.0


def _normalise_daily_at(value: str) -> str:
    candidate = value.strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", candidate):
        raise ValueError("daily time must be HH:MM in 24-hour local time")
    return candidate


def _next_daily_epoch(daily_at: str, now: float, *, include_now: bool = False) -> float:
    hour, minute = (int(part) for part in _normalise_daily_at(daily_at).split(":"))
    current = datetime.fromtimestamp(now)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    candidate_epoch = candidate.timestamp()
    if candidate_epoch < now or (candidate_epoch == now and not include_now):
        candidate = candidate + timedelta(days=1)
        candidate_epoch = candidate.timestamp()
    return candidate_epoch


@dataclass(frozen=True)
class PromptJob:
    name: str
    prompt: str
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    daily_at: str | None = None
    exact_interval: bool = False
    run_at_epoch: float | None = None


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
        bidi_url: str,
        *,
        driver_factory: DriverFactory | None = None,
    ) -> None:
        self.config = config
        self.bidi_url = bidi_url
        self._driver_factory = driver_factory
        self.driver: BrowserDriver | None = None
        cache_path = config.cache_path
        if cache_path is None:
            cache_path = (
                DEFAULT_CACHE_PATH
                if config.jobs_file == DEFAULT_JOBS_PATH and config.state_path == DEFAULT_STATE_PATH
                else config.jobs_file.expanduser().parent / "chats.sqlite3"
            )
        self.cache = ChatCache(cache_path)
        self.tool_enricher = ChromiumToolEnricher()
        self._active_conversations: dict[str, ActiveConversation] = {}
        self._next_recovery_retry_at = time.monotonic() + _RESTART_RECOVERY_RETRY_SECONDS
        self._backoffs: dict[str, RateLimitBackoff] = {}
        self._global_backoff = RateLimitBackoff()
        self._failure_retry_until: dict[str, float] = {}
        self._once_requests: asyncio.Queue[tuple[str, list[str], asyncio.Future[str]]] = asyncio.Queue()
        self._reply_requests: asyncio.Queue[tuple[str, str, list[str], asyncio.Future[str]]] = asyncio.Queue()
        self._sync_requests: asyncio.Queue[tuple[str, asyncio.Future[int]]] = asyncio.Queue()
        self._restore_backoffs()

    @staticmethod
    def _normalise(text: str) -> str:
        return " ".join(text.split()).strip()

    @staticmethod
    def _prompt_hash(prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()

    def _load_state(self) -> dict[str, Any]:
        path = self.config.state_path.expanduser()
        try:
            value = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write_state(self, state: dict[str, Any]) -> None:
        path = self.config.state_path.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        os.chmod(temporary, 0o600)
        temporary.replace(path)

    def _job_state(self, name: str) -> dict[str, Any]:
        jobs = self._load_state().get("jobs")
        if not isinstance(jobs, dict):
            return {}
        value = jobs.get(name)
        return value if isinstance(value, dict) else {}

    def _update_job_state(self, name: str, updates: dict[str, Any]) -> None:
        state = self._load_state()
        jobs = state.setdefault("jobs", {})
        if not isinstance(jobs, dict):
            jobs = {}
            state["jobs"] = jobs
        current = jobs.get(name)
        if not isinstance(current, dict):
            current = {}
            jobs[name] = current
        current.update(updates)
        self._write_state(state)

    def _scheduler_state(self) -> dict[str, Any]:
        value = self._load_state().get("scheduler")
        return value if isinstance(value, dict) else {}

    def _update_scheduler_state(self, updates: dict[str, Any]) -> None:
        state = self._load_state()
        scheduler = state.setdefault("scheduler", {})
        if not isinstance(scheduler, dict):
            scheduler = {}
            state["scheduler"] = scheduler
        scheduler.update(updates)
        self._write_state(state)

    def _restore_backoffs(self) -> None:
        state = self._load_state()
        scheduler = state.get("scheduler")
        if isinstance(scheduler, dict):
            snapshot = scheduler.get("rate_limit_backoff")
            if isinstance(snapshot, dict):
                self._global_backoff.restore(snapshot)
        jobs = state.get("jobs")
        if not isinstance(jobs, dict):
            return
        for name, job_state in jobs.items():
            if not isinstance(job_state, dict):
                continue
            snapshot = job_state.get("rate_limit_backoff")
            if not isinstance(snapshot, dict):
                continue
            backoff = RateLimitBackoff()
            backoff.restore(snapshot)
            if backoff.attempts:
                self._backoffs[str(name)] = backoff

    def _persist_backoff(self, name: str, backoff: RateLimitBackoff) -> None:
        self._update_job_state(name, {"rate_limit_backoff": backoff.snapshot()})

    def _persist_global_backoff(self) -> None:
        self._update_scheduler_state({"rate_limit_backoff": self._global_backoff.snapshot()})

    def _send_gap_remaining(self, now: float) -> float:
        try:
            last_attempt_at = float(self._scheduler_state().get("last_attempt_at") or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, last_attempt_at + _MIN_SEND_GAP_SECONDS - now)

    def _ensure_initial_schedules(self, jobs: list[PromptJob], now: float) -> None:
        for job in jobs:
            state = self._job_state(job.name)
            if any(
                state.get(key)
                for key in (
                    "last_sent_at",
                    "last_uncertain_send_at",
                    "initial_due_at_epoch",
                    "next_due_at_epoch",
                )
            ):
                continue
            if job.run_at_epoch is not None:
                due_at = float(job.run_at_epoch)
                self._update_job_state(job.name, {"initial_due_at_epoch": due_at})
                logger.info(
                    "Prompta job=%s one-time send scheduled for %s",
                    job.name,
                    datetime.fromtimestamp(due_at).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
                )
                continue
            if job.daily_at is not None:
                due_at = _next_daily_epoch(job.daily_at, now, include_now=True)
                self._update_job_state(job.name, {"initial_due_at_epoch": due_at})
                logger.info(
                    "Prompta job=%s initial daily send scheduled for %s",
                    job.name,
                    datetime.fromtimestamp(due_at).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
                )
                continue
            window = min(max(0.0, job.interval_seconds), _INITIAL_DELAY_CAP_SECONDS)
            delay = random.uniform(0.0, window) if window > 0 else 0.0
            self._update_job_state(job.name, {"initial_due_at_epoch": now + delay})
            logger.info("Prompta job=%s initial start delayed by %.0fs", job.name, delay)

    @staticmethod
    def _next_delay(job: PromptJob) -> float:
        interval = max(0.0, job.interval_seconds)
        if job.exact_interval:
            return interval
        jitter_cap = min(_RECURRING_JITTER_CAP_SECONDS, interval * _RECURRING_JITTER_FRACTION)
        return interval + (random.uniform(0.0, jitter_cap) if jitter_cap > 0 else 0.0)

    def _failure_retry_remaining(self, name: str, now: float) -> float:
        state = self._job_state(name)
        try:
            persisted = float(state.get("failure_retry_until_epoch") or 0.0)
        except (TypeError, ValueError):
            persisted = 0.0
        in_memory = self._failure_retry_until.get(name, 0.0)
        return max(0.0, max(persisted, in_memory) - now)

    def _mark_failure(self, name: str, message: str, *, retry_until: float | None = None) -> None:
        updates: dict[str, Any] = {
            "status": "failing",
            "status_message": message,
            "status_at": time.time(),
        }
        if retry_until is not None:
            updates["failure_retry_until_epoch"] = retry_until
        self._update_job_state(name, updates)

    def read_jobs(self) -> dict[str, PromptJob]:
        return load_jobs(self.config.jobs_file)

    def due_in(self, job: PromptJob, now: float | None = None) -> float:
        state = self._job_state(job.name)
        current = time.time() if now is None else now
        try:
            last_sent_at = float(state.get("last_sent_at") or 0.0)
            last_uncertain_send_at = float(state.get("last_uncertain_send_at") or 0.0)
            next_due_at = float(state.get("next_due_at_epoch") or 0.0)
            initial_due_at = float(state.get("initial_due_at_epoch") or 0.0)
        except (TypeError, ValueError):
            return 0.0
        last_attempt_at = max(last_sent_at, last_uncertain_send_at)
        if job.run_at_epoch is not None:
            if last_attempt_at > 0:
                return float("inf")
            due_at = initial_due_at if initial_due_at > 0 else float(job.run_at_epoch)
            return max(0.0, due_at - current)
        if next_due_at > 0 and last_sent_at >= last_uncertain_send_at:
            return max(0.0, next_due_at - current)
        if last_attempt_at > 0:
            if job.daily_at is not None:
                return max(0.0, _next_daily_epoch(job.daily_at, last_attempt_at) - current)
            return max(0.0, last_attempt_at + max(0.0, job.interval_seconds) - current)
        if initial_due_at > 0:
            return max(0.0, initial_due_at - current)
        return 0.0

    async def _ensure_driver(self) -> BrowserDriver:
        if self.driver is None:
            self.driver = (
                self._driver_factory()
                if self._driver_factory is not None
                else FirefoxBiDiDriver(self.bidi_url)
            )
        if not self.driver.is_connected:
            await self.driver.connect()
        return self.driver

    async def _ensure_conversation_route(
        self,
        driver: BrowserDriver,
        expected_path: str,
        *,
        context: str | None = None,
    ) -> None:
        expected = expected_path.rstrip("/")
        deadline = asyncio.get_running_loop().time() + 10.0
        activated_history = False

        async def current_path() -> str:
            if context is None:
                return str(await driver.eval("location.pathname") or "").rstrip("/")
            return str(
                await driver.eval("location.pathname", context=context) or ""
            ).rstrip("/")

        path = await current_path()
        while path != expected and asyncio.get_running_loop().time() < deadline:
            if path in {"", "/"} and not activated_history:
                if context is None:
                    activated_history = await driver.activate_history_link(expected)
                else:
                    activated_history = await driver.activate_history_link(
                        expected,
                        context=context,
                    )
            await asyncio.sleep(0.25)
            path = await current_path()
        if path != expected:
            raise RuntimeError(
                f"ChatGPT opened unexpected conversation path {path!r}; expected {expected!r}"
            )

    async def _pointer_click(self, driver: BrowserDriver, x: float, y: float) -> None:
        await driver._click_viewport_point(driver.context, x, y)

    async def _effort_trigger_info(
        self,
        driver: BrowserDriver,
        *,
        timeout: float = _EFFORT_CONTROL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            raw = await driver.eval(
                """JSON.stringify((()=>{
                  const levels=['Instant','Medium','High','Extra high','Extra High'];
                  const normalise=value=>(value||'').replace(/\\s+/g,' ').trim();
                  const visible=el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);
                    return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
                  const composer=document.querySelector('main form[data-type="unified-composer"],main form,[data-composer-surface]');
                  const roots=composer?[composer,document]:[document];
                  let button=null;
                  for(const root of roots){
                    button=[...root.querySelectorAll('button[aria-haspopup="menu"]')]
                      .find(el=>visible(el)&&levels.includes(normalise(el.innerText||el.textContent||'')));
                    if(button)break;
                  }
                  if(!button)return null;
                  button.scrollIntoView({block:'center',inline:'center'});
                  const r=button.getBoundingClientRect();
                  const width=document.documentElement.clientWidth||window.innerWidth;
                  const height=document.documentElement.clientHeight||window.innerHeight;
                  const x=r.left+r.width/2,y=r.top+r.height/2;
                  if(x<0||y<0||x>=width||y>=height)return null;
                  return {text:normalise(button.innerText||button.textContent||''),x,y};
                })())"""
            )
            if raw and raw != "null":
                payload = json.loads(raw)
                if isinstance(payload, dict) and payload.get("text"):
                    return payload
            await asyncio.sleep(0.15)
        raise RuntimeError("ChatGPT thinking-effort control did not become available")

    async def _high_effort_slider_point(self, driver: BrowserDriver) -> dict[str, float]:
        deadline = asyncio.get_running_loop().time() + 3.0
        while asyncio.get_running_loop().time() < deadline:
            raw = await driver.eval(
                """JSON.stringify((()=>{
                  const slider=document.querySelector('[data-model-reasoning-effort-slider] [role="slider"]');
                  if(!slider)return null;
                  const root=slider.parentElement?.parentElement;
                  if(!root)return null;
                  const min=Number(slider.getAttribute('aria-valuemin')||0);
                  const max=Number(slider.getAttribute('aria-valuemax')||3);
                  const target=2;
                  if(target<min||target>max)return {error:'high-out-of-range'};
                  const ticks=[...root.querySelectorAll('[data-locked]')];
                  if(ticks[target]?.getAttribute('data-locked')==='true')return {error:'high-locked'};
                  const r=root.getBoundingClientRect(),pad=13;
                  const width=document.documentElement.clientWidth||window.innerWidth;
                  const height=document.documentElement.clientHeight||window.innerHeight;
                  const x=r.left+pad+(r.width-pad*2)*(target-min)/(max-min),y=r.top+r.height/2;
                  if(x<0||y<0||x>=width||y>=height)return null;
                  return {x,y};
                })())"""
            )
            if raw and raw != "null":
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    if payload.get("error"):
                        raise RuntimeError(
                            f"ChatGPT High effort is unavailable: {payload['error']}"
                        )
                    if "x" in payload and "y" in payload:
                        return {"x": float(payload["x"]), "y": float(payload["y"])}
            await asyncio.sleep(0.1)
        raise RuntimeError("ChatGPT thinking-effort slider did not open")

    async def _ensure_high_effort(self, driver: BrowserDriver) -> None:
        trigger = await self._effort_trigger_info(driver)
        if str(trigger.get("text") or "").strip().casefold() == "high":
            logger.info("Prompta verified thinking effort=High")
            return
        for attempt in range(2):
            try:
                await self._pointer_click(driver, float(trigger["x"]), float(trigger["y"]))
                break
            except RuntimeError as exc:
                if "out of bounds" not in str(exc).casefold() or attempt > 0:
                    raise
                trigger = await self._effort_trigger_info(driver)
        for attempt in range(2):
            point = await self._high_effort_slider_point(driver)
            try:
                await self._pointer_click(driver, point["x"], point["y"])
                break
            except RuntimeError as exc:
                if "out of bounds" not in str(exc).casefold() or attempt > 0:
                    raise
        deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < deadline:
            value = str(
                await driver.eval(
                    "document.querySelector('[data-model-reasoning-effort-slider] [role=\"slider\"]')?.getAttribute('aria-valuenow')||''"
                )
                or ""
            )
            if value == "2":
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("ChatGPT thinking-effort slider did not reach High")
        await driver._perform_actions(
            driver.context,
            [
                {
                    "type": "key",
                    "id": "keyboard",
                    "actions": [
                        {"type": "keyDown", "value": "\ue00c"},
                        {"type": "keyUp", "value": "\ue00c"},
                    ],
                }
            ],
        )
        await asyncio.sleep(0.2)
        verified = await self._effort_trigger_info(driver)
        if str(verified.get("text") or "").strip().casefold() != "high":
            raise RuntimeError(
                f"ChatGPT thinking effort verification failed: {verified.get('text')!r}"
            )
        logger.info("Prompta set and verified thinking effort=High")

    async def send_once(
        self,
        prompt: str,
        *,
        job_name: str = "",
        attachments: list[str] | None = None,
    ) -> str:
        if not prompt.strip():
            raise ValueError("prompta prompt is empty")
        driver = await self._ensure_driver()
        context = await driver.new_tab()
        capture: dict[str, Any] | None = None
        probe_armed = False
        succeeded = False
        try:
            await driver.wait_for_composer()
            await self._ensure_high_effort(driver)
            if attachments:
                await driver.attach_files(attachments)
                await driver.wait_for_composer()
            baseline = await driver.dom_state()
            baseline_path = str(await driver.eval("location.pathname") or "")
            if self._normalise(str(baseline.get("composer_text") or "")):
                logger.warning(
                    "Prompta found stale text in the dedicated new-chat composer; clearing it"
                )
                await driver.clear_composer()
                baseline = await driver.dom_state()
                if self._normalise(str(baseline.get("composer_text") or "")):
                    raise RuntimeError("ChatGPT stale new-chat composer could not be cleared")

            await driver.arm_page_send_probe()
            probe_armed = True
            capture = driver.arm_send_capture()
            await driver.type_message(prompt)
            typed = await driver.dom_state()
            if self._normalise(str(typed.get("composer_text") or "")) != self._normalise(prompt):
                raise RuntimeError("ChatGPT composer did not contain the configured prompt")
            if attachments:
                await driver.click_send_button()
            else:
                await driver.click_send()
                await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)
                post_submit = await driver.dom_state()
                if self._normalise(str(post_submit.get("composer_text") or "")) == self._normalise(prompt):
                    logger.warning(
                        "Prompta Enter submit left the prompt in the composer; retrying with the send button"
                    )
                    await driver.click_send_button(timeout=5.0)

            provisional_conversation_id = ""
            provisional_confirmed = False
            last_state: dict[str, Any] = post_submit if not attachments else {}
            last_probe: dict[str, Any] = {}
            last_path = baseline_path
            last_send_confirmed = False
            confirmation_timeout = max(1.0, self.config.send_timeout_seconds)
            if attachments:
                confirmation_timeout = max(confirmation_timeout, 120.0)
            deadline = asyncio.get_running_loop().time() + confirmation_timeout
            while asyncio.get_running_loop().time() < deadline:
                state = await driver.dom_state()
                rate_limit_text = str(state.get("rate_limit_text") or "")
                if is_rate_limited_text(rate_limit_text):
                    raise RateLimitError.from_text(rate_limit_text)
                probe = await driver.page_send_probe()
                path = str(await driver.eval("location.pathname") or "")
                last_state = state
                last_probe = probe
                last_path = path
                user_text = self._normalise(str(state.get("last_user_text") or ""))
                message_id = str(probe.get("message_id") or state.get("last_user_id") or "")
                status = int(probe.get("response_status") or capture.get("status") or 0)
                send_confirmed = (
                    bool(probe.get("committed"))
                    or driver.captured_send_response(capture) is not None
                )
                last_send_confirmed = send_confirmed
                if status == 429:
                    raise RateLimitError("prompta send rate limited")
                if status >= 400:
                    raise RuntimeError(f"prompta send failed with HTTP {status}")
                if capture.get("fetch_error"):
                    raise RuntimeError(f"prompta send failed: {capture['fetch_error']}")

                route_confirmed = path.startswith("/c/") and path != baseline_path
                dom_confirmed = user_text == self._normalise(prompt) and not self._normalise(
                    str(state.get("composer_text") or "")
                )
                route_conversation_id = (
                    path.removeprefix("/c/").split("/", 1)[0] if route_confirmed else ""
                )
                probe_conversation_id = str(probe.get("conversation_id") or "")
                durable_conversation_id = next(
                    (
                        candidate
                        for candidate in (probe_conversation_id, route_conversation_id)
                        if candidate and not candidate.startswith("WEB:")
                    ),
                    "",
                )
                provisional = next(
                    (
                        candidate
                        for candidate in (probe_conversation_id, route_conversation_id)
                        if candidate.startswith("WEB:")
                    ),
                    "",
                )
                if provisional:
                    provisional_conversation_id = provisional
                    provisional_confirmed = (
                        provisional_confirmed or send_confirmed or dom_confirmed or route_confirmed
                    )

                if durable_conversation_id:
                    conversation_id = durable_conversation_id
                    logger.info(
                        "Prompta sent prompt in new conversation=%s message_id=%s transport_confirmed=%s dom_confirmed=%s",
                        conversation_id,
                        message_id or "unknown",
                        send_confirmed,
                        dom_confirmed,
                    )
                    self.cache.start(
                        conversation_id,
                        context_id=context,
                        job_name=job_name,
                        prompt=prompt,
                    )
                    self._active_conversations[context] = ActiveConversation(
                        conversation_id=conversation_id,
                        context_id=context,
                        job_name=job_name,
                        prompt=prompt,
                    )
                    succeeded = True
                    return conversation_id
                await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)

            if provisional_conversation_id and provisional_confirmed:
                logger.warning(
                    "Prompta only observed provisional conversation=%s before send confirmation timeout; continuing cache capture until ChatGPT publishes the durable route",
                    provisional_conversation_id,
                )
                self.cache.start(
                    provisional_conversation_id,
                    context_id=context,
                    job_name=job_name,
                    prompt=prompt,
                )
                self._active_conversations[context] = ActiveConversation(
                    conversation_id=provisional_conversation_id,
                    context_id=context,
                    job_name=job_name,
                    prompt=prompt,
                )
                succeeded = True
                return provisional_conversation_id

            final_composer = self._normalise(str(last_state.get("composer_text") or ""))
            final_user_text = self._normalise(str(last_state.get("last_user_text") or ""))
            if (
                final_composer == self._normalise(prompt)
                and final_user_text != self._normalise(prompt)
                and not last_send_confirmed
                and not provisional_conversation_id
                and last_path == baseline_path
            ):
                raise RuntimeError(
                    "ChatGPT did not accept the prompt; it remained in the composer after submit"
                )
            raise SendVerificationError(
                "prompta could not prove the prompt was sent in a new conversation "
                f"(composer_empty={not bool(final_composer)}, "
                f"last_user_matches={final_user_text == self._normalise(prompt)}, "
                f"transport_confirmed={last_send_confirmed}, "
                f"probe_status={int(last_probe.get('response_status') or 0)}, "
                f"path={last_path or '/'})"
            )
        finally:
            if capture is not None:
                driver.clear_send_capture(capture)
            if probe_armed:
                try:
                    await driver.clear_page_send_probe()
                except Exception:
                    logger.debug("Could not clear page send probe", exc_info=True)
            if not succeeded:
                try:
                    await driver.close_context(context)
                except Exception:
                    logger.debug("Could not close failed Prompta tab", exc_info=True)

    async def recover_cached_conversations(self, *, limit: int = 50) -> int:
        """Reattach live cache capture after a daemon/browser restart."""

        attached_ids = {
            active.conversation_id for active in self._active_conversations.values()
        }
        recoverable = [
            row
            for row in self.cache.recoverable_conversations(
                interrupted_after=time.time() - _RESTART_RECOVERY_INTERRUPTED_SECONDS,
                limit=max(1, limit) + len(attached_ids),
            )
            if str(row.get("id") or "") not in attached_ids
        ][: max(1, limit)]
        if not recoverable:
            self._next_recovery_retry_at = (
                time.monotonic() + _RESTART_RECOVERY_RETRY_SECONDS
            )
            return 0

        driver = await self._ensure_driver()
        recovered = 0
        for row in recoverable:
            conversation_id = str(row.get("id") or "")
            target_url = str(
                row.get("url") or f"https://chatgpt.com/c/{conversation_id}"
            )
            context = ""
            try:
                context = await driver.new_tab(target_url)
                expected_path = urlsplit(target_url).path.rstrip("/")
                await self._ensure_conversation_route(driver, expected_path)
                snapshot: dict[str, Any] = {}
                messages: list[Any] = []
                for load_attempt in range(_RESTART_RECOVERY_LOAD_ATTEMPTS):
                    deadline = (
                        asyncio.get_running_loop().time()
                        + _RESTART_RECOVERY_MESSAGE_TIMEOUT_SECONDS
                    )
                    while asyncio.get_running_loop().time() < deadline:
                        snapshot = await driver.conversation_snapshot(context)
                        candidate_messages = snapshot.get("messages")
                        if isinstance(candidate_messages, list) and candidate_messages:
                            messages = candidate_messages
                            break
                        await asyncio.sleep(0.5)
                    if messages:
                        break
                    if load_attempt + 1 < _RESTART_RECOVERY_LOAD_ATTEMPTS:
                        logger.warning(
                            "Prompta recovery conversation=%s did not expose messages; "
                            "reloading before retry",
                            conversation_id,
                        )
                        await driver.navigate(target_url)
                        await self._ensure_conversation_route(driver, expected_path)
                if not messages:
                    logger.warning(
                        "Prompta recovery conversation=%s still has no messages; "
                        "retrying through ChatGPT history",
                        conversation_id,
                    )
                    await driver.navigate("https://chatgpt.com/")
                    await self._ensure_conversation_route(driver, expected_path)
                    deadline = (
                        asyncio.get_running_loop().time()
                        + _RESTART_RECOVERY_MESSAGE_TIMEOUT_SECONDS
                    )
                    while asyncio.get_running_loop().time() < deadline:
                        snapshot = await driver.conversation_snapshot(context)
                        candidate_messages = snapshot.get("messages")
                        if isinstance(candidate_messages, list) and candidate_messages:
                            messages = candidate_messages
                            break
                        await asyncio.sleep(0.5)
                if not messages:
                    raise RuntimeError(
                        "ChatGPT conversation did not expose any messages after "
                        "direct reload and history recovery"
                    )

                # A daemon restart can happen while ChatGPT is still working server-side.
                # Keep the row live until normal polling observes a stable completed turn.
                snapshot["streaming"] = True
                self.cache.resume(conversation_id, context_id=context)
                self.cache.write_snapshot(conversation_id, snapshot)
                self._active_conversations[context] = ActiveConversation(
                    conversation_id=conversation_id,
                    context_id=context,
                    job_name=str(row.get("job_name") or ""),
                    prompt=str(row.get("prompt") or ""),
                    last_digest=self.cache.digest(snapshot),
                    last_live_snapshot_at=time.monotonic(),
                    recovered_cache_updated_at=float(row.get("updated_at") or 0.0),
                )
                recovered += 1
                logger.info(
                    "Prompta reattached live conversation=%s after restart",
                    conversation_id,
                )
            except Exception:
                logger.exception(
                    "Prompta could not reattach conversation=%s after restart",
                    conversation_id,
                )
                if context:
                    try:
                        await driver.close_context(context)
                    except Exception:
                        logger.debug(
                            "Could not close failed Prompta recovery tab",
                            exc_info=True,
                        )
                if str(row.get("status") or "") == "active":
                    self.cache.mark_interrupted(conversation_id)
        self._next_recovery_retry_at = time.monotonic() + _RESTART_RECOVERY_RETRY_SECONDS
        return recovered

    async def _retry_cached_recovery_if_due(self) -> bool:
        """Retry one transiently failed restart recovery without recycling the daemon."""

        if time.monotonic() < self._next_recovery_retry_at:
            return False
        self._next_recovery_retry_at = time.monotonic() + _RESTART_RECOVERY_RETRY_SECONDS
        recovered = await self.recover_cached_conversations(limit=1)
        if recovered:
            logger.info(
                "Prompta recovered %d live conversation(s) after deferred retry",
                recovered,
            )
            return True
        return False

    async def sync_conversation(self, conversation_id: str) -> int:
        """Reload one cached conversation from ChatGPT without sending a message."""

        if not conversation_id.strip():
            raise ValueError("conversation id is empty")

        metadata = self.cache.metadata(conversation_id)
        if str(metadata.get("status") or "") == "active":
            live = next(
                (
                    active
                    for active in self._active_conversations.values()
                    if active.conversation_id == conversation_id
                ),
                None,
            )
            if live is not None:
                logger.info(
                    "Prompta sync reused active conversation=%s context=%s",
                    conversation_id,
                    live.context_id,
                )
                return len(self.cache.messages(conversation_id))

        target_url = str(metadata.get("url") or f"https://chatgpt.com/c/{conversation_id}")
        driver = await self._ensure_driver()
        context = await driver.new_tab(target_url)
        retain_context = False
        try:
            await driver.wait_for_composer()
            expected_path = urlsplit(target_url).path.rstrip("/")
            await self._ensure_conversation_route(driver, expected_path)
            await driver.wait_for_composer()

            self.cache.resume(conversation_id, context_id=context)
            deadline = asyncio.get_running_loop().time() + 15.0
            last_digest = ""
            stable_polls = 0
            failure_polls = 0
            latest: dict[str, Any] = {}
            while asyncio.get_running_loop().time() < deadline:
                activity = await driver.conversation_activity(context)
                streaming_hint = bool(activity.get("streaming"))
                transient_hint = bool(activity.get("transient"))
                failure_hint = bool(activity.get("failed"))
                completion_hint = bool(activity.get("complete", True))
                latest = await driver.conversation_snapshot(context)
                if streaming_hint:
                    latest["streaming"] = True
                messages = latest.get("messages")
                if not isinstance(messages, list):
                    messages = []
                digest = self.cache.digest(latest)
                streaming = bool(latest.get("streaming"))

                # A sync is observational: never call a stable-but-failed or
                # transient DOM a successful completion. Keep live states
                # attached to normal background polling, and only persist
                # "complete" after ChatGPT exposes its final-turn action.
                self.cache.write_snapshot(conversation_id, latest)

                if failure_hint:
                    failure_polls += 1
                    stable_polls = 0
                    if failure_polls < 3:
                        await asyncio.sleep(0.5)
                        continue
                    self.cache.mark_interrupted(conversation_id)
                    raise RuntimeError(
                        "ChatGPT conversation has a persistent delivery failure"
                    )
                failure_polls = 0

                if streaming or transient_hint:
                    self._active_conversations[context] = ActiveConversation(
                        conversation_id=conversation_id,
                        context_id=context,
                        job_name=str(metadata.get("job_name") or ""),
                        prompt=str(metadata.get("prompt") or ""),
                        last_digest=digest,
                        last_live_snapshot_at=time.monotonic(),
                    )
                    retain_context = True
                    return len(messages)

                if messages and digest == last_digest:
                    stable_polls += 1
                else:
                    stable_polls = 0
                last_digest = digest

                if stable_polls >= 2 and completion_hint:
                    latest = await self._enrich_completed_tool_calls(
                        conversation_id,
                        latest,
                    )
                    self.cache.write_snapshot(conversation_id, latest, complete=True)
                    return len(messages)
                if stable_polls >= 2 and not completion_hint:
                    self._active_conversations[context] = ActiveConversation(
                        conversation_id=conversation_id,
                        context_id=context,
                        job_name=str(metadata.get("job_name") or ""),
                        prompt=str(metadata.get("prompt") or ""),
                        last_digest=digest,
                        last_live_snapshot_at=time.monotonic(),
                    )
                    retain_context = True
                    return len(messages)
                await asyncio.sleep(0.5)

            messages = latest.get("messages")
            if not isinstance(messages, list) or not messages:
                raise RuntimeError("ChatGPT conversation did not expose any messages")
            self._active_conversations[context] = ActiveConversation(
                conversation_id=conversation_id,
                context_id=context,
                job_name=str(metadata.get("job_name") or ""),
                prompt=str(metadata.get("prompt") or ""),
                last_digest=last_digest,
                last_live_snapshot_at=time.monotonic(),
            )
            retain_context = True
            return len(messages)
        finally:
            if not retain_context:
                await driver.close_context(context)

    async def send_reply(
        self,
        conversation_id: str,
        prompt: str,
        *,
        attachments: list[str] | None = None,
    ) -> str:
        """Send into a cached conversation, reusing its live tab whenever possible."""

        if not conversation_id.strip():
            raise ValueError("conversation id is empty")
        if not prompt.strip():
            raise ValueError("prompta prompt is empty")

        driver = await self._ensure_driver()
        metadata = self.cache.metadata(conversation_id)
        target_url = str(metadata.get("url") or f"https://chatgpt.com/c/{conversation_id}")
        expected_path = urlsplit(target_url).path.rstrip("/")
        existing = next(
            (
                (context, active)
                for context, active in self._active_conversations.items()
                if active.conversation_id == conversation_id
            ),
            None,
        )
        if existing is not None:
            retained_context, retained_active = existing
            if retained_active.settled_at <= 0:
                if not await self.wait_for_cached_response(conversation_id):
                    raise RuntimeError(
                        "Prompta cannot reply before the current assistant response is cached"
                    )
            self._active_conversations.pop(retained_context, None)
            try:
                await driver.close_context(retained_context)
            except Exception:
                logger.debug(
                    "Could not close retained Prompta tab before reply",
                    exc_info=True,
                )

        context = await driver.new_tab(target_url)
        active: ActiveConversation | None = None
        created_context = True

        capture: dict[str, Any] | None = None
        probe_armed = False
        try:
            async def prepare_conversation_route() -> None:
                try:
                    await driver.wait_for_composer()
                except RuntimeError as exc:
                    if not created_context or "composer did not become ready" not in str(exc):
                        raise
                    logger.warning(
                        "Prompta deep-link composer unavailable for conversation=%s; retrying via ChatGPT home",
                        conversation_id,
                    )
                    await driver.navigate("https://chatgpt.com/")
                    await driver.wait_for_composer()
                await self._ensure_conversation_route(driver, expected_path)
                await driver.wait_for_composer()

            try:
                await prepare_conversation_route()
            except RuntimeError as exc:
                if not created_context or "composer did not become ready" not in str(exc):
                    raise
                logger.warning(
                    "Prompta conversation composer still unavailable for conversation=%s; reloading target once",
                    conversation_id,
                )
                await driver.navigate(target_url)
                await prepare_conversation_route()

            await self._ensure_high_effort(driver)
            if attachments:
                await driver.attach_files(attachments)
                await driver.wait_for_composer()
            baseline = await driver.dom_state()
            if self._normalise(str(baseline.get("composer_text") or "")):
                raise RuntimeError("ChatGPT composer already contains unsent text")
            baseline_user_id = str(baseline.get("last_user_id") or "")

            await driver.arm_page_send_probe()
            probe_armed = True
            capture = driver.arm_send_capture()
            await driver.type_message(prompt)
            typed = await driver.dom_state()
            if self._normalise(str(typed.get("composer_text") or "")) != self._normalise(prompt):
                raise RuntimeError("ChatGPT composer did not contain the requested reply")
            if attachments:
                await driver.click_send_button()
            else:
                await driver.click_send()
                await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)
                post_submit = await driver.dom_state()
                if self._normalise(str(post_submit.get("composer_text") or "")) == self._normalise(prompt):
                    logger.warning(
                        "Prompta Enter reply left the prompt in the composer; retrying with the send button"
                    )
                    await driver.click_send_button(timeout=5.0)

            confirmation_timeout = max(1.0, self.config.send_timeout_seconds)
            if attachments:
                confirmation_timeout = max(confirmation_timeout, 120.0)
            deadline = asyncio.get_running_loop().time() + confirmation_timeout
            while asyncio.get_running_loop().time() < deadline:
                state = await driver.dom_state()
                rate_limit_text = str(state.get("rate_limit_text") or "")
                if is_rate_limited_text(rate_limit_text):
                    raise RateLimitError.from_text(rate_limit_text)
                probe = await driver.page_send_probe()
                status = int(probe.get("response_status") or capture.get("status") or 0)
                if status == 429:
                    raise RateLimitError("prompta send rate limited")
                if status >= 400:
                    raise RuntimeError(f"prompta send failed with HTTP {status}")
                if capture.get("fetch_error"):
                    raise RuntimeError(f"prompta send failed: {capture['fetch_error']}")

                send_confirmed = (
                    bool(probe.get("committed"))
                    or driver.captured_send_response(capture) is not None
                )
                user_text = self._normalise(str(state.get("last_user_text") or ""))
                user_id = str(state.get("last_user_id") or "")
                dom_confirmed = (
                    user_text == self._normalise(prompt)
                    and not self._normalise(str(state.get("composer_text") or ""))
                    and (bool(user_id and user_id != baseline_user_id) or send_confirmed)
                )
                if send_confirmed or dom_confirmed:
                    metadata = self.cache.resume(conversation_id, context_id=context)
                    if active is None:
                        active = ActiveConversation(
                            conversation_id=conversation_id,
                            context_id=context,
                            job_name=str(metadata.get("job_name") or ""),
                            prompt=str(metadata.get("prompt") or ""),
                        )
                        self._active_conversations[context] = active
                    active.idle_polls = 0
                    active.settled_at = 0.0
                    snapshot = await driver.conversation_snapshot(context)
                    self.cache.write_snapshot(conversation_id, snapshot)
                    active.last_digest = self.cache.digest(snapshot)
                    logger.info(
                        "Prompta sent reply conversation=%s reused_tab=%s",
                        conversation_id,
                        not created_context,
                    )
                    return conversation_id
                await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)

            raise SendVerificationError(
                "prompta could not prove the reply was sent to the selected conversation"
            )
        finally:
            if capture is not None:
                driver.clear_send_capture(capture)
            if probe_armed:
                try:
                    await driver.clear_page_send_probe()
                except Exception:
                    logger.debug("Could not clear page send probe", exc_info=True)
            if created_context and not any(
                active.context_id == context for active in self._active_conversations.values()
            ):
                try:
                    await driver.close_context(context)
                except Exception:
                    logger.debug("Could not close failed reply tab", exc_info=True)

    async def _run_job(self, job: PromptJob, *, now: float) -> bool:
        if self._job_state(job.name).get("paused") is True:
            return False
        if self.due_in(job, now) > 0:
            return False
        if any(
            active.job_name == job.name
            for active in self._active_conversations.values()
        ):
            return False
        backoff = self._backoffs.setdefault(job.name, RateLimitBackoff())
        if backoff.remaining() > 0:
            return False
        if self._global_backoff.remaining() > 0:
            return False
        if self._failure_retry_remaining(job.name, now) > 0:
            return False
        if self._send_gap_remaining(now) > 0:
            return False
        self._update_scheduler_state({"last_attempt_at": now})
        try:
            conversation_id = await self.send_once(job.prompt, job_name=job.name)
        except RateLimitError as exc:
            delay = self._global_backoff.record(float(exc.retry_after))
            self._persist_global_backoff()
            self._mark_failure(job.name, str(exc))
            logger.warning(
                "Prompta job=%s rate limited account-wide; attempt=%d retry_after=%ds pausing all jobs for %.1fs",
                job.name,
                self._global_backoff.attempts,
                exc.retry_after,
                delay,
            )
            return False
        except SendVerificationError as exc:
            attempted_at = time.time()
            self._update_job_state(
                job.name,
                {
                    "last_uncertain_send_at": attempted_at,
                    "status": "failing",
                    "status_message": str(exc),
                    "status_at": attempted_at,
                },
            )
            logger.warning(
                "Prompta job=%s send outcome uncertain; suppressing retries for %.0fs: %s",
                job.name,
                job.interval_seconds,
                exc,
            )
            if self.driver is not None:
                self._interrupt_active_conversations()
                await self.driver.close()
                self.driver = None
            return False
        except (ConnectionClosed, OSError, RuntimeError) as exc:
            logger.exception("Prompta job=%s send failed: %s", job.name, exc)
            retry_until = time.time() + _FAILURE_RETRY_SECONDS
            self._mark_failure(job.name, str(exc), retry_until=retry_until)
            browser_restart_required = bool(
                self.driver is not None and self.driver.needs_browser_restart is True
            )
            if self.driver is not None:
                self._interrupt_active_conversations()
                if not browser_restart_required:
                    await self.driver.close()
                    self.driver = None
            self._failure_retry_until[job.name] = retry_until
            if browser_restart_required:
                raise RuntimeError(
                    "Browser session was lost; restarting Prompta to recycle browser"
                ) from exc
            return False
        sent_at = time.time()
        if job.run_at_epoch is not None:
            backoff.reset()
            self._failure_retry_until.pop(job.name, None)
            self._update_job_state(
                job.name,
                {
                    "prompt_sha256": self._prompt_hash(job.prompt),
                    "last_sent_at": sent_at,
                    "last_uncertain_send_at": 0.0,
                    "initial_due_at_epoch": 0.0,
                    "next_due_at_epoch": 0.0,
                    "last_conversation_id": conversation_id,
                    "rate_limit_backoff": backoff.snapshot(),
                    "failure_retry_until_epoch": 0.0,
                    "status": "healthy",
                    "status_message": "",
                    "status_at": sent_at,
                },
            )
            remove_job(self.config.jobs_file, job.name)
            logger.info("Prompta one-time job=%s completed and was removed", job.name)
            return True
        if job.daily_at is not None:
            next_due_at = _next_daily_epoch(job.daily_at, sent_at)
            next_delay = max(0.0, next_due_at - sent_at)
        else:
            next_delay = self._next_delay(job)
            next_due_at = sent_at + next_delay
        backoff.reset()
        self._failure_retry_until.pop(job.name, None)
        self._update_job_state(
            job.name,
            {
                "prompt_sha256": self._prompt_hash(job.prompt),
                "last_sent_at": sent_at,
                "last_uncertain_send_at": 0.0,
                "initial_due_at_epoch": 0.0,
                "next_due_at_epoch": next_due_at,
                "last_conversation_id": conversation_id,
                "rate_limit_backoff": backoff.snapshot(),
                "failure_retry_until_epoch": 0.0,
                "status": "healthy",
                "status_message": "",
                "status_at": sent_at,
            },
        )
        if job.daily_at is not None:
            logger.info(
                "Prompta job=%s completed; next daily send at %s",
                job.name,
                datetime.fromtimestamp(next_due_at).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
            )
        else:
            logger.info(
                "Prompta job=%s completed; next send in %.0fs (includes %.0fs jitter)",
                job.name,
                next_delay,
                max(0.0, next_delay - job.interval_seconds),
            )
        return True

    def _interrupt_active_conversations(self) -> None:
        for active in self._active_conversations.values():
            self.cache.mark_interrupted(active.conversation_id)
        self._active_conversations.clear()

    @staticmethod
    def _apply_structured_tool_blocks(
        snapshot: dict[str, Any],
        blocks: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        if not blocks:
            return snapshot
        messages = snapshot.get("messages")
        if not isinstance(messages, list):
            return snapshot
        assistant_index = next(
            (
                index
                for index in range(len(messages) - 1, -1, -1)
                if isinstance(messages[index], dict)
                and str(messages[index].get("role") or "") == "assistant"
            ),
            None,
        )
        if assistant_index is None:
            return snapshot
        assistant = messages[assistant_index]
        content = str(assistant.get("content") or "")
        enriched_content = merge_tool_blocks(content, list(blocks))
        if enriched_content == content:
            return snapshot
        enriched = dict(snapshot)
        enriched_messages = [
            dict(message) if isinstance(message, dict) else message for message in messages
        ]
        enriched_messages[assistant_index]["content"] = enriched_content
        enriched["messages"] = enriched_messages
        return enriched

    async def _enrich_completed_tool_calls(
        self,
        conversation_id: str,
        snapshot: dict[str, Any],
        *,
        active: ActiveConversation | None = None,
    ) -> dict[str, Any]:
        messages = snapshot.get("messages")
        if not isinstance(messages, list):
            return snapshot
        assistant = next(
            (
                message
                for message in reversed(messages)
                if isinstance(message, dict)
                and str(message.get("role") or "") == "assistant"
            ),
            None,
        )
        if assistant is None:
            return snapshot
        content = str(assistant.get("content") or "")
        if "tool:" not in content and "function:" not in content:
            return snapshot
        metadata = self.cache.metadata(conversation_id)
        url = str(metadata.get("url") or f"https://chatgpt.com/c/{conversation_id}")
        blocks, ordered_content = await self.tool_enricher.enrichment(url)
        if not blocks:
            return snapshot
        if active is not None:
            active.structured_tool_blocks = tuple(blocks)
        if ordered_content:
            enriched = dict(snapshot)
            enriched_messages = [
                dict(message) if isinstance(message, dict) else message for message in messages
            ]
            assistant_index = next(
                (
                    index
                    for index in range(len(enriched_messages) - 1, -1, -1)
                    if isinstance(enriched_messages[index], dict)
                    and str(enriched_messages[index].get("role") or "") == "assistant"
                ),
                None,
            )
            if assistant_index is not None:
                enriched_messages[assistant_index]["content"] = ordered_content
                enriched["messages"] = enriched_messages
            else:
                enriched = self._apply_structured_tool_blocks(snapshot, blocks)
        else:
            enriched = self._apply_structured_tool_blocks(snapshot, blocks)
        logger.info(
            "Prompta enriched conversation=%s with %d structured Chromium tool call(s)",
            conversation_id,
            len(blocks),
        )
        return enriched

    async def stop_conversation(self, conversation_id: str) -> str:
        match = next(
            (
                (context, active)
                for context, active in self._active_conversations.items()
                if active.conversation_id == conversation_id
            ),
            None,
        )
        if match is None:
            raise RuntimeError(f"Prompta has no active tab for conversation {conversation_id}")
        context, active = match
        driver = await self._ensure_driver()
        if driver is None:
            raise RuntimeError("Prompta browser session is unavailable")

        activity = await driver.conversation_activity(context)
        if bool(activity.get("streaming")):
            clicked = await driver.click_stop(context)
            if not clicked:
                activity = await driver.conversation_activity(context)
                if bool(activity.get("streaming")):
                    raise RuntimeError("ChatGPT stop button was not available")
            else:
                deadline = asyncio.get_running_loop().time() + 5.0
                stopped = False
                while asyncio.get_running_loop().time() < deadline:
                    if not bool((await driver.conversation_activity(context)).get("streaming")):
                        stopped = True
                        break
                    await asyncio.sleep(0.1)
                if not stopped:
                    raise RuntimeError("ChatGPT response did not stop")

        snapshot = await driver.conversation_snapshot(context)
        snapshot["streaming"] = False
        self.cache.write_snapshot(conversation_id, snapshot, complete=True)
        active.last_digest = self.cache.digest(snapshot)
        active.idle_polls = max(active.idle_polls, 3)
        active.settled_at = time.monotonic()
        logger.info("Prompta stopped conversation=%s", conversation_id)
        return conversation_id

    async def _poll_active_conversations(self) -> None:
        if not self._active_conversations:
            return
        try:
            driver = await self._ensure_driver()
        except Exception:
            logger.exception("Prompta cache capture could not reconnect Firefox BiDi")
            return
        if driver is None:
            return
        for context, active in list(self._active_conversations.items()):
            try:
                activity = await driver.conversation_activity(context)
                streaming_hint = bool(activity.get("streaming"))
                completion_hint = bool(activity.get("complete", True))
                transient_hint = bool(activity.get("transient"))
                failure_hint = bool(activity.get("failed"))
                persistent_transient = transient_hint and not streaming_hint
                if persistent_transient:
                    now_epoch = time.time()
                    if active.transient_since_epoch <= 0:
                        recovered_at = active.recovered_cache_updated_at
                        active.transient_since_epoch = (
                            min(now_epoch, recovered_at) if recovered_at > 0 else now_epoch
                        )
                    transient_timeout = (
                        _TRANSIENT_FAILURE_TIMEOUT_SECONDS
                        if active.transient_recovery_attempts <= 0
                        else _TRANSIENT_RECOVERY_GRACE_SECONDS
                    )
                    if now_epoch - active.transient_since_epoch >= transient_timeout:
                        if active.transient_recovery_attempts <= 0:
                            target_url = str(
                                self.cache.metadata(active.conversation_id).get("url")
                                or f"https://chatgpt.com/c/{active.conversation_id}"
                            )
                            expected_path = urlsplit(target_url).path.rstrip("/")
                            active.transient_recovery_attempts = 1
                            active.transient_since_epoch = now_epoch
                            active.recovered_cache_updated_at = 0.0
                            try:
                                await driver.navigate(target_url, context=context)
                                await self._ensure_conversation_route(
                                    driver,
                                    expected_path,
                                    context=context,
                                )
                                await driver.wait_for_composer(
                                    timeout=10.0,
                                    context=context,
                                )
                                active.last_live_snapshot_at = 0.0
                                logger.warning(
                                    "Prompta reloaded persistently interrupted conversation=%s "
                                    "before giving up",
                                    active.conversation_id,
                                )
                                continue
                            except Exception:
                                logger.exception(
                                    "Prompta recovery reload failed conversation=%s",
                                    active.conversation_id,
                                )
                        self.cache.mark_interrupted(active.conversation_id)
                        try:
                            await driver.close_context(context)
                        except Exception:
                            logger.debug(
                                "Could not close persistently interrupted Prompta tab",
                                exc_info=True,
                            )
                        self._active_conversations.pop(context, None)
                        logger.warning(
                            "Prompta marked conversation=%s interrupted after persistent "
                            "ChatGPT connection interruption",
                            active.conversation_id,
                        )
                        continue
                else:
                    active.transient_since_epoch = 0.0
                    active.transient_recovery_attempts = 0
                    active.recovered_cache_updated_at = 0.0
                if streaming_hint or transient_hint:
                    active.idle_polls = 0
                    active.settled_at = 0.0
                    now = time.monotonic()
                    if now - active.last_live_snapshot_at < _LIVE_SNAPSHOT_INTERVAL_SECONDS:
                        continue
                    active.last_live_snapshot_at = now
                snapshot = await driver.conversation_snapshot(context)
                if streaming_hint:
                    snapshot["streaming"] = True
            except Exception:
                logger.exception(
                    "Prompta cache capture failed conversation=%s", active.conversation_id
                )
                continue

            if active.structured_tool_blocks:
                snapshot = self._apply_structured_tool_blocks(
                    snapshot,
                    active.structured_tool_blocks,
                )

            digest = self.cache.digest(snapshot)
            changed = digest != active.last_digest
            messages = snapshot.get("messages")
            if not isinstance(messages, list):
                messages = []
            last_message = messages[-1] if messages else None
            has_assistant = (
                isinstance(last_message, dict)
                and str(last_message.get("role") or "") == "assistant"
                and bool(str(last_message.get("content") or "").strip())
            )
            streaming = bool(snapshot.get("streaming"))

            if changed:
                self.cache.write_snapshot(active.conversation_id, snapshot)
                active.last_digest = digest
                # ChatGPT can mutate final-turn chrome (actions, ids, metadata)
                # after Prompta has already declared the response complete. Do
                # not restart the retention clock for those harmless changes or
                # completed tabs can linger indefinitely. A response that
                # actually resumes streaming/fails loses its settled state via
                # the activity hints above/below.
                if not (
                    active.settled_at > 0
                    and completion_hint
                    and not streaming
                    and not failure_hint
                ):
                    active.idle_polls = 0
                    active.settled_at = 0.0

            if failure_hint:
                active.idle_polls += 1
                active.settled_at = 0.0
                now = time.monotonic()
                if (
                    active.delivery_recovery_at > 0
                    and now - active.delivery_recovery_at < _DELIVERY_RECOVERY_GRACE_SECONDS
                ):
                    continue
                if (
                    active.delivery_retry_at > 0
                    and now - active.delivery_retry_at < _DELIVERY_RETRY_GRACE_SECONDS
                ):
                    continue
                if active.idle_polls < _DELIVERY_FAILURE_POLLS:
                    continue
                if active.delivery_retry_attempts < _DELIVERY_RETRY_MAX_ATTEMPTS:
                    try:
                        retried = await driver.click_delivery_retry(context, timeout=3.0)
                    except Exception:
                        logger.exception(
                            "Prompta could not retry failed ChatGPT delivery conversation=%s",
                            active.conversation_id,
                        )
                        retried = False
                    if retried:
                        active.delivery_retry_attempts += 1
                        active.delivery_retry_at = time.monotonic()
                        active.idle_polls = 0
                        logger.warning(
                            "Prompta retried failed ChatGPT delivery conversation=%s attempt=%d",
                            active.conversation_id,
                            active.delivery_retry_attempts,
                        )
                        continue
                    discovery_deadline = (
                        _DELIVERY_FAILURE_POLLS + _DELIVERY_RETRY_DISCOVERY_POLLS
                    )
                    if active.idle_polls < discovery_deadline:
                        logger.warning(
                            "Prompta delivery retry control not available conversation=%s "
                            "poll=%d/%d; keeping tab alive",
                            active.conversation_id,
                            active.idle_polls,
                            discovery_deadline,
                        )
                        continue
                if active.delivery_recovery_attempts < _DELIVERY_RECOVERY_MAX_ATTEMPTS:
                    target_url = str(
                        self.cache.metadata(active.conversation_id).get("url")
                        or f"https://chatgpt.com/c/{active.conversation_id}"
                    )
                    expected_path = urlsplit(target_url).path.rstrip("/")
                    try:
                        await driver.navigate(target_url, context=context)
                        await self._ensure_conversation_route(
                            driver,
                            expected_path,
                            context=context,
                        )
                        await driver.wait_for_composer(
                            timeout=10.0,
                            context=context,
                        )
                    except Exception:
                        logger.exception(
                            "Prompta delivery-failure recovery reload failed conversation=%s",
                            active.conversation_id,
                        )
                    else:
                        active.delivery_recovery_attempts += 1
                        active.delivery_recovery_at = time.monotonic()
                        active.delivery_retry_at = 0.0
                        active.idle_polls = 0
                        active.last_live_snapshot_at = 0.0
                        logger.warning(
                            "Prompta reloaded failed-delivery conversation=%s before giving up",
                            active.conversation_id,
                        )
                        continue
                self.cache.mark_interrupted(active.conversation_id)
                try:
                    await driver.close_context(context)
                except Exception:
                    logger.debug("Could not close failed Prompta tab", exc_info=True)
                self._active_conversations.pop(context, None)
                logger.warning(
                    "Prompta marked conversation=%s interrupted after persistent ChatGPT delivery failure",
                    active.conversation_id,
                )
                continue

            active.delivery_retry_at = 0.0
            if streaming_hint or transient_hint:
                continue

            if active.settled_at > 0 and completion_hint and not streaming:
                # Preserve the original completion timestamp during the short
                # retained-tab grace period, including across late DOM changes.
                pass
            elif not changed and has_assistant and not streaming:
                active.idle_polls += 1
            else:
                active.idle_polls = 0
                active.settled_at = 0.0

            completion_polls = 3
            if (
                completion_hint
                and "turn_ended" in activity
                and activity.get("turn_ended") is None
            ):
                # Copy/action chrome can appear between tool calls before the
                # model has actually ended its turn. If React turn metadata is
                # unavailable, require a longer quiet window before trusting
                # that weaker completion signal.
                completion_polls = _FALLBACK_COMPLETION_POLLS
            if active.idle_polls < completion_polls:
                continue
            if not completion_hint and active.idle_polls < 30:
                continue

            if active.settled_at <= 0:
                snapshot = await self._enrich_completed_tool_calls(
                    active.conversation_id,
                    snapshot,
                    active=active,
                )
                self.cache.write_snapshot(active.conversation_id, snapshot, complete=True)
                active.last_digest = self.cache.digest(snapshot)
                active.settled_at = time.monotonic()
                logger.info(
                    "Prompta cached completed conversation=%s messages=%d; retaining tab for %.0fs",
                    active.conversation_id,
                    len(messages),
                    _ACTIVE_TAB_RETENTION_SECONDS,
                )
                continue

            if time.monotonic() - active.settled_at < _ACTIVE_TAB_RETENTION_SECONDS:
                continue

            close_driver = self.driver
            if close_driver is not None:
                try:
                    await close_driver.close_context(context)
                except Exception:
                    logger.debug("Could not close retained Prompta tab", exc_info=True)
            self._active_conversations.pop(context, None)
            logger.info(
                "Prompta closed retained conversation tab=%s after %.0fs",
                active.conversation_id,
                _ACTIVE_TAB_RETENTION_SECONDS,
            )

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
        did_work = False
        while True:
            try:
                prompt, attachments, future = self._once_requests.get_nowait()
            except asyncio.QueueEmpty:
                return did_work
            try:
                conversation_id = await self.send_once(prompt, attachments=attachments)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            else:
                if not future.done():
                    future.set_result(conversation_id)
                did_work = True
            finally:
                self._once_requests.task_done()

    def _reply_target_is_busy(self, conversation_id: str) -> bool:
        return any(
            active.conversation_id == conversation_id and active.settled_at <= 0
            for active in self._active_conversations.values()
        )

    async def _drain_reply_requests(self) -> bool:
        did_work = False
        pending = self._reply_requests.qsize()
        for _ in range(pending):
            try:
                item = self._reply_requests.get_nowait()
            except asyncio.QueueEmpty:
                return did_work
            conversation_id, prompt, attachments, future = item
            if self._reply_target_is_busy(conversation_id):
                self._reply_requests.task_done()
                await self._reply_requests.put(item)
                continue
            try:
                result = await self.send_reply(conversation_id, prompt, attachments=attachments)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            else:
                if not future.done():
                    future.set_result(result)
                did_work = True
            finally:
                self._reply_requests.task_done()
        return did_work

    async def _drain_sync_requests(self) -> bool:
        did_work = False
        while True:
            try:
                conversation_id, future = self._sync_requests.get_nowait()
            except asyncio.QueueEmpty:
                return did_work
            try:
                message_count = await self.sync_conversation(conversation_id)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            else:
                if not future.done():
                    future.set_result(message_count)
                did_work = True
            finally:
                self._sync_requests.task_done()

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
            did_work = await self._retry_cached_recovery_if_due() or did_work
            await self._poll_active_conversations()
            if self.driver is not None and self.driver.needs_browser_restart is True:
                raise RuntimeError(
                    "Browser session was lost; restarting Prompta to recycle browser"
                )
            jobs = self.read_jobs()
            if not jobs:
                await self._release_driver_if_idle()
                if once:
                    return
                await asyncio.sleep(_IDLE_POLL_SECONDS)
                continue
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
            await self._poll_active_conversations()
            await self._release_driver_if_idle()
            await asyncio.sleep(_IDLE_POLL_SECONDS if did_work else 1.0)

    async def close(self) -> None:
        if self.driver is not None:
            for context, active in list(self._active_conversations.items()):
                complete = active.settled_at > 0
                try:
                    snapshot = await self.driver.conversation_snapshot(context)
                    messages = snapshot.get("messages")
                    if not isinstance(messages, list):
                        messages = []
                    last_message = messages[-1] if messages else None
                    has_assistant = (
                        isinstance(last_message, dict)
                        and str(last_message.get("role") or "") == "assistant"
                        and bool(str(last_message.get("content") or "").strip())
                    )
                    complete = complete or (has_assistant and not bool(snapshot.get("streaming")))
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
            await self.driver.close()
            self.driver = None
        self.cache.close()


def load_jobs(path: Path) -> dict[str, PromptJob]:
    target = path.expanduser()
    try:
        payload = json.loads(target.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    jobs_raw = payload.get("jobs", payload)
    if not isinstance(jobs_raw, dict):
        return {}
    jobs: dict[str, PromptJob] = {}
    for name, value in jobs_raw.items():
        if isinstance(value, str):
            prompt = value
            interval = DEFAULT_INTERVAL_SECONDS
        elif isinstance(value, dict):
            prompt = str(value.get("prompt") or "")
            try:
                raw_interval = value.get("interval_seconds")
                interval = DEFAULT_INTERVAL_SECONDS if raw_interval is None else float(raw_interval)
            except (TypeError, ValueError):
                interval = DEFAULT_INTERVAL_SECONDS
        else:
            continue
        daily_at = None
        exact_interval = False
        run_at_epoch: float | None = None
        if isinstance(value, dict):
            exact_interval = value.get("exact_interval") is True
            if value.get("run_at_epoch") is not None:
                try:
                    run_at_epoch = float(value["run_at_epoch"])
                except (TypeError, ValueError):
                    logger.warning("Ignoring invalid run_at_epoch for Prompta job=%s", name)
            if value.get("daily_at") is not None:
                try:
                    daily_at = _normalise_daily_at(str(value["daily_at"]))
                except ValueError:
                    logger.warning("Ignoring invalid daily_at for Prompta job=%s", name)
        if str(name).strip() and prompt.strip():
            jobs[str(name)] = PromptJob(
                str(name), prompt, max(0.0, interval), daily_at, exact_interval, run_at_epoch
            )
    return jobs


def _write_jobs(path: Path, jobs: dict[str, PromptJob]) -> None:
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "jobs": {
            name: {
                "prompt": job.prompt,
                "interval_seconds": job.interval_seconds,
                **({"daily_at": job.daily_at} if job.daily_at is not None else {}),
                **({"exact_interval": True} if job.exact_interval else {}),
                **({"run_at_epoch": job.run_at_epoch} if job.run_at_epoch is not None else {}),
            }
            for name, job in sorted(jobs.items())
        }
    }
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(target)


def add_job(
    path: Path,
    name: str,
    prompt: str,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    daily_at: str | None = None,
    exact_interval: bool = False,
    run_at_epoch: float | None = None,
) -> None:
    if not name.strip():
        raise ValueError("prompta job name is empty")
    if not prompt.strip():
        raise ValueError("prompta prompt is empty")
    jobs = load_jobs(path)
    normalised_daily_at = _normalise_daily_at(daily_at) if daily_at is not None else None
    normalised_run_at = float(run_at_epoch) if run_at_epoch is not None else None
    if normalised_run_at is not None and normalised_run_at <= 0:
        raise ValueError("run_at_epoch must be a positive Unix timestamp")
    jobs[name] = PromptJob(
        name,
        prompt,
        max(0.0, interval_seconds),
        normalised_daily_at,
        exact_interval,
        normalised_run_at,
    )
    _write_jobs(path, jobs)


def remove_job(path: Path, name: str) -> None:
    jobs = load_jobs(path)
    jobs.pop(name, None)
    _write_jobs(path, jobs)


def clear_jobs(path: Path) -> None:
    try:
        path.expanduser().unlink()
    except FileNotFoundError:
        pass


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


def _control_socket_path(state_path: Path) -> Path:
    return state_path.expanduser().parent / _CONTROL_SOCKET_NAME


def _daemon_lock_path(state_path: Path) -> Path:
    return state_path.expanduser().parent / _DAEMON_LOCK_NAME


def _daemon_is_running(state_path: Path) -> bool:
    path = _daemon_lock_path(state_path)
    try:
        handle = path.open("r")
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return True
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()
    return False


def _acquire_daemon_lock(state_path: Path) -> Any:
    path = _daemon_lock_path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    os.chmod(path, 0o600)
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("another Prompta scheduler is already running") from exc
    return handle


async def _handle_control_client(
    prompta: Prompta,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=10.0)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid Prompta control request")
        op = str(payload.get("op") or "")
        if op == "sync":
            conversation_id = str(payload.get("conversation_id") or "")
            if not conversation_id.strip():
                raise ValueError("conversation id is empty")
            sync_future: asyncio.Future[int] = asyncio.get_running_loop().create_future()
            await prompta._sync_requests.put((conversation_id, sync_future))
            message_count = await sync_future
            response = {"ok": True, "message_count": message_count}
        elif op == "stop":
            conversation_id = str(payload.get("conversation_id") or "")
            if not conversation_id.strip():
                raise ValueError("conversation id is empty")
            stopped_id = await prompta.stop_conversation(conversation_id)
            response = {"ok": True, "conversation_id": stopped_id}
        else:
            prompt = str(payload.get("prompt") or "")
            raw_attachments = payload.get("attachments")
            attachments = [
                str(path)
                for path in raw_attachments
                if isinstance(path, str) and path.strip()
            ] if isinstance(raw_attachments, list) else []
            if not prompt.strip():
                raise ValueError("prompta prompt is empty")
            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            if op == "once":
                await prompta._once_requests.put((prompt, attachments, future))
            elif op == "reply":
                conversation_id = str(payload.get("conversation_id") or "")
                if not conversation_id.strip():
                    raise ValueError("conversation id is empty")
                await prompta._reply_requests.put((conversation_id, prompt, attachments, future))
            else:
                raise ValueError("unsupported Prompta control request")
            conversation_id = await future
            response = {"ok": True, "conversation_id": conversation_id}
    except RateLimitError as exc:
        response = {
            "ok": False,
            "error": str(exc),
            "error_type": "rate_limit",
            "retry_after": exc.retry_after,
        }
    except Exception as exc:
        response = {"ok": False, "error": str(exc)}
    try:
        writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        await writer.drain()
    except (BrokenPipeError, ConnectionResetError):
        logger.debug("Prompta control client disconnected before receiving its result")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (BrokenPipeError, ConnectionResetError):
            pass


async def _start_control_server(
    prompta: Prompta,
    state_path: Path,
) -> tuple[asyncio.AbstractServer, Path]:
    path = _control_socket_path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    server = await asyncio.start_unix_server(
        lambda reader, writer: _handle_control_client(prompta, reader, writer),
        path=str(path),
    )
    os.chmod(path, 0o600)
    return server, path


async def _open_control_connection(
    state_path: Path,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    path = _control_socket_path(state_path)
    deadline = asyncio.get_running_loop().time() + _CONTROL_CONNECT_TIMEOUT_SECONDS
    last_error: OSError | None = None
    while True:
        try:
            return await asyncio.open_unix_connection(str(path))
        except OSError as exc:
            last_error = exc
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError(
                    f"Prompta scheduler is running but its control socket is unavailable: {path}"
                ) from last_error
            await asyncio.sleep(0.1)


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
        if isinstance(payload, dict) and payload.get("error_type") == "rate_limit":
            raise RateLimitError(error, retry_after=int(payload.get("retry_after") or DEFAULT_RETRY_AFTER))
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
) -> str:
    payload = await _control_send_request_with_restart_retry(
        state_path,
        {
            "op": "reply",
            "conversation_id": conversation_id,
            "prompt": prompt,
            "attachments": attachments or [],
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


async def _firefox_port_is_open(port: int) -> bool:
    try:
        _reader, writer = await asyncio.open_connection("127.0.0.1", port)
    except OSError:
        return False
    writer.close()
    await writer.wait_closed()
    return True


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    """Stop a child process without leaking it if shutdown races process exit."""

    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            return
        await process.wait()


def _firefox_profile_owner_pid(profile: Path) -> int | None:
    """Return Firefox's live-profile owner PID encoded in its lock symlink."""

    try:
        target = os.readlink(profile / "lock")
    except (FileNotFoundError, OSError):
        return None
    match = re.search(r"\+(\d+)$", target)
    return int(match.group(1)) if match is not None else None


def _firefox_process_uses_profile(pid: int, profile: Path) -> bool:
    """Conservatively identify a live Firefox process using this profile."""

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    try:
        arguments = [
            value.decode("utf-8", errors="replace")
            for value in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            if value
        ]
    except OSError:
        # If the PID exists but procfs cannot be inspected, preserve the lock
        # instead of risking two Firefox instances writing the same profile.
        return True
    if not arguments or Path(arguments[0]).name != "firefox":
        return False
    resolved = str(profile.resolve())
    return any(
        argument == resolved
        for index, argument in enumerate(arguments)
        if index > 0 and arguments[index - 1] == "--profile"
    )


async def _spawn_firefox(
    profile: Path, firefox_path: str, port: int
) -> asyncio.subprocess.Process | None:
    resolved = profile.expanduser().resolve()
    if not resolved.is_dir():
        raise RuntimeError(f"Firefox profile does not exist: {resolved}")
    if await _firefox_port_is_open(port):
        # A systemd restart can briefly leave the old Firefox listener alive while
        # the previous service cgroup is still being torn down. A single delayed
        # recheck still leaves a race if that process exits immediately afterwards,
        # so require the listener to survive several consecutive polls before reuse.
        listener_stable = True
        for _ in range(_FIREFOX_REUSE_STABILITY_CHECKS):
            await asyncio.sleep(_FIREFOX_REUSE_POLL_SECONDS)
            if not await _firefox_port_is_open(port):
                listener_stable = False
                break
        if listener_stable:
            logger.info("Prompta reusing Firefox already listening on port %d", port)
            return None
        logger.info(
            "Prompta Firefox listener on port %d disappeared during reuse check",
            port,
        )

    owner_pid = _firefox_profile_owner_pid(resolved)
    if owner_pid is not None and _firefox_process_uses_profile(owner_pid, resolved):
        logger.info(
            "Prompta Firefox profile is still owned by pid=%d; waiting for it to exit",
            owner_pid,
        )
        deadline = (
            asyncio.get_running_loop().time()
            + _FIREFOX_PROFILE_RELEASE_TIMEOUT_SECONDS
        )
        while _firefox_process_uses_profile(owner_pid, resolved):
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError(
                    "Firefox profile is still in use after "
                    f"{_FIREFOX_PROFILE_RELEASE_TIMEOUT_SECONDS:.0f}s "
                    f"(pid={owner_pid})"
                )
            await asyncio.sleep(_FIREFOX_REUSE_POLL_SECONDS)
            if await _firefox_port_is_open(port):
                listener_stable = True
                for _ in range(_FIREFOX_REUSE_STABILITY_CHECKS):
                    await asyncio.sleep(_FIREFOX_REUSE_POLL_SECONDS)
                    if not await _firefox_port_is_open(port):
                        listener_stable = False
                        break
                if listener_stable:
                    logger.info(
                        "Prompta reusing Firefox already listening on port %d",
                        port,
                    )
                    return None
        logger.info(
            "Prompta previous Firefox pid=%d released the profile; starting a fresh browser",
            owner_pid,
        )

    # Only remove lock artifacts after proving that their recorded Firefox
    # owner is gone. Deleting a live profile lock can let two Firefox instances
    # write cookies/session state concurrently.
    for name in ("lock", ".parentlock"):
        try:
            os.unlink(resolved / name)
        except FileNotFoundError:
            pass
    # Keep Firefox independent from the host's shared /tmp quota. Prompta can
    # have plenty of state-disk space while a busy user tmpfs is exhausted,
    # which otherwise makes a clean daemon restart fail before BiDi starts.
    firefox_tmp = resolved.parent / "firefox-tmp"
    firefox_tmp.mkdir(parents=True, exist_ok=True)
    os.chmod(firefox_tmp, 0o700)
    environment = os.environ.copy()
    environment["TMPDIR"] = str(firefox_tmp)
    process = await asyncio.create_subprocess_exec(
        firefox_path,
        "--headless",
        "--profile",
        str(resolved),
        "--remote-debugging-port",
        str(port),
        "-remote-allow-system-access",
        "https://chatgpt.com/",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env=environment,
    )
    try:
        await wait_for_port(port)
    except BaseException:
        # Callers cannot own/clean this child until _spawn_firefox returns.
        # Direct UI sends keep their parent process alive, so a failed startup
        # must not leave a headless Firefox child consuming memory indefinitely.
        await _terminate_process(process)
        raise
    return process


async def _recover_disappeared_reused_firefox(
    prompta: Prompta,
    profile: Path,
    firefox_path: str,
    port: int,
) -> asyncio.subprocess.Process | None:
    """Replace a Firefox listener that vanished after the reuse stability check."""

    try:
        await prompta._ensure_driver()
        return None
    except (ConnectionClosed, OSError, RuntimeError):
        # Authentication/session errors can occur while a healthy Firefox listener
        # remains available. Only replace a reused browser when the endpoint itself
        # has actually disappeared; otherwise preserve the original error.
        if await _firefox_port_is_open(port):
            raise

    logger.warning(
        "Prompta reused Firefox on port %d but its BiDi endpoint disappeared; "
        "starting a fresh browser",
        port,
    )
    if prompta.driver is not None:
        await prompta.driver.close()
        prompta.driver = None

    replacement = await _spawn_firefox(profile, firefox_path, port)
    try:
        await prompta._ensure_driver()
    except BaseException:
        if replacement is not None:
            await _terminate_process(replacement)
        raise
    return replacement


async def _send_direct(
    state_path: Path,
    cache_path: Path,
    prompt: str,
    *,
    conversation_id: str = "",
    attachments: list[str] | None = None,
    firefox_profile: Path = DEFAULT_FIREFOX_PROFILE,
    firefox_path: str = "/usr/bin/firefox",
    firefox_port: int = DEFAULT_FIREFOX_PORT,
) -> str:
    """Send without a resident scheduler, keeping Firefox alive until the reply is cached."""
    firefox: asyncio.subprocess.Process | None = None
    prompta: Prompta | None = None
    try:
        firefox = await _spawn_firefox(firefox_profile, firefox_path, firefox_port)
        prompta = Prompta(
            PromptaConfig(
                state_path=state_path,
                cache_path=cache_path,
            ),
            f"ws://127.0.0.1:{firefox_port}/session",
        )
        if firefox is None:
            firefox = await _recover_disappeared_reused_firefox(
                prompta,
                firefox_profile,
                firefox_path,
                firefox_port,
            )
        if conversation_id:
            result = await prompta.send_reply(
                conversation_id,
                prompt,
                attachments=attachments,
            )
        else:
            result = await prompta.send_once(prompt, attachments=attachments)
        await prompta.wait_for_cached_response(result)
        return result
    finally:
        if prompta is not None:
            await prompta.close()
        if firefox is not None:
            await _terminate_process(firefox)


def _add_browser_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--send-timeout-seconds", type=float, default=_SEND_CONFIRM_TIMEOUT_SECONDS)
    parser.add_argument("--bidi-url")
    parser.add_argument(
        "--direct-browser",
        action="store_true",
        help="Bypass a running Prompta daemon and use this command's browser backend directly",
    )
    parser.add_argument(
        "--browser",
        choices=("firefox", "chrome"),
        default=os.environ.get("PROMPTA_BROWSER", "chrome"),
    )
    parser.add_argument("--firefox-profile", type=Path, default=DEFAULT_FIREFOX_PROFILE)
    parser.add_argument("--firefox-path", default="/usr/bin/firefox")
    parser.add_argument("--firefox-port", type=int, default=DEFAULT_FIREFOX_PORT)
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
        "--chromedriver-path",
        default=os.environ.get("PROMPTA_CHROMEDRIVER_PATH", "/usr/bin/chromedriver"),
    )
    parser.add_argument(
        "--chrome-debugger-address",
        default=os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS"),
        help="Attach ChromeDriver to an existing Chromium-family browser debugger address",
    )
    parser.add_argument(
        "--chrome-auth-timeout-seconds",
        type=float,
        default=float(os.environ.get("PROMPTA_CHROME_AUTH_TIMEOUT_SECONDS", "30")),
        help="How long ChromeDriver may wait for a ChatGPT login before failing",
    )
    parser.add_argument(
        "--chrome-headed",
        action="store_true",
        help="Run Chromium with a visible window (useful for the first ChatGPT login)",
    )


def _chrome_driver_factory(args: argparse.Namespace) -> DriverFactory:
    profile = args.chrome_profile.expanduser().resolve()
    chrome_path = str(args.chrome_path)
    chromedriver_path = str(args.chromedriver_path)
    headless = not bool(args.chrome_headed)

    def factory() -> BrowserDriver:
        return ChromeDriverDriver(
            profile=profile,
            chrome_path=chrome_path,
            chromedriver_path=chromedriver_path,
            headless=headless,
            auth_timeout_seconds=max(0.1, float(args.chrome_auth_timeout_seconds)),
            debugger_address=args.chrome_debugger_address,
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
        if not args.direct_browser and not args.bidi_url and _daemon_is_running(args.state):
            conversation_id = await _send_once_via_control(args.state, args.prompt)
            _print_notice("✓", "Sent", f"conversation {conversation_id}", tone="32")
            _print_notice("…", "Waiting", "assistant response", tone="36")
            if await _wait_for_cache_completion(args.cache, conversation_id):
                _print_notice("✓", "Cached", "assistant response complete", tone="32")
            return
    elif args.command == "reply":
        _print_notice("◆", "Reply", _prompt_preview(args.prompt, 72))
        if not args.direct_browser and not args.bidi_url and _daemon_is_running(args.state):
            conversation_id = await _send_reply_via_control(
                args.state,
                args.conversation_id,
                args.prompt,
            )
            _print_notice("✓", "Sent", f"conversation {conversation_id}", tone="32")
            return
    elif args.command == "sync":
        if not args.direct_browser and not args.bidi_url and _daemon_is_running(args.state):
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
    firefox: asyncio.subprocess.Process | None = None
    prompta: Prompta | None = None

    if args.command == "run":
        daemon_lock = _acquire_daemon_lock(args.state)

    try:
        driver_factory: DriverFactory | None = None
        using_firefox = bool(args.bidi_url) or args.browser == "firefox"
        if args.bidi_url:
            bidi_url = args.bidi_url
        elif using_firefox:
            firefox = await _spawn_firefox(
                args.firefox_profile, args.firefox_path, args.firefox_port
            )
            bidi_url = f"ws://127.0.0.1:{args.firefox_port}/session"
        else:
            bidi_url = ""
            driver_factory = _chrome_driver_factory(args)

        prompta = Prompta(
            PromptaConfig(
                jobs_file=getattr(args, "jobs_file", DEFAULT_JOBS_PATH),
                state_path=args.state,
                cache_path=args.cache,
                send_timeout_seconds=max(1.0, args.send_timeout_seconds),
            ),
            bidi_url,
            driver_factory=driver_factory,
        )
        if args.command == "run":
            # Publish the control socket before browser/cache recovery. The daemon lock is
            # already held at this point, so UI sends otherwise see a running scheduler
            # but can race a potentially slow recovery and fail before the socket exists.
            control_server, control_path = await _start_control_server(prompta, args.state)
            if using_firefox and not args.bidi_url and firefox is None:
                firefox = await _recover_disappeared_reused_firefox(
                    prompta,
                    args.firefox_profile,
                    args.firefox_path,
                    args.firefox_port,
                )
            recovered = await prompta.recover_cached_conversations()
            if recovered:
                logger.info(
                    "Prompta recovered %d live conversation(s) after restart", recovered
                )

        if (
            args.command != "run"
            and using_firefox
            and not args.bidi_url
            and firefox is None
        ):
            firefox = await _recover_disappeared_reused_firefox(
                prompta,
                args.firefox_profile,
                args.firefox_path,
                args.firefox_port,
            )

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
        if firefox is not None:
            await _terminate_process(firefox)
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
        interval_minutes = 30.0 if args.interval_minutes is None else args.interval_minutes
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
