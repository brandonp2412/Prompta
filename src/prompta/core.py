"""Periodic fresh-chat scheduler for Prompta."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from websockets.exceptions import ConnectionClosed

from .bidi import FirefoxBiDiDriver, wait_for_port

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30 * 60
DEFAULT_JOBS_PATH = Path.home() / ".config" / "prompta" / "jobs.json"
DEFAULT_STATE_PATH = Path.home() / ".local" / "state" / "prompta" / "state.json"
DEFAULT_FIREFOX_PROFILE = Path.home() / ".local" / "state" / "prompta" / "firefox-profile"
DEFAULT_FIREFOX_PORT = 9229
DEFAULT_RETRY_AFTER = 5 * 60
_SEND_CONFIRM_TIMEOUT_SECONDS = 20.0
_SEND_CONFIRM_POLL_SECONDS = 0.2
_EFFORT_CONTROL_TIMEOUT_SECONDS = 20.0
_IDLE_POLL_SECONDS = 1.0
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
    def __init__(self, message: str = "ChatGPT rate limit reached", retry_after: int = DEFAULT_RETRY_AFTER) -> None:
        super().__init__(message)
        self.retry_after = max(0, int(retry_after))

    @classmethod
    def from_text(cls, text: str) -> RateLimitError:
        return cls(retry_after=parse_retry_after(text))


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
        if self.attempts and self.last_limited_at and now - self.last_limited_at >= _RATE_LIMIT_RESET_SECONDS:
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


@dataclass(frozen=True)
class PromptaConfig:
    jobs_file: Path = DEFAULT_JOBS_PATH
    state_path: Path = DEFAULT_STATE_PATH
    send_timeout_seconds: float = _SEND_CONFIRM_TIMEOUT_SECONDS


class Prompta:
    def __init__(self, config: PromptaConfig, bidi_url: str) -> None:
        self.config = config
        self.bidi_url = bidi_url
        self.driver: FirefoxBiDiDriver | None = None
        self._backoffs: dict[str, RateLimitBackoff] = {}
        self._global_backoff = RateLimitBackoff()
        self._failure_retry_until: dict[str, float] = {}
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
        if next_due_at > 0 and last_sent_at >= last_uncertain_send_at:
            return max(0.0, next_due_at - current)
        if last_attempt_at > 0:
            if job.daily_at is not None:
                return max(0.0, _next_daily_epoch(job.daily_at, last_attempt_at) - current)
            return max(0.0, last_attempt_at + max(0.0, job.interval_seconds) - current)
        if initial_due_at > 0:
            return max(0.0, initial_due_at - current)
        return 0.0

    async def _ensure_driver(self) -> FirefoxBiDiDriver:
        if self.driver is None:
            self.driver = FirefoxBiDiDriver(self.bidi_url)
        if not self.driver.is_connected:
            await self.driver.connect()
        return self.driver

    async def _pointer_click(self, driver: FirefoxBiDiDriver, x: float, y: float) -> None:
        await driver._call(
            "input.performActions",
            {
                "context": driver.context,
                "actions": [
                    {
                        "type": "pointer",
                        "id": "mouse",
                        "parameters": {"pointerType": "mouse"},
                        "actions": [
                            {
                                "type": "pointerMove",
                                "x": int(x),
                                "y": int(y),
                                "duration": 0,
                                "origin": "viewport",
                            },
                            {"type": "pointerDown", "button": 0},
                            {"type": "pointerUp", "button": 0},
                        ],
                    }
                ],
            },
        )
        await driver._call("input.releaseActions", {"context": driver.context})

    async def _effort_trigger_info(
        self,
        driver: FirefoxBiDiDriver,
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
                  const r=button.getBoundingClientRect();
                  return {text:normalise(button.innerText||button.textContent||''),x:r.left+r.width/2,y:r.top+r.height/2};
                })())"""
            )
            if raw and raw != "null":
                payload = json.loads(raw)
                if isinstance(payload, dict) and payload.get("text"):
                    return payload
            await asyncio.sleep(0.15)
        raise RuntimeError("ChatGPT thinking-effort control did not become available")

    async def _high_effort_slider_point(self, driver: FirefoxBiDiDriver) -> dict[str, float]:
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
                  return {x:r.left+pad+(r.width-pad*2)*(target-min)/(max-min),y:r.top+r.height/2};
                })())"""
            )
            if raw and raw != "null":
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    if payload.get("error"):
                        raise RuntimeError(f"ChatGPT High effort is unavailable: {payload['error']}")
                    if "x" in payload and "y" in payload:
                        return {"x": float(payload["x"]), "y": float(payload["y"])}
            await asyncio.sleep(0.1)
        raise RuntimeError("ChatGPT thinking-effort slider did not open")

    async def _ensure_high_effort(self, driver: FirefoxBiDiDriver) -> None:
        trigger = await self._effort_trigger_info(driver)
        if str(trigger.get("text") or "").strip().casefold() == "high":
            logger.info("Prompta verified thinking effort=High")
            return
        await self._pointer_click(driver, float(trigger["x"]), float(trigger["y"]))
        point = await self._high_effort_slider_point(driver)
        await self._pointer_click(driver, point["x"], point["y"])
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
        await driver._call(
            "input.performActions",
            {
                "context": driver.context,
                "actions": [
                    {
                        "type": "key",
                        "id": "keyboard",
                        "actions": [
                            {"type": "keyDown", "value": "\ue00c"},
                            {"type": "keyUp", "value": "\ue00c"},
                        ],
                    }
                ],
            },
        )
        await driver._call("input.releaseActions", {"context": driver.context})
        await asyncio.sleep(0.2)
        verified = await self._effort_trigger_info(driver)
        if str(verified.get("text") or "").strip().casefold() != "high":
            raise RuntimeError(
                f"ChatGPT thinking effort verification failed: {verified.get('text')!r}"
            )
        logger.info("Prompta set and verified thinking effort=High")

    async def send_once(self, prompt: str) -> str:
        if not prompt.strip():
            raise ValueError("prompta prompt is empty")
        driver = await self._ensure_driver()
        await driver.navigate("https://chatgpt.com/")
        await driver.wait_for_composer()
        await self._ensure_high_effort(driver)
        baseline = await driver.dom_state()
        baseline_path = str(await driver.eval("location.pathname") or "")
        if self._normalise(str(baseline.get("composer_text") or "")):
            logger.warning("Prompta found stale text in the dedicated new-chat composer; clearing it")
            await driver.clear_composer()
            baseline = await driver.dom_state()
            if self._normalise(str(baseline.get("composer_text") or "")):
                raise RuntimeError("ChatGPT stale new-chat composer could not be cleared")
        await driver.arm_page_send_probe()
        capture = driver.arm_send_capture()
        try:
            await driver.type_message(prompt)
            typed = await driver.dom_state()
            if self._normalise(str(typed.get("composer_text") or "")) != self._normalise(prompt):
                raise RuntimeError("ChatGPT composer did not contain the configured prompt")
            await driver.click_send()
            deadline = asyncio.get_running_loop().time() + max(
                1.0, self.config.send_timeout_seconds
            )
            while asyncio.get_running_loop().time() < deadline:
                state = await driver.dom_state()
                rate_limit_text = str(state.get("rate_limit_text") or "")
                if is_rate_limited_text(rate_limit_text):
                    raise RateLimitError.from_text(rate_limit_text)
                probe = await driver.page_send_probe()
                path = str(await driver.eval("location.pathname") or "")
                user_text = self._normalise(str(state.get("last_user_text") or ""))
                message_id = str(probe.get("message_id") or state.get("last_user_id") or "")
                status = int(probe.get("response_status") or capture.get("status") or 0)
                send_confirmed = bool(probe.get("committed")) or driver.captured_send_response(capture) is not None
                if status == 429:
                    raise RateLimitError("prompta send rate limited")
                if status >= 400:
                    raise RuntimeError(f"prompta send failed with HTTP {status}")
                if capture.get("fetch_error"):
                    raise RuntimeError(f"prompta send failed: {capture['fetch_error']}")
                route_confirmed = path.startswith("/c/") and path != baseline_path
                dom_confirmed = (
                    user_text == self._normalise(prompt)
                    and not self._normalise(str(state.get("composer_text") or ""))
                )
                if route_confirmed:
                    conversation_id = path.removeprefix("/c/").split("/", 1)[0]
                    logger.info(
                        "Prompta sent prompt in new conversation=%s message_id=%s transport_confirmed=%s dom_confirmed=%s",
                        conversation_id,
                        message_id or "unknown",
                        send_confirmed,
                        dom_confirmed,
                    )
                    return conversation_id
                await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)
        finally:
            driver.clear_send_capture(capture)
            try:
                await driver.clear_page_send_probe()
            except Exception:
                logger.debug("Could not clear page send probe", exc_info=True)
        raise SendVerificationError("prompta could not prove the prompt was sent in a new conversation")

    async def _run_job(self, job: PromptJob, *, now: float) -> bool:
        if self._job_state(job.name).get("paused") is True:
            return False
        if self.due_in(job, now) > 0:
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
            conversation_id = await self.send_once(job.prompt)
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
                await self.driver.close()
                self.driver = None
            return False
        except (ConnectionClosed, OSError, RuntimeError) as exc:
            logger.exception("Prompta job=%s send failed: %s", job.name, exc)
            retry_until = time.time() + _FAILURE_RETRY_SECONDS
            self._mark_failure(job.name, str(exc), retry_until=retry_until)
            if self.driver is not None:
                await self.driver.close()
                self.driver = None
            self._failure_retry_until[job.name] = retry_until
            return False
        sent_at = time.time()
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

    async def run(self, *, once: bool = False) -> None:
        while True:
            jobs = self.read_jobs()
            if not jobs:
                if once:
                    return
                await asyncio.sleep(_IDLE_POLL_SECONDS)
                continue
            now = time.time()
            scheduled_jobs = list(jobs.values())
            self._ensure_initial_schedules(scheduled_jobs, now)
            did_work = False
            for job in scheduled_jobs:
                if await self._run_job(job, now=now):
                    did_work = True
                if self._global_backoff.remaining() > 0:
                    break
            if once:
                return
            await asyncio.sleep(_IDLE_POLL_SECONDS if did_work else 1.0)

    async def close(self) -> None:
        if self.driver is not None:
            await self.driver.close()
            self.driver = None


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
                interval = (
                    DEFAULT_INTERVAL_SECONDS
                    if raw_interval is None
                    else float(raw_interval)
                )
            except (TypeError, ValueError):
                interval = DEFAULT_INTERVAL_SECONDS
        else:
            continue
        daily_at = None
        if isinstance(value, dict) and value.get("daily_at") is not None:
            try:
                daily_at = _normalise_daily_at(str(value["daily_at"]))
            except ValueError:
                logger.warning("Ignoring invalid daily_at for Prompta job=%s", name)
        if str(name).strip() and prompt.strip():
            jobs[str(name)] = PromptJob(str(name), prompt, max(0.0, interval), daily_at)
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
) -> None:
    if not name.strip():
        raise ValueError("prompta job name is empty")
    if not prompt.strip():
        raise ValueError("prompta prompt is empty")
    jobs = load_jobs(path)
    normalised_daily_at = _normalise_daily_at(daily_at) if daily_at is not None else None
    jobs[name] = PromptJob(name, prompt, max(0.0, interval_seconds), normalised_daily_at)
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


def _print_job_table(prompta: Prompta, jobs: dict[str, PromptJob]) -> None:
    if not jobs:
        print("No prompts configured.")
        return
    rows = []
    for job in jobs.values():
        icon, status = _job_status(prompta, job)
        rows.append((icon, status, job.name, _format_next_due(prompta, job), _prompt_preview(job.prompt)))
    headers = ("", "STATUS", "NAME", "NEXT DUE", "PROMPT")
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    print("  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)).rstrip())
    print("  ".join("─" * width for width in widths).rstrip())
    for row in rows:
        print("  ".join(value.ljust(widths[i]) for i, value in enumerate(row)).rstrip())


async def _spawn_firefox(profile: Path, firefox_path: str, port: int) -> asyncio.subprocess.Process:
    resolved = profile.expanduser().resolve()
    if not resolved.is_dir():
        raise RuntimeError(f"Firefox profile does not exist: {resolved}")
    for name in ("lock", ".parentlock"):
        try:
            os.unlink(resolved / name)
        except FileNotFoundError:
            pass
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
    )
    await wait_for_port(port)
    return process


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send named prompts into fresh ChatGPT chats on a cadence"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_parser = subparsers.add_parser("add", help="Add or replace a named job")
    add_parser.add_argument("name")
    add_parser.add_argument("prompt")
    schedule_group = add_parser.add_mutually_exclusive_group()
    schedule_group.add_argument("--interval-minutes", type=float)
    schedule_group.add_argument("--daily-at", metavar="HH:MM")
    add_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    remove_parser = subparsers.add_parser("remove", help="Remove a named job")
    remove_parser.add_argument("name")
    remove_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    show_parser = subparsers.add_parser("show", help="Show one named job")
    show_parser.add_argument("name")
    show_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    show_parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    list_parser = subparsers.add_parser("list", help="List configured jobs")
    list_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    list_parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    clear_parser = subparsers.add_parser("clear", help="Remove all jobs")
    clear_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    for command, help_text in (("pause", "Pause a named job"), ("resume", "Resume a named job")):
        job_parser = subparsers.add_parser(command, help=help_text)
        job_parser.add_argument("name")
        job_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
        job_parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    run_parser = subparsers.add_parser("run", help="Run the scheduler")
    run_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    run_parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    run_parser.add_argument(
        "--send-timeout-seconds", type=float, default=_SEND_CONFIRM_TIMEOUT_SECONDS
    )
    run_parser.add_argument("--once", action="store_true")
    run_parser.add_argument("--bidi-url")
    run_parser.add_argument("--firefox-profile", type=Path, default=DEFAULT_FIREFOX_PROFILE)
    run_parser.add_argument("--firefox-path", default="/usr/bin/firefox")
    run_parser.add_argument("--firefox-port", type=int, default=DEFAULT_FIREFOX_PORT)
    return parser


async def _run(args: argparse.Namespace) -> None:
    firefox: asyncio.subprocess.Process | None = None
    if args.bidi_url:
        bidi_url = args.bidi_url
    else:
        firefox = await _spawn_firefox(args.firefox_profile, args.firefox_path, args.firefox_port)
        bidi_url = f"ws://127.0.0.1:{args.firefox_port}/session"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=args.jobs_file,
            state_path=args.state,
            send_timeout_seconds=max(1.0, args.send_timeout_seconds),
        ),
        bidi_url,
    )
    try:
        await prompta.run(once=args.once)
    finally:
        await prompta.close()
        if firefox is not None and firefox.returncode is None:
            firefox.terminate()
            try:
                await asyncio.wait_for(firefox.wait(), timeout=5)
            except TimeoutError:
                firefox.kill()
                await firefox.wait()


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "add":
        interval_minutes = 30.0 if args.interval_minutes is None else args.interval_minutes
        add_job(
            args.jobs_file,
            args.name,
            args.prompt,
            max(0.0, interval_minutes * 60.0),
            args.daily_at,
        )
        if args.daily_at is not None:
            print(f"✓ Added prompt '{args.name}' (daily at {_normalise_daily_at(args.daily_at)} local time)")
        else:
            print(f"✓ Added prompt '{args.name}' (next due in {_format_duration(interval_minutes * 60)})")
        return
    if args.command == "remove":
        existed = args.name in load_jobs(args.jobs_file)
        remove_job(args.jobs_file, args.name)
        print(f"✓ Removed prompt '{args.name}'" if existed else f"○ No prompt named '{args.name}'")
        return
    if args.command == "show":
        job = load_jobs(args.jobs_file).get(args.name)
        if job is None:
            raise SystemExit(f"No Prompta job named {args.name!r}")
        prompta = Prompta(PromptaConfig(jobs_file=args.jobs_file, state_path=args.state), "")
        icon, status = _job_status(prompta, job)
        state = prompta._job_state(job.name)
        print(f"{icon} {job.name} · {status}")
        if job.daily_at is not None:
            print(f"Schedule  daily at {job.daily_at} local time")
        else:
            print(f"Interval  {_format_duration(job.interval_seconds)}")
        print(f"Next due  {_format_next_due(prompta, job)}")
        if state.get("status_message"):
            print(f"Issue     {state['status_message']}")
        print(f"Prompt    {job.prompt}")
        return
    if args.command == "list":
        prompta = Prompta(PromptaConfig(jobs_file=args.jobs_file, state_path=args.state), "")
        _print_job_table(prompta, load_jobs(args.jobs_file))
        return
    if args.command == "clear":
        count = len(load_jobs(args.jobs_file))
        clear_jobs(args.jobs_file)
        print(f"✓ Cleared {count} prompt{'s' if count != 1 else ''}.")
        return
    if args.command in {"pause", "resume"}:
        jobs = load_jobs(args.jobs_file)
        if args.name not in jobs:
            raise SystemExit(f"No Prompta job named {args.name!r}")
        paused = args.command == "pause"
        set_job_paused(args.jobs_file, args.state, args.name, paused)
        print(f"✓ {'Paused' if paused else 'Resumed'} prompt '{args.name}'")
        return
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
