from pathlib import Path

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
