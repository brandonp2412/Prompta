"""API-level regression for lost-lease recovery without a second ChatGPT send."""

from __future__ import annotations

from pathlib import Path

from test_web_results import get, server


def test_expired_delivery_appears_terminal_in_live_api_without_replay(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        app.queue.upsert({
            "send_id": "lost-receipt",
            "message": "Private synthetic test prompt",
            "client_id": "manual:test",
            "created_at": 10.0,
        })
        assert app.queue.claim_next("crashed-owner", now=100.0, lease_seconds=10.0)

        status, health_before, _ = get(port, "/api/health")
        assert status == 200
        queue_before = health_before["queue"]
        assert isinstance(queue_before, dict)
        assert queue_before.get("running") == 1

        # The maintenance sweep runs despite a blocked dispatch admission.
        assert app.queue.expire_leases(now=110.0) == 1
        status, health_after, _ = get(port, "/api/health")
        assert status == 200
        queue_after = health_after["queue"]
        assert isinstance(queue_after, dict)
        assert queue_after.get("running") == 0
        assert queue_after.get("outcome_unknown") == 1

        status, detail, _ = get(port, "/api/results/lost-receipt")
        assert status == 200
        assert detail["status"] == "unavailable"
        assert app.queue.claim_next("another-worker", now=111.0, lease_seconds=30.0) is None

        # Health stays payload-free even while the UI can show the local receipt.
        assert "Private synthetic test prompt" not in str(health_after)
