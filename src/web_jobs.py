from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from .delivery_queue import DeliveryQueueStore
from .image_store import ImageStore, image_refs
from .jobs import PromptJob, add_job, clear_jobs, load_jobs, remove_job
from .manual_fire import fire_job_now
from .scheduler_runtime import SchedulerRuntime
from .strict_types import float_value, string_object_dict
from .web_models import (
    JOB_ACTION,
    AddJob,
    AllJobAction,
    JobAction,
    ManyJobAction,
    NamedJobAction,
    RunOnce,
)


class ScheduledJobsPayload(TypedDict):
    jobs: list[dict[str, object]]
    server: str


class WebJobActionResult(ScheduledJobsPayload):
    ok: bool


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
                "created_order": job.created_order,
                "prompt": job.prompt,
                "images": [
                    {"ref": ref, "name": ref.split("/", 1)[1], "url": "./api/images/" + ref}
                    for ref in job.images
                ],
                "interval_minutes": job.interval_seconds / 60.0,
                "daily_at": job.daily_at,
                "run_at_epoch": job.run_at_epoch,
                "pin_chat": job.pin_chat,
                "exact_interval": job.exact_interval,
                "mutex_group": job.mutex_group,
                "source_revision": job.source_revision,
                "paused": paused,
                "status": status,
                "status_message": str(job_state.get("status_message") or ""),
                "next_due_at_epoch": state_float("next_due_at_epoch")
                or state_float("initial_due_at_epoch"),
                "last_sent_at": state_float("last_sent_at"),
                "last_uncertain_send_at": state_float("last_uncertain_send_at"),
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
        self.images = ImageStore(self.state_path.parent)
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
        command = JOB_ACTION.validate_python({**payload, "action": action.strip().lower()})
        return self.execute(command)

    def execute(self, command: JobAction) -> WebJobActionResult:
        runtime = self.runtime
        if isinstance(command, AddJob):
            name, prompt = command.name, command.prompt
            existing = load_jobs(self.jobs_path).get(name)
            if "images" in command.model_fields_set:
                images = image_refs(command.images)
            else:
                images = existing.images if existing else ()
            for ref in images:
                self.images.path(ref)
            if "mutex_group" in command.model_fields_set:
                mutex_group = command.mutex_group.strip()
            else:
                mutex_group = existing.mutex_group if existing else ""
            once = command.schedule == "once"
            pin_chat = False
            if once:
                if "pin_chat" in command.model_fields_set:
                    pin_chat = command.pin_chat
                elif existing:
                    pin_chat = existing.pin_chat
            daily_at = command.daily_at or None
            if once:
                daily_at, interval_seconds, exact_interval = None, 0.0, False
                if "delay_minutes" in command.model_fields_set:
                    run_at_epoch = time.time() + command.delay_minutes * 60
                else:
                    run_at_epoch = (
                        existing.run_at_epoch
                        if existing is not None and existing.run_at_epoch is not None
                        else time.time()
                    )
            elif daily_at is not None:
                interval_seconds, exact_interval, run_at_epoch = 0.0, False, None
            else:
                assert command.interval_minutes is not None
                interval_seconds = command.interval_minutes * 60.0
                exact_interval, run_at_epoch = command.exact_interval, None
            add_job(
                self.jobs_path,
                name,
                prompt,
                interval_seconds,
                daily_at=daily_at,
                exact_interval=exact_interval,
                run_at_epoch=run_at_epoch,
                pin_chat=pin_chat,
                mutex_group=mutex_group,
                images=images,
            )
            if existing is None:
                runtime.clear_job_state(name)
            elif (
                existing.interval_seconds != interval_seconds
                or existing.daily_at != daily_at
                or existing.run_at_epoch != run_at_epoch
                or existing.exact_interval != exact_interval
            ):
                # Preserve dispatch history; a cadence edit rebases from the last send.
                runtime.update_job_state(
                    name, {"next_due_at_epoch": 0.0, "initial_due_at_epoch": 0.0}
                )
            self._wake_scheduler()

        elif isinstance(command, RunOnce):
            images = image_refs(command.images)
            for ref in images:
                self.images.path(ref)
            if command.delay_minutes == 0:
                DeliveryQueueStore(self.state_path.parent / "ui-send-jobs.sqlite3").enqueue_manual(
                    command.prompt,
                    images=images,
                    pin_chat=command.pin_chat,
                    request_id=command.request_id,
                )
            else:
                run_at_epoch = time.time() + command.delay_minutes * 60
                label = datetime.fromtimestamp(run_at_epoch).strftime("%d %b %H:%M")
                name = f"Once {label} {uuid.uuid4().hex[:8]}"
                add_job(
                    self.jobs_path,
                    name,
                    command.prompt,
                    0,
                    run_at_epoch=run_at_epoch,
                    images=images,
                    pin_chat=command.pin_chat,
                )
                runtime.clear_job_state(name)
                self._wake_scheduler()

        elif isinstance(command, NamedJobAction):
            name = command.name
            if command.action == "fire_now":
                job = load_jobs(self.jobs_path).get(name)
                if job is None:
                    raise ValueError("Unknown job: " + name)
                request_id = command.request_id
                queue = DeliveryQueueStore(self.state_path.parent / "ui-send-jobs.sqlite3")
                existing_delivery = queue.get("manual-" + request_id) if request_id else None
                if existing_delivery is not None:
                    client_id = f"manual:{'once:' if job.pin_chat else ''}{request_id}"
                    if (
                        existing_delivery["client_id"] != client_id
                        or existing_delivery["message"] != job.prompt
                        or image_refs(existing_delivery["images"]) != job.images
                    ):
                        raise ValueError(
                            "Manual queue identifier belongs to a different job payload"
                        )
                else:
                    fire_job_now(job, runtime=runtime, queue=queue, request_id=request_id)
            elif command.action == "remove":
                remove_job(self.jobs_path, name)
                self._cancel_pending_delivery(name, error="scheduled job removed")
                runtime.clear_job_state(name)
            else:
                if not runtime.set_job_paused(name, command.action == "pause"):
                    raise ValueError("Unknown job: " + name)
                if command.action == "resume":
                    self._wake_scheduler()

        elif isinstance(command, ManyJobAction):
            runtime.set_jobs_paused(command.names, command.action == "pause_many")
            if command.action == "resume_many":
                self._wake_scheduler()

        elif isinstance(command, AllJobAction):
            if command.action == "clear":
                names = list(load_jobs(self.jobs_path))
                clear_jobs(self.jobs_path)
                for name in names:
                    self._cancel_pending_delivery(name, error="scheduled job cleared")
                runtime.clear_all_job_state()
            else:
                runtime.set_all_jobs_paused(command.action == "pause_all")
                if command.action == "resume_all":
                    self._wake_scheduler()

        return {"ok": True, **self.scheduled_jobs()}
