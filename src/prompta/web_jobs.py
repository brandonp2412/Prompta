from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .jobs import _normalise_max_reprompts, add_job, clear_jobs, load_jobs, remove_job
from .scheduler_runtime import SchedulerRuntime


def schedule_job_name(prompt: str, interval_minutes: float) -> str:
    normalised_prompt = re.sub(r"\s+", " ", prompt).strip()
    words = re.findall(r"[a-z0-9]+", normalised_prompt.casefold())[:6]
    slug = "-".join(words) or "job"
    interval_seconds = float(interval_minutes) * 60.0
    identity = f"{normalised_prompt.casefold()}\0{interval_seconds:.9g}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"ui-{slug[:36]}-{digest}"


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
        try:
            state_payload = json.loads(self.state_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            state_payload = {}
        state_jobs = state_payload.get("jobs") if isinstance(state_payload, dict) else {}
        if not isinstance(state_jobs, dict):
            state_jobs = {}

        jobs = []
        for job in load_jobs(self.jobs_path).values():
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
            jobs.append(
                {
                    "name": job.name,
                    "prompt": job.prompt,
                    "interval_minutes": job.interval_seconds / 60.0,
                    "daily_at": job.daily_at,
                    "run_at_epoch": job.run_at_epoch,
                    "exact_interval": job.exact_interval,
                    "max_reprompts": job.max_reprompts,
                    "paused": paused,
                    "status": status,
                    "next_due_at_epoch": next_due_at,
                }
            )
        return {"jobs": jobs, "server": self.server_name}

    def run_cli(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        action = action.strip().lower()
        display = ["prompta", action]
        runtime = SchedulerRuntime(self.state_path, self.jobs_path)
        affected_jobs: int | None = None
        shown_job: dict[str, Any] | None = None

        if action in {"add", "replace"}:
            name = str(payload.get("name") or "").strip()
            prompt = str(payload.get("prompt") or "").strip()
            if not name:
                raise ValueError("Job name is required")
            if not prompt:
                raise ValueError("Job prompt is required")
            display += [name, prompt]
            try:
                max_reprompts = _normalise_max_reprompts(payload.get("max_reprompts"))
            except ValueError as exc:
                raise ValueError("Max reprompts must be a non-negative integer") from exc
            if max_reprompts:
                display += ["--max-reprompts", str(max_reprompts)]
            daily_at = str(payload.get("daily_at") or "").strip()
            if daily_at:
                if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", daily_at):
                    raise ValueError("Daily time must use HH:MM")
                add_job(
                    self.jobs_path,
                    name,
                    prompt,
                    daily_at=daily_at,
                    max_reprompts=max_reprompts,
                )
                display += ["--daily-at", daily_at]
            else:
                raw_interval_minutes = payload.get("interval_minutes")
                exact_interval = payload.get("exact_interval") is True
                if raw_interval_minutes is None:
                    add_job(
                        self.jobs_path,
                        name,
                        prompt,
                        exact_interval=exact_interval,
                        max_reprompts=max_reprompts,
                    )
                else:
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
                    add_job(
                        self.jobs_path,
                        name,
                        prompt,
                        interval_minutes * 60.0,
                        exact_interval=exact_interval,
                        max_reprompts=max_reprompts,
                    )
                    display += ["--interval-minutes", str(interval_minutes)]
                if exact_interval:
                    display.append("--exact-interval")
            display += ["--jobs-file", str(self.jobs_path)]
        elif action == "remove":
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("Job name is required")
            remove_job(self.jobs_path, name)
            display += [name, "--jobs-file", str(self.jobs_path)]
        elif action == "pause":
            name = str(payload.get("name") or "").strip()
            if name:
                if not runtime.set_job_paused(name, True):
                    raise ValueError(f"No Prompta job named {name!r}")
                affected_jobs = 1
                display.append(name)
            else:
                affected_jobs = runtime.set_all_jobs_paused(True)
            display += ["--jobs-file", str(self.jobs_path), "--state", str(self.state_path)]
        elif action == "resume":
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("Job name is required")
            if not runtime.set_job_paused(name, False):
                raise ValueError(f"No Prompta job named {name!r}")
            affected_jobs = 1
            display += [
                name,
                "--jobs-file",
                str(self.jobs_path),
                "--state",
                str(self.state_path),
            ]
        elif action == "clear":
            affected_jobs = clear_jobs(self.jobs_path)
            display += ["--jobs-file", str(self.jobs_path)]
        elif action in {"show", "list"}:
            jobs = self.scheduled_jobs()
            if action == "show":
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ValueError("Job name is required")
                shown_job = next((job for job in jobs["jobs"] if job["name"] == name), None)
                if shown_job is None:
                    raise ValueError(f"No Prompta job named {name!r}")
                display += [
                    name,
                    "--jobs-file",
                    str(self.jobs_path),
                    "--state",
                    str(self.state_path),
                ]
            else:
                display += [
                    "--jobs-file",
                    str(self.jobs_path),
                    "--state",
                    str(self.state_path),
                ]
            return {
                "ok": True,
                "command": display,
                **({"job": shown_job} if shown_job is not None else {}),
                **jobs,
            }
        else:
            raise ValueError(f"Unsupported jobs command: {action}")

        if action in {"add", "replace", "resume"}:
            self.start_scheduler()
        return {
            "ok": True,
            "command": display,
            **({"affected_jobs": affected_jobs} if affected_jobs is not None else {}),
            **self.scheduled_jobs(),
        }

    def schedule_every(self, prompt: str, interval_minutes: float) -> dict[str, Any]:
        prompt = re.sub(r"\s+", " ", prompt).strip()
        if not prompt:
            raise ValueError("Schedule prompt is required")
        interval_minutes = float(interval_minutes)
        if not math.isfinite(interval_minutes) or interval_minutes <= 0:
            raise ValueError("Schedule interval must be a finite value greater than zero")
        if interval_minutes < 0.1:
            raise ValueError("Schedule interval must be at least 6 seconds")
        if interval_minutes > 60.0 * 24.0 * 30.0:
            raise ValueError("Schedule interval cannot exceed 30 days")

        interval_seconds = interval_minutes * 60.0
        prompt_identity = prompt.casefold()
        for existing in load_jobs(self.jobs_path).values():
            existing_prompt = re.sub(r"\s+", " ", existing.prompt).strip().casefold()
            if (
                existing_prompt == prompt_identity
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
                scheduler_started = self.start_scheduler()
                return {
                    "name": existing.name,
                    "prompt": existing.prompt,
                    "interval_minutes": existing.interval_seconds / 60.0,
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
            "scheduler_started": scheduler_started,
            "server": self.server_name,
            "created": True,
        }

    def schedule_at(self, prompt: str, run_at_epoch: float) -> dict[str, Any]:
        run_at_epoch = float(run_at_epoch)
        if not math.isfinite(run_at_epoch) or run_at_epoch <= time.time():
            raise ValueError("Schedule time must be a finite timestamp in the future")
        name = f"at-{int(run_at_epoch)}-{hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:10]}"
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
            "scheduler_started": scheduler_started,
            "server": self.server_name,
        }
