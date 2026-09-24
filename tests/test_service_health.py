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


def test_activity_age_survives_process_replacement(tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    first = ServiceHealthStore(path)
    assert first.begin_activity("conversation_worker", "poll", now=200.0)

    restarted = ServiceHealthStore(path)
    snapshot = restarted.snapshot(now=215.0)

    assert snapshot["conversation_worker"]["activity"] == "poll"
    assert snapshot["conversation_worker"]["activity_age_seconds"] == 15.0
    assert restarted.end_activity("conversation_worker", "poll", now=216.0)
    assert restarted.snapshot(now=216.0)["conversation_worker"]["activity"] == ""


def test_browser_page_count_counts_only_pages() -> None:
    payload = io.BytesIO(b'[{"type":"page"},{"type":"service_worker"},{"type":"page"}]')
    with patch("prompta.service_health.urlopen", return_value=payload):
        reachable, count = browser_page_count()

    assert reachable is True
    assert count == 2
