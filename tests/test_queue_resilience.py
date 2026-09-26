from __future__ import annotations

import sqlite3
import threading
from unittest.mock import Mock

import pytest

from prompta.delivery_state import exponential_retry_delay
from prompta.send_jobs import SendJobRegistry


@pytest.mark.parametrize("failure_stage", ["admission", "claim", "send"])
def test_consumer_survives_transient_failures(failure_stage: str) -> None:
    registry = object.__new__(SendJobRegistry)
    registry._stop_event = threading.Event()
    registry._work_event = threading.Event()
    registry._admission_reason = ""
    registry._admission = Mock(return_value=(True, ""))
    registry._next_database_task = Mock(return_value=("send-id",))
    completed = []

    def delivered(*args):
        completed.append(args)
        registry._stop_event.set()

    run_mock = Mock(side_effect=delivered)
    registry._run = run_mock
    failure = sqlite3.OperationalError("database is locked")
    if failure_stage == "admission":
        registry._admission.side_effect = [failure, (True, "")]
    elif failure_stage == "claim":
        registry._next_database_task.side_effect = [failure, ("send-id",)]
    else:

        def retry_send(*args):
            if run_mock.call_count == 1:
                raise failure
            delivered(*args)

        registry._run.side_effect = retry_send

    worker = threading.Thread(target=registry._worker_loop, daemon=True)
    worker.start()
    worker.join(timeout=5)
    registry._stop_event.set()
    worker.join(timeout=2)
    assert completed == [("send-id",)]


@pytest.mark.parametrize("attempt", [1025, 10000, 10**100])
def test_retry_backoff_stays_capped_during_prolonged_outage(attempt: int) -> None:
    assert exponential_retry_delay(attempt, base_seconds=2, cap_seconds=60) == 60


@pytest.mark.parametrize("attempt,expected", [(0, 2), (1, 2), (2, 4), (5, 32), (6, 60)])
def test_retry_backoff_preserves_initial_schedule(attempt: int, expected: float) -> None:
    assert exponential_retry_delay(attempt, base_seconds=2, cap_seconds=60) == expected
