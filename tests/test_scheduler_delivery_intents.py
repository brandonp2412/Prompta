from __future__ import annotations

from pathlib import Path

import pytest

from prompta.jobs import add_job, load_jobs
from prompta.scheduler_service import DurableSchedulerProducer


def test_scheduler_restart_with_worker_stopped_records_one_pending_delivery(tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    add_job(
        runtime_path,
        "one-time",
        "Run exactly once",
        0,
        exact_interval=True,
        run_at_epoch=1000.0,
    )

    first = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    assert first.tick(now=1000.0) == 1

    rows = first.queue.records()
    assert len(rows) == 1
    assert rows[0]["status"] == "queued"
    assert rows[0]["message"] == "Run exactly once"
    assert "one-time" not in load_jobs(runtime_path)

    restarted = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    assert restarted.tick(now=1001.0) == 0

    rows = restarted.queue.records()
    assert len(rows) == 1
    assert rows[0]["status"] == "queued"
    send_id = rows[0]["send_id"]
    assert isinstance(send_id, str)
    assert send_id.startswith("scheduled-")


def test_scheduler_reconciles_worker_success_and_advances_recurring_job(tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    add_job(
        runtime_path,
        "recurring",
        "Keep going",
        60,
        exact_interval=True,
    )
    producer = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    producer.runtime.update_job_state("recurring", {"initial_due_at_epoch": 1000.0})

    job = load_jobs(runtime_path)["recurring"]
    assert producer.enqueue_if_due(job, now=1000.0) is True

    claimed = producer.queue.claim_next("test-worker", now=1001.0, lease_seconds=30.0)
    assert claimed is not None
    send_id = claimed["send_id"]
    assert isinstance(send_id, str)
    assert producer.queue.complete_claim(
        send_id,
        "test-worker",
        now=1005.0,
    )

    restarted = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    assert restarted.reconcile_terminal_receipts() == 1

    state = restarted.runtime.job_state("recurring")
    assert state["last_sent_at"] == pytest.approx(1005.0)
    assert state["next_due_at_epoch"] == pytest.approx(1065.0)
    assert "last_conversation_id" not in state
    assert state["status"] == "healthy"

    assert restarted.tick(now=1006.0) == 0
    assert len(restarted.queue.records()) == 1


def test_scheduler_serializes_due_jobs_in_same_mutex_group(tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    for name in ("first", "second"):
        add_job(
            runtime_path,
            name,
            f"Run {name}",
            60,
            exact_interval=True,
            mutex_group="ibkr-refactor",
        )

    producer = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    for name in ("first", "second"):
        producer.runtime.update_job_state(name, {"initial_due_at_epoch": 1000.0})

    assert producer.tick(now=1000.0) == 1
    records = producer.queue.records()
    assert len(records) == 1
    assert records[0]["message"] == "Run first"

    claimed = producer.queue.claim_next("test-worker", now=1001.0, lease_seconds=30.0)
    assert claimed is not None
    send_id = claimed["send_id"]
    assert isinstance(send_id, str)
    assert producer.queue.complete_claim(
        send_id,
        "test-worker",
        now=1005.0,
    )

    assert producer.tick(now=1005.0) == 2
    records = producer.queue.records()
    assert len(records) == 2
    assert records[1]["message"] == "Run second"
