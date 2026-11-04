from __future__ import annotations

from pathlib import Path

from sqlalchemy import insert

from prompta.delivery_queue import DeliveryQueueStore
from prompta.queue_eta import QueueEtaEstimator, SlotProjection
from prompta.reply_contracts import ManualReplyStore
from prompta.response_store import results
from prompta.scheduler_service import DurableSchedulerProducer


def test_slot_projection_waits_for_actual_capacity_and_preserves_order() -> None:
    projection = SlotProjection(2, [30, 100], 120)
    assert [projection.enqueue() for _ in range(4)] == [30, 100, 150, 220]
    # A cap lowered below the number of active runs drains the excess first.
    lowered = SlotProjection(1, [10, 20, 30], 120)
    assert lowered.enqueue() == 30


def test_queue_eta_learns_recent_completed_scheduled_capture_durations(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    with queue.results.engine.begin() as connection:
        for index, duration in enumerate((60, 120, 180)):
            connection.execute(
                insert(results).values(
                    send_id=f"complete-{index}",
                    job_name=f"scheduled-{index}",
                    user_text="Private test prompt",
                    status="completed",
                    created_at=100,
                    accepted_at=200,
                    updated_at=200 + duration,
                    finished_at=200 + duration,
                )
            )
        connection.execute(
            insert(results).values(
                send_id="active",
                job_name="scheduled-active",
                user_text="Another private test prompt",
                status="generating",
                created_at=900,
                accepted_at=950,
                updated_at=950,
                capture_owner="owner",
                capture_deadline=1500,
            )
        )
    estimator = QueueEtaEstimator(queue, now=1000, active_ids={"active"})
    assert estimator.samples == 3
    assert estimator.duration_seconds == 120
    assert estimator.remaining({"active"}) == [70]
    projection = estimator.projection(1, {"active"})
    assert [projection.enqueue(), projection.enqueue()] == [70, 190]

    # This capture has outlived every historical sample. The estimate must
    # not remain stuck at one minute until it eventually finishes.
    overdue = QueueEtaEstimator(queue, now=1200, active_ids={"active"})
    assert overdue.remaining({"active"}) == [120]


def test_queue_eta_uses_clearly_labelled_initial_estimate_without_history(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    estimator = QueueEtaEstimator(queue, now=1000, active_ids={"not-yet-accepted"})
    assert estimator.samples == 0
    assert estimator.duration_seconds == 600
    assert estimator.projection(1, {"not-yet-accepted"}).enqueue() == 600


def test_queue_snapshot_estimates_explicit_queued_followups_by_chat(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text("[concurrency]\nenabled = true\nmax_workers = 1\n", encoding="utf-8")
    scheduler = DurableSchedulerProducer(
        state_path, state_path, concurrency_config_path=config_path,
    )
    replies = ManualReplyStore(scheduler.queue.results.path)
    with scheduler.queue.results.engine.begin() as connection:
        for send_id in ("manual-first", "manual-second"):
            connection.execute(insert(results).values(
                send_id=send_id, job_name="", user_text="Private original prompt",
                status="completed", created_at=100, updated_at=200,
                conversation_id="conversation-123", message_id="verified-parent-123",
            ))
        connection.execute(insert(results).values(
            send_id="manual-active", job_name="", user_text="Active prompt",
            status="generating", created_at=900, accepted_at=950,
            updated_at=950, capture_owner="worker", capture_deadline=1500,
        ))
    replies.queue_followup("manual-first", "followup-first-111111", "First", now=1000)
    replies.queue_followup("manual-first", "followup-second-22222", "Second", now=1001)
    replies.queue_followup("manual-second", "followup-third-333333", "Third", now=1002)

    snapshot = scheduler.concurrency_queue_snapshot(now=1000, replies=replies)
    assert snapshot["occupied_slots"] == 1
    assert snapshot["waiting_runs"] == [
        {"send_id": "manual-first", "eta_seconds": 1150},
        {"send_id": "manual-second", "eta_seconds": 1750},
    ]
    # The shared queue has no fresh deliveries; reply-only work still gets ETAs.
    assert snapshot["waiting"] == []
    assert scheduler.concurrency_queue_snapshot(now=1000)["waiting_runs"] == []
