import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from prompta.control_server import ControlUnavailableError
from prompta.delivery_queue import DeliveryQueueStore
from prompta.delivery_worker import _control_sender
from prompta.send_jobs import SendJobRegistry


def test_delivery_worker_classifies_missing_backend_as_control_outage(tmp_path: Path) -> None:
    with (
        patch("prompta.delivery_worker._daemon_is_running", return_value=False),
        pytest.raises(ControlUnavailableError, match="control socket is unavailable"),
    ):
        _control_sender(tmp_path / "runtime.sqlite3", "once", "Hello", "", [])


def test_delivery_worker_uses_control_socket_when_backend_is_running(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime.sqlite3"
    with (
        patch("prompta.delivery_worker._daemon_is_running", return_value=True),
        patch(
            "prompta.delivery_worker._send_once_via_control",
            AsyncMock(return_value="chat-control"),
        ) as control,
    ):
        result = _control_sender(state_path, "once", "Hello", "", [])

    assert result == "chat-control"
    control.assert_awaited_once_with(state_path, "Hello", [])


def _wait_for(predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_producer_only_registry_observes_external_completion(tmp_path: Path) -> None:
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    producer = SendJobRegistry(None, queue_path=queue_path, consume=False)
    try:
        submitted = producer.submit(
            operation="once",
            message="hello",
            client_id="client-1",
        )
        assert producer._worker is None

        queue = DeliveryQueueStore(queue_path)
        claimed = queue.claim_next("external-worker", lease_seconds=30.0)
        assert claimed is not None
        assert claimed["send_id"] == submitted["send_id"]
        assert queue.complete_claim(
            submitted["send_id"],
            "external-worker",
            conversation_id="chat-1",
        )

        observed = producer.get(submitted["send_id"])
        assert observed is not None
        assert observed["status"] == "succeeded"
        assert observed["conversation_id"] == "chat-1"
    finally:
        producer.close()


def test_worker_rechecks_lease_before_external_send(tmp_path: Path) -> None:
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    delivered = threading.Event()

    def sender(
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str],
    ) -> str:
        delivered.set()
        return "should-not-send"

    consumer = SendJobRegistry(sender, queue_path=queue_path, consume=True)
    producer = SendJobRegistry(None, queue_path=queue_path, consume=False)
    assert consumer._delivery_queue is not None
    try:
        with patch.object(consumer._delivery_queue, "renew_lease", return_value=False):
            producer.submit(
                operation="once",
                message="cancelled ownership",
                client_id="lease-check",
            )
            assert not delivered.wait(timeout=1.2)
    finally:
        producer.close()
        consumer.close()


def test_consumer_started_before_enqueue_claims_later_sqlite_work(tmp_path: Path) -> None:
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    delivered = threading.Event()
    calls: list[tuple[str, str, str, list[str]]] = []

    def sender(
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str],
    ) -> str:
        calls.append((operation, message, conversation_id, attachments))
        delivered.set()
        return "chat-created"

    consumer = SendJobRegistry(sender, queue_path=queue_path, consume=True)
    producer = SendJobRegistry(None, queue_path=queue_path, consume=False)
    try:
        submitted = producer.submit(
            operation="once",
            message="from another process",
            client_id="client-later",
        )

        assert delivered.wait(timeout=3.0)
        assert _wait_for(
            lambda: (producer.get(submitted["send_id"]) or {}).get("status") == "succeeded"
        )
        observed = producer.get(submitted["send_id"])
        assert observed is not None
        assert observed["conversation_id"] == "chat-created"
        assert calls == [("once", "from another process", "", [])]
        assert len(DeliveryQueueStore(queue_path).records()) == 1
    finally:
        producer.close()
        consumer.close()
