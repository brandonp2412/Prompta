from __future__ import annotations

import concurrent.futures
import sqlite3
from pathlib import Path

from prompta.delivery_queue import DeliveryQueueStore


def _queued_record(send_id: str = "send-1", *, client_id: str = "client-1") -> dict[str, object]:
    return {
        "send_id": send_id,
        "operation": "once",
        "message": "hello",
        "conversation_id": "",
        "attachments": [],
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


def test_completion_is_idempotent_and_rejects_stale_owner(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())
    assert store.claim_next("worker-a", now=100.0, lease_seconds=10.0) is not None

    assert not store.complete_claim(
        "send-1",
        "worker-b",
        conversation_id="chat-wrong",
        now=101.0,
    )
    assert store.complete_claim(
        "send-1",
        "worker-a",
        conversation_id="chat-1",
        now=102.0,
    )
    first = store.records()[0]
    assert first["status"] == "succeeded"
    assert first["conversation_id"] == "chat-1"
    assert first["finished_at"] == 102.0
    assert first["lease_owner"] == ""

    assert store.complete_claim(
        "send-1",
        "worker-a",
        conversation_id="chat-1",
        now=200.0,
    )
    again = store.records()[0]
    assert again["finished_at"] == 102.0
    assert again["conversation_id"] == "chat-1"


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


def test_old_queue_schema_migrates_queued_and_retrying_rows(tmp_path: Path) -> None:
    path = tmp_path / "delivery.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE send_jobs (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            send_id TEXT NOT NULL UNIQUE,
            operation TEXT NOT NULL,
            message TEXT NOT NULL,
            conversation_id TEXT NOT NULL DEFAULT '',
            attachments_json TEXT NOT NULL DEFAULT '[]',
            client_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            retry_at REAL NOT NULL DEFAULT 0,
            retry_attempt INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            finished_at REAL NOT NULL DEFAULT 0
        );
        INSERT INTO send_jobs (
            send_id, operation, message, client_id, status, created_at, updated_at
        ) VALUES (
            'old-queued', 'once', 'queued payload', 'old-client-q', 'queued', 1, 1
        );
        INSERT INTO send_jobs (
            send_id, operation, message, client_id, status, created_at, updated_at,
            retry_at, retry_attempt, last_error
        ) VALUES (
            'old-retry', 'reply', 'retry payload', 'old-client-r', 'retrying', 2, 2,
            50, 3, 'temporary'
        );
        """
    )
    connection.commit()
    connection.close()

    store = DeliveryQueueStore(path)
    connection = store.connect()
    try:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(send_jobs)")}
    finally:
        connection.close()
    assert {"lease_owner", "lease_acquired_at", "lease_expires_at"} <= columns

    records = store.records()
    assert [record["send_id"] for record in records] == ["old-queued", "old-retry"]
    assert [record["client_id"] for record in records] == ["old-client-q", "old-client-r"]

    first = store.claim_next("worker-a", now=100.0, lease_seconds=30.0)
    assert first is not None
    assert first["send_id"] == "old-queued"
    assert store.complete_claim(
        "old-queued",
        "worker-a",
        conversation_id="chat-q",
        now=101.0,
    )
    second = store.claim_next("worker-b", now=102.0, lease_seconds=30.0)
    assert second is not None
    assert second["send_id"] == "old-retry"
    assert second["retry_attempt"] == 3
