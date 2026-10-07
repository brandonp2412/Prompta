import json
import shlex
import sys
from datetime import datetime
from pathlib import Path

import prompta.core as core
from prompta.core import _parse_run_at, build_parser, main
from prompta.delivery_queue import DeliveryQueueStore
from prompta.jobs import add_job, load_jobs
from prompta.scheduler_runtime import SchedulerRuntime
from prompta.scheduler_service import DurableSchedulerProducer


def _run_cli(monkeypatch, capsys, *args: str) -> str:
    monkeypatch.setattr(sys, "argv", ["prompta", *args])
    main()
    output = capsys.readouterr().out
    assert isinstance(output, str)
    return output


def _paths(runtime: Path) -> tuple[str, str, str, str]:
    return ("--jobs-file", str(runtime), "--state", str(runtime))


def test_remote_cli_dispatches_to_configured_host(monkeypatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    class Result:
        returncode = 0

    def fake_run(argv: list[str], *, check: bool):
        calls.append((argv, check))
        return Result()

    monkeypatch.setenv("PROMPTA_HOST", "nox")
    monkeypatch.setattr(core.socket, "gethostname", lambda: "glass")
    monkeypatch.setattr(core.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prompta",
            "add",
            "audit",
            "Run the audit with 'quotes' and\na newline",
            "--interval-minutes",
            "40",
        ],
    )

    try:
        main()
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("remote dispatch should exit with the ssh command status")

    assert len(calls) == 1
    ssh_argv, check = calls[0]
    assert ssh_argv[:2] == ["ssh", "nox"]
    assert check is False
    assert shlex.split(ssh_argv[2]) == [
        "env",
        "PROMPTA_HOST=local",
        "/home/brandon/.local/bin/prompta",
        "add",
        "audit",
        "Run the audit with 'quotes' and\na newline",
        "--interval-minutes",
        "40",
    ]


def test_host_config_is_used_when_env_is_unset(tmp_path: Path, monkeypatch) -> None:
    host_file = tmp_path / "host"
    host_file.write_text("nox\n", encoding="utf-8")
    monkeypatch.delenv("PROMPTA_HOST", raising=False)
    monkeypatch.setattr(core, "HOST_CONFIG_PATH", host_file)

    assert core._configured_host() == "nox"


def test_explicit_runtime_paths_stay_local(monkeypatch) -> None:
    monkeypatch.setenv("PROMPTA_HOST", "nox")
    assert core._dispatch_remote(["list", "--jobs-file", "/tmp/jobs.sqlite3"]) is None
    assert core._dispatch_remote(["list", "--state", "/tmp/state.sqlite3"]) is None


def test_parser_restores_job_management_surface() -> None:
    parser = build_parser()

    assert parser.parse_args(["add", "audit", "Run audit"]).command == "add"
    assert parser.parse_args(["push", "audit", "Run audit"]).command == "push"
    assert parser.parse_args(["edit", "audit", "Rewrite audit"]).command == "edit"
    assert parser.parse_args(["at", "13:00", "audit", "Run audit"]).command == "at"
    assert parser.parse_args(["remove", "audit"]).command == "remove"
    assert parser.parse_args(["rm", "audit"]).command == "rm"
    assert parser.parse_args(["show", "audit"]).command == "show"
    assert parser.parse_args(["list"]).command == "list"
    assert parser.parse_args(["ls"]).command == "ls"
    assert parser.parse_args(["clear"]).command == "clear"
    assert parser.parse_args(["cls"]).command == "cls"
    assert parser.parse_args(["pause"]).name is None
    assert parser.parse_args(["resume"]).name is None


def test_cli_edit_updates_prompt_without_resetting_schedule_or_state(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    paths = _paths(runtime_path)

    _run_cli(
        monkeypatch,
        capsys,
        "add",
        "audit",
        "Run the original audit",
        "--interval-minutes",
        "40",
        "--exact-interval",
        *paths,
    )
    runtime = SchedulerRuntime(runtime_path, runtime_path)
    runtime.update_job_state(
        "audit",
        {
            "paused": True,
            "last_run_at_epoch": 1234.0,
            "status_message": "keep me",
        },
    )
    before_state = runtime.job_state("audit")

    output = _run_cli(
        monkeypatch,
        capsys,
        "edit",
        "audit",
        "Run the rewritten audit",
        *paths,
    )

    assert "Updated audit" in output
    assert "prompt text only" in output
    job = load_jobs(runtime_path)["audit"]
    assert job.prompt == "Run the rewritten audit"
    assert job.interval_seconds == 2400.0
    assert job.exact_interval is True
    assert job.daily_at is None
    assert job.run_at_epoch is None
    assert runtime.job_state("audit") == before_state


def test_cli_restores_human_readable_list_show_and_json(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    runtime = tmp_path / "runtime.sqlite3"
    paths = _paths(runtime)

    output = _run_cli(
        monkeypatch,
        capsys,
        "push",
        "audit",
        "Run the audit",
        "--interval-minutes",
        "40",
        "--exact-interval",
        "--mutex-group",
        "ibkr-refactor",
        *paths,
    )
    assert "Saved audit" in output
    assert "every 40m exactly" in output

    output = _run_cli(monkeypatch, capsys, "ls", *paths)
    assert "Prompta" in output
    assert "STATUS" in output
    assert "NEXT DUE" in output
    assert "audit" in output
    assert "Run the audit" in output

    output = _run_cli(monkeypatch, capsys, "show", "audit", *paths)
    assert "audit" in output
    assert "Interval" in output
    assert "40m exactly" in output
    assert "Next due" in output
    assert "Mutex group" in output
    assert "ibkr-refactor" in output
    assert "Prompt" in output
    assert "Run the audit" in output

    payload = json.loads(_run_cli(monkeypatch, capsys, "ls", "--json", *paths))
    assert payload == [
        {
            "name": "audit",
            "prompt": "Run the audit",
            "interval_seconds": 2400.0,
            "daily_at": None,
            "exact_interval": True,
            "mutex_group": "ibkr-refactor",
            "run_at_epoch": None,
            "paused": False,
            "status": "pending",
        }
    ]


def test_cli_start_in_minutes_sets_first_due_without_changing_interval(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    monkeypatch.setattr(core.time, "time", lambda: 1000.0)

    _run_cli(
        monkeypatch,
        capsys,
        "add",
        "staggered",
        "Run later",
        "--interval-minutes",
        "30",
        "--exact-interval",
        "--start-in-minutes",
        "10",
        *_paths(runtime_path),
    )

    job = load_jobs(runtime_path)["staggered"]
    state = SchedulerRuntime(runtime_path, runtime_path).job_state("staggered")
    assert job.interval_seconds == 1800.0
    assert state["initial_due_at_epoch"] == 1600.0


def test_cli_at_schedules_one_time_job(tmp_path: Path, monkeypatch, capsys) -> None:
    runtime = tmp_path / "runtime.sqlite3"
    paths = _paths(runtime)

    output = _run_cli(
        monkeypatch,
        capsys,
        "at",
        "2099-01-01T13:00",
        "translation-hi",
        "Finish Hindi translation",
        *paths,
    )
    assert "Scheduled translation-hi" in output
    assert "once at 2099-01-01 13:00 local time" in output

    job = load_jobs(runtime)["translation-hi"]
    assert job.interval_seconds == 0.0
    assert job.exact_interval is True
    assert job.daily_at is None
    assert job.run_at_epoch is not None

    output = _run_cli(monkeypatch, capsys, "show", "translation-hi", *paths)
    assert "Schedule" in output
    assert "once at 2099-01-01 13:00 local time" in output


def test_parse_run_at_rolls_time_only_to_next_day() -> None:
    current = datetime(2026, 10, 2, 14, 0).astimezone()
    scheduled = datetime.fromtimestamp(_parse_run_at("13:00", now=current.timestamp())).astimezone()

    assert scheduled.date().isoformat() == "2026-10-03"
    assert (scheduled.hour, scheduled.minute) == (13, 0)


def test_cli_pause_and_resume_without_name_apply_to_all_jobs(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    runtime = tmp_path / "runtime.sqlite3"
    paths = _paths(runtime)

    for name in ("one", "two"):
        _run_cli(monkeypatch, capsys, "add", name, f"Run {name}", *paths)

    output = _run_cli(monkeypatch, capsys, "pause", *paths)
    assert "Paused 2 jobs" in output
    state = SchedulerRuntime(runtime, runtime)
    assert all(state.job_state(name).get("paused") is True for name in ("one", "two"))

    output = _run_cli(monkeypatch, capsys, "resume", *paths)
    assert "Resumed 2 jobs" in output
    assert all(state.job_state(name).get("paused") is False for name in ("one", "two"))


def test_cli_aliases_remove_and_clear_jobs(tmp_path: Path, monkeypatch, capsys) -> None:
    runtime = tmp_path / "runtime.sqlite3"
    paths = _paths(runtime)

    _run_cli(monkeypatch, capsys, "push", "one", "Run one", *paths)
    _run_cli(monkeypatch, capsys, "push", "two", "Run two", *paths)

    output = _run_cli(monkeypatch, capsys, "rm", "one", *paths)
    assert "Removed one" in output
    assert set(load_jobs(runtime)) == {"two"}

    output = _run_cli(monkeypatch, capsys, "cls", *paths)
    assert "Cleared 1 job" in output
    assert load_jobs(runtime) == {}


def test_cli_remove_cancels_pending_delivery(tmp_path: Path, monkeypatch, capsys) -> None:
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

    output = _run_cli(
        monkeypatch,
        capsys,
        "rm",
        "audit",
        "--jobs-file",
        str(jobs),
        "--state",
        str(state),
    )

    assert "Removed audit" in output
    cancelled = queue.get(str(queued[0]["send_id"]))
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
