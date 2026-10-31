from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

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


def test_expired_delivery_lease_is_quarantined_and_renewal_extends_it(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())

    first = store.claim_next("worker-a", now=100.0, lease_seconds=10.0)
    assert first is not None
    assert first["lease_expires_at"] == 110.0
    assert store.renew_lease("send-1", "worker-a", now=105.0, lease_seconds=10.0)
    assert store.claim_next("worker-b", now=111.0, lease_seconds=10.0) is None

    assert store.claim_next("worker-b", now=116.0, lease_seconds=10.0) is None
    unknown = store.get("send-1")
    assert unknown is not None
    assert unknown["status"] == "outcome_unknown"
    assert unknown["lease_owner"] == ""
    assert "Automatic resubmission is disabled" in str(unknown["last_error"])
    assert store.health_metrics(now=117.0)["outcome_unknown"] == 1
    assert store.claim_next("worker-c", now=117.0, lease_seconds=10.0) is None


def test_expired_leases_are_quarantined_without_any_new_claim(tmp_path: Path) -> None:
    """Even during admission backoff, an expired send must not stay running."""
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record("expired", client_id="manual:expired"))
    store.upsert(_queued_record("active", client_id="manual:active"))
    assert store.claim_next("worker-a", now=100.0, lease_seconds=10.0) is not None
    assert store.claim_next("worker-b", now=100.0, lease_seconds=30.0) is not None

    assert store.expire_leases(now=110.0) == 1
    assert store.expire_leases(now=110.0) == 0

    expired = store.get("expired")
    active = store.get("active")
    assert expired is not None and expired["status"] == "outcome_unknown"
    assert expired["lease_owner"] == ""
    assert expired["finished_at"] == 110.0
    assert active is not None and active["status"] == "running"
    assert store.renew_lease("active", "worker-b", now=111.0, lease_seconds=30.0)
    assert store.claim_next("worker-c", now=111.0, lease_seconds=30.0) is None


def test_expired_lease_sweep_preserves_accepted_response(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())
    assert store.claim_next("worker-a", now=100.0, lease_seconds=10.0) is not None
    assert store.results.accept("send-1", "capture-owner", deadline=500.0, now=101.0)

    assert store.expire_leases(now=110.0) == 1
    accepted = store.results.get("send-1")
    assert accepted is not None
    assert accepted["status"] == "accepted"
    assert accepted["accepted_at"] == 101.0
    delivery = store.get("send-1")
    assert delivery is not None and delivery["status"] == "succeeded"
    assert delivery["last_error"] == ""
    assert store.claim_next("worker-b", now=111.0, lease_seconds=10.0) is None


def test_acceptance_recorded_after_quarantine_reconciles_without_replay(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())
    assert store.claim_next("worker-a", now=100.0, lease_seconds=10.0) is not None

    assert store.expire_leases(now=110.0) == 1
    unknown = store.get("send-1")
    assert unknown is not None and unknown["status"] == "outcome_unknown"
    assert store.results.accept("send-1", "late-capture", deadline=500.0, now=111.0)

    assert store.expire_leases(now=112.0) == 0
    reconciled = store.get("send-1")
    assert reconciled is not None and reconciled["status"] == "succeeded"
    assert reconciled["last_error"] == ""
    assert store.expire_leases(now=113.0) == 0
    assert store.claim_next("worker-b", now=114.0, lease_seconds=10.0) is None


def test_unknown_receipt_without_acceptance_proof_remains_quarantined(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())
    assert store.claim_next("worker-a", now=100.0, lease_seconds=10.0) is not None

    assert store.expire_leases(now=110.0) == 1
    assert store.reconcile_accepted_outcomes(now=200.0) == 0
    unknown = store.get("send-1")
    assert unknown is not None and unknown["status"] == "outcome_unknown"
    assert store.claim_next("worker-b", now=201.0, lease_seconds=10.0) is None


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


def test_health_metrics_separate_confirmed_failures_from_unknown_outcomes(
    tmp_path: Path,
) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    for send_id, status in (
        ("successful", "succeeded"),
        ("failed", "dead_lettered"),
        ("unknown", "outcome_unknown"),
        ("cancelled", "cancelled"),
    ):
        store.upsert(
            {
                **_queued_record(send_id, client_id=f"client-{send_id}"),
                "status": status,
            }
        )

    metrics = store.health_metrics(now=20.0)

    assert metrics["succeeded"] == 1
    assert metrics["dead_lettered"] == 1
    assert metrics["outcome_unknown"] == 1
    assert metrics["cancelled"] == 1


def test_delivery_queue_creates_jobs_only_lookup_indexes(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    indexes = {str(index["name"]) for index in inspect(store.engine).get_indexes("job_deliveries")}

    assert "job_deliveries_claimable" in indexes
    assert "job_deliveries_client_id" in indexes


def test_pending_scheduled_prefixes_are_literal_not_sql_wildcards(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    names = ("stage_under", "stageXunder", "rate%target", "rateXtarget", r"slash\name", "slashXname")
    for index, name in enumerate(names):
        store.upsert(_queued_record(f"send-{index}", client_id=f"scheduled:key:{name}"))

    assert store.pending_scheduled_send_ids(("stage_",)) == {"send-0"}
    assert store.pending_scheduled_send_ids(("rate%",)) == {"send-2"}
    assert store.pending_scheduled_send_ids(("slash\\",)) == {"send-4"}
    assert store.pending_scheduled_send_ids(("stage_", "rate%", "slash\\")) == {
        "send-0", "send-2", "send-4"
    }
    assert store.pending_scheduled_send_ids(()) == set()
    assert len(store.pending_scheduled_send_ids()) == len(names)


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


def test_expired_delivery_lease_is_not_resent_at_exact_boundary(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())
    assert store.claim_next("worker-a", now=100.0, lease_seconds=10.0) is not None

    assert store.claim_next("worker-b", now=110.0, lease_seconds=10.0) is None
    unknown = store.get("send-1")
    assert unknown is not None
    assert unknown["status"] == "outcome_unknown"
    assert unknown["finished_at"] == 110.0
    assert unknown["lease_acquired_at"] == 0.0
    assert not store.complete_claim("send-1", "worker-a", now=111.0)


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


def test_manual_claim_prioritized_and_restricted_during_closed_hours(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    queue.upsert(_queued_record("scheduled-1", client_id="scheduled:key:job"))
    assert queue.claim_next("worker", now=15.0, lease_seconds=30, manual_only=True) is None
    first = queue.enqueue_manual("Just once", now=11.0)
    manual = queue.claim_next("worker", now=15.0, lease_seconds=30, manual_only=True)
    assert manual is not None and manual["send_id"] == first["send_id"]
    scheduled = queue.claim_next("worker", now=15.0, lease_seconds=30, manual_only=True)
    assert scheduled is None
    scheduled = queue.claim_next("worker", now=15.0, lease_seconds=30)
    assert scheduled is not None and scheduled["send_id"] == "scheduled-1"


def test_manual_claim_has_priority_over_old_scheduled_backlog(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    queue.upsert(_queued_record("scheduled-old", client_id="scheduled:key:job"))
    manual = queue.enqueue_manual("Now", now=12.0)
    claimed = queue.claim_next("worker", now=12.0, lease_seconds=30)
    assert claimed is not None and claimed["send_id"] == manual["send_id"]


def test_non_ui_manual_queue_does_not_pin_local_sidebar_by_default(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    receipt = queue.enqueue_manual("Manual CLI or job run", now=12.0)
    assert receipt["pin_chat"] is False
    assert queue.results.local_pinned_runs() == []


def test_expired_running_delivery_does_not_block_new_work(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record("old", client_id="client-old"))
    store.upsert(_queued_record("new", client_id="client-new"))
    first = store.claim_next("worker-a", now=100.0, lease_seconds=10.0)
    assert first is not None and first["send_id"] == "old"
    next_claim = store.claim_next("worker-b", now=110.0, lease_seconds=10.0)
    assert next_claim is not None and next_claim["send_id"] == "new"
    old = store.get("old")
    new = store.get("new")
    assert old is not None and old["status"] == "outcome_unknown"
    assert new is not None and new["status"] == "running"


def test_expired_owner_cannot_requeue_or_reclassify_uncertain_send(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    for send_id in ("retry", "failed", "complete"):
        store.upsert(_queued_record(send_id, client_id=send_id))
        assert store.claim_next("worker-a", now=100.0, lease_seconds=10.0) is not None
        # Restore the other rows to terminal states so each claim stays isolated.
        # Every mutation below happens at the exact lease-expiry boundary.
        if send_id == "retry":
            assert not store.retry_claim(
                send_id, "worker-a", retry_at=111.0, retry_attempt=1,
                error="backend unavailable", now=110.0,
            )
        elif send_id == "failed":
            assert not store.fail_claim(
                send_id, "worker-a", status="dead_lettered",
                error="too many failures", now=110.0,
            )
        else:
            assert not store.complete_claim(send_id, "worker-a", now=110.0)
        running = store.get(send_id)
        assert running is not None and running["status"] == "running"
        # A scan quarantines the receipt, but must never claim the expired send.
        assert store.claim_next("worker-b", now=110.0, lease_seconds=10.0) is None
        unknown = store.get(send_id)
        assert unknown is not None and unknown["status"] == "outcome_unknown"


def test_lease_can_be_committed_until_but_not_at_expiry(tmp_path: Path) -> None:
    store = DeliveryQueueStore(tmp_path / "delivery.sqlite3")
    store.upsert(_queued_record())
    assert store.claim_next("worker-a", now=100.0, lease_seconds=10.0)
    assert store.complete_claim("send-1", "worker-a", now=109.999)


@pytest.mark.parametrize("operation", ["cancel", "fail"])
@pytest.mark.parametrize("failure", [OSError("results disk unavailable"), SQLAlchemyError("results database locked")])
def test_terminal_receipt_survives_result_projection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, failure: Exception,
) -> None:
    queue = DeliveryQueueStore(tmp_path / "queue.sqlite3")
    queue.upsert(_queued_record())
    if operation == "fail":
        record = queue.claim_next("owner", now=11.0, lease_seconds=30.0)
        assert record is not None

    def unavailable(_send_id: str) -> None:
        raise failure

    monkeypatch.setattr(queue.results, "unavailable", unavailable)
    if operation == "cancel":
        assert queue.cancel_pending("send-1", now=12.0)
        status = "cancelled"
    else:
        assert queue.fail_claim(
            "send-1", "owner", status="outcome_unknown", error="uncertain", now=12.0,
        )
        status = "outcome_unknown"

    committed = queue.get("send-1")
    assert committed is not None and committed["status"] == status
    assert queue.claim_next("another", now=50.0, lease_seconds=30.0) is None
