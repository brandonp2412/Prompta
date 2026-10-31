from pathlib import Path

import pytest

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


def test_bulk_pause_only_affects_selected_jobs_and_resumes_them(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    wakeups: list[bool] = []
    service = WebJobService(
        database, database, "test-host", start_scheduler=lambda: wakeups.append(True) or True
    )
    for name in ("visible-a", "visible-b", "hidden-long"):
        add_job(database, name, "Work", 2400)

    paused = service.apply("pause_many", {"names": ["visible-a", "visible-b"]})
    states = {job["name"]: job["paused"] for job in paused["jobs"]}
    assert states == {"visible-a": True, "visible-b": True, "hidden-long": False}
    assert wakeups == []

    resumed = service.apply("resume_many", {"names": ["visible-a"]})
    states = {job["name"]: job["paused"] for job in resumed["jobs"]}
    assert states == {"visible-a": False, "visible-b": True, "hidden-long": False}
    assert wakeups == [True]


def test_bulk_pause_validates_full_selection_before_mutating(tmp_path: Path) -> None:
    import pytest

    database = tmp_path / "jobs.sqlite3"
    add_job(database, "known", "Work", 2400)
    service = WebJobService(database, database, "test-host")
    with pytest.raises(ValueError, match="Unknown job"):
        service.apply("pause_many", {"names": ["known", "unknown"]})
    assert service.runtime.job_state("known").get("paused") is not True
    with pytest.raises(ValueError, match="names"):
        service.apply("pause_many", {"names": []})
    with pytest.raises(ValueError, match="names"):
        service.apply("pause_many", {"names": ["known", 10]})


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


def test_job_creation_order_tracks_insertions_not_edits(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    service = WebJobService(database, database, "test-host")
    add_job(database, "z-old", "First", 2400, source_revision="test")
    add_job(database, "a-new", "Second", 2400, source_revision="test")

    initial = {job["name"]: job["created_order"] for job in service.scheduled_jobs()["jobs"]}
    older_order = initial["z-old"]
    newer_order = initial["a-new"]
    assert isinstance(older_order, int) and isinstance(newer_order, int)
    assert newer_order > older_order

    add_job(database, "z-old", "Edited", 2400, source_revision="test")
    edited = {job["name"]: job["created_order"] for job in service.scheduled_jobs()["jobs"]}
    assert edited == initial

    service.apply("remove", {"name": "z-old"})
    add_job(database, "z-old", "Recreated", 2400, source_revision="test")
    recreated = {job["name"]: job["created_order"] for job in service.scheduled_jobs()["jobs"]}
    recreated_old = recreated["z-old"]
    recreated_new = recreated["a-new"]
    assert isinstance(recreated_old, int) and isinstance(recreated_new, int)
    assert recreated_old > recreated_new


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


def test_fire_now_restarts_interval_and_preserves_pause(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    import prompta.manual_fire as manual_fire

    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "state.sqlite3"
    add_job(jobs, "audit", "Check the code", 2400, exact_interval=True)
    service = WebJobService(jobs, state, "test-host")
    service.runtime.update_job_state(
        "audit", {"paused": True, "initial_due_at_epoch": 900.0, "next_due_at_epoch": 9000.0}
    )
    times = iter([1000.0, 1200.0])
    monkeypatch.setattr(manual_fire, "time", SimpleNamespace(time=lambda: next(times)))

    first = service.apply("fire_now", {"name": "audit"})
    assert first["jobs"][0]["next_due_at_epoch"] == 3400.0
    second = service.apply("fire_now", {"name": "audit"})
    assert second["jobs"][0]["next_due_at_epoch"] == 3600.0

    deliveries = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3").records()
    assert len(deliveries) == 2
    assert all(item["message"] == "Check the code" for item in deliveries)
    assert all(str(item["client_id"]).startswith("manual:") for item in deliveries)
    assert deliveries[0]["send_id"] != deliveries[1]["send_id"]
    persisted = service.runtime.job_state("audit")
    assert persisted["paused"] is True
    assert persisted["initial_due_at_epoch"] == 0.0
    assert persisted["next_due_at_epoch"] == 3600.0
    assert persisted["last_manual_fire_at_epoch"] == 1200.0

    service.apply("resume", {"name": "audit"})
    producer = DurableSchedulerProducer(state, jobs)
    assert producer.tick(now=3599.0) == 0
    assert producer.tick(now=3600.0) == 1
    assert len(DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3").records()) == 3


def test_fire_now_preserves_fixed_daily_and_one_time_schedules(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "state.sqlite3"
    add_job(jobs, "daily", "Daily work", 0, daily_at="09:00")
    add_job(jobs, "once", "At a fixed time", 0, run_at_epoch=10000.0)
    service = WebJobService(jobs, state, "test-host")
    for name in ("daily", "once"):
        service.runtime.update_job_state(name, {"next_due_at_epoch": 8000.0})
        before = service.runtime.job_state(name)
        service.apply("fire_now", {"name": name})
        assert service.runtime.job_state(name) == before


def test_fire_now_rejects_unknown_job_without_queuing(tmp_path: Path) -> None:
    import pytest

    service = WebJobService(tmp_path / "jobs.sqlite3", tmp_path / "state.sqlite3", "test")
    with pytest.raises(ValueError, match="Unknown job"):
        service.apply("fire_now", {"name": "not-found"})
    assert DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3").records() == []


@pytest.mark.parametrize("pin_chat", [False, True])
def test_run_once_queues_prompt_without_scheduling_or_changing_existing_jobs(
    tmp_path: Path, pin_chat: bool
) -> None:
    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "state.sqlite3"
    add_job(jobs, "audit", "Recurring work", 2400)
    service = WebJobService(jobs, state, "test-host")
    service.runtime.update_job_state("audit", {"next_due_at_epoch": 5000.0})

    result = service.apply(
        "run_once", {"prompt": "  Investigate now  ", **({"pin_chat": True} if pin_chat else {})}
    )
    assert [job["name"] for job in result["jobs"]] == ["audit"]
    assert service.runtime.job_state("audit")["next_due_at_epoch"] == 5000.0
    deliveries = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3").records()
    assert len(deliveries) == 1
    assert deliveries[0]["message"] == "Investigate now"
    assert deliveries[0]["pin_chat"] is pin_chat
    assert str(deliveries[0]["client_id"]).startswith("manual:")


@pytest.mark.parametrize("pin_chat", [False, True])
def test_run_once_delay_creates_durable_one_shot_and_sends_at_due(
    tmp_path: Path, monkeypatch, pin_chat: bool
) -> None:
    monkeypatch.setattr("prompta.web_jobs.time.time", lambda: 1000.0)
    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "state.sqlite3"
    service = WebJobService(jobs, state, "test-host")
    scheduled = service.apply(
        "run_once", {"prompt": "Run later", "delay_minutes": 15, "pin_chat": pin_chat}
    )
    assert len(scheduled["jobs"]) == 1
    job = scheduled["jobs"][0]
    assert str(job["name"]).startswith("Once ")
    assert job["run_at_epoch"] == 1900.0
    assert job["pin_chat"] is pin_chat
    assert DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3").records() == []

    producer = DurableSchedulerProducer(state, jobs)
    assert producer.tick(now=1899.0) == 0
    assert producer.tick(now=1900.0) == 1
    assert producer.tick(now=2000.0) == 0
    records = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3").records()
    assert len(records) == 1
    assert records[0]["message"] == "Run later"
    assert records[0]["pin_chat"] is pin_chat
    assert service.scheduled_jobs()["jobs"] == []


def test_delayed_once_edit_preserves_due_until_delay_changes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("prompta.web_jobs.time.time", lambda: 1000.0)
    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "state.sqlite3"
    service = WebJobService(jobs, state, "test-host")
    created = service.apply("run_once", {"prompt": "Original", "delay_minutes": 15})
    name = created["jobs"][0]["name"]
    edited = service.apply(
        "add", {"name": name, "prompt": "Updated", "schedule": "once", "pin_chat": True}
    )
    assert edited["jobs"][0]["run_at_epoch"] == 1900.0
    assert edited["jobs"][0]["pin_chat"] is True

    rescheduled = service.apply(
        "add", {"name": name, "prompt": "Updated", "schedule": "once", "delay_minutes": 30}
    )
    assert rescheduled["jobs"][0]["run_at_epoch"] == 2800.0
    assert rescheduled["jobs"][0]["pin_chat"] is True
    producer = DurableSchedulerProducer(state, jobs)
    assert producer.tick(now=1900.0) == 0
    assert producer.tick(now=2800.0) == 1
    assert (
        DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3").records()[0]["message"] == "Updated"
    )
    assert DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3").records()[0]["pin_chat"] is True


@pytest.mark.parametrize("action", ["run_once", "add"])
def test_once_rejects_non_boolean_pin_choice(tmp_path: Path, action: str) -> None:
    service = WebJobService(tmp_path / "jobs.sqlite3", tmp_path / "state.sqlite3", "test-host")
    payload: dict[str, object] = {"prompt": "No", "pin_chat": "false"}
    if action == "add":
        payload.update({"name": "invalid", "schedule": "once"})
    with pytest.raises(ValueError, match="pin_chat"):
        service.apply(action, payload)
    assert service.scheduled_jobs()["jobs"] == []


@pytest.mark.parametrize("delay", [-1, 43201, "nan", "inf", None, True, "abc"])
@pytest.mark.parametrize("action", ["run_once", "add"])
def test_once_rejects_invalid_delay(tmp_path: Path, delay: object, action: str) -> None:
    service = WebJobService(tmp_path / "jobs.sqlite3", tmp_path / "state.sqlite3", "test-host")
    payload: dict[str, object] = {"prompt": "No", "delay_minutes": delay}
    if action == "add":
        payload.update({"name": "invalid", "schedule": "once"})
    with pytest.raises(ValueError, match="delay_minutes"):
        service.apply(action, payload)
    assert service.scheduled_jobs()["jobs"] == []
    assert DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3").records() == []


def test_run_once_rejects_empty_prompt(tmp_path: Path) -> None:
    import pytest

    service = WebJobService(tmp_path / "jobs.sqlite3", tmp_path / "state.sqlite3", "test-host")
    with pytest.raises(ValueError, match="prompt"):
        service.apply("run_once", {"prompt": "   "})
    assert DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3").records() == []


def test_editing_prompt_preserves_schedule_pause_and_delivery_history(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "state.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    service = WebJobService(jobs, state, "test-host")
    service.apply(
        "add",
        {"name": "soak", "prompt": "Original", "interval_minutes": 45, "exact_interval": True},
    )
    service.runtime.update_job_state(
        "soak",
        {
            "last_sent_at": 1000.0,
            "last_enqueued_at": 990.0,
            "next_due_at_epoch": 3700.0,
            "paused": True,
        },
    )
    before = service.runtime.job_state("soak")
    edited = service.apply(
        "add", {"name": "soak", "prompt": "Updated", "interval_minutes": 45, "exact_interval": True}
    )
    assert edited["jobs"][0]["prompt"] == "Updated"
    assert service.runtime.job_state("soak") == before
    producer = DurableSchedulerProducer(state, jobs, queue_path)
    assert producer.tick(now=3700.0) == 0  # still paused after editing
    service.apply("resume", {"name": "soak"})
    assert producer.tick(now=3699.0) == 0
    assert producer.tick(now=3700.0) == 1
    assert DeliveryQueueStore(queue_path).records()[0]["message"] == "Updated"


def test_editing_interval_rebases_from_last_dispatch_without_firing_early(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "state.sqlite3"
    service = WebJobService(jobs, state, "test-host")
    service.apply(
        "add", {"name": "soak", "prompt": "Run", "interval_minutes": 60, "exact_interval": True}
    )
    service.runtime.update_job_state(
        "soak",
        {
            "last_sent_at": 1000.0,
            "last_enqueued_at": 999.0,
            "next_due_at_epoch": 4600.0,
            "paused": True,
        },
    )
    service.apply(
        "add",
        {"name": "soak", "prompt": "Run revised", "interval_minutes": 45, "exact_interval": True},
    )
    recorded = service.runtime.job_state("soak")
    assert recorded["last_sent_at"] == 1000.0
    assert recorded["paused"] is True
    assert recorded["next_due_at_epoch"] == 0.0
    service.apply("resume", {"name": "soak"})
    producer = DurableSchedulerProducer(state, jobs)
    assert producer.tick(now=3699.0) == 0
    assert producer.tick(now=3700.0) == 1


def test_editing_while_delivery_pending_never_sends_second_copy(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "state.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    service = WebJobService(jobs, state, "test-host")
    service.apply(
        "add", {"name": "soak", "prompt": "Run", "interval_minutes": 45, "exact_interval": True}
    )
    producer = DurableSchedulerProducer(state, jobs, queue_path)
    producer.runtime.update_job_state("soak", {"initial_due_at_epoch": 1000.0})
    assert producer.tick(now=1000.0) == 1
    service.apply(
        "add", {"name": "soak", "prompt": "Revised", "interval_minutes": 45, "exact_interval": True}
    )
    assert producer.tick(now=1001.0) == 0
    assert len(DeliveryQueueStore(queue_path).records()) == 1
