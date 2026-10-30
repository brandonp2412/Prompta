"""Manual reply ownership must outlive the UI and drain on worker shutdown."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from prompta import manual_reply_worker


def test_shutdown_drains_active_capture_without_starting_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = threading.Event()
    scanned = threading.Event()
    finished = threading.Event()
    dispatchers: list[FakeDispatcher] = []

    class FakeDispatcher:
        def __init__(self, _store: object, _state: Path) -> None:
            self.scans = 0
            dispatchers.append(self)

        def pump_queued(self) -> None:
            self.scans += 1
            scanned.set()

        def active_count(self) -> int:
            return 0 if finished.is_set() else 1

    monkeypatch.setattr(manual_reply_worker, "ManualReplyDispatcher", FakeDispatcher)
    worker = threading.Thread(
        target=manual_reply_worker.run,
        args=(tmp_path / "runtime.sqlite3",),
        kwargs={"stop": stop},
    )
    worker.start()
    try:
        assert scanned.wait(timeout=5)
        stop.set()
        time.sleep(0.05)
        assert worker.is_alive(), "An accepted reply must finish during worker shutdown"
        assert len(dispatchers) == 1
        assert dispatchers[0].scans == 1
    finally:
        finished.set()
        stop.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
