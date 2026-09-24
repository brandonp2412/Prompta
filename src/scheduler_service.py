from __future__ import annotations

import argparse
import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from .delivery_queue import DeliveryQueueStore
from .jobs import PromptJob, _next_daily_epoch, remove_job
from .persistence import DEFAULT_RUNTIME_PATH
from .scheduler_runtime import SchedulerRuntime
from .service_health import ServiceHealthStore, notify_watchdog

logger = logging.getLogger(__name__)

_TERMINAL_DELIVERY_STATES = {"succeeded", "dead_lettered", "cancelled"}
_PENDING_DELIVERY_STATES = {"queued", "running", "retrying", "rate_limited"}


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()


def scheduled_job_prompt(job: PromptJob) -> str:
    if not job.source_revision:
        return job.prompt
    return (
        f"{job.prompt}\n\n"
        "Prompta job context: the Prompta source revision when this job was created was "
        f"{job.source_revision}. Use this revision when checking whether a reported bug predates "
        "later code changes."
    )


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
        state = self.runtime.job_state(job.name)
        try:
            last_sent_at = float(state.get("last_sent_at") or 0.0)
            last_uncertain_send_at = float(state.get("last_uncertain_send_at") or 0.0)
        except (TypeError, ValueError):
            last_sent_at = 0.0
            last_uncertain_send_at = 0.0

        keys = (
            ("last_uncertain_send_at",)
            if last_uncertain_send_at > last_sent_at
            else ("next_due_at_epoch", "initial_due_at_epoch", "last_sent_at")
        )
        marker = 0.0
        for key in keys:
            try:
                value = float(state.get(key) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                marker = value
                break
        if job.run_at_epoch is not None:
            marker = float(job.run_at_epoch)

        raw = f"{job.name}\0{prompt_hash(job.prompt)}\0{marker:.6f}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _send_id(idempotency_key: str) -> str:
        return f"scheduled-{idempotency_key}"

    def _pending_receipt(self, job_name: str) -> dict[str, Any] | None:
        state = self.runtime.job_state(job_name)
        send_id = str(state.get("last_delivery_send_id") or "")
        if not send_id:
            return None
        receipt = self.queue.get(send_id)
        if receipt is None:
            return None
        if str(receipt.get("status") or "") in _PENDING_DELIVERY_STATES:
            return receipt
        return None

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
            {
                "last_enqueued_at": queued_at,
                "last_delivery_send_id": send_id,
                "last_delivery_idempotency_key": idempotency_key,
                "pending_delivery_prompt_sha256": prompt_hash(job.prompt),
                "pending_delivery_interval_seconds": float(job.interval_seconds),
                "pending_delivery_daily_at": job.daily_at or "",
                "pending_delivery_exact_interval": bool(job.exact_interval),
                "pending_delivery_one_time": job.run_at_epoch is not None,
                "status": "queued",
                "status_message": "",
                "status_at": queued_at,
            },
        )

    def enqueue_if_due(self, job: PromptJob, *, now: float) -> bool:
        if self.runtime.job_state(job.name).get("paused") is True:
            return False
        if self.runtime.due_in(job, now) > 0:
            return False
        if self._pending_receipt(job.name) is not None:
            return False

        idempotency_key = self._occurrence_key(job)
        send_id = self._send_id(idempotency_key)
        receipt, created = self.queue.enqueue_idempotent(
            {
                "send_id": send_id,
                "operation": "once",
                "message": scheduled_job_prompt(job),
                "conversation_id": "",
                "attachments": [],
                "client_id": f"scheduled:{idempotency_key}",
                "status": "queued",
                "created_at": now,
                "updated_at": now,
            }
        )
        self._record_pending_metadata(
            job,
            send_id=str(receipt["send_id"]),
            idempotency_key=idempotency_key,
            queued_at=float(receipt.get("created_at") or now),
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
        state: dict[str, Any],
        receipt: dict[str, Any],
    ) -> None:
        send_id = str(receipt["send_id"])
        if str(state.get("last_completed_delivery_send_id") or "") == send_id:
            return

        completed_at = float(
            receipt.get("finished_at")
            or receipt.get("updated_at")
            or receipt.get("created_at")
            or time.time()
        )
        one_time = bool(state.get("pending_delivery_one_time"))
        daily_at = str(state.get("pending_delivery_daily_at") or "") or None
        try:
            interval_seconds = float(state.get("pending_delivery_interval_seconds") or 0.0)
        except (TypeError, ValueError):
            interval_seconds = 0.0
        exact_interval = bool(state.get("pending_delivery_exact_interval"))
        status = str(receipt.get("status") or "")

        next_due_at = 0.0
        if not one_time:
            if daily_at is not None:
                next_due_at = _next_daily_epoch(daily_at, completed_at)
            else:
                next_due_at = completed_at + self.runtime.next_delay(
                    PromptJob(
                        job_name,
                        "",
                        interval_seconds,
                        exact_interval=exact_interval,
                    )
                )

        updates: dict[str, Any] = {
            "initial_due_at_epoch": 0.0,
            "next_due_at_epoch": next_due_at,
            "last_completed_delivery_send_id": send_id,
            "status_at": completed_at,
        }
        if status == "succeeded":
            updates.update(
                {
                    "prompt_sha256": str(state.get("pending_delivery_prompt_sha256") or ""),
                    "last_sent_at": completed_at,
                    "last_uncertain_send_at": 0.0,
                    "last_conversation_id": str(receipt.get("conversation_id") or ""),
                    "failure_retry_until_epoch": 0.0,
                    "status": "healthy",
                    "status_message": "",
                }
            )
        else:
            updates.update(
                {
                    "status": "failing",
                    "status_message": str(
                        receipt.get("last_error") or receipt.get("error") or status
                    ),
                }
            )
        self.runtime.update_job_state(job_name, updates)

    def reconcile_terminal_receipts(self) -> int:
        payload = self.runtime.load_state()
        states = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(states, dict):
            return 0

        reconciled = 0
        for job_name, state in states.items():
            if not isinstance(state, dict):
                continue
            send_id = str(state.get("last_delivery_send_id") or "")
            if not send_id:
                continue
            receipt = self.queue.get(send_id)
            if receipt is None:
                continue
            if str(receipt.get("status") or "") not in _TERMINAL_DELIVERY_STATES:
                continue
            before = str(state.get("last_completed_delivery_send_id") or "")
            self._advance_after_terminal(str(job_name), state, receipt)
            if before != send_id:
                reconciled += 1
        return reconciled

    def migrate_legacy_pending_intents(self) -> int:
        migrated = 0
        for intent in self.runtime.delivery_intents():
            if str(intent.get("status") or "") != "queued":
                continue
            idempotency_key = str(intent["idempotency_key"])
            send_id = self._send_id(idempotency_key)
            receipt, created = self.queue.enqueue_idempotent(
                {
                    "send_id": send_id,
                    "operation": "once",
                    "message": str(intent["prompt"]),
                    "conversation_id": "",
                    "attachments": [],
                    "client_id": f"scheduled:{idempotency_key}",
                    "status": "queued",
                    "created_at": float(intent.get("queued_at") or time.time()),
                    "updated_at": float(intent.get("queued_at") or time.time()),
                }
            )
            if str(receipt.get("status") or "") in _TERMINAL_DELIVERY_STATES:
                continue
            self.runtime.update_job_state(
                str(intent["job_name"]),
                {
                    "last_delivery_send_id": str(receipt["send_id"]),
                    "last_delivery_idempotency_key": idempotency_key,
                    "pending_delivery_prompt_sha256": str(intent["job_prompt_sha256"]),
                    "pending_delivery_interval_seconds": float(intent["interval_seconds"]),
                    "pending_delivery_daily_at": str(intent.get("daily_at") or ""),
                    "pending_delivery_exact_interval": bool(intent["exact_interval"]),
                    "pending_delivery_one_time": bool(intent["one_time"]),
                    "last_enqueued_at": float(intent.get("queued_at") or time.time()),
                    "status": "queued",
                    "status_message": "",
                },
            )
            if created:
                migrated += 1
        if migrated:
            logger.info("Migrated %d legacy scheduled delivery intent(s)", migrated)
        return migrated

    def tick(self, *, now: float | None = None) -> int:
        current = time.time() if now is None else float(now)
        work = self.migrate_legacy_pending_intents()
        work += self.reconcile_terminal_receipts()

        jobs = list(self.runtime.read_jobs().values())
        self.runtime.ensure_initial_schedules(jobs, current)
        for job in jobs:
            if self.enqueue_if_due(job, now=current):
                work += 1
        return work

    def run_forever(self, *, poll_seconds: float = 1.0) -> None:
        health = ServiceHealthStore(self.runtime.state_path)
        while True:
            did_work = self.tick()
            health.beat("scheduler")
            notify_watchdog()
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
