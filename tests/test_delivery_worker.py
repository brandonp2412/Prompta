from pathlib import Path
from typing import cast

from prompta.delivery_browser import BrowserDeliverySender
from prompta.delivery_queue import DeliveryQueueStore
from prompta.delivery_worker import _deliver_one
from prompta.scheduler_runtime import SchedulerRuntime
from prompta.service_health import ServiceHealthStore


def test_removed_job_is_cancelled_before_browser_dispatch(tmp_path: Path) -> None:
    state = tmp_path / "scheduler.sqlite3"
    jobs = tmp_path / "jobs.sqlite3"
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    queue.upsert(
        {
            "send_id": "scheduled-send",
            "message": "Run the audit",
            "client_id": "scheduled:idempotency-key:audit",
            "status": "queued",
            "created_at": 10.0,
        }
    )
    record = queue.claim_next("worker", now=20.0, lease_seconds=30.0)
    assert record is not None

    calls: list[str] = []

    def sender(message: str) -> None:
        calls.append(message)

    _deliver_one(
        queue,
        cast(BrowserDeliverySender, sender),
        SchedulerRuntime(state, jobs),
        ServiceHealthStore(tmp_path / "health.sqlite3"),
        "worker",
        record,
    )

    assert calls == []
    cancelled = queue.get("scheduled-send")
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
