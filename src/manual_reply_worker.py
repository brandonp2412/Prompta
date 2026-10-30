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

from .manual_reply_dispatch import ManualReplyDispatcher
from .persistence import DEFAULT_RUNTIME_PATH
from .reply_contracts import ManualReplyStore
from .service_health import ServiceHealthStore

logger = logging.getLogger(__name__)


def run(state_path: Path = DEFAULT_RUNTIME_PATH, *, stop: threading.Event | None = None) -> None:
    shutdown = stop or threading.Event()
    state_path = state_path.expanduser()
    store = ManualReplyStore(state_path.parent / "chat-results.sqlite3")
    dispatcher = ManualReplyDispatcher(store, state_path)
    health = ServiceHealthStore(state_path)
    store.recover_orphans()
    logger.info("Prompta manual reply worker ready")
    while not shutdown.is_set():
        try:
            health.beat("manual_reply_worker")
            dispatcher.pump_queued()
        except Exception as exc:
            # A database or browser failure must not kill existing captured replies.
            logger.warning("Manual reply queue scan failed error_type=%s", type(exc).__name__)
        shutdown.wait(1.0)

    # systemd waits through the full owned-tab lifetime before stopping the
    # worker. No new reply starts, but verified active captures can finish.
    logger.info("Manual reply worker draining active captures")
    while dispatcher.active_count() > 0:
        health.beat("manual_reply_worker")
        time.sleep(1.0)
    logger.info("Manual reply worker drained")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    shutdown = threading.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        shutdown.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    run(stop=shutdown)


if __name__ == "__main__":
    main()
