from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .jobs import add_job, load_jobs


def schedule_job_name(prompt: str) -> str:
    words = re.findall(r"[a-z0-9]+", prompt.casefold())[:6]
    slug = "-".join(words) or "job"
    digest = hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()[:6]
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
                    "paused": paused,
                    "status": status,
                    "next_due_at_epoch": next_due_at,
                }
            )
        return {"jobs": jobs, "server": self.server_name}

    def run_cli(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        action = action.strip().lower()
        command = [sys.executable, "-m", "prompta.core"]

        if action == "add":
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
                if (
                    not isinstance(raw_interval_minutes, (str, int, float))
                    or isinstance(raw_interval_minutes, bool)
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
            command += ["--jobs-file", str(self.jobs_path)]
        elif action in {"remove", "pause", "resume"}:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("Job name is required")
            command += [action, name, "--jobs-file", str(self.jobs_path)]
            if action in {"pause", "resume"}:
                command += ["--state", str(self.state_path)]
        elif action == "clear":
            command += ["clear", "--jobs-file", str(self.jobs_path)]
        else:
            raise ValueError(f"Unsupported jobs command: {action}")

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

        if action in {"add", "resume"}:
            self.start_scheduler()
        display = ["prompta", *command[3:]]
        return {
            "ok": True,
            "command": display,
            **self.scheduled_jobs(),
        }

    def schedule_every(self, prompt: str, interval_minutes: float) -> dict[str, Any]:
        interval_minutes = float(interval_minutes)
        if not math.isfinite(interval_minutes):
            raise ValueError("Schedule interval must be finite")
        interval_minutes = max(0.1, min(interval_minutes, 60.0 * 24.0 * 30.0))
        name = schedule_job_name(prompt)
        interval_seconds = interval_minutes * 60.0
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
