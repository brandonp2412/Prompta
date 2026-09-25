from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from prompta.jobs import PromptJob, add_job, load_jobs
from prompta.scheduler_runtime import SchedulerRuntime
from prompta.scheduler_service import DurableSchedulerProducer


def _occurrence_hash(job: PromptJob, marker: float) -> str:
    raw = f"{job.name}\0{hashlib.sha256(job.prompt.encode()).hexdigest()}\0{marker:.6f}"
    return hashlib.sha256(raw.encode()).hexdigest()


def test_initial_interval_schedule_persists_sampled_delay_across_restart(tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    jobs = [
        PromptJob("one", "first", 1800),
        PromptJob("two", "second", 7200),
    ]
    runtime = SchedulerRuntime(runtime_path, runtime_path)

    with patch("prompta.scheduler_runtime.random.uniform", side_effect=[120.0, 900.0]):
        runtime.ensure_initial_schedules(jobs, 1000.0)

    assert runtime.due_in(jobs[0], 1000.0) == pytest.approx(120.0)
    assert runtime.due_in(jobs[1], 1000.0) == pytest.approx(900.0)

    restarted = SchedulerRuntime(runtime_path, runtime_path)
    with patch("prompta.scheduler_runtime.random.uniform") as random_uniform:
        restarted.ensure_initial_schedules(jobs, 1100.0)

    random_uniform.assert_not_called()
    assert restarted.due_in(jobs[0], 1100.0) == pytest.approx(20.0)
    assert restarted.due_in(jobs[1], 1100.0) == pytest.approx(800.0)


def test_recurring_delay_preserves_exact_interval_and_capped_jitter() -> None:
    exact = PromptJob("exact", "run", 1800, exact_interval=True)
    jittered = PromptJob("jittered", "run", 1800)

    with patch("prompta.scheduler_runtime.random.uniform", return_value=240.0) as uniform:
        assert SchedulerRuntime.next_delay(exact) == pytest.approx(1800.0)
        assert SchedulerRuntime.next_delay(jittered) == pytest.approx(2040.0)

    uniform.assert_called_once_with(0.0, 300.0)


def test_due_in_uses_uncertain_send_as_duplicate_protection_marker(tmp_path: Path) -> None:
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "runtime.sqlite3")
    job = PromptJob("job", "work", 1800)
    runtime.update_job_state(
        job.name,
        {
            "last_sent_at": 900.0,
            "last_uncertain_send_at": 1000.0,
            "next_due_at_epoch": 5000.0,
        },
    )

    assert runtime.due_in(job, 1300.0) == pytest.approx(1500.0)


def test_occurrence_key_prefers_uncertain_send_marker_and_one_time_epoch(tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    producer = DurableSchedulerProducer(runtime_path, runtime_path, tmp_path / "queue.sqlite3")
    job = PromptJob("job", "work", 1800)
    producer.runtime.update_job_state(
        job.name,
        {
            "last_sent_at": 900.0,
            "last_uncertain_send_at": 1000.0,
            "next_due_at_epoch": 5000.0,
        },
    )

    assert producer._occurrence_key(job) == _occurrence_hash(job, 1000.0)

    one_time = PromptJob("once", "work once", 0, exact_interval=True, run_at_epoch=2345.0)
    producer.runtime.update_job_state(one_time.name, {"initial_due_at_epoch": 9999.0})
    assert producer._occurrence_key(one_time) == _occurrence_hash(one_time, 2345.0)


def test_terminal_failure_advances_exact_recurring_schedule_once(tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    queue_path = tmp_path / "queue.sqlite3"
    add_job(runtime_path, "recurring", "Keep going", 60, exact_interval=True)
    producer = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    producer.runtime.update_job_state("recurring", {"initial_due_at_epoch": 1000.0})

    job = load_jobs(runtime_path)["recurring"]
    assert producer.enqueue_if_due(job, now=1000.0)

    receipt = producer.queue.records()[0]
    receipt.update(
        {
            "status": "outcome_unknown",
            "error": "permanent failure",
            "last_error": "permanent failure",
            "finished_at": 1005.0,
            "updated_at": 1005.0,
        }
    )
    producer.queue.upsert(receipt)

    assert producer.reconcile_terminal_receipts() == 1
    state = producer.runtime.job_state("recurring")
    assert state["next_due_at_epoch"] == pytest.approx(1065.0)
    assert state["status"] == "failing"
    assert state["status_message"] == "permanent failure"

    assert producer.reconcile_terminal_receipts() == 0
    assert producer.runtime.job_state("recurring")["next_due_at_epoch"] == pytest.approx(1065.0)
