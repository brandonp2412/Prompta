"""Framework-boundary regressions: strict validation, privacy, limits, and lifecycle."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sse_starlette import EventSourceResponse

from prompta.web import WebServices, create_app


@pytest.fixture
def services(tmp_path: Path) -> WebServices:
    return WebServices(state_path=tmp_path / "runtime.sqlite3", jobs_path=tmp_path / "jobs.sqlite3")


def test_openapi_describes_discriminated_job_actions_and_strict_reply_fields(
    services: WebServices,
) -> None:
    with TestClient(create_app(services=services)) as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        models = schema["components"]["schemas"]
        assert models["ReplyRequest"]["additionalProperties"] is False
        assert models["ReplyRequest"]["properties"]["text"]["maxLength"] == 32000
        action = schema["paths"]["/api/jobs"]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        assert action["discriminator"]["propertyName"] == "action"
        assert "run_once" in action["discriminator"]["mapping"]
        responses = schema["paths"]["/api/jobs"]["post"]["responses"]
        assert "4XX" in responses and "422" not in responses


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "run_once", "prompt": "secret validation input", "pin_chat": "true"},
        {"action": "run_once", "prompt": "secret validation input", "delay_minutes": True},
        {"action": "run_once", "prompt": "secret validation input", "unexpected": "private extra"},
        {
            "action": "add",
            "name": "bad",
            "prompt": "secret validation input",
            "interval_minutes": "nan",
        },
        {
            "action": "add",
            "name": "bad",
            "prompt": "secret validation input",
            "interval_minutes": "inf",
        },
        {"action": "add", "name": "bad", "prompt": "secret validation input", "schedule": "daily"},
    ],
)
def test_invalid_jobs_never_enqueue_or_echo_private_input(
    services: WebServices, payload: dict[str, object], caplog
) -> None:
    with TestClient(create_app(services=services)) as client:
        response = client.post("/api/jobs", json=payload)
        assert response.status_code == 400
        assert "secret validation input" not in response.text + caplog.text
        assert "private extra" not in response.text + caplog.text
        assert services.queue.records() == []
        assert services.jobs.scheduled_jobs()["jobs"] == []


def test_malformed_and_chunked_oversized_bodies_are_bounded_before_mutation(
    services: WebServices,
) -> None:
    with TestClient(create_app(services=services)) as client:
        for content in (b"", b"{secret broken json", b"[]", b"null"):
            response = client.post(
                "/api/chats", content=content, headers={"content-type": "application/json"}
            )
            assert response.status_code == 400
            assert "secret broken" not in response.text
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
        body = json.dumps({"request_id": "a" * 32, "prompt": "private", "images": []}).encode()
        oversized = client.post(
            "/api/chats",
            content=iter([body, b" " * (1024 * 1024)]),
            headers={"content-type": "application/json"},
        )
        assert oversized.status_code == 400
        assert "body size" in oversized.json()["error"]
        assert services.queue.records() == []
        assert (
            client.post(
                "/api/chats", content=body, headers={"content-type": "text/plain"}
            ).status_code
            == 400
        )
        assert client.post("/api/results/missing/turns").status_code == 405


def test_database_exception_does_not_escape_to_uvicorn_or_disclose_values(
    services: WebServices, monkeypatch, caplog
) -> None:
    def fail() -> dict[str, object]:
        raise RuntimeError("secret SQL parameters and transcript")

    monkeypatch.setattr(services, "health_payload", fail)
    # raise_server_exceptions remains True: the boundary must contain the error.
    with TestClient(create_app(services=services)) as client:
        response = client.get("/api/health")
        assert response.status_code == 500
        assert "secret SQL" not in response.text + caplog.text
        assert "RuntimeError" in caplog.text


def test_head_queries_and_lookup_errors_preserve_private_headers(services: WebServices) -> None:
    with TestClient(create_app(services=services)) as client:
        for path in ("/", "/api/jobs", "/api/results", "/api/events", "/app.js"):
            response = client.head(path)
            assert response.status_code == 200
            assert response.content == b""
        for query in (
            "limit=1&limit=2",
            "unknown=secret",
            "status=not-a-status",
            "limit=0",
            "offset=100001",
        ):
            response = client.get("/api/results?" + query)
            assert response.status_code == 400
            assert "secret" not in response.text
        missing = client.get("/api/results/missing")
        assert missing.status_code == 404
        assert missing.json()["error"] == "Run not found"


def test_lifespan_maintains_watchdog_without_request_traffic(
    services: WebServices, monkeypatch
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(services, "service_actions", lambda: calls.append(True))
    with TestClient(create_app(services=services)) as client:
        # A request on the portal establishes that the startup task had a turn.
        assert client.get("/api/jobs").status_code == 200
        assert calls


@pytest.mark.asyncio
async def test_sse_transport_cancels_generator_on_disconnect_and_emits_heartbeat() -> None:
    closed = asyncio.Event()
    heartbeat = asyncio.Event()
    disconnect = asyncio.Event()
    frames: list[bytes] = []

    async def stream():
        try:
            yield {"event": "sync", "data": "refresh"}
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def receive():
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            frames.append(message.get("body", b""))
            if b": ping -" in frames[-1]:
                heartbeat.set()

    response = EventSourceResponse(stream(), ping=0.01, sep="\n")
    task = asyncio.create_task(
        response({"type": "http", "method": "GET", "asgi": {"spec_version": "2.4"}}, receive, send)
    )
    await asyncio.wait_for(heartbeat.wait(), timeout=2)
    disconnect.set()
    await asyncio.wait_for(task, timeout=2)
    assert closed.is_set()
    assert b"event: sync" in b"".join(frames)
