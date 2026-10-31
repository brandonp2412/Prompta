from __future__ import annotations

import json
import threading
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from typing import Literal

import pytest
from live_server import LiveServer

from prompta.response_capture import CaptureResult
from prompta.strict_types import json_object


@pytest.fixture(autouse=True)
def serve_worktree_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    # Nox's editable installation points at main even in an isolated worktree.
    import prompta.web as web_module

    assets = Path(__file__).resolve().parents[1] / "src/static"
    assert (assets / "app.js").is_file()
    monkeypatch.setattr(web_module, "_STATIC_ROOT", assets)


@contextmanager
def server(tmp_path: Path) -> Generator[tuple[LiveServer, int]]:
    app = LiveServer(
        ("127.0.0.1", 0),
        state_path=tmp_path / "runtime.sqlite3",
        jobs_path=tmp_path / "jobs.sqlite3",
    )
    thread = threading.Thread(target=app.serve_forever, daemon=True)
    thread.start()
    try:
        yield app, int(app.server_address[1])
    finally:
        app.shutdown()
        thread.join(timeout=3)
        app.server_close()


def get(
    port: int, path: str, *, method: Literal["GET", "POST"] = "GET"
) -> tuple[int, dict[str, object], dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request(method, path)
        response = conn.getresponse()
        body = response.read()
        headers = {key.lower(): value for key, value in response.getheaders()}
        return (
            response.status,
            json_object(body, label="result") if body.startswith(b"{") else {},
            headers,
        )
    finally:
        conn.close()


def post_json(port: int, path: str, data: Mapping[str, object]) -> tuple[int, dict[str, object]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request(
            "POST", path, body=json.dumps(data), headers={"content-type": "application/json"}
        )
        response = conn.getresponse()
        return response.status, json_object(response.read(), label="pin response")
    finally:
        conn.close()


def completed_run(app: LiveServer, send_id: str, name: str, now: float) -> None:
    app.results.ensure_queued(send_id, f"Prompt for {name}", name, now=now)
    assert app.results.accept(send_id, f"100:{send_id}", deadline=now + 1000, now=now + 1)
    assert app.results.write(
        send_id,
        f"100:{send_id}",
        CaptureResult(
            "sse", "complete", f"**Answer** for {name}\n\n```py\nprint(1)\n```", "c1", "m1", "p1"
        ),
        now=now + 2,
    )
