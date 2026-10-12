from __future__ import annotations

import fcntl
from pathlib import Path

import pytest

from prompta.jobs import add_job, load_jobs
from prompta.manual_fire import fire_job_now
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


def test_scheduler_defers_due_job_while_external_mutex_is_locked(tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    add_job(
        runtime_path,
        "sloppa",
        "Run playback soak",
        60,
        exact_interval=True,
        mutex_group="sloppatv-remux-e2e",
    )
    producer = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    producer.runtime.update_job_state("sloppa", {"initial_due_at_epoch": 1000.0})

    lock_path = tmp_path / "sloppatv-remux-e2e.lock"
    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert producer.tick(now=1000.0) == 0
        assert producer.queue.records() == []
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    assert producer.tick(now=1001.0) == 1
    records = producer.queue.records()
    assert len(records) == 1
    assert records[0]["message"] == "Run playback soak"


def test_scheduler_ignores_missing_external_mutex_file(tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    add_job(
        runtime_path,
        "plain",
        "Run plain job",
        60,
        exact_interval=True,
        mutex_group="no-external-lock",
    )
    producer = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    producer.runtime.update_job_state("plain", {"initial_due_at_epoch": 1000.0})

    assert producer.tick(now=1000.0) == 1


def test_manual_fire_deadline_survives_late_scheduled_receipt_reconciliation(tmp_path: Path) -> None:
    state = tmp_path / "runtime.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    add_job(state, "recurring", "Do work", 600, exact_interval=True)
    producer = DurableSchedulerProducer(state, state, queue_path)
    producer.runtime.update_job_state("recurring", {"initial_due_at_epoch": 1000.0})
    assert producer.tick(now=1000.0) == 1
    scheduled = producer.queue.claim_next("worker", now=1001.0, lease_seconds=90.0)
    assert scheduled is not None
    assert producer.queue.complete_claim(str(scheduled["send_id"]), "worker", now=1050.0)

    fire_job_now(
        load_jobs(state)["recurring"],
        runtime=producer.runtime,
        queue=producer.queue,
        now=1100.0,
    )
    assert producer.tick(now=1100.0) == 1
    assert producer.runtime.job_state("recurring")["next_due_at_epoch"] == 1700.0
    assert producer.tick(now=1699.0) == 0
    assert producer.tick(now=1700.0) == 1


def test_manual_fire_deadline_survives_uncertain_scheduled_attempt(tmp_path: Path) -> None:
    from prompta.scheduler_policy import due_in

    state = tmp_path / "runtime.sqlite3"
    add_job(state, "recurring", "Do work", 600, exact_interval=True)
    producer = DurableSchedulerProducer(state, state)
    producer.runtime.update_job_state(
        "recurring",
        {"last_sent_at": 100.0, "last_uncertain_send_at": 105.0},
    )
    fire_job_now(
        load_jobs(state)["recurring"],
        runtime=producer.runtime,
        queue=producer.queue,
        now=1100.0,
    )
    job = load_jobs(state)["recurring"]
    assert due_in(job, producer.runtime.job_state("recurring"), now=1699.0) == 1.0
    assert due_in(job, producer.runtime.job_state("recurring"), now=1700.0) == 0.0


def test_manual_fire_replaces_queued_scheduled_send(tmp_path: Path) -> None:
    state = tmp_path / "runtime.sqlite3"
    add_job(state, "recurring", "Do work", 600, exact_interval=True)
    producer = DurableSchedulerProducer(state, state)
    producer.runtime.update_job_state("recurring", {"initial_due_at_epoch": 1000.0})
    assert producer.tick(now=1000.0) == 1
    scheduled_id = str(producer.queue.records()[0]["send_id"])

    fire_job_now(
        load_jobs(state)["recurring"],
        runtime=producer.runtime,
        queue=producer.queue,
        now=1100.0,
    )
    cancelled = producer.queue.get(scheduled_id)
    assert cancelled is not None and cancelled["status"] == "cancelled"
    state_after = producer.runtime.job_state("recurring")
    assert state_after["last_completed_delivery_send_id"] == scheduled_id
    assert state_after["next_due_at_epoch"] == 1700.0
    assert producer.tick(now=1100.0) == 0
    assert producer.tick(now=1699.0) == 0
    assert producer.tick(now=1700.0) == 1
