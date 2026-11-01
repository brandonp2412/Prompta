from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from prompta.deployment_gate import DeploymentGate
from scripts import deploy_guarded


def make_databases(state_dir: Path, *, active: bool = False) -> None:
    with sqlite3.connect(state_dir / "chat-results.sqlite3") as db:
        db.execute(
            "CREATE TABLE job_responses "
            "(status TEXT, capture_deadline REAL, capture_owner TEXT, send_id TEXT)"
        )
        db.execute(
            "CREATE TABLE manual_reply_turns (status TEXT, lease_deadline REAL, reply_id TEXT)"
        )
        db.execute(
            "INSERT INTO job_responses VALUES (?, 200, 'capture-owner', 'fresh-one')",
            ("generating" if active else "completed",),
        )
        db.execute(
            "INSERT INTO manual_reply_turns VALUES (?, 200, 'reply-one')",
            ("accepted" if active else "completed",),
        )
    with sqlite3.connect(state_dir / "ui-send-jobs.sqlite3") as db:
        db.execute(
            "CREATE TABLE job_deliveries "
            "(status TEXT, lease_owner TEXT, lease_expires_at REAL, send_id TEXT)"
        )
        db.execute(
            "INSERT INTO job_deliveries VALUES (?, 'delivery-owner', 200, 'fresh-one')",
            ("running" if active else "completed",),
        )
    with sqlite3.connect(state_dir / "runtime.sqlite3") as db:
        db.execute("CREATE TABLE service_health (service TEXT, activity TEXT)")
        db.execute(
            "INSERT INTO service_health VALUES ('delivery_worker', ?)",
            ("dispatch:inflight" if active else "",),
        )


def test_records_active_work_without_waiting(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    make_databases(tmp_path, active=True)
    deploy_guarded.record_interrupted_work(gate)
    inventory = json.loads((tmp_path / "deployment-interrupted.json").read_text())
    assert inventory["job_responses"] == [{"id": "fresh-one", "status": "generating"}]
    assert inventory["manual_reply_turns"] == [{"id": "reply-one", "status": "accepted"}]
    assert inventory["job_deliveries"] == [{"id": "fresh-one", "status": "running"}]
    assert inventory["priority"] == {
        "job_responses": ["fresh-one"],
        "manual_reply_turns": ["reply-one"],
    }


def test_deploy_verification_reports_pending_recovery_without_claiming_completion(
    tmp_path: Path,
) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    make_databases(tmp_path, active=True)
    deploy_guarded.record_interrupted_work(gate)
    assert deploy_guarded.verify_recorded_work(gate)
    report = json.loads((tmp_path / "deployment-verification.json").read_text())
    assert report["preserved"] == 3
    assert report["pending_recovery"] == 3
    assert report["missing"] == {}
    assert report["status_counts"]["job_responses"] == {"generating": 1}

    with sqlite3.connect(tmp_path / "chat-results.sqlite3") as db:
        db.execute("DELETE FROM manual_reply_turns WHERE reply_id='reply-one'")
    assert not deploy_guarded.verify_recorded_work(gate)
    report = json.loads((tmp_path / "deployment-verification.json").read_text())
    assert report["missing"] == {"manual_reply_turns": ["reply-one"]}


def test_next_deploy_keeps_unfinished_recovery_priority(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    make_databases(tmp_path, active=True)
    deploy_guarded.record_interrupted_work(gate)
    with sqlite3.connect(tmp_path / "chat-results.sqlite3") as db:
        db.execute("UPDATE job_responses SET status='interrupted', capture_owner='' ")
        db.execute("UPDATE manual_reply_turns SET status='interrupted'")
    deploy_guarded.record_interrupted_work(gate)
    inventory = json.loads((tmp_path / "deployment-interrupted.json").read_text())
    assert inventory["priority"] == {
        "job_responses": ["fresh-one"],
        "manual_reply_turns": ["reply-one"],
    }


def test_bounded_shutdown_interrupts_busy_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(args: list[str], **_kwargs: object) -> object:
        commands.append(tuple(args))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(deploy_guarded.subprocess, "run", fake_run)
    deploy_guarded.stop_workers(timeout=0)
    assert commands[0][2:4] == ("stop", "--no-block")
    assert commands[1][2:4] == ("kill", "--signal=SIGKILL")
    assert commands[2][2] == "stop"


def test_refuses_to_take_over_existing_pause(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    deploy_guarded.request_pause(gate)
    with pytest.raises(FileExistsError):
        deploy_guarded.request_pause(gate)
    assert gate.is_paused()


def test_wait_for_idle_checks_live_leases_not_stale_statuses(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    make_databases(tmp_path, active=True)
    with sqlite3.connect(tmp_path / "chat-results.sqlite3") as db:
        db.execute("UPDATE job_responses SET capture_deadline=?", (time.time() + 60,))
        db.execute("UPDATE manual_reply_turns SET lease_deadline=?", (time.time() + 60,))
    with sqlite3.connect(tmp_path / "ui-send-jobs.sqlite3") as db:
        db.execute("UPDATE job_deliveries SET lease_expires_at=?", (time.time() + 60,))
    assert not deploy_guarded.wait_for_idle(gate, timeout=0)
    with sqlite3.connect(tmp_path / "chat-results.sqlite3") as db:
        db.execute("UPDATE job_responses SET capture_deadline=0")
        db.execute("UPDATE manual_reply_turns SET lease_deadline=0")
    with sqlite3.connect(tmp_path / "ui-send-jobs.sqlite3") as db:
        db.execute("UPDATE job_deliveries SET lease_expires_at=0")
    assert deploy_guarded.wait_for_idle(gate, timeout=0)


def test_wait_for_idle_drains_read_only_browser_operations(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    make_databases(tmp_path)
    with gate.admission() as admitted:
        assert admitted
        deploy_guarded.request_pause(gate)
        # No active database leases: the in-flight read is protected by flock.
        assert not deploy_guarded.wait_for_idle(gate, timeout=0)
    assert deploy_guarded.wait_for_idle(gate, timeout=0)


def test_busy_deployment_aborts_without_stopping_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    gate = DeploymentGate(state / "runtime.sqlite3")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    commands: list[tuple[str, ...]] = []

    def fake_run(args: list[str], **_kwargs: object) -> object:
        commands.append(tuple(args))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(deploy_guarded.subprocess, "run", fake_run)
    monkeypatch.setattr(deploy_guarded, "wait_for_idle", lambda _gate: False)
    assert not deploy_guarded.deploy(repo, gate)
    assert not gate.is_paused()
    assert not (state / "deployment-interrupted.json").exists()
    assert all(command[0] == "git" for command in commands)


def test_successful_deploy_restarts_apps_but_not_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = DeploymentGate(tmp_path / "state/runtime.sqlite3")
    make_databases(tmp_path / "state", active=True)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".venv/bin").mkdir(parents=True)
    commands: list[tuple[str, ...]] = []

    def fake_run(args: list[str], **_kwargs: object) -> object:
        commands.append(tuple(args))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(deploy_guarded.subprocess, "run", fake_run)
    monkeypatch.setattr(deploy_guarded, "verify_services", lambda: True)
    monkeypatch.setattr(deploy_guarded, "stop_workers", lambda: None)
    assert deploy_guarded.deploy(repo, gate)
    assert not gate.is_paused()
    with sqlite3.connect(tmp_path / "state/ui-send-jobs.sqlite3") as db:
        assert db.execute("SELECT lease_expires_at FROM job_deliveries").fetchone() == (0,)
    with sqlite3.connect(tmp_path / "state/chat-results.sqlite3") as db:
        assert db.execute("SELECT capture_deadline FROM job_responses").fetchone() == (0,)
        assert db.execute("SELECT lease_deadline FROM manual_reply_turns").fetchone() == (0,)
    assert sum(command[:3] == ("systemctl", "--user", "restart") for command in commands) == 4
    assert all("prompta-browser.service" not in command for command in commands)


def test_post_update_failure_keeps_admission_paused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = DeploymentGate(tmp_path / "state/runtime.sqlite3")
    make_databases(tmp_path / "state", active=True)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".venv/bin").mkdir(parents=True)

    def fake_run(args: list[str], **_kwargs: object) -> object:
        if args[0].endswith("prompta-migrate"):
            raise RuntimeError("migrations did not complete")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(deploy_guarded.subprocess, "run", fake_run)
    monkeypatch.setattr(deploy_guarded, "stop_workers", lambda: None)
    with pytest.raises(RuntimeError, match="migrations did not complete"):
        deploy_guarded.deploy(repo, gate)
    assert gate.is_paused()


def test_stopped_capture_recovers_from_verified_history_without_resending(tmp_path: Path) -> None:
    from prompta.response_capture import CaptureResult
    from prompta.response_store import ResponseStore

    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    conversation = "12345678-1234-4123-8123-123456789abc"
    store.ensure_queued("manual-deploy", "Original prompt", now=10)
    assert store.accept("manual-deploy", "999999999:stopped", deadline=10000, now=11)
    assert store.bind_conversation_route(
        "manual-deploy", "999999999:stopped", "/c/" + conversation, now=12
    )
    assert store.recover_orphans(now=13) == 1
    candidate = store.next_history_recovery(now=14)
    assert candidate is not None and candidate["send_id"] == "manual-deploy"
    assert store.recover_historical_response(
        "manual-deploy",
        CaptureResult("dom", "complete", "Recovered answer", conversation, None, None, "turn"),
        now=15,
    )
    record = store.detail("manual-deploy")
    assert record is not None
    assert record["status"] == "completed"
    assert record["assistant_text"] == "Recovered answer"
