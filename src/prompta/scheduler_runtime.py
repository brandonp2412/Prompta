from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .jobs import PromptJob, _next_daily_epoch, load_jobs
from .rate_limit import RateLimitBackoff, RateLimitError

logger = logging.getLogger(__name__)

_MIN_SEND_GAP_SECONDS = 60.0
_INITIAL_DELAY_CAP_SECONDS = 30 * 60.0
_RECURRING_JITTER_FRACTION = 0.20
_RECURRING_JITTER_CAP_SECONDS = 5 * 60.0


class SchedulerRuntime:
    def __init__(self, state_path: Path, jobs_file: Path) -> None:
        self.state_path = state_path
        self.jobs_file = jobs_file
        self.backoffs: dict[str, RateLimitBackoff] = {}
        self.global_backoff = RateLimitBackoff()
        self.failure_retry_until: dict[str, float] = {}
        self.restore_backoffs()

    def load_state(self) -> dict[str, Any]:
        path = self.state_path.expanduser()
        try:
            value = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return value if isinstance(value, dict) else {}

    def write_state(self, state: dict[str, Any]) -> None:
        path = self.state_path.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        os.chmod(temporary, 0o600)
        temporary.replace(path)

    def job_state(self, name: str) -> dict[str, Any]:
        jobs = self.load_state().get("jobs")
        if not isinstance(jobs, dict):
            return {}
        value = jobs.get(name)
        return value if isinstance(value, dict) else {}

    def update_job_state(self, name: str, updates: dict[str, Any]) -> None:
        state = self.load_state()
        jobs = state.setdefault("jobs", {})
        if not isinstance(jobs, dict):
            jobs = {}
            state["jobs"] = jobs
        current = jobs.get(name)
        if not isinstance(current, dict):
            current = {}
            jobs[name] = current
        current.update(updates)
        self.write_state(state)

    def set_job_paused(self, name: str, paused: bool) -> bool:
        if name not in load_jobs(self.jobs_file):
            return False
        self.update_job_state(name, {"paused": paused})
        return True

    def set_all_jobs_paused(self, paused: bool) -> int:
        names = list(load_jobs(self.jobs_file))
        if not names:
            return 0
        state = self.load_state()
        jobs = state.setdefault("jobs", {})
        if not isinstance(jobs, dict):
            jobs = {}
            state["jobs"] = jobs
        for name in names:
            current = jobs.get(name)
            if not isinstance(current, dict):
                current = {}
                jobs[name] = current
            current["paused"] = paused
        self.write_state(state)
        return len(names)

    def scheduler_state(self) -> dict[str, Any]:
        value = self.load_state().get("scheduler")
        return value if isinstance(value, dict) else {}

    def update_scheduler_state(self, updates: dict[str, Any]) -> None:
        state = self.load_state()
        scheduler = state.setdefault("scheduler", {})
        if not isinstance(scheduler, dict):
            scheduler = {}
            state["scheduler"] = scheduler
        scheduler.update(updates)
        self.write_state(state)

    def restore_backoffs(self) -> None:
        state = self.load_state()
        scheduler = state.get("scheduler")
        if isinstance(scheduler, dict):
            snapshot = scheduler.get("rate_limit_backoff")
            if isinstance(snapshot, dict):
                self.global_backoff.restore(snapshot)
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
                self.backoffs[str(name)] = backoff

    def persist_backoff(self, name: str, backoff: RateLimitBackoff) -> None:
        self.update_job_state(name, {"rate_limit_backoff": backoff.snapshot()})

    def persist_global_backoff(self) -> None:
        self.update_scheduler_state({"rate_limit_backoff": self.global_backoff.snapshot()})

    def record_global_rate_limit(self, exc: RateLimitError) -> float:
        remaining = self.global_backoff.remaining()
        if remaining > 0:
            return remaining
        delay = self.global_backoff.record(float(exc.retry_after))
        self.persist_global_backoff()
        return delay

    def send_gap_remaining(self, now: float) -> float:
        try:
            last_attempt_at = float(self.scheduler_state().get("last_attempt_at") or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, last_attempt_at + _MIN_SEND_GAP_SECONDS - now)

    def ensure_initial_schedules(self, jobs: list[PromptJob], now: float) -> None:
        for job in jobs:
            state = self.job_state(job.name)
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
                self.update_job_state(job.name, {"initial_due_at_epoch": due_at})
                logger.info(
                    "Prompta job=%s one-time send scheduled for %s",
                    job.name,
                    datetime.fromtimestamp(due_at).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
                )
                continue
            if job.daily_at is not None:
                due_at = _next_daily_epoch(job.daily_at, now, include_now=True)
                self.update_job_state(job.name, {"initial_due_at_epoch": due_at})
                logger.info(
                    "Prompta job=%s initial daily send scheduled for %s",
                    job.name,
                    datetime.fromtimestamp(due_at).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
                )
                continue
            window = min(max(0.0, job.interval_seconds), _INITIAL_DELAY_CAP_SECONDS)
            delay = random.uniform(0.0, window) if window > 0 else 0.0
            self.update_job_state(job.name, {"initial_due_at_epoch": now + delay})
            logger.info("Prompta job=%s initial start delayed by %.0fs", job.name, delay)

    @staticmethod
    def next_delay(job: PromptJob) -> float:
        interval = max(0.0, job.interval_seconds)
        if job.exact_interval:
            return interval
        jitter_cap = min(_RECURRING_JITTER_CAP_SECONDS, interval * _RECURRING_JITTER_FRACTION)
        return interval + (random.uniform(0.0, jitter_cap) if jitter_cap > 0 else 0.0)

    def failure_retry_remaining(self, name: str, now: float) -> float:
        state = self.job_state(name)
        try:
            persisted = float(state.get("failure_retry_until_epoch") or 0.0)
        except (TypeError, ValueError):
            persisted = 0.0
        in_memory = self.failure_retry_until.get(name, 0.0)
        return max(0.0, max(persisted, in_memory) - now)

    def mark_failure(self, name: str, message: str, *, retry_until: float | None = None) -> None:
        updates: dict[str, Any] = {
            "status": "failing",
            "status_message": message,
            "status_at": time.time(),
        }
        if retry_until is not None:
            updates["failure_retry_until_epoch"] = retry_until
        self.update_job_state(name, updates)

    def read_jobs(self) -> dict[str, PromptJob]:
        return load_jobs(self.jobs_file)

    def due_in(self, job: PromptJob, now: float | None = None) -> float:
        state = self.job_state(job.name)
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
