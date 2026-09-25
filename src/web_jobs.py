from __future__ import annotations

import hashlib
import math
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .jobs import PromptJob, add_job, load_jobs
from .scheduler_runtime import SchedulerRuntime


def schedule_job_name(prompt: str, interval_minutes: float) -> str:
    normalised_prompt = re.sub(r"\s+", " ", prompt).strip()
    words = re.findall(r"[a-z0-9]+", normalised_prompt.casefold())[:6]
    slug = "-".join(words) or "job"
    interval_seconds = float(interval_minutes) * 60.0
    identity = f"{normalised_prompt.casefold()}\0{interval_seconds:.9g}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"ui-{slug[:36]}-{digest}"


def normalize_schedule_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt).strip()


def validate_schedule_interval(interval_minutes: float) -> float:
    value = float(interval_minutes)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Schedule interval must be a finite value greater than zero")
    if value < 0.1:
        raise ValueError("Schedule interval must be at least 6 seconds")
    if value > 60.0 * 24.0 * 30.0:
        raise ValueError("Schedule interval cannot exceed 30 days")
    return value


def matching_exact_interval_job(
    jobs: list[PromptJob],
    *,
    prompt: str,
    interval_seconds: float,
) -> PromptJob | None:
    prompt_identity = normalize_schedule_prompt(prompt).casefold()
    for existing in jobs:
        if (
            normalize_schedule_prompt(existing.prompt).casefold() == prompt_identity
            and existing.daily_at is None
            and existing.run_at_epoch is None
            and existing.exact_interval
            and math.isclose(
                existing.interval_seconds,
                interval_seconds,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
        ):
            return existing
    return None


def schedule_at_job_name(prompt: str, run_at_epoch: float) -> str:
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:10]
    return f"at-{int(run_at_epoch)}-{digest}"


def validate_schedule_time(run_at_epoch: float, *, now: float) -> float:
    value = float(run_at_epoch)
    if not math.isfinite(value) or value <= now:
        raise ValueError("Schedule time must be a finite timestamp in the future")
    return value


def serialize_scheduled_jobs(
    jobs: list[PromptJob],
    state_jobs: dict[str, Any],
) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for job in jobs:
        job_state = state_jobs.get(job.name)
        if not isinstance(job_state, dict):
            job_state = {}
        paused = job_state.get("paused") is True
        status = "paused" if paused else str(job_state.get("status") or "pending")
        if status not in {"paused", "pending", "healthy", "failing", "rate-limited"}:
            status = "pending"
        try:
            next_due_at = float(job_state.get("next_due_at_epoch") or 0.0)
        except (TypeError, ValueError):
            next_due_at = 0.0
        serialized.append(
            {
                "name": job.name,
                "prompt": job.prompt,
                "interval_minutes": job.interval_seconds / 60.0,
                "daily_at": job.daily_at,
                "run_at_epoch": job.run_at_epoch,
                "exact_interval": job.exact_interval,
                "source_revision": job.source_revision,
                "paused": paused,
                "status": status,
                "next_due_at_epoch": next_due_at,
            }
        )
    return serialized


def build_job_cli_command(
    action: str,
    payload: dict[str, Any],
    *,
    jobs_path: Path,
    state_path: Path,
) -> tuple[str, list[str], bool]:
    normalized_action = action.strip().lower()
    command = [sys.executable, "-m", "prompta.core"]

    if normalized_action == "add":
        name = str(payload.get("name") or "").strip()
        prompt = str(payload.get("prompt") or "").strip()
        if not name:
            raise ValueError("Job name is required")
        if not prompt:
            raise ValueError("Job prompt is required")
        command += ["add", name, prompt]
        daily_at = str(payload.get("daily_at") or "").strip()
        if daily_at:
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", daily_at):
                raise ValueError("Daily time must use HH:MM")
            command += ["--daily-at", daily_at]
        else:
            raw_interval_minutes = payload.get("interval_minutes")
            if not isinstance(raw_interval_minutes, (str, int, float)) or isinstance(
                raw_interval_minutes, bool
            ):
                raise ValueError("Interval minutes must be a number")
            try:
                interval_minutes = float(raw_interval_minutes)
            except ValueError as exc:
                raise ValueError("Interval minutes must be a number") from exc
            if not math.isfinite(interval_minutes) or interval_minutes <= 0:
                raise ValueError("Interval minutes must be greater than zero")
            command += ["--interval-minutes", str(interval_minutes)]
            if payload.get("exact_interval") is True:
                command.append("--exact-interval")
        command += ["--jobs-file", str(jobs_path)]
    elif normalized_action in {"remove", "pause", "resume"}:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Job name is required")
        command += [normalized_action, name, "--jobs-file", str(jobs_path)]
        if normalized_action in {"pause", "resume"}:
            command += ["--state", str(state_path)]
    elif normalized_action == "clear":
        command += ["clear", "--jobs-file", str(jobs_path)]
    else:
        raise ValueError(f"Unsupported jobs command: {normalized_action}")

    return normalized_action, command, normalized_action in {"add", "resume"}


class WebJobService:
    def __init__(
        self,
        jobs_path: Path,
        state_path: Path,
        server_name: str,
        start_scheduler: Callable[[], bool],
    ) -> None:
        self.jobs_path = jobs_path
        self.state_path = state_path
        self.server_name = server_name
        self.start_scheduler = start_scheduler

    def scheduled_jobs(self) -> dict[str, Any]:
        state_payload = SchedulerRuntime(self.state_path, self.jobs_path).load_state()
        state_jobs = state_payload.get("jobs") if isinstance(state_payload, dict) else {}
        if not isinstance(state_jobs, dict):
            state_jobs = {}

        jobs = serialize_scheduled_jobs(list(load_jobs(self.jobs_path).values()), state_jobs)
        return {"jobs": jobs, "server": self.server_name}

    def run_cli(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        action, command, should_start_scheduler = build_job_cli_command(
            action,
            payload,
            jobs_path=self.jobs_path,
            state_path=self.state_path,
        )

        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(detail or f"prompta {action} failed")

        if should_start_scheduler:
            self.start_scheduler()
        display = ["prompta", *command[3:]]
        return {
            "ok": True,
            "command": display,
            **self.scheduled_jobs(),
        }

    def schedule_every(self, prompt: str, interval_minutes: float) -> dict[str, Any]:
        prompt = normalize_schedule_prompt(prompt)
        if not prompt:
            raise ValueError("Schedule prompt is required")
        interval_minutes = validate_schedule_interval(interval_minutes)
        interval_seconds = interval_minutes * 60.0
        existing = matching_exact_interval_job(
            list(load_jobs(self.jobs_path).values()),
            prompt=prompt,
            interval_seconds=interval_seconds,
        )
        if existing is not None:
            scheduler_started = self.start_scheduler()
            return {
                "name": existing.name,
                "prompt": existing.prompt,
                "interval_minutes": existing.interval_seconds / 60.0,
                "source_revision": existing.source_revision,
                "scheduler_started": scheduler_started,
                "server": self.server_name,
                "created": False,
            }

        name = schedule_job_name(prompt, interval_minutes)
        add_job(
            self.jobs_path,
            name,
            prompt,
            interval_seconds,
            exact_interval=True,
        )
        scheduler_started = self.start_scheduler()
        return {
            "name": name,
            "prompt": prompt,
            "interval_minutes": interval_minutes,
            "source_revision": load_jobs(self.jobs_path)[name].source_revision,
            "scheduler_started": scheduler_started,
            "server": self.server_name,
            "created": True,
        }

    def schedule_at(self, prompt: str, run_at_epoch: float) -> dict[str, Any]:
        run_at_epoch = validate_schedule_time(run_at_epoch, now=time.time())
        name = schedule_at_job_name(prompt, run_at_epoch)
        add_job(
            self.jobs_path,
            name,
            prompt,
            0.0,
            exact_interval=True,
            run_at_epoch=run_at_epoch,
        )
        scheduler_started = self.start_scheduler()
        return {
            "name": name,
            "prompt": prompt,
            "run_at_epoch": run_at_epoch,
            "source_revision": load_jobs(self.jobs_path)[name].source_revision,
            "scheduler_started": scheduler_started,
            "server": self.server_name,
        }
