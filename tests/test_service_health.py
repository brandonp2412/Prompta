from __future__ import annotations

import io
from unittest.mock import patch

from prompta.service_health import ServiceHealthStore, browser_page_count


def test_stale_heartbeat_is_explicitly_diagnosable(tmp_path) -> None:
    store = ServiceHealthStore(tmp_path / "runtime.sqlite3")
    assert store.beat("scheduler", now=100.0)

    snapshot = store.snapshot(now=131.0)

    assert snapshot["scheduler"]["heartbeat_at"] == 100.0
    assert snapshot["scheduler"]["heartbeat_age_seconds"] == 31.0
    assert snapshot["scheduler"]["stale"] is True
    assert snapshot["scheduler"]["stale_after_seconds"] == 20.0
    assert "conversation_worker" not in snapshot


def test_delivery_activity_age_survives_process_replacement(tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    first = ServiceHealthStore(path)
    assert first.begin_activity("delivery_worker", "dispatch:test", now=200.0)

    restarted = ServiceHealthStore(path)
    snapshot = restarted.snapshot(now=215.0)

    assert snapshot["delivery_worker"]["activity"] == "dispatch:test"
    assert snapshot["delivery_worker"]["activity_age_seconds"] == 15.0
    assert restarted.end_activity("delivery_worker", "dispatch:test", now=216.0)
    assert restarted.snapshot(now=216.0)["delivery_worker"]["activity"] == ""


def test_bounded_delivery_activity_is_not_reported_stale(tmp_path) -> None:
    store = ServiceHealthStore(tmp_path / "runtime.sqlite3")
    assert store.begin_activity("delivery_worker", "dispatch:opaque", now=200.0)

    during_delivery = store.snapshot(now=250.0)["delivery_worker"]
    near_handoff_deadline = store.snapshot(now=380.0)["delivery_worker"]
    after_delivery_deadline = store.snapshot(now=396.0)["delivery_worker"]

    assert during_delivery["heartbeat_age_seconds"] == 50.0
    assert during_delivery["activity_age_seconds"] == 50.0
    assert during_delivery["active"] is True
    assert during_delivery["stale"] is False
    assert near_handoff_deadline["active"] is True
    assert near_handoff_deadline["stale"] is False
    assert after_delivery_deadline["active"] is False
    assert after_delivery_deadline["stale"] is True


def test_worker_start_clears_orphaned_delivery_activity(tmp_path) -> None:
    store = ServiceHealthStore(tmp_path / "runtime.sqlite3")
    assert store.begin_activity("delivery_worker", "dispatch:opaque", now=200.0)

    assert store.reset_activity("delivery_worker", now=300.0)
    snapshot = store.snapshot(now=301.0)["delivery_worker"]

    assert snapshot["activity"] == ""
    assert snapshot["activity_age_seconds"] is None
    assert snapshot["active"] is False
    assert snapshot["stale"] is False


def test_browser_page_count_counts_only_pages() -> None:
    payload = io.BytesIO(b'[{"type":"page"},{"type":"service_worker"},{"type":"page"}]')
    with patch("prompta.service_health.urlopen", return_value=payload):
        reachable, count = browser_page_count()

    assert reachable is True
    assert count == 2
