from __future__ import annotations

import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from .delivery_queue import DeliveryQueueStore
from .jobs import PromptJob, add_job, clear_jobs, load_jobs, remove_job
from .scheduler_runtime import SchedulerRuntime
from .strict_types import float_value, string_object_dict


class ScheduledJobsPayload(TypedDict):
    jobs: list[dict[str, object]]
    server: str


class WebJobActionResult(ScheduledJobsPayload):
    ok: bool


def _validated_interval_minutes(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("Interval minutes must be a number")
    try:
        minutes = float(value)
    except ValueError as exc:
        raise ValueError("Interval minutes must be a number") from exc
    if not math.isfinite(minutes) or minutes < 0.1:
        raise ValueError("Interval minutes must be at least 0.1")
    if minutes > 60.0 * 24.0 * 30.0:
        raise ValueError("Interval minutes cannot exceed 30 days")
    return minutes


def serialize_scheduled_jobs(
    jobs: list[PromptJob],
    state_jobs: dict[str, object],
) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for job in jobs:
        raw_state = state_jobs.get(job.name)
        job_state = raw_state if isinstance(raw_state, dict) else {}
        paused = job_state.get("paused") is True
        status = "paused" if paused else str(job_state.get("status") or "pending")
        if status not in {"paused", "pending", "queued", "healthy", "failing", "rate-limited"}:
            status = "pending"

        def state_float(key: str) -> float:
            try:
                return float_value(job_state.get(key))
            except (TypeError, ValueError):
                return 0.0

        serialized.append(
            {
                "name": job.name,
                "prompt": job.prompt,
                "interval_minutes": job.interval_seconds / 60.0,
                "daily_at": job.daily_at,
                "run_at_epoch": job.run_at_epoch,
                "exact_interval": job.exact_interval,
                "mutex_group": job.mutex_group,
                "source_revision": job.source_revision,
                "paused": paused,
                "status": status,
                "status_message": str(job_state.get("status_message") or ""),
                "next_due_at_epoch": state_float("next_due_at_epoch")
                or state_float("initial_due_at_epoch"),
                "last_sent_at": state_float("last_sent_at"),
            }
        )
    return serialized


class WebJobService:
    def __init__(
        self,
        jobs_path: Path,
        state_path: Path,
        server_name: str,
        start_scheduler: Callable[[], bool] | None = None,
    ) -> None:
        self.jobs_path = jobs_path.expanduser()
        self.state_path = state_path.expanduser()
        self.server_name = server_name
        self.start_scheduler = start_scheduler

    @property
    def runtime(self) -> SchedulerRuntime:
        return SchedulerRuntime(self.state_path, self.jobs_path)

    def _cancel_pending_delivery(self, name: str, *, error: str) -> bool:
        state = self.runtime.job_state(name)
        send_id = str(state.get("last_delivery_send_id") or "")
        if not send_id:
            return False
        queue = DeliveryQueueStore(self.state_path.parent / "ui-send-jobs.sqlite3")
        return queue.cancel_pending(send_id, error=error)

    def scheduled_jobs(self) -> ScheduledJobsPayload:
        state_payload = self.runtime.load_state()
        state_jobs = string_object_dict(state_payload.get("jobs")) or {}
        jobs = serialize_scheduled_jobs(list(load_jobs(self.jobs_path).values()), state_jobs)
        return {"jobs": jobs, "server": self.server_name}

    def _wake_scheduler(self) -> None:
        if self.start_scheduler is not None:
            self.start_scheduler()

    def apply(self, action: str, payload: dict[str, object]) -> WebJobActionResult:
        normalized_action = action.strip().lower()
        runtime = self.runtime

        if normalized_action == "add":
            name = str(payload.get("name") or "").strip()
            prompt = str(payload.get("prompt") or "").strip()
            if not name:
                raise ValueError("Job name is required")
            if not prompt:
                raise ValueError("Job prompt is required")

            existing = load_jobs(self.jobs_path).get(name)
            mutex_group = str(
                payload.get("mutex_group")
                if "mutex_group" in payload
                else (existing.mutex_group if existing is not None else "")
            ).strip()
            daily_at = str(payload.get("daily_at") or "").strip() or None
            if daily_at is not None:
                if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", daily_at) is None:
                    raise ValueError("Daily time must use HH:MM")
                interval_seconds = 0.0
                exact_interval = False
            else:
                minutes = _validated_interval_minutes(payload.get("interval_minutes"))
                interval_seconds = minutes * 60.0
                exact_interval = payload.get("exact_interval") is True

            add_job(
                self.jobs_path,
                name,
                prompt,
                interval_seconds,
                daily_at=daily_at,
                exact_interval=exact_interval,
                mutex_group=mutex_group,
            )
            runtime.clear_job_state(name)
            self._wake_scheduler()

        elif normalized_action == "remove":
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("Job name is required")
            remove_job(self.jobs_path, name)
            self._cancel_pending_delivery(name, error="scheduled job removed")
            runtime.clear_job_state(name)

        elif normalized_action in {"pause", "resume"}:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("Job name is required")
            if not runtime.set_job_paused(name, normalized_action == "pause"):
                raise ValueError("Unknown job: " + name)
            if normalized_action == "resume":
                self._wake_scheduler()

        elif normalized_action in {"pause_all", "resume_all"}:
            runtime.set_all_jobs_paused(normalized_action == "pause_all")
            if normalized_action == "resume_all":
                self._wake_scheduler()

        elif normalized_action == "clear":
            names = list(load_jobs(self.jobs_path))
            clear_jobs(self.jobs_path)
            for name in names:
                self._cancel_pending_delivery(name, error="scheduled job cleared")
            runtime.clear_all_job_state()

        else:
            raise ValueError("Unsupported jobs action: " + normalized_action)

        scheduled = self.scheduled_jobs()
        return {"ok": True, "jobs": scheduled["jobs"], "server": scheduled["server"]}
