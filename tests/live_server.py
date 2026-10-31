"""Real Uvicorn HTTP harness shared by API and browser regression tests."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import uvicorn

from prompta.persistence import create_database
from prompta.web import WebServices, create_app


class LiveServer(WebServices):
    def __init__(self, address: tuple[str, int], *, state_path: Path, jobs_path: Path) -> None:
        super().__init__(state_path=state_path, jobs_path=jobs_path)
        self.socket = socket.socket()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(address)
        self.socket.listen(128)
        self.server_address: tuple[str, int] = self.socket.getsockname()
        self.server_port = self.server_address[1]
        self.stopped = threading.Event()
        self.http = uvicorn.Server(
            uvicorn.Config(
                create_app(services=self),
                access_log=False,
                log_config=None,
                timeout_graceful_shutdown=1,
            )
        )

    def serve_forever(self) -> None:
        try:
            self.http.run(sockets=[self.socket])
        finally:
            self.stopped.set()

    def shutdown(self) -> None:
        deadline = time.monotonic() + 5
        while not self.http.started and not self.stopped.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.http.should_exit = True
        if not self.stopped.wait(5):
            raise RuntimeError("Uvicorn test server did not shut down")

    def server_close(self) -> None:
        self.socket.close()
        create_database(self.state_path).dispose()
        self.queue.engine.dispose()
        self.results.engine.dispose()
        self.replies.engine.dispose()
