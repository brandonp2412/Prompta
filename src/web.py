"""Local jobs-only web UI for Prompta."""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import socket
import subprocess
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .core import DEFAULT_JOBS_PATH, DEFAULT_STATE_PATH
from .delivery_queue import DeliveryQueueStore
from .service_health import ServiceHealthStore, browser_page_count, notify_watchdog
from .web_jobs import WebJobService

logger = logging.getLogger(__name__)
_STATIC_ROOT = Path(__file__).with_name("static")
_ALLOWED_STATIC = {
    "app.js",
    "app.css",
    "icon.svg",
    "icon-maskable.svg",
    "icon-192.png",
    "icon-512.png",
    "icon-maskable-512.png",
    "apple-touch-icon.png",
    "screenshot-mobile.png",
    "screenshot-wide.png",
    "manifest.webmanifest",
    "sw.js",
}


def _git_short_head() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _start_scheduler_service() -> bool:
    try:
        completed = subprocess.run(
            ["systemctl", "--user", "start", "prompta-scheduler.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


class PromptaJobServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        state_path: Path = DEFAULT_STATE_PATH,
        jobs_path: Path = DEFAULT_JOBS_PATH,
    ) -> None:
        super().__init__(address, PromptaJobHandler)
        self.state_path = state_path.expanduser()
        self.jobs_path = jobs_path.expanduser()
        host = socket.gethostname().strip() or "localhost"
        self.host_name = host.split(".", 1)[0]
        self.health = ServiceHealthStore(self.state_path)
        self.queue = DeliveryQueueStore(self.state_path.parent / "ui-send-jobs.sqlite3")
        self.jobs = WebJobService(
            self.jobs_path,
            self.state_path,
            self.host_name,
            start_scheduler=_start_scheduler_service,
        )
        self._last_health_beat = 0.0
        self.health.beat("ui")

    def service_actions(self) -> None:
        super().service_actions()
        now = time.time()
        if now - self._last_health_beat < 5.0:
            return
        self.health.beat("ui", now=now)
        notify_watchdog()
        self._last_health_beat = now

    def health_payload(self) -> dict[str, Any]:
        now = time.time()
        debugger_address = os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9222")
        browser_reachable, page_count = browser_page_count(debugger_address)
        if browser_reachable:
            self.health.beat("browser", now=now)
        return {
            "ok": True,
            "server": self.host_name,
            "services": self.health.snapshot(now=now),
            "browser": {"reachable": browser_reachable, "page_count": page_count},
            "queue": self.queue.health_metrics(now=now),
        }


class PromptaJobHandler(BaseHTTPRequestHandler):
    server: PromptaJobServer

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _headers(self, status: HTTPStatus, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(length))
        self.send_header("cache-control", "no-store")
        self.send_header("x-content-type-options", "nosniff")
        self.end_headers()

    def _write(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self._headers(status, content_type, len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._write(status, "application/json; charset=utf-8", body)

    def _index(self) -> None:
        text = (_STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        text = text.replace("__PROMPTA_SERVER_NAME__", self.server.host_name)
        self._write(HTTPStatus.OK, "text/html; charset=utf-8", text.encode("utf-8"))

    def _static(self, name: str) -> None:
        if name not in _ALLOWED_STATIC:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        path = _STATIC_ROOT / name
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        if name == "sw.js":
            content = content.replace(b"__PROMPTA_UI_HEAD__", _git_short_head().encode("ascii"))
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix in {".js", ".css", ".svg", ".webmanifest"}:
            content_type += "; charset=utf-8"
        self._write(HTTPStatus.OK, content_type, content)

    def _json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("content-length") or "0")
        except ValueError as exc:
            raise ValueError("Invalid content length") from exc
        if length <= 0 or length > 1024 * 1024:
            raise ValueError("Request body must be between 1 byte and 1 MiB")
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"", "/"}:
            self._index()
            return
        if path == "/api/jobs":
            self._json(self.server.jobs.scheduled_jobs())
            return
        if path == "/api/health":
            self._json(self.server.health_payload())
            return
        if path.startswith("/") and path[1:] in _ALLOWED_STATIC:
            self._static(path[1:])
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/jobs":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._json_body()
            action = str(payload.get("action") or "")
            result = self.server.jobs.apply(action, payload)
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            logger.exception("Prompta jobs update failed")
            self._json(
                {"ok": False, "error": str(exc) or exc.__class__.__name__},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        self._json(result)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    state_path: Path = DEFAULT_STATE_PATH,
    jobs_path: Path = DEFAULT_JOBS_PATH,
) -> None:
    server = PromptaJobServer((host, port), state_path=state_path, jobs_path=jobs_path)
    logger.info("Prompta jobs UI listening on http://%s:%d", host, port)
    notify_watchdog()
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Prompta jobs web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serve(host=args.host, port=args.port, state_path=args.state, jobs_path=args.jobs_file)


if __name__ == "__main__":
    main()
