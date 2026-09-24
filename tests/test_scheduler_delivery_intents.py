from __future__ import annotations

from pathlib import Path

import pytest

from prompta.jobs import PromptJob, add_job, load_jobs
from prompta.scheduler_runtime import SchedulerRuntime
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
    assert rows[0]["message"].startswith("Run exactly once\n\nPrompta job context:")
    assert "one-time" not in load_jobs(runtime_path)

    restarted = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    assert restarted.tick(now=1001.0) == 0

    rows = restarted.queue.records()
    assert len(rows) == 1
    assert rows[0]["status"] == "queued"
    assert rows[0]["send_id"].startswith("scheduled-")


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
    assert producer.queue.complete_claim(
        claimed["send_id"],
        "test-worker",
        conversation_id="conversation-1",
        now=1005.0,
    )

    restarted = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    assert restarted.reconcile_terminal_receipts() == 1

    state = restarted.runtime.job_state("recurring")
    assert state["last_sent_at"] == pytest.approx(1005.0)
    assert state["next_due_at_epoch"] == pytest.approx(1065.0)
    assert state["last_conversation_id"] == "conversation-1"
    assert state["status"] == "healthy"

    assert restarted.tick(now=1006.0) == 0
    assert len(restarted.queue.records()) == 1


def test_legacy_pending_intent_is_migrated_to_shared_delivery_queue(tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    runtime = SchedulerRuntime(runtime_path, runtime_path)
    job = PromptJob("legacy", "Legacy scheduled work", 1800, exact_interval=True)

    intent_id, created = runtime.enqueue_delivery_intent(
        job,
        prompt=job.prompt,
        job_prompt_sha256="hash",
        idempotency_key="legacy-key",
        queued_at=1000.0,
    )
    assert created is True
    assert intent_id > 0

    producer = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    assert producer.migrate_legacy_pending_intents() == 1
    assert producer.migrate_legacy_pending_intents() == 0

    rows = producer.queue.records()
    assert len(rows) == 1
    assert rows[0]["send_id"] == "scheduled-legacy-key"
    assert rows[0]["message"] == "Legacy scheduled work"
