from __future__ import annotations

import argparse
import asyncio
import logging
import time
from pathlib import Path

from .control_server import ControlUnavailableError
from .core import (
    DEFAULT_STATE_PATH,
    _daemon_is_running,
    _send_once_via_control,
    _send_reply_via_control,
)
from .delivery_queue import DeliveryQueueStore
from .image_previews import ImagePreviewStore
from .send_jobs import SendJobRegistry

logger = logging.getLogger(__name__)


def _control_sender(
    state_path: Path,
    operation: str,
    message: str,
    conversation_id: str,
    attachments: list[str],
) -> str:
    if not _daemon_is_running(state_path):
        raise ControlUnavailableError("Prompta scheduler control socket is unavailable")
    if operation == "once":
        return asyncio.run(_send_once_via_control(state_path, message, attachments))
    return asyncio.run(
        _send_reply_via_control(
            state_path,
            conversation_id,
            message,
            attachments,
            defer_if_busy=True,
        )
    )


def _reconcile_completed_previews(
    queue: DeliveryQueueStore,
    previews: ImagePreviewStore,
) -> None:
    for record in queue.records():
        if str(record.get("status") or "") != "succeeded":
            continue
        client_id = str(record.get("client_id") or "")
        conversation_id = str(record.get("conversation_id") or "")
        if not client_id or not conversation_id:
            continue
        previews.bind(
            client_id,
            conversation_id,
            str(record.get("message") or ""),
        )


def run(state_path: Path = DEFAULT_STATE_PATH) -> None:
    state_path = state_path.expanduser()
    state_dir = state_path.parent
    queue_path = state_dir / "ui-send-jobs.sqlite3"
    previews = ImagePreviewStore(state_dir)
    queue = DeliveryQueueStore(queue_path)
    registry = SendJobRegistry(
        lambda operation, message, conversation_id, attachments: _control_sender(
            state_path,
            operation,
            message,
            conversation_id,
            attachments,
        ),
        recovery_path=state_dir / "ui-send-retries.json",
        queue_path=queue_path,
        on_success=previews.bind,
        consume=True,
    )
    logger.info("Prompta delivery worker consuming %s", queue_path)
    try:
        while True:
            _reconcile_completed_previews(queue, previews)
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        registry.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Prompta durable delivery worker")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.state)


if __name__ == "__main__":
    main()
