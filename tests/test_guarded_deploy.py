from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from prompta.deployment_gate import DeploymentGate
from scripts import deploy_guarded


def make_databases(state_dir: Path, *, active: bool = False) -> None:
    with sqlite3.connect(state_dir / "chat-results.sqlite3") as db:
        db.execute(
            "CREATE TABLE job_responses "
            "(status TEXT, capture_deadline REAL, capture_owner TEXT, send_id TEXT, "
            "conversation_id TEXT)"
        )
        db.execute("CREATE TABLE manual_reply_turns "
                   "(status TEXT, lease_deadline REAL, reply_id TEXT, "
                   "conversation_id TEXT, parent_id TEXT)")
        db.execute(
            "INSERT INTO job_responses VALUES (?, 200, 'capture-owner', 'fresh-one', '')",
            ("generating" if active else "completed",),
        )
        db.execute(
            "INSERT INTO manual_reply_turns VALUES (?, 200, 'reply-one', '', '')",
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


def test_handoff_guard_refuses_unknown_dispatches(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    make_databases(tmp_path, active=True)
    with pytest.raises(TimeoutError, match="running_deliveries=1, unidentified_captures=1"):
        deploy_guarded.wait_for_recoverable_handoff(gate, timeout=0)


def test_handoff_guard_allows_verified_generation_without_wait(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    make_databases(tmp_path, active=True)
    with sqlite3.connect(tmp_path / "ui-send-jobs.sqlite3") as db:
        db.execute("UPDATE job_deliveries SET status='succeeded'")
    with sqlite3.connect(tmp_path / "chat-results.sqlite3") as db:
        db.execute("UPDATE job_responses SET conversation_id='verified-chat'")
        db.execute("UPDATE manual_reply_turns SET conversation_id='verified-chat', "
                   "parent_id='verified-parent'")
    deploy_guarded.wait_for_recoverable_handoff(gate, timeout=0)


def test_handoff_guard_refuses_unconfirmed_reply(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    make_databases(tmp_path)
    with sqlite3.connect(tmp_path / "chat-results.sqlite3") as db:
        db.execute("UPDATE manual_reply_turns SET status='dispatching', "
                   "conversation_id='verified-chat', parent_id='verified-parent'")
    with pytest.raises(TimeoutError, match="unverified_replies=1"):
        deploy_guarded.wait_for_recoverable_handoff(gate, timeout=0)


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


def test_shutdown_interrupts_application_owners(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import rolling_deploy

    monkeypatch.setattr(rolling_deploy, "all_worker_units", lambda: rolling_deploy.LEGACY_WORKERS)
    commands: list[tuple[str, ...]] = []

    def fake_run(args: list[str], **_kwargs: object) -> object:
        commands.append(tuple(args))
        return type("Result", (), {"returncode": 0, "stdout": "inactive"})()

    monkeypatch.setattr(deploy_guarded.subprocess, "run", fake_run)
    deploy_guarded.stop_workers()
    assert commands[0] == ("systemctl", "--user", "stop", "--no-block", *rolling_deploy.FRONTENDS, *rolling_deploy.LEGACY_WORKERS)
    assert commands[1] == (
        "systemctl", "--user", "kill", "--signal=SIGKILL", "--kill-whom=all",
        *rolling_deploy.FRONTENDS, *rolling_deploy.LEGACY_WORKERS,
    )
    assert all("prompta-browser.service" not in command for command in commands)


def test_shutdown_failure_prevents_checkout_update(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import rolling_deploy

    monkeypatch.setattr(rolling_deploy, "all_worker_units", lambda: rolling_deploy.LEGACY_WORKERS)
    monkeypatch.setattr(
        deploy_guarded.subprocess, "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0})(),
    )
    with pytest.raises(TimeoutError, match="did not stop"):
        deploy_guarded.stop_workers(timeout=0)


def test_refuses_to_take_over_existing_pause(tmp_path: Path) -> None:
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")
    deploy_guarded.request_pause(gate)
    with pytest.raises(FileExistsError):
        deploy_guarded.request_pause(gate)
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


def test_deploy_recovery_holds_capacity_until_idle_timeout(tmp_path: Path) -> None:
    from prompta.response_capture import CaptureResult
    from prompta.response_store import ResponseStore

    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    send_id = "manual-deploy"
    conversation = "12345678-1234-4123-8123-123456789abc"
    store.ensure_queued(send_id, "Original prompt", now=10)
    assert store.accept(send_id, "999999999:dead", deadline=10000, now=11)
    assert store.bind_conversation_route(send_id, "999999999:dead", "/c/" + conversation, now=12)
    store.prepare_deployment_recovery((send_id,), (), now=20)
    assert store.recover_orphans(now=21) == 0
    record = store.get(send_id)
    assert record is not None and record["status"] == "generating"
    assert store.active_capture_send_ids(now=919) == {send_id}
    candidate = store.next_history_recovery(now=21)
    assert candidate is not None and candidate["send_id"] == send_id
    # A clean read, even if a spinner is visible, is not new progress.
    store.observe_history_generating(send_id, conversation, now=900)
    assert store.active_capture_send_ids(now=919) == {send_id}
    assert store.recover_orphans(now=920) == 1
    assert store.active_capture_send_ids(now=920) == set()
    record = store.get(send_id)
    assert record is not None and record["status"] == "interrupted"
    assert store.recover_historical_response(
        send_id, CaptureResult("dom", "complete", "Recovered", conversation, None, None, "turn"),
        now=1801,
    )


def test_history_rechecks_do_not_reanimate_or_renew_idle_capture(tmp_path: Path) -> None:
    from prompta.response_capture import CaptureResult
    from prompta.response_store import ResponseStore

    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    send_id = "manual-stuck"
    conversation = "12345678-1234-4123-8123-123456789abc"
    store.ensure_queued(send_id, "Original prompt", now=10)
    assert store.accept(send_id, "999999999:dead", deadline=10000, now=11)
    assert store.bind_conversation_route(
        send_id, "999999999:dead", "/c/" + conversation, now=12,
    )
    store.prepare_deployment_recovery((send_id,), (), now=20)

    # Initial verified history read may record one short-lived observation.
    assert store.observe_history_generating(send_id, conversation, now=100)
    # The same loaded page cannot keep extending it or the capture lease.
    assert store.observe_history_generating(send_id, conversation, now=800)
    row = store.get(send_id)
    assert row is not None and row["live_observed_at"] == 100
    assert row["capture_deadline"] == 920

    partial = CaptureResult(
        "dom", "partial", "Actual new text", conversation, None, None, "turn",
        verified_generating=True, verified_loaded=True,
    )
    assert store.recover_historical_response(send_id, partial, now=810)
    row = store.get(send_id)
    assert row is not None and row["capture_deadline"] == 1710
    assert row["live_observed_at"] == 810
    assert store.recover_historical_response(send_id, partial, now=1600)
    assert store.observe_history_generating(send_id, conversation, now=1601)
    row = store.get(send_id)
    assert row is not None and row["capture_deadline"] == 1710
    assert row["live_observed_at"] == 810
    assert store.recover_orphans(now=1710) == 1
    assert store.observe_history_generating(send_id, conversation, now=1800)
    row = store.get(send_id)
    assert row is not None and row["status"] == "interrupted"
    assert row["live_observed_at"] == 810


def test_repeated_deploy_preserves_ownerless_idle_deadline_and_terminal_status(
    tmp_path: Path,
) -> None:
    from prompta.response_store import ResponseStore

    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    store.ensure_queued("stalled", "Prompt", now=10)
    assert store.accept("stalled", "999999999:dead", deadline=10000, now=11)
    store.prepare_deployment_recovery(("stalled",), (), now=20)
    first = store.get("stalled")
    assert first is not None and first["capture_deadline"] == 920
    assert first["capture_owner"] == ""

    # Old deploy inventories still list this as generating. It is not owned.
    store.prepare_deployment_recovery(("stalled",), (), now=850)
    unchanged = store.get("stalled")
    assert unchanged is not None and unchanged["capture_deadline"] == 920
    assert store.recover_orphans(now=920) == 1
    store.prepare_deployment_recovery(("stalled",), (), now=1000)
    terminal = store.get("stalled")
    assert terminal is not None and terminal["status"] == "interrupted"
    assert terminal["capture_deadline"] == 920


def test_repeated_partial_snapshot_does_not_extend_recovery_slot(tmp_path: Path) -> None:
    from prompta.response_capture import CaptureResult
    from prompta.response_store import ResponseStore

    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    store.ensure_queued("manual-deploy", "Prompt", now=10)
    assert store.accept("manual-deploy", "999999999:dead", deadline=10000, now=11)
    conversation = "12345678-1234-4123-8123-123456789abc"
    assert store.bind_conversation_route("manual-deploy", "999999999:dead", "/c/" + conversation, now=12)
    store.prepare_deployment_recovery(("manual-deploy",), (), now=20)
    partial = CaptureResult("dom", "partial", "Partial", conversation, None, None, "turn")
    assert store.recover_historical_response("manual-deploy", partial, now=100)
    assert store.recover_historical_response("manual-deploy", partial, now=999)
    assert store.recover_orphans(now=1000) == 1
