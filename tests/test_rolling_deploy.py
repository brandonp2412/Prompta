from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from prompta.deployment_gate import DeploymentGate
from scripts import deploy_guarded, rolling_deploy
from tests.test_guarded_deploy import make_databases


@pytest.fixture
def rollout(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "src/migrations").mkdir(parents=True)
    gate = DeploymentGate(tmp_path / "state/runtime.sqlite3")
    make_databases(gate.pause_path.parent, active=True)
    commands = []

    def command(*args, cwd=None):
        commands.append(args)
        if args[:3] == ("git", "rev-parse", "origin/main"):
            return "a" * 40
        return ""

    def archive(repo, revision, target):
        target.mkdir(parents=True)
        (target / "src/migrations").mkdir(parents=True)
        shutil.copytree(Path(__file__).resolve().parents[1] / "systemd", target / "systemd")

    monkeypatch.setattr(rolling_deploy, "run", command)
    monkeypatch.setattr(rolling_deploy, "snapshot", archive)
    monkeypatch.setattr(rolling_deploy.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(deploy_guarded, "verify_services", lambda **kwargs: True)
    return repo, gate, commands


def test_handover_preserves_live_work_and_starts_new_owners_first(rollout):
    repo, gate, commands = rollout
    assert rolling_deploy.deploy(repo, gate)
    assert not gate.is_paused()
    current = rolling_deploy.current_workers(gate.pause_path.parent)
    assert current != rolling_deploy.LEGACY_WORKERS
    start = commands.index(("systemctl", "--user", "start", *current))
    stop = commands.index(("systemctl", "--user", "stop", "--no-block",
                           *rolling_deploy.LEGACY_WORKERS))
    assert start < stop
    assert not any("kill" in arg or "prompta-browser.service" == arg
                   for command in commands for arg in command)
    for filename, table, deadline in (
        ("chat-results.sqlite3", "job_responses", "capture_deadline"),
        ("chat-results.sqlite3", "manual_reply_turns", "lease_deadline"),
        ("ui-send-jobs.sqlite3", "job_deliveries", "lease_expires_at"),
    ):
        with sqlite3.connect(gate.pause_path.parent / filename) as db:
            assert db.execute(f"SELECT {deadline} FROM {table}").fetchone() == (200,)
    report = json.loads((gate.pause_path.parent / "worker-handover.json").read_text())
    assert report["status"] == "serving"
    config = Path.home() / ".config/systemd/user"
    for unit in rolling_deploy.LEGACY_WORKERS:
        override = (config / f"{unit}.d/draining.conf").read_text()
        assert "KillMode=mixed" in override
        assert "SendSIGKILL=no" in override
        assert "TimeoutStopSec=infinity" in override
        assert "ConditionPathExists=!" in override
    definition = (config / current[0]).read_text()
    assert " -m prompta.delivery_worker" in definition
    assert str(repo) not in definition


def test_failed_start_keeps_original_workers_and_reopens_admission(rollout, monkeypatch):
    repo, gate, commands = rollout
    monkeypatch.setattr(deploy_guarded, "verify_services", lambda **kwargs: False)
    with pytest.raises(RuntimeError, match="failed startup"):
        rolling_deploy.deploy(repo, gate)
    assert not gate.is_paused()
    assert not any(command[-2:] == rolling_deploy.LEGACY_WORKERS and "stop" in command
                   for command in commands)
    assert rolling_deploy.current_workers(gate.pause_path.parent) == rolling_deploy.LEGACY_WORKERS


def test_health_failure_after_retirement_keeps_new_generation_paused(rollout, monkeypatch):
    repo, gate, _commands = rollout
    monkeypatch.setattr(deploy_guarded, "verify_services",
                        lambda **kwargs: not kwargs.get("check_http", True))
    with pytest.raises(RuntimeError, match="health verification failed"):
        rolling_deploy.deploy(repo, gate)
    assert gate.is_paused()
    assert rolling_deploy.current_workers(gate.pause_path.parent) != rolling_deploy.LEGACY_WORKERS


def test_host_overrides_follow_new_generation(rollout):
    repo, gate, _commands = rollout
    config = Path.home() / ".config/systemd/user"
    original = config / "prompta-delivery-worker.service.d"
    original.mkdir(parents=True)
    (original / "40-browser.conf").write_text("[Service]\nEnvironment=PROMPTA_FLARESOLVERR_URL=http://127.0.0.1:8193\n")
    assert rolling_deploy.deploy(repo, gate)
    unit = rolling_deploy.current_workers(gate.pause_path.parent)[0]
    assert "8193" in (config / f"{unit}.d/40-browser.conf").read_text()


def test_subsequent_deployment_retires_only_current_generation(rollout):
    repo, gate, commands = rollout
    assert rolling_deploy.deploy(repo, gate)
    first = rolling_deploy.current_workers(gate.pause_path.parent)
    commands.clear()
    assert rolling_deploy.deploy(repo, gate)
    second = rolling_deploy.current_workers(gate.pause_path.parent)
    assert second != first
    assert ("systemctl", "--user", "stop", "--no-block", *first) in commands
    assert not any("stop" in command and any(unit in command for unit in rolling_deploy.LEGACY_WORKERS)
                   for command in commands)


def test_checkout_stays_unchanged_while_original_owner_drains(tmp_path, monkeypatch):
    commands = []

    def command(*args, cwd=None):
        commands.append(args)
        return "deactivating" if "show" in args else ""

    monkeypatch.setattr(rolling_deploy, "run", command)
    assert not rolling_deploy.sync_checkout(tmp_path)
    assert not any("merge" in command for command in commands)


def test_schema_change_records_and_stops_owners_before_migration(rollout, monkeypatch):
    repo, gate, commands = rollout
    (repo / "src/migrations/old.py").write_text("old migration")
    events = []
    record = deploy_guarded.record_interrupted_work

    def inventory(gate):
        assert gate.is_paused()
        events.append("record")
        record(gate)

    def stop():
        assert gate.is_paused()
        events.append("stop")

    def migrate(*args, **kwargs):
        assert events == ["record", "stop"]
        events.append("migrate")

    monkeypatch.setattr(deploy_guarded, "record_interrupted_work", inventory)
    monkeypatch.setattr(deploy_guarded, "stop_workers", stop)
    monkeypatch.setattr(rolling_deploy.subprocess, "run", migrate)
    assert rolling_deploy.deploy(repo, gate)
    assert events == ["record", "stop", "migrate"]
    assert not gate.is_paused()
    assert (gate.pause_path.parent / "deployment-verification.json").exists()
    assert not any("prompta-browser.service" in command for command in commands)


def test_schema_startup_failure_keeps_admission_paused(rollout, monkeypatch):
    repo, gate, _commands = rollout
    (repo / "src/migrations/old.py").write_text("old migration")
    monkeypatch.setattr(deploy_guarded, "stop_workers", lambda: None)
    monkeypatch.setattr(deploy_guarded, "verify_services", lambda **kwargs: False)
    with pytest.raises(RuntimeError, match="failed startup"):
        rolling_deploy.deploy(repo, gate)
    assert gate.is_paused()
