import json
import sys
from pathlib import Path

from prompta.core import build_parser, main
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

    assert parser.parse_args(["push", "audit", "Run audit"]).command == "push"
    assert parser.parse_args(["show", "audit"]).command == "show"
    assert parser.parse_args(["ls"]).command == "ls"
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
