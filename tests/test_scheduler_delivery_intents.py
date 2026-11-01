from __future__ import annotations

import fcntl
from pathlib import Path

import pytest

from prompta.config import StageConcurrencySettings
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


def test_manual_fire_deadline_survives_late_scheduled_receipt_reconciliation(
    tmp_path: Path,
) -> None:
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


def _stage_config(tmp_path: Path, *, max_workers: int = 3) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        f"[stage_concurrency]\nenabled = true\nmax_workers = {max_workers}\n",
        encoding="utf-8",
    )
    return path


def _due_producer(tmp_path: Path, *, due: float, count: int) -> DurableSchedulerProducer:
    state = tmp_path / "runtime.sqlite3"
    for index in range(count):
        if index % 2 == 0:
            add_job(state, f"once-{index}", "One-time job", 0, run_at_epoch=due)
        else:
            add_job(state, f"recurring-{index}", "Recurring job", 60, exact_interval=True)
    producer = DurableSchedulerProducer(
        state, state, concurrency_config_path=_stage_config(tmp_path)
    )
    for index in range(count):
        if index % 2:
            producer.runtime.update_job_state(
                f"recurring-{index}", {"initial_due_at_epoch": due}
            )
    return producer


def _accept_and_finish_delivery(
    producer: DurableSchedulerProducer, *, now: float, deadline: float,
    max_active: int | None = None,
) -> tuple[str, str]:
    claimed = producer.queue.claim_next(
        "test-worker", now=now, lease_seconds=30.0, max_active=max_active
    )
    assert claimed is not None
    send_id = str(claimed["send_id"])
    job_name = str(claimed["client_id"]).rsplit(":", 1)[-1]
    producer.queue.results.ensure_queued(send_id, str(claimed["message"]), job_name, now=now)
    assert producer.queue.results.accept(send_id, "test-owner", deadline=deadline, now=now)
    assert producer.queue.complete_claim(send_id, "test-worker", now=now + 0.1)
    return send_id, job_name


def test_once_and_recurring_jobs_enter_same_durable_queue(tmp_path: Path) -> None:
    due = 1000.0
    producer = _due_producer(tmp_path, due=due, count=5)
    assert producer.tick(now=due) == 5
    assert len(producer.queue.records()) == 5
    assert len(load_jobs(producer.jobs_path)) == 2  # once definitions removed
    assert producer.queue.pending_scheduled_deliveries() == [
        "once-0", "once-2", "once-4", "recurring-1", "recurring-3"
    ]
    # The queue remains durable across scheduler restarts.
    fresh = DurableSchedulerProducer(
        producer.state_path, producer.jobs_path, producer.queue.path,
        producer.concurrency_config_path
    )
    assert fresh.concurrency_queue_snapshot(now=due + 1)["waiting"] == (
        producer.concurrency_queue_snapshot(now=due + 1)["waiting"]
    )


def test_global_cap_counts_running_and_capturing_once_and_recurring_jobs(
    tmp_path: Path,
) -> None:
    due = 1000.0
    producer = _due_producer(tmp_path, due=due, count=5)
    producer.tick(now=due)
    first, _ = _accept_and_finish_delivery(
        producer, now=due + 1, deadline=due + 7200, max_active=2
    )
    second, _ = _accept_and_finish_delivery(
        producer, now=due + 2, deadline=due + 7200, max_active=2
    )
    assert producer.queue.claim_next(
        "worker", now=due + 3, lease_seconds=30, max_active=2
    ) is None
    assert producer.queue.results.active_capture_send_ids(now=due + 3) == {
        first, second
    }
    assert producer.queue.results.finish(first, "test-owner", "interrupted", now=due + 4)
    third = producer.queue.claim_next(
        "worker", now=due + 5, lease_seconds=30, max_active=2
    )
    assert third is not None
    assert str(third["client_id"]).endswith(":once-4")


def test_global_cap_applies_to_direct_one_off_chat_and_scheduled_job(
    tmp_path: Path,
) -> None:
    producer = _due_producer(tmp_path, due=1000, count=1)
    producer.tick(now=1000)
    manual = producer.queue.enqueue_manual("A manually requested one-off", now=1000)
    # Manually requested one-offs take priority, but use the same capacity.
    claim = producer.queue.claim_next("worker", now=1001, lease_seconds=30, max_active=1)
    assert claim is not None and claim["send_id"] == manual["send_id"]
    assert producer.queue.claim_next(
        "other", now=1002, lease_seconds=30, max_active=1
    ) is None
    manual_id = str(claim["send_id"])
    producer.queue.results.ensure_queued(manual_id, "A manually requested one-off", "", now=1001)
    assert producer.queue.results.accept(
        manual_id, "owner", deadline=5000, now=1001
    )
    assert producer.queue.complete_claim(manual_id, "worker", now=1001.5)
    assert producer.queue.claim_next(
        "other", now=1002, lease_seconds=30, max_active=1
    ) is None
    assert producer.queue.results.finish(manual_id, "owner", "interrupted", now=1003)
    assert producer.queue.claim_next(
        "other", now=1004, lease_seconds=30, max_active=1
    ) is not None


def test_stage_concurrency_hot_reloads_without_worker_restart(tmp_path: Path) -> None:
    producer = _due_producer(tmp_path, due=1000, count=5)
    assert producer.tick(now=1000) == 5
    config = producer.concurrency_config_path
    assert producer._current_concurrency_settings().active_limit == 3
    for index in range(3):
        assert producer.queue.claim_next(
            f"worker-{index}", now=1001, lease_seconds=30, max_active=3
        ) is not None
    assert producer.queue.claim_next(
        "worker-4", now=1001, lease_seconds=30, max_active=3
    ) is None
    _stage_config(tmp_path, max_workers=4)
    assert producer._current_concurrency_settings().active_limit == 4
    assert producer.queue.claim_next(
        "worker-4", now=1001, lease_seconds=30,
        max_active=StageConcurrencySettings.load(config).active_limit
    ) is not None
    _stage_config(tmp_path, max_workers=1)
    assert producer._current_concurrency_settings().active_limit == 1
    assert producer.queue.claim_next(
        "worker-5", now=1002, lease_seconds=30,
        max_active=StageConcurrencySettings.load(config).active_limit
    ) is None


def test_disabled_global_cap_allows_all_due_jobs(tmp_path: Path) -> None:
    state = tmp_path / "runtime.sqlite3"
    for index in range(4):
        add_job(state, f"independent-{index}", "Independent job", 0, run_at_epoch=1000)
    producer = DurableSchedulerProducer(
        state, state, concurrency_config_path=tmp_path / "missing.toml"
    )
    assert producer._current_concurrency_settings().active_limit is None
    assert producer.tick(now=1000) == 4
    for index in range(4):
        assert producer.queue.claim_next(
            f"worker-{index}", now=1001, lease_seconds=30,
            max_active=producer._current_concurrency_settings().active_limit
        ) is not None


def test_queued_chat_eta_uses_actual_manual_dispatch_priority(tmp_path: Path) -> None:
    producer = _due_producer(tmp_path, due=1000, count=2)
    _stage_config(tmp_path, max_workers=1)
    assert producer.tick(now=1000) == 2
    manual = producer.queue.enqueue_manual("Queued user request", now=1001, request_id="a" * 32)

    snapshot = producer.concurrency_queue_snapshot(now=1002)
    assert snapshot["waiting_runs"] == [
        {"send_id": manual["send_id"], "eta_seconds": 0},
        *[
            {"send_id": receipt["send_id"], "eta_seconds": index * 600}
            for index, receipt in enumerate(producer.queue.records(), start=1)
            if str(receipt["send_id"]).startswith("scheduled-")
        ],
    ]
    assert [row["eta_seconds"] for row in snapshot["waiting"]] == [600, 1200]


def test_concurrency_queue_snapshot_includes_all_due_job_types(tmp_path: Path) -> None:
    producer = _due_producer(tmp_path, due=1000, count=3)
    _stage_config(tmp_path, max_workers=2)
    assert producer.tick(now=1000) == 3
    assert producer.concurrency_queue_snapshot(now=1001) == {
        "max_workers": 2,
        "occupied_slots": 0,
        "estimated_run_seconds": 600,
        "estimate_samples": 0,
        "waiting_runs": [
            {"send_id": receipt["send_id"], "eta_seconds": (index // 2) * 600}
            for index, receipt in enumerate(producer.queue.records())
        ],
        "waiting": [
            {
                "name": name,
                "position": position,
                "reason": "global",
                "occupied": 0,
                "limit": 2,
                "eta_seconds": eta,
            }
            for position, (name, eta) in enumerate(
                [("once-0", 0), ("once-2", 0), ("recurring-1", 600)],
                start=1,
            )
        ],
    }
    first, _ = _accept_and_finish_delivery(
        producer, now=1001, deadline=5000, max_active=2
    )
    second, _ = _accept_and_finish_delivery(
        producer, now=1002, deadline=5000, max_active=2
    )
    snap = producer.concurrency_queue_snapshot(now=1003)
    assert snap["occupied_slots"] == 2
    assert snap["waiting"] == [
        {
            "name": "recurring-1",
            "position": 1,
            "reason": "global",
            "occupied": 2,
            "limit": 2,
            "eta_seconds": 598,
        }
    ]
    assert producer.queue.results.finish(first, "test-owner", "interrupted", now=1004)
    assert producer.queue.results.finish(second, "test-owner", "interrupted", now=1004)
    assert producer.concurrency_queue_snapshot(now=1005)["occupied_slots"] == 0
