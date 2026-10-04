from __future__ import annotations

import concurrent.futures
from pathlib import Path

from prompta.delivery_queue import DeliveryQueueStore


def _queued_record(send_id: str = "send-1", *, client_id: str = "client-1") -> dict[str, object]:
    return {
        "send_id": send_id,
        "message": "hello",
        "client_id": client_id,
        "status": "queued",
        "created_at": 10.0,
    }


def test_only_one_live_claimant_owns_delivery(tmp_path: Path) -> None:
    path = tmp_path / "delivery.sqlite3"
    seed = DeliveryQueueStore(path)
    seed.upsert(_queued_record())

    def claim(owner: str) -> dict[str, object] | None:
        return DeliveryQueueStore(path).claim_next(owner, now=100.0, lease_seconds=30.0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ["worker-a", "worker-b"]))

    live = [claim for claim in claims if claim is not None]
    assert len(live) == 1
    assert live[0]["status"] == "running"
    assert live[0]["lease_owner"] in {"worker-a", "worker-b"}
    assert seed.claim_next("worker-c", now=110.0, lease_seconds=30.0) is None


def test_expired_delivery_lease_is_reclaimable_and_renewal_extends_it(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())

    first = store.claim_next("worker-a", now=100.0, lease_seconds=10.0)
    assert first is not None
    assert first["lease_expires_at"] == 110.0
    assert store.renew_lease("send-1", "worker-a", now=105.0, lease_seconds=10.0)
    assert store.claim_next("worker-b", now=111.0, lease_seconds=10.0) is None

    reclaimed = store.claim_next("worker-b", now=116.0, lease_seconds=10.0)
    assert reclaimed is not None
    assert reclaimed["send_id"] == "send-1"
    assert reclaimed["lease_owner"] == "worker-b"


def test_health_metrics_cover_pending_and_last_success(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())

    ready = store.health_metrics(now=20.0)
    assert ready["queued"] == 1
    assert ready["running"] == 0
    assert ready["oldest_pending_age_seconds"] == 10.0
    assert ready["last_successful_delivery_at"] == 0.0

    claimed = store.claim_next("worker-a", now=20.0, lease_seconds=90.0)
    assert claimed is not None
    leased = store.health_metrics(now=25.0)
    assert leased["queued"] == 0
    assert leased["running"] == 1
    assert leased["oldest_pending_age_seconds"] == 15.0

    assert store.complete_claim("send-1", "worker-a", now=30.0)
    completed = store.health_metrics(now=31.0)
    assert completed["running"] == 0
    assert completed["oldest_pending_age_seconds"] == 0.0
    assert completed["last_successful_delivery_at"] == 30.0


def test_delivery_queue_creates_jobs_only_lookup_indexes(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    connection = store.connect()
    indexes = {
        str(row["name"])
        for row in connection.execute("PRAGMA index_list(job_deliveries)").fetchall()
    }
    connection.close()

    assert "job_deliveries_claimable" in indexes
    assert "job_deliveries_client_id" in indexes


def test_completion_is_idempotent_and_rejects_stale_owner(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())
    assert store.claim_next("worker-a", now=100.0, lease_seconds=10.0) is not None

    assert not store.complete_claim("send-1", "worker-b", now=101.0)
    assert store.complete_claim("send-1", "worker-a", now=102.0)
    first = store.records()[0]
    assert first["status"] == "succeeded"
    assert first["finished_at"] == 102.0
    assert first["lease_owner"] == ""

    assert store.complete_claim("send-1", "stale-worker", now=200.0)
    again = store.records()[0]
    assert again["finished_at"] == 102.0


def test_expired_delivery_lease_is_reclaimable_at_exact_boundary(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())
    assert store.claim_next("worker-a", now=100.0, lease_seconds=10.0) is not None

    reclaimed = store.claim_next("worker-b", now=110.0, lease_seconds=10.0)

    assert reclaimed is not None
    assert reclaimed["lease_owner"] == "worker-b"
    assert reclaimed["lease_acquired_at"] == 110.0


def test_retry_backoff_controls_claim_eligibility(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())
    assert store.claim_next("worker-a", now=100.0, lease_seconds=30.0) is not None
    assert store.retry_claim(
        "send-1",
        "worker-a",
        retry_at=130.0,
        retry_attempt=2,
        error="temporary failure",
        now=101.0,
    )

    assert store.claim_next("worker-b", now=129.0, lease_seconds=30.0) is None
    claimed = store.claim_next("worker-b", now=130.0, lease_seconds=30.0)
    assert claimed is not None
    assert claimed["retry_attempt"] == 2
    assert claimed["lease_owner"] == "worker-b"


def test_cancel_pending_makes_delivery_unclaimable(tmp_path: Path) -> None:
    path = tmp_path / "delivery.sqlite3"
    queue = DeliveryQueueStore(path)
    queue.upsert(_queued_record())

    assert queue.cancel_pending("send-1", error="scheduled job removed", now=20.0) is True

    record = queue.get("send-1")
    assert record is not None
    assert record["status"] == "cancelled"
    assert record["last_error"] == "scheduled job removed"
    assert record["finished_at"] == 20.0
    assert queue.claim_next("worker", now=21.0, lease_seconds=30.0) is None
