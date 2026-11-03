from __future__ import annotations

import json
import shutil
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
    monkeypatch.setattr(deploy_guarded, "stop_workers", lambda: commands.append(("stop-all-workers",)))
    return repo, gate, commands


def test_deployment_stops_owners_before_starting_recovery_workers(rollout):
    repo, gate, commands = rollout
    assert rolling_deploy.deploy(repo, gate)
    assert not gate.is_paused()
    current = rolling_deploy.current_workers(gate.pause_path.parent)
    assert current != rolling_deploy.LEGACY_WORKERS
    start = commands.index(("systemctl", "--user", "start", *current))
    stop = commands.index(("stop-all-workers",))
    assert stop < start
    assert not any("prompta-browser.service" == arg for command in commands for arg in command)
    assert (gate.pause_path.parent / "deployment-interrupted.json").exists()
    assert (gate.pause_path.parent / "deployment-verification.json").exists()
    report = json.loads((gate.pause_path.parent / "worker-handover.json").read_text())
    assert report["status"] == "serving"
    config = Path.home() / ".config/systemd/user"
    definition = (config / current[0]).read_text()
    assert " -m prompta.delivery_worker" in definition
    assert str(repo) not in definition


def test_failed_start_keeps_admission_paused(rollout, monkeypatch):
    repo, gate, commands = rollout
    monkeypatch.setattr(deploy_guarded, "verify_services", lambda **kwargs: False)
    with pytest.raises(RuntimeError, match="failed startup"):
        rolling_deploy.deploy(repo, gate)
    assert gate.is_paused()
    assert ("stop-all-workers",) in commands
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
    assert ("stop-all-workers",) in commands
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
        events.append("prepare" if "--prepare-recovery" in args[0] else "migrate")

    monkeypatch.setattr(deploy_guarded, "record_interrupted_work", inventory)
    monkeypatch.setattr(deploy_guarded, "stop_workers", stop)
    monkeypatch.setattr(rolling_deploy.subprocess, "run", migrate)
    assert rolling_deploy.deploy(repo, gate)
    assert events == ["record", "stop", "migrate", "prepare"]
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
