from __future__ import annotations

from pathlib import Path

from sqlalchemy import insert

from prompta.delivery_queue import DeliveryQueueStore
from prompta.queue_eta import QueueEtaEstimator, SlotProjection
from prompta.response_store import results


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
