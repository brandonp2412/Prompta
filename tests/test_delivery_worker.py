import sqlite3
from datetime import time
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from prompta.config import WorkingHours
from prompta.delivery_queue import DeliveryQueueStore
from prompta.delivery_worker import DeliveryAdmission, _deliver_one, _sqlite_busy
from prompta.jobs import add_job, load_jobs
from prompta.scheduler_runtime import SchedulerRuntime
from prompta.scheduler_service import DurableSchedulerProducer
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


def test_delivery_admission_ignores_previous_claim_and_dispatch(tmp_path: Path, monkeypatch) -> None:
    runtime = SchedulerRuntime(tmp_path / "state.sqlite3", tmp_path / "jobs.sqlite3")
    admission = DeliveryAdmission(runtime, resource_admission=lambda: (True, ""))
    now = 10_000.0
    runtime.update_scheduler_state({"last_delivery_claim_at": now, "last_attempt_at": now})
    monkeypatch.setattr("prompta.delivery_worker.time.time", lambda: now)

    assert admission(manual=True) == (True, "", 0.0)
    monkeypatch.setattr("prompta.delivery_worker.time.time", lambda: now + 1)
    assert admission(manual=True) == (True, "", 0.0)


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


def test_future_queued_delivery_waits_for_its_slot(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "queue.sqlite3")
    queue.upsert(
        {
            "send_id": "later",
            "message": "Later",
            "client_id": "scheduled:key:later",
            "status": "queued",
            "created_at": 100.0,
            "retry_at": 500.0,
        }
    )
    assert queue.claim_next("worker", now=499.0, lease_seconds=30.0) is None
    record = queue.claim_next("worker", now=500.0, lease_seconds=30.0)
    assert record is not None and record["send_id"] == "later"


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

    def sender(message: str, *, pin_chat: bool = False) -> None:
        assert not pin_chat
        calls.append(message)

    _deliver_one(
        queue,
        sender,
        SchedulerRuntime(state, jobs),
        ServiceHealthStore(tmp_path / "health.sqlite3"),
        "worker",
        record,
    )

    assert calls == []
    cancelled = queue.get("scheduled-send")
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"


@pytest.mark.parametrize("pin_chat", [False, True])
def test_queued_once_job_survives_scheduled_job_removal_and_respects_pin_choice(
    tmp_path: Path, pin_chat: bool
) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    add_job(runtime_path, "one-time", "Only once", 0, run_at_epoch=1000.0, pin_chat=pin_chat)
    producer = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    assert producer.tick(now=1000.0) == 1
    assert "one-time" not in load_jobs(runtime_path)
    record = producer.queue.claim_next("worker", now=1001.0, lease_seconds=30.0)
    assert record is not None
    calls: list[tuple[str, bool]] = []

    def sender(message: str, *, pin_chat: bool = False) -> None:
        calls.append((message, pin_chat))

    _deliver_one(
        producer.queue,
        sender,
        producer.runtime,
        ServiceHealthStore(tmp_path / "health.sqlite3"),
        "worker",
        record,
    )
    assert calls == [("Only once", pin_chat)]
    receipt = producer.queue.get(str(record["send_id"]))
    assert receipt is not None and receipt["status"] == "succeeded"


@pytest.mark.parametrize("pin_chat", [False, True])
def test_manual_once_job_respects_pin_choice(tmp_path: Path, pin_chat: bool) -> None:
    from prompta.manual_fire import fire_job_now

    state = tmp_path / "runtime.sqlite3"
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    runtime = SchedulerRuntime(state, state)
    add_job(state, "once", "Fire me", 0, run_at_epoch=2000.0, pin_chat=pin_chat)
    fire_job_now(load_jobs(state)["once"], runtime=runtime, queue=queue, now=1000.0)
    record = queue.claim_next("worker", now=1001.0, lease_seconds=30.0)
    assert record is not None
    calls: list[tuple[str, bool]] = []

    def sender(message: str, *, pin_chat: bool = False) -> None:
        calls.append((message, pin_chat))

    _deliver_one(
        queue, sender, runtime, ServiceHealthStore(tmp_path / "health.sqlite3"), "worker", record
    )
    assert calls == [("Fire me", pin_chat)]


def test_manual_delivery_bypasses_working_hours_but_keeps_other_limits(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = SchedulerRuntime(tmp_path / "state.sqlite3", tmp_path / "jobs.sqlite3")
    hours = WorkingHours(enabled=True, start=time(22, 30), end=time(8), timezone="Pacific/Auckland")
    monkeypatch.setattr("prompta.delivery_worker.time.time", lambda: 1791154800.0)
    admission = DeliveryAdmission(
        runtime, resource_admission=lambda: (True, ""), working_hours=hours
    )
    assert admission()[0] is False
    assert admission(manual=True) == (True, "", 0.0)
    blocked = DeliveryAdmission(
        runtime, resource_admission=lambda: (False, "busy"), working_hours=hours
    )
    assert blocked(manual=True) == (False, "busy", 0.0)


def test_manual_queued_prompt_uses_standard_delivery_path(tmp_path: Path) -> None:
    state = tmp_path / "scheduler.sqlite3"
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    receipt = queue.enqueue_manual("Deliver one chat", now=10.0)
    claimed = queue.claim_next("worker", now=20.0, lease_seconds=30.0)
    assert claimed is not None
    messages: list[str] = []

    def sender(message: str, *, pin_chat: bool = False) -> None:
        assert not pin_chat
        messages.append(message)

    _deliver_one(
        queue,
        sender,
        SchedulerRuntime(state, state),
        ServiceHealthStore(tmp_path / "health.sqlite3"),
        "worker",
        claimed,
    )
    assert messages == ["Deliver one chat"]
    finished = queue.get(str(receipt["send_id"]))
    assert finished is not None and finished["status"] == "succeeded"


def _locked_error(message: str = "database is locked") -> OperationalError:
    return OperationalError("INSERT INTO account_state ...", (), sqlite3.OperationalError(message))


def test_admission_defers_sends_when_resource_state_write_is_locked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = SchedulerRuntime(tmp_path / "state.sqlite3", tmp_path / "jobs.sqlite3")
    admission = DeliveryAdmission(runtime, resource_admission=lambda: (True, ""))
    original = runtime.set_resource_admission
    attempts = 0

    def intermittently_locked(allowed: bool, reason: str) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _locked_error()
        original(allowed, reason)

    monkeypatch.setattr(runtime, "set_resource_admission", intermittently_locked)
    assert admission(manual=True) == (False, "SQLite database busy; retrying admission", 1.0)
    assert runtime.account_state().get("resource_updated_at") is None
    assert admission(manual=True) == (True, "", 0.0)
    assert runtime.account_state()["resource_blocked"] is False
    assert attempts == 2


def test_admission_does_not_hide_nonlocking_database_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = SchedulerRuntime(tmp_path / "state.sqlite3", tmp_path / "jobs.sqlite3")
    admission = DeliveryAdmission(runtime, resource_admission=lambda: (True, ""))
    monkeypatch.setattr(
        runtime,
        "set_resource_admission",
        lambda allowed, reason: (_ for _ in ()).throw(_locked_error("no such table")),
    )
    with pytest.raises(OperationalError):
        admission(manual=True)
    assert _sqlite_busy(_locked_error("database table is locked"))
    assert not _sqlite_busy(_locked_error("no such table"))


def test_admission_reads_fail_closed_when_runtime_database_is_locked(tmp_path: Path) -> None:
    runtime = SchedulerRuntime(tmp_path / "state.sqlite3", tmp_path / "jobs.sqlite3")
    runtime.update_account_state({"rate_limit_backoff": {}})
    with sqlite3.connect(tmp_path / "state.sqlite3", timeout=1) as blocker:
        blocker.execute("BEGIN EXCLUSIVE")
        with pytest.raises(OperationalError) as exc:
            runtime.global_backoff_status()
        assert _sqlite_busy(exc.value)
        blocker.rollback()
    assert runtime.global_backoff_status()[0] == 0


def test_worker_keeps_running_after_transient_sqlite_lock(tmp_path: Path, monkeypatch) -> None:
    from prompta import delivery_worker

    class HealthWithTransientLock:
        beats = 0

        def __init__(self, path: Path) -> None:
            pass

        def reset_activity(self, service: str) -> None:
            pass

        def beat(self, service: str) -> None:
            self.beats += 1
            if self.beats == 1:
                raise _locked_error()

    class EmptyQueue:
        def __init__(self, path: Path) -> None:
            self.path = path

        def claim_next(self, *args, **kwargs):
            return None

    health = HealthWithTransientLock(tmp_path)
    monkeypatch.setattr(delivery_worker, "ServiceHealthStore", lambda path: health)
    monkeypatch.setattr(delivery_worker, "DeliveryQueueStore", EmptyQueue)
    monkeypatch.setattr(delivery_worker, "BrowserDeliverySender", lambda *a, **kw: object())
    monkeypatch.setattr(delivery_worker, "notify_watchdog", lambda: None)
    sleeps = 0

    def halt_after_retry(seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(delivery_worker.time, "sleep", halt_after_retry)
    delivery_worker.run(state_path=tmp_path / "runtime.sqlite3")
    assert health.beats == 2
    assert sleeps == 2
