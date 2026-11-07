"""Durable explicit-reply owner, independent of the reloadable UI process.

Only user-clicked intents marked queued_by_user are eligible. This process
never decides to continue a chat or retransmit an ambiguous submission.
"""

from __future__ import annotations

import logging
import signal
import threading
import time
from pathlib import Path
from types import FrameType

from .deployment_gate import mark_worker_ready
from .fire_and_forget import enabled as fire_and_forget_enabled
from .logging_config import configure_logging
from .manual_reply_dispatch import ManualReplyDispatcher
from .persistence import DEFAULT_RUNTIME_PATH
from .reply_contracts import ManualReplyStore
from .service_health import ServiceHealthStore

logger = logging.getLogger(__name__)


def run(state_path: Path = DEFAULT_RUNTIME_PATH, *, stop: threading.Event | None = None) -> None:
    shutdown = stop or threading.Event()
    state_path = state_path.expanduser()
    if fire_and_forget_enabled():
        health = ServiceHealthStore(state_path)
        mark_worker_ready(state_path, "prompta-manual-reply")
        logger.info("Fire-and-forget: remote reply dispatch and recovery disabled")
        while not shutdown.is_set():
            health.beat("manual_reply_worker")
            shutdown.wait(1.0)
        return
    store = ManualReplyStore(state_path.parent / "chat-results.sqlite3")
    dispatcher = ManualReplyDispatcher(store, state_path)
    health = ServiceHealthStore(state_path)
    store.recover_orphans()
    mark_worker_ready(state_path, "prompta-manual-reply")
    logger.info("Prompta manual reply worker ready")
    while not shutdown.is_set():
        try:
            health.beat("manual_reply_worker")
            dispatcher.pump_queued()
        except Exception as exc:
            # A database or browser failure must not kill existing captured replies.
            logger.warning("Manual reply queue scan failed error_type=%s", type(exc).__name__)
        shutdown.wait(1.0)

    # Drain sends and exact-parent reads before stopping browser owners.
    logger.info("Manual reply worker draining active operations")
    while dispatcher.inflight_count() > 0:
        health.beat("manual_reply_worker")
        time.sleep(1.0)
    logger.info("Manual reply worker drained")


def main() -> None:
    configure_logging("manual_reply_worker")
    shutdown = threading.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        shutdown.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    run(stop=shutdown)


if __name__ == "__main__":
    main()
