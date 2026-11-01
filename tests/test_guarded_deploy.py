from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from prompta.deployment_gate import DeploymentGate
from scripts import deploy_guarded


def make_databases(state_dir: Path, *, active: bool = False) -> None:
    with sqlite3.connect(state_dir / "chat-results.sqlite3") as db:
        db.execute(
            "CREATE TABLE job_responses "
            "(status TEXT, capture_deadline REAL, capture_owner TEXT)"
        )
        db.execute(
            "CREATE TABLE manual_reply_turns "
            "(status TEXT, lease_deadline REAL)"
        )
        db.execute(
            "INSERT INTO job_responses VALUES (?, 200, 'capture-owner')",
            ("generating" if active else "completed",),
        )
        db.execute(
            "INSERT INTO manual_reply_turns VALUES (?, 200)",
            ("accepted" if active else "completed",),
        )
    with sqlite3.connect(state_dir / "ui-send-jobs.sqlite3") as db:
        db.execute(
            "CREATE TABLE job_deliveries "
            "(status TEXT, lease_owner TEXT, lease_expires_at REAL)"
        )
        db.execute(
            "INSERT INTO job_deliveries VALUES (?, 'delivery-owner', 200)",
            ("running" if active else "completed",),
        )
    with sqlite3.connect(state_dir / "runtime.sqlite3") as db:
        db.execute("CREATE TABLE service_health (service TEXT, activity TEXT)")
        db.execute(
            "INSERT INTO service_health VALUES ('delivery_worker', ?)",
            ("dispatch:inflight" if active else "",),
        )


def test_waits_for_admitted_operation_and_blocks_new_work(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    make_databases(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def running_capture() -> None:
        with gate.admission() as allowed:
            assert allowed
            entered.set()
            assert release.wait(2.0)

    worker = threading.Thread(target=running_capture)
    worker.start()
    try:
        assert entered.wait(2.0)
        deploy_guarded.request_pause(gate)
        assert gate.is_paused()
        assert not deploy_guarded.wait_until_idle(gate, timeout=0.02, poll=0.005)
    finally:
        release.set()
        worker.join(timeout=2.0)
    assert not worker.is_alive()
    with gate.admission() as allowed:
        assert not allowed
    assert deploy_guarded.wait_until_idle(gate, timeout=1.0, poll=0.005)


def test_active_leases_block_even_after_dispatch_returns(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    make_databases(tmp_path, active=True)
    assert deploy_guarded.active_work(tmp_path, now=100) == (1, 1, 1, True)
    deploy_guarded.request_pause(gate)
    assert not deploy_guarded.wait_until_idle(gate, timeout=0.02, poll=0.005)
    with sqlite3.connect(tmp_path / "chat-results.sqlite3") as db:
        db.execute("UPDATE job_responses SET status='completed'")
        db.execute("UPDATE manual_reply_turns SET status='completed'")
    with sqlite3.connect(tmp_path / "ui-send-jobs.sqlite3") as db:
        db.execute("UPDATE job_deliveries SET status='completed'")
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as db:
        db.execute("UPDATE service_health SET activity=''")
    assert deploy_guarded.wait_until_idle(gate, timeout=0.1, poll=0.005)


def test_missing_database_fails_closed(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    deploy_guarded.request_pause(gate)
    assert not deploy_guarded.wait_until_idle(gate, timeout=0.02, poll=0.005)


def test_timeout_defers_without_updating_or_leaving_paused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = DeploymentGate(tmp_path / "state/runtime.sqlite3")
    make_databases(tmp_path / "state", active=True)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    commands: list[tuple[str, ...]] = []

    def fake_run(args: list[str], **_kwargs: object) -> object:
        commands.append(tuple(args))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(deploy_guarded.subprocess, "run", fake_run)
    assert not deploy_guarded.deploy(repo, gate, wait_seconds=0.02)
    assert not gate.is_paused()
    assert commands == [
        ("git", "fetch", "origin", "main"),
        ("git", "diff", "--quiet"),
    ]


def test_refuses_to_take_over_existing_pause(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    deploy_guarded.request_pause(gate)
    with pytest.raises(FileExistsError):
        deploy_guarded.request_pause(gate)
    assert gate.is_paused()


def test_successful_deploy_restarts_apps_but_not_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = DeploymentGate(tmp_path / "state/runtime.sqlite3")
    make_databases(tmp_path / "state")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".venv/bin").mkdir(parents=True)
    commands: list[tuple[str, ...]] = []

    def fake_run(args: list[str], **_kwargs: object) -> object:
        commands.append(tuple(args))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(deploy_guarded.subprocess, "run", fake_run)
    monkeypatch.setattr(deploy_guarded, "verify_services", lambda: True)
    assert deploy_guarded.deploy(repo, gate, wait_seconds=0.2)
    assert not gate.is_paused()
    assert sum(command[:3] == ("systemctl", "--user", "restart") for command in commands) == 4
    assert all("prompta-browser.service" not in command for command in commands)


def test_post_update_failure_keeps_admission_paused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = DeploymentGate(tmp_path / "state/runtime.sqlite3")
    make_databases(tmp_path / "state")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".venv/bin").mkdir(parents=True)

    def fake_run(args: list[str], **_kwargs: object) -> object:
        if args[0].endswith("prompta-migrate"):
            raise RuntimeError("migrations did not complete")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(deploy_guarded.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="migrations did not complete"):
        deploy_guarded.deploy(repo, gate, wait_seconds=0.2)
    assert gate.is_paused()
