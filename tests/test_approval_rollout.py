from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest


def test_rollout_waits_for_live_capture_and_manual_reply_leases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    rollout = importlib.import_module("scripts.approval_rollout_when_idle")
    monkeypatch.setattr(rollout, "STATE_DIR", tmp_path)
    with sqlite3.connect(tmp_path / "chat-results.sqlite3") as db:
        db.execute(
            "CREATE TABLE job_responses "
            "(status TEXT, capture_deadline REAL, capture_owner TEXT)"
        )
        db.execute(
            "CREATE TABLE manual_reply_turns "
            "(status TEXT, lease_deadline REAL)"
        )
        db.execute(
            "INSERT INTO job_responses VALUES ('generating', 200, 'worker')"
        )
        db.execute(
            "INSERT INTO manual_reply_turns VALUES ('dispatching', 200)"
        )
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as db:
        db.execute("CREATE TABLE service_health (service TEXT, activity TEXT)")
        db.execute("INSERT INTO service_health VALUES ('delivery_worker', 'dispatch:active')")

    assert rollout.active_work(100) == (1, 1, True)

    with sqlite3.connect(tmp_path / "chat-results.sqlite3") as db:
        db.execute("UPDATE job_responses SET status='completed'")
        db.execute("UPDATE manual_reply_turns SET status='completed'")
    with sqlite3.connect(tmp_path / "runtime.sqlite3") as db:
        db.execute("UPDATE service_health SET activity=''")

    assert rollout.active_work(100) == (0, 0, False)
