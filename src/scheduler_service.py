from __future__ import annotations

import argparse
import fcntl
import logging
import random
import time
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, ParallelismSettings, StageConcurrencySettings
from .delivery_queue import DeliveryQueueStore
from .jobs import PromptJob, remove_job
from .persistence import DEFAULT_RUNTIME_PATH
from .queue_eta import QueueEtaEstimator
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
        concurrency_config_path: Path = DEFAULT_CONFIG_PATH,
    ) -> None:
        self.state_path = state_path.expanduser()
        self.jobs_path = jobs_path.expanduser()
        self.runtime = SchedulerRuntime(self.state_path, self.jobs_path)
        self.queue = DeliveryQueueStore(
            (queue_path or self.state_path.parent / "ui-send-jobs.sqlite3").expanduser()
        )
        self.concurrency_config_path = concurrency_config_path.expanduser()
        self._concurrency_signature: tuple[int, int, int] | None = None
        self._concurrency_settings: StageConcurrencySettings | None = None
        self._parallelism_signature: tuple[int, int, int] | None = None
        self._parallelism_settings: ParallelismSettings | None = None

    def _current_concurrency_settings(self) -> StageConcurrencySettings:
        """Reload only on file replacement/change; invalid files never disable the cap."""
        try:
            stat = self.concurrency_config_path.stat()
            signature = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            signature = None
        if self._concurrency_settings is None or signature != self._concurrency_signature:
            settings = StageConcurrencySettings.load(self.concurrency_config_path)
            self._concurrency_settings = settings
            self._concurrency_signature = signature
        return self._concurrency_settings

    def _current_parallelism_settings(self) -> ParallelismSettings:
        """Hot-reload the global limit, failing closed if configuration is invalid."""
        try:
            stat = self.concurrency_config_path.stat()
            signature = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            signature = None
        if self._parallelism_settings is None or signature != self._parallelism_signature:
            settings = ParallelismSettings.load(self.concurrency_config_path)
            self._parallelism_settings = settings
            self._parallelism_signature = signature
        return self._parallelism_settings

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

    def _mutex_group_busy(self, job: PromptJob, jobs: list[PromptJob], *, now: float) -> bool:
        global_limit = self._current_parallelism_settings().max_workers
        if global_limit is not None:
            active = self.queue.pending_scheduled_send_ids()
            active.update(self.queue.results.active_capture_send_ids(now=now))
            if len(active) >= global_limit:
                return True

        settings = self._current_concurrency_settings()
        if settings.enabled and job.name.startswith(settings.job_prefixes):
            # One-shot definitions vanish on enqueue, but their active response
            # captures still occupy the configured group's concurrency slots.
            active = self.queue.pending_scheduled_send_ids(settings.job_prefixes)
            active.update(
                self.queue.results.active_capture_send_ids(settings.job_prefixes, now=now)
            )
            limit = settings.limit_at(now)
            assert limit is not None
            return len(active) >= limit
        if not job.mutex_group:
            return False
        return any(
            other.name != job.name
            and other.mutex_group == job.mutex_group
            and self._pending_receipt(other.name) is not None
            for other in jobs
        )

    def concurrency_queue_snapshot(self, *, now: float | None = None) -> dict[str, object]:
        """Read-only view of due chats waiting behind global or stage worker limits.

        The scheduler deliberately does not enqueue these until capacity frees.
        Do not create fake result rows or advance a job's occurrence marker.
        """
        at = time.time() if now is None else float(now)
        limit = self._current_parallelism_settings().max_workers
        active = self.queue.pending_scheduled_send_ids()
        active.update(self.queue.results.active_capture_send_ids(now=at))
        global_full = limit is not None and len(active) >= limit

        stage = self._current_concurrency_settings()
        stage_limit = stage.limit_at(at) if stage.enabled else None
        stage_active: set[str] = set()
        if stage_limit is not None:
            stage_active = self.queue.pending_scheduled_send_ids(stage.job_prefixes)
            stage_active.update(
                self.queue.results.active_capture_send_ids(stage.job_prefixes, now=at)
            )
        stage_full = stage_limit is not None and len(stage_active) >= stage_limit
        if not global_full and not stage_full:
            return {
                "max_workers": limit,
                "occupied_slots": len(active),
                "estimated_run_seconds": 600,
                "estimate_samples": 0,
                "waiting": [],
            }

        estimator = QueueEtaEstimator(self.queue, now=at, active_ids=active)
        global_projection = (
            estimator.projection(limit, active) if global_full and limit is not None else None
        )
        stage_projection = (
            estimator.projection(stage_limit, stage_active)
            if stage_full and stage_limit is not None
            else None
        )
        waiting: list[dict[str, object]] = []
        if global_full or stage_full:
            raw_states = self.runtime.load_state().get("jobs")
            states = string_object_dict(raw_states) or {}
            # Preserve tick()'s job iteration order when numbering waiters.
            for job in self.runtime.read_jobs().values():
                is_stage = stage_full and job.name.startswith(stage.job_prefixes)
                if not global_full and not is_stage:
                    continue
                raw_state = states.get(job.name)
                state = string_object_dict(raw_state) or {}
                send_id = str(state.get("last_delivery_send_id") or "")
                receipt = self.queue.get(send_id) if send_id else None
                if not should_enqueue_job(
                    job, state, now=at, pending_delivery=receipt_is_pending(receipt)
                ):
                    continue
                if self._external_mutex_group_busy(job):
                    continue
                if global_full:
                    assert limit is not None
                    reason, occupied, capacity = "global", len(active), limit
                else:
                    assert stage_limit is not None
                    reason, occupied, capacity = "stage", len(stage_active), stage_limit
                global_eta = global_projection.enqueue() if global_projection else 0
                stage_eta = stage_projection.enqueue() if is_stage and stage_projection else 0
                waiting.append(
                    {
                        "name": job.name,
                        "position": len(waiting) + 1,
                        "reason": reason,
                        "occupied": occupied,
                        "limit": capacity,
                        "eta_seconds": max(global_eta, stage_eta),
                    }
                )
        return {
            "max_workers": limit,
            "occupied_slots": len(active),
            "estimated_run_seconds": estimator.duration_seconds,
            "estimate_samples": estimator.samples,
            "waiting": waiting,
        }

    def _external_mutex_group_busy(self, job: PromptJob) -> bool:
        if not job.mutex_group:
            return False
        lock_path = self.state_path.parent / f"{job.mutex_group}.lock"
        if not lock_path.exists():
            return False
        with lock_path.open("a+") as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return False

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
        if self._mutex_group_busy(job, all_jobs, now=now) or self._external_mutex_group_busy(job):
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
                "images": job.images,
                "client_id": f"scheduled:{idempotency_key}:{job.name}",
                "pin_chat": job.pin_chat,
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
