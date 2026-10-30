from __future__ import annotations

import time

from .delivery_queue import DeliveryQueueStore
from .jobs import PromptJob
from .scheduler_runtime import SchedulerRuntime


def fire_job_now(
    job: PromptJob,
    *,
    runtime: SchedulerRuntime,
    queue: DeliveryQueueStore,
    now: float | None = None,
    pin_chat: bool | None = None,
    request_id: str | None = None,
) -> dict[str, object]:
    """Queue a fresh chat and restart an interval job's countdown."""
    fired_at = time.time() if now is None else float(now)
    receipt = queue.enqueue_manual(
        job.prompt,
        now=fired_at,
        pin_chat=job.pin_chat if pin_chat is None else pin_chat,
        images=job.images,
        request_id=request_id,
    )
    if job.interval_seconds > 0 and job.daily_at is None and job.run_at_epoch is None:
        updates: dict[str, object] = {
            "initial_due_at_epoch": 0.0,
            "next_due_at_epoch": fired_at + job.interval_seconds,
            "last_manual_fire_at_epoch": fired_at,
        }
        scheduled_send_id = str(runtime.job_state(job.name).get("last_delivery_send_id") or "")
        if scheduled_send_id and queue.cancel_pending(
            scheduled_send_id, error="superseded by manual fire", now=fired_at
        ):
            updates.update(
                {
                    "last_completed_delivery_send_id": scheduled_send_id,
                    "status": "pending",
                    "status_message": "",
                }
            )
        runtime.update_job_state(job.name, updates)
    return receipt
