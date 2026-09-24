from __future__ import annotations

from pathlib import Path

from prompta.delivery_queue import DeliveryQueueStore
from prompta.delivery_worker import DeliveryAdmission
from prompta.jobs import add_job
from prompta.rate_limit import RateLimitError
from prompta.resource_pressure import ResourceAdmission
from prompta.scheduler_runtime import SchedulerRuntime
from prompta.scheduler_service import DurableSchedulerProducer
from prompta.send_jobs import SendJobRegistry
from prompta.service_health import ServiceHealthStore


class _StaticResourceAdmission(ResourceAdmission):
    def __init__(self, allowed: bool, reason: str = "") -> None:
        self.allowed = allowed
        self.reason = reason

    def __call__(self) -> tuple[bool, str]:
        return self.allowed, self.reason


def _delivery(send_id: str = "send-1") -> dict[str, object]:
    return {
        "send_id": send_id,
        "operation": "once",
        "message": "failure injection",
        "client_id": f"client-{send_id}",
        "status": "queued",
    }


def test_ui_restart_preserves_durable_delivery_without_consumer_thread(tmp_path: Path) -> None:
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    first = SendJobRegistry(None, queue_path=queue_path, consume=False)
    submitted = first.submit(operation="once", message="hello", client_id="client-ui")
    assert first._worker is None
    first.close()

    restarted = SendJobRegistry(None, queue_path=queue_path, consume=False)
    try:
        recovered = restarted.get(submitted["send_id"])
        assert restarted._worker is None
        assert recovered is not None
        assert recovered["status"] == "queued"
        assert recovered["message"] == "hello"
    finally:
        restarted.close()


def test_scheduler_restart_does_not_duplicate_enqueued_occurrence(tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.sqlite3"
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    add_job(
        runtime_path,
        "restart-once",
        "scheduled work",
        0,
        exact_interval=True,
        run_at_epoch=1000.0,
    )

    first = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    assert first.tick(now=1000.0) == 1
    restarted = DurableSchedulerProducer(runtime_path, runtime_path, queue_path)
    assert restarted.tick(now=1001.0) == 0
    assert len(restarted.queue.records()) == 1


def test_delivery_worker_kill_mid_lease_reclaims_only_after_expiry(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    queue.enqueue_idempotent(_delivery())

    first = queue.claim_next("worker-a", now=100.0, lease_seconds=10.0)
    assert first is not None
    assert queue.claim_next("worker-b", now=109.9, lease_seconds=10.0) is None

    reclaimed = queue.claim_next("worker-b", now=110.1, lease_seconds=10.0)
    assert reclaimed is not None
    assert reclaimed["send_id"] == first["send_id"]
    assert reclaimed["lease_owner"] == "worker-b"


def test_conversation_worker_restart_preserves_mid_poll_activity(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    first = ServiceHealthStore(path)
    assert first.begin_activity("conversation_worker", "poll", now=200.0)

    restarted = ServiceHealthStore(path)
    state = restarted.snapshot(now=205.0)
    assert state["conversation_worker"]["activity"] == "poll"
    assert state["conversation_worker"]["activity_age_seconds"] == 5.0


def test_browser_outage_isolated_from_other_component_health(tmp_path: Path) -> None:
    health = ServiceHealthStore(tmp_path / "runtime.sqlite3")
    for service in ("ui", "scheduler", "delivery_worker", "conversation_worker"):
        assert health.beat(service, now=300.0)

    snapshot = health.snapshot(now=301.0)
    assert snapshot["browser"]["stale"] is True
    assert snapshot["ui"]["stale"] is False
    assert snapshot["scheduler"]["stale"] is False
    assert snapshot["delivery_worker"]["stale"] is False
    assert snapshot["conversation_worker"]["stale"] is False


def test_rate_limit_survives_delivery_worker_restart(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    runtime = SchedulerRuntime(path, path)
    runtime.record_global_rate_limit(RateLimitError("temporary account limit", retry_after=60))

    restarted = SchedulerRuntime(path, path)
    admission = DeliveryAdmission(restarted, resource_admission=_StaticResourceAdmission(True))
    allowed, reason = admission()
    assert allowed is False
    assert "temporary account limit" in reason
    assert restarted.account_admission_status()["kind"] == "rate_limit"


def test_resource_pressure_is_persisted_without_consuming_queue(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    runtime = SchedulerRuntime(path, path)
    admission = DeliveryAdmission(
        runtime, resource_admission=_StaticResourceAdmission(False, "memory pressure")
    )
    assert admission() == (False, "memory pressure")

    restarted = SchedulerRuntime(path, path)
    status = restarted.account_admission_status()
    assert status["blocked"] is True
    assert status["kind"] == "resource_pressure"
    assert status["reason"] == "memory pressure"


def test_committed_send_success_is_not_reclaimed_after_restarts(tmp_path: Path) -> None:
    path = tmp_path / "ui-send-jobs.sqlite3"
    queue = DeliveryQueueStore(path)
    _, created = queue.enqueue_idempotent(_delivery("accepted"))
    assert created is True

    claimed = queue.claim_next("worker-a", now=400.0, lease_seconds=10.0)
    assert claimed is not None
    assert queue.complete_claim(
        "accepted",
        "worker-a",
        conversation_id="chat-accepted",
        now=401.0,
    )

    restarted = DeliveryQueueStore(path)
    assert restarted.claim_next("worker-b", now=999.0, lease_seconds=10.0) is None
    existing, created = restarted.enqueue_idempotent(_delivery("accepted"))
    assert created is False
    assert existing["status"] == "succeeded"
    assert existing["conversation_id"] == "chat-accepted"
