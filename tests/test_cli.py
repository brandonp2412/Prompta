import json
import sys
from datetime import datetime
from pathlib import Path

from prompta.core import _parse_run_at, build_parser, main
from prompta.jobs import load_jobs
from prompta.scheduler_runtime import SchedulerRuntime


def _run_cli(monkeypatch, capsys, *args: str) -> str:
    monkeypatch.setattr(sys, "argv", ["prompta", *args])
    main()
    return capsys.readouterr().out


def _paths(runtime: Path) -> tuple[str, str, str, str]:
    return ("--jobs-file", str(runtime), "--state", str(runtime))


def test_parser_restores_job_management_surface() -> None:
    parser = build_parser()

    assert parser.parse_args(["add", "audit", "Run audit"]).command == "add"
    assert parser.parse_args(["push", "audit", "Run audit"]).command == "push"
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
            "run_at_epoch": None,
            "paused": False,
            "status": "pending",
        }
    ]


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
