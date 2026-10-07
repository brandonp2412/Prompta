from __future__ import annotations

import argparse
import logging
import random
import time
from pathlib import Path

from .delivery_queue import DeliveryQueueStore
from .jobs import PromptJob, remove_job
from .persistence import DEFAULT_RUNTIME_PATH
from .scheduler_policy import (
    occurrence_key,
    pending_delivery_updates,
    receipt_is_pending,
    receipt_is_terminal,
    recurring_jitter_cap,
    scheduled_job_prompt,
    should_enqueue_job,
    terminal_reconciliation_updates,
)
from .scheduler_runtime import SchedulerRuntime
from .service_health import ServiceHealthStore, notify_watchdog
from .strict_types import float_value, string_object_dict

logger = logging.getLogger(__name__)


class DurableSchedulerProducer:
    def __init__(
        self,
        state_path: Path = DEFAULT_RUNTIME_PATH,
        jobs_path: Path = DEFAULT_RUNTIME_PATH,
        queue_path: Path | None = None,
    ) -> None:
        self.state_path = state_path.expanduser()
        self.jobs_path = jobs_path.expanduser()
        self.runtime = SchedulerRuntime(self.state_path, self.jobs_path)
        self.queue = DeliveryQueueStore(
            (queue_path or self.state_path.parent / "ui-send-jobs.sqlite3").expanduser()
        )

    def _occurrence_key(self, job: PromptJob) -> str:
        return occurrence_key(job, self.runtime.job_state(job.name))

    @staticmethod
    def _send_id(idempotency_key: str) -> str:
        return f"scheduled-{idempotency_key}"

    def _pending_receipt(self, job_name: str) -> dict[str, object] | None:
        state = self.runtime.job_state(job_name)
        send_id = str(state.get("last_delivery_send_id") or "")
        if not send_id:
            return None
        receipt = self.queue.get(send_id)
        return receipt if receipt_is_pending(receipt) else None

    def _mutex_group_busy(self, job: PromptJob, jobs: list[PromptJob]) -> bool:
        if not job.mutex_group:
            return False
        return any(
            other.name != job.name
            and other.mutex_group == job.mutex_group
            and self._pending_receipt(other.name) is not None
            for other in jobs
        )

    def _record_pending_metadata(
        self,
        job: PromptJob,
        *,
        send_id: str,
        idempotency_key: str,
        queued_at: float,
    ) -> None:
        self.runtime.update_job_state(
            job.name,
            pending_delivery_updates(
                job,
                send_id=send_id,
                idempotency_key=idempotency_key,
                queued_at=queued_at,
            ),
        )

    def enqueue_if_due(
        self,
        job: PromptJob,
        *,
        now: float,
        jobs: list[PromptJob] | None = None,
    ) -> bool:
        state = self.runtime.job_state(job.name)
        pending_receipt = self._pending_receipt(job.name)
        all_jobs = jobs if jobs is not None else list(self.runtime.read_jobs().values())
        if self._mutex_group_busy(job, all_jobs):
            return False
        if not should_enqueue_job(
            job,
            state,
            now=now,
            pending_delivery=pending_receipt is not None,
        ):
            return False

        idempotency_key = occurrence_key(job, state)
        send_id = self._send_id(idempotency_key)
        receipt, created = self.queue.enqueue_idempotent(
            {
                "send_id": send_id,
                "message": scheduled_job_prompt(job),
                "client_id": f"scheduled:{idempotency_key}:{job.name}",
                "status": "queued",
                "created_at": now,
                "updated_at": now,
            }
        )
        self._record_pending_metadata(
            job,
            send_id=str(receipt["send_id"]),
            idempotency_key=idempotency_key,
            queued_at=float_value(receipt.get("created_at"), default=now),
        )
        if job.run_at_epoch is not None:
            remove_job(self.jobs_path, job.name)
        if created:
            logger.info(
                "Prompta scheduler queued job=%s send_id=%s",
                job.name,
                receipt["send_id"],
            )
        return created

    def _advance_after_terminal(
        self,
        job_name: str,
        state: dict[str, object],
        receipt: dict[str, object],
    ) -> None:
        send_id = str(receipt.get("send_id") or "")
        if str(state.get("last_completed_delivery_send_id") or "") == send_id:
            return

        one_time = bool(state.get("pending_delivery_one_time"))
        daily_at = str(state.get("pending_delivery_daily_at") or "") or None
        try:
            interval_seconds = float_value(state.get("pending_delivery_interval_seconds"))
        except (TypeError, ValueError):
            interval_seconds = 0.0
        exact_interval = bool(state.get("pending_delivery_exact_interval"))
        jitter_seconds = 0.0
        if not one_time and daily_at is None:
            scheduling_job = PromptJob(
                job_name,
                "",
                interval_seconds,
                exact_interval=exact_interval,
            )
            jitter_cap = recurring_jitter_cap(scheduling_job)
            if jitter_cap > 0:
                jitter_seconds = random.uniform(0.0, jitter_cap)

        updates = terminal_reconciliation_updates(
            state,
            receipt,
            fallback_completed_at=time.time(),
            jitter_seconds=jitter_seconds,
        )
        if updates is not None:
            self.runtime.update_job_state(job_name, updates)

    def reconcile_terminal_receipts(self) -> int:
        payload = self.runtime.load_state()
        states = string_object_dict(payload.get("jobs"))
        if states is None:
            return 0

        reconciled = 0
        for job_name, state in states.items():
            state_mapping = string_object_dict(state)
            if state_mapping is None:
                continue
            state = state_mapping
            send_id = str(state.get("last_delivery_send_id") or "")
            if not send_id:
                continue
            receipt = self.queue.get(send_id)
            if receipt is None:
                continue
            if not receipt_is_terminal(receipt):
                continue
            before = str(state.get("last_completed_delivery_send_id") or "")
            self._advance_after_terminal(str(job_name), state, receipt)
            if before != send_id:
                reconciled += 1
        return reconciled

    def tick(self, *, now: float | None = None) -> int:
        current = time.time() if now is None else float(now)
        work = self.reconcile_terminal_receipts()

        jobs = list(self.runtime.read_jobs().values())
        self.runtime.ensure_initial_schedules(jobs, current)
        for job in jobs:
            if self.enqueue_if_due(job, now=current, jobs=jobs):
                work += 1
        return work

    def run_forever(self, *, poll_seconds: float = 1.0) -> None:
        health = ServiceHealthStore(self.runtime.state_path)
        while True:
            did_work = self.tick()
            notify_watchdog()
            health.beat("scheduler")
            time.sleep(0.1 if did_work else max(0.1, poll_seconds))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Prompta durable scheduler producer")
    parser.add_argument("--state", type=Path, default=DEFAULT_RUNTIME_PATH)
    parser.add_argument("--jobs-file", type=Path, default=DEFAULT_RUNTIME_PATH)
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    producer = DurableSchedulerProducer(args.state, args.jobs_file, args.queue)
    if args.once:
        producer.tick()
        return
    try:
        producer.run_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
