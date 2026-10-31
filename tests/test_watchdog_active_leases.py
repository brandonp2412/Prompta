"""The watchdog must never restart a browser with another live send lease."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from prompta.browser_watchdog import delivery_in_flight


def _db(path: Path, schema: str, rows: list[tuple[object, ...]], insert: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(schema)
        connection.executemany(insert, rows)


def _runtime(tmp_path: Path, activity: str = "", started: float | str = 0) -> Path:
    path = tmp_path / "runtime.sqlite3"
    _db(
        path,
        "CREATE TABLE service_health (service TEXT, activity TEXT, activity_started_at REAL)",
        [("delivery_worker", activity, started)],
        "INSERT INTO service_health VALUES (?, ?, ?)",
    )
    return path


@pytest.mark.parametrize("status, deadline, expected", [
    ("running", 1200.0, True),
    ("running", 1000.0, False),
    ("succeeded", 1200.0, False),
    ("retrying", 1200.0, False),
])
def test_queue_lease_survives_concurrent_health_overwrite(
    tmp_path: Path, status: str, deadline: float, expected: bool,
) -> None:
    runtime = _runtime(tmp_path)
    _db(
        tmp_path / "ui-send-jobs.sqlite3",
        "CREATE TABLE job_deliveries "
        "(status TEXT, lease_owner TEXT, lease_expires_at REAL)",
        [(status, "worker-a", deadline)],
        "INSERT INTO job_deliveries VALUES (?, ?, ?)",
    )
    assert delivery_in_flight(runtime, 1100.0) is expected


@pytest.mark.parametrize("status, deadline, expected", [
    ("dispatching", 1200.0, True),
    ("accepted", 1200.0, True),
    ("generating", 1200.0, True),
    ("completed", 1200.0, False),
    ("dispatching", 1000.0, False),
])
def test_manual_reply_lease_blocks_browser_restart(
    tmp_path: Path, status: str, deadline: float, expected: bool,
) -> None:
    runtime = _runtime(tmp_path)
    with sqlite3.connect(tmp_path / "chat-results.sqlite3") as connection:
        connection.execute(
            "CREATE TABLE manual_reply_turns "
            "(status TEXT, lease_owner TEXT, lease_deadline REAL)"
        )
        connection.execute(
            "CREATE TABLE job_responses "
            "(status TEXT, capture_owner TEXT, capture_deadline REAL)"
        )
        connection.execute(
            "INSERT INTO manual_reply_turns VALUES (?, ?, ?)",
            (status, "reply-worker", deadline),
        )
    assert delivery_in_flight(runtime, 1100.0) is expected


@pytest.mark.parametrize("status, deadline, expected", [
    ("accepted", 1200.0, True),
    ("generating", 1200.0, True),
    ("interrupted", 1200.0, False),
    ("accepted", 1000.0, False),
])
def test_passive_capture_lease_blocks_browser_restart(
    tmp_path: Path, status: str, deadline: float, expected: bool,
) -> None:
    runtime = _runtime(tmp_path)
    with sqlite3.connect(tmp_path / "chat-results.sqlite3") as connection:
        connection.execute(
            "CREATE TABLE manual_reply_turns "
            "(status TEXT, lease_owner TEXT, lease_deadline REAL)"
        )
        connection.execute(
            "CREATE TABLE job_responses "
            "(status TEXT, capture_owner TEXT, capture_deadline REAL)"
        )
        connection.execute(
            "INSERT INTO job_responses VALUES (?, ?, ?)",
            (status, "capture-worker", deadline),
        )
    assert delivery_in_flight(runtime, 1100.0) is expected


def test_recent_health_activity_still_blocks_without_lease(tmp_path: Path) -> None:
    assert delivery_in_flight(_runtime(tmp_path, "dispatch:send", 1080.0), 1100.0)


def test_corrupt_lease_database_fails_closed(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    (tmp_path / "ui-send-jobs.sqlite3").write_bytes(b"not sqlite")
    assert delivery_in_flight(runtime, 1100.0)


def test_invalid_health_timestamp_fails_closed(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, "dispatch:send", "invalid")
    assert delivery_in_flight(runtime, 1100.0)


def test_absent_optional_lease_databases_do_not_block(tmp_path: Path) -> None:
    assert not delivery_in_flight(_runtime(tmp_path), 1100.0)


def test_watchdog_skips_restart_until_durable_lease_expires(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two failed CDP probes cannot trump another worker's active send."""
    from types import SimpleNamespace

    import prompta.browser_watchdog as watchdog

    _runtime(tmp_path)
    _db(
        tmp_path / "ui-send-jobs.sqlite3",
        "CREATE TABLE job_deliveries "
        "(status TEXT, lease_owner TEXT, lease_expires_at REAL)",
        [("running", "other-worker", 1200.0)],
        "INSERT INTO job_deliveries VALUES (?, ?, ?)",
    )
    clock = [1100.0]
    calls: list[list[str]] = []
    monkeypatch.setattr(watchdog, "STATE_DIR", tmp_path)
    monkeypatch.setattr(watchdog, "STATE_FILE", tmp_path / "watchdog.json")
    monkeypatch.setattr(watchdog.time, "time", lambda: clock[0])
    monkeypatch.setattr(watchdog, "debugger_responding", lambda address: False)
    monkeypatch.setattr(
        watchdog.subprocess, "run",
        lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0),
    )
    watchdog.main()
    watchdog.main()
    assert calls == []

    # The browser can recover after the durable lease has genuinely expired.
    clock[0] = 1201.0
    watchdog.main()
    assert calls == [
        ["systemctl", "--user", "is-active", "--quiet", "prompta-browser.service"],
        ["systemctl", "--user", "restart", "prompta-browser.service"],
    ]


def test_unreadable_lease_path_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    original_exists = Path.exists

    def exists(path: Path) -> bool:
        if path.name == "ui-send-jobs.sqlite3":
            raise PermissionError("lease database inaccessible")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", exists)
    assert delivery_in_flight(runtime, 1100.0)
