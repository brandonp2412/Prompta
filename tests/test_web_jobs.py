from pathlib import Path

from prompta.delivery_queue import DeliveryQueueStore
from prompta.jobs import add_job
from prompta.scheduler_service import DurableSchedulerProducer
from prompta.web_jobs import WebJobService


def test_web_job_service_manages_interval_job_lifecycle(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.sqlite3"
    wakeups: list[bool] = []
    service = WebJobService(
        runtime,
        runtime,
        "test-host",
        start_scheduler=lambda: wakeups.append(True) or True,
    )

    added = service.apply(
        "add",
        {
            "name": "audit",
            "prompt": "Run the audit",
            "interval_minutes": 40,
            "exact_interval": True,
        },
    )
    job = added["jobs"][0]
    assert job["name"] == "audit"
    assert job["prompt"] == "Run the audit"
    assert job["interval_minutes"] == 40
    assert job["exact_interval"] is True
    assert wakeups == [True]

    paused = service.apply("pause", {"name": "audit"})
    assert paused["jobs"][0]["paused"] is True

    resumed = service.apply("resume", {"name": "audit"})
    assert resumed["jobs"][0]["paused"] is False
    assert wakeups == [True, True]

    paused_all = service.apply("pause_all", {})
    assert all(job["paused"] for job in paused_all["jobs"])

    resumed_all = service.apply("resume_all", {})
    assert all(not job["paused"] for job in resumed_all["jobs"])
    assert wakeups == [True, True, True]

    removed = service.apply("remove", {"name": "audit"})
    assert removed["jobs"] == []


def test_web_job_service_manages_daily_jobs_and_clear(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.sqlite3"
    service = WebJobService(runtime, runtime, "test-host")

    result = service.apply(
        "add",
        {"name": "daily", "prompt": "Do daily work", "daily_at": "09:15"},
    )
    job = result["jobs"][0]
    assert job["daily_at"] == "09:15"
    assert job["interval_minutes"] == 0

    cleared = service.apply("clear", {})
    assert cleared["jobs"] == []


def test_removing_job_cancels_already_queued_delivery(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "scheduler.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    add_job(jobs, "audit", "Run the audit", 60.0, exact_interval=True, source_revision="test")
    producer = DurableSchedulerProducer(state, jobs, queue_path)
    producer.runtime.update_job_state("audit", {"initial_due_at_epoch": 1000.0})
    assert producer.tick(now=1000.0) == 1

    queue = DeliveryQueueStore(queue_path)
    queued = queue.records()
    assert len(queued) == 1
    assert queued[0]["status"] == "queued"

    WebJobService(jobs, state, "test-host").apply("remove", {"name": "audit"})

    cancelled = queue.get(str(queued[0]["send_id"]))
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
    assert queue.claim_next("worker", now=1001.0, lease_seconds=30.0) is None
