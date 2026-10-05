from datetime import time
from pathlib import Path
from typing import cast

from prompta.config import WorkingHours
from prompta.delivery_browser import BrowserDeliverySender
from prompta.delivery_queue import DeliveryQueueStore
from prompta.delivery_worker import DeliveryAdmission, _deliver_one
from prompta.scheduler_runtime import SchedulerRuntime
from prompta.service_health import ServiceHealthStore


def test_delivery_admission_blocks_outside_working_hours(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = SchedulerRuntime(tmp_path / "state.sqlite3", tmp_path / "jobs.sqlite3")
    working_hours = WorkingHours(
        enabled=True,
        start=time(22, 30),
        end=time(8, 0),
        timezone="Pacific/Auckland",
    )
    midday = 1791154800.0
    monkeypatch.setattr("prompta.delivery_worker.time.time", lambda: midday)

    admission = DeliveryAdmission(
        runtime,
        resource_admission=lambda: (True, ""),
        working_hours=working_hours,
    )

    allowed, reason, retry_after = admission()

    assert allowed is False
    assert "Outside Prompta working hours" in reason
    assert retry_after > 0

def test_delivery_admission_reloads_working_hours_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = SchedulerRuntime(tmp_path / "state.sqlite3", tmp_path / "jobs.sqlite3")
    midday = 1791154800.0
    current_hours = [
        WorkingHours(
            enabled=True,
            start=time(22, 30),
            end=time(8, 0),
            timezone="Pacific/Auckland",
        )
    ]
    monkeypatch.setattr("prompta.delivery_worker.time.time", lambda: midday)
    monkeypatch.setattr(
        WorkingHours,
        "load",
        classmethod(lambda cls: current_hours[0]),
    )
    admission = DeliveryAdmission(
        runtime,
        resource_admission=lambda: (True, ""),
    )

    assert admission()[0] is False

    current_hours[0] = WorkingHours()

    assert admission() == (True, "", 0.0)


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
