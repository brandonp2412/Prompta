from __future__ import annotations

import base64
import concurrent.futures
import json
import subprocess
import sys
import time
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from threading import Event, Lock, Thread
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.request import Request, urlopen

import pytest

from prompta.cache import ChatCache
from prompta.core import RateLimitError
from prompta.web import (
    PromptaUIHandler,
    PromptaUIServer,
    ReadOnlyChatStore,
    SendJobRegistry,
    _reconcile_orphaned_local_chats,
    _start_local_scheduler_service,
    _wait_for_local_scheduler,
)


def _seed_cache(path: Path) -> None:
    cache = ChatCache(path)
    cache.start(
        "chat-1",
        context_id="context-1",
        job_name="kite-roadmap",
        prompt="Keep working on Kite",
    )
    cache.write_snapshot(
        "chat-1",
        {
            "title": "Kite roadmap work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep working on Kite"},
                {
                    "id": "a1",
                    "role": "assistant",
                    "content": "Implemented the next roadmap slice.",
                },
            ],
        },
    )
    cache.close()


@pytest.mark.parametrize(
    "disconnect_error",
    [BrokenPipeError(), ConnectionResetError(), ConnectionAbortedError()],
)
def test_ui_response_ignores_disconnected_client(disconnect_error: OSError) -> None:
    handler = object.__new__(PromptaUIHandler)
    handler._headers = MagicMock()  # type: ignore[method-assign]
    handler.wfile = MagicMock()
    handler.wfile.write.side_effect = disconnect_error

    handler._write_response(HTTPStatus.OK, "application/json", b"{}")

    handler._headers.assert_called_once_with(  # type: ignore[attr-defined]
        HTTPStatus.OK,
        "application/json",
        2,
    )


@pytest.mark.parametrize(
    "disconnect_error",
    [BrokenPipeError(), ConnectionResetError(), ConnectionAbortedError()],
)
def test_event_headers_ignore_disconnected_client(disconnect_error: OSError) -> None:
    handler = object.__new__(PromptaUIHandler)
    handler.send_response = MagicMock()  # type: ignore[method-assign]
    handler.send_header = MagicMock()  # type: ignore[method-assign]
    handler.end_headers = MagicMock(side_effect=disconnect_error)  # type: ignore[method-assign]

    assert handler._event_headers() is False


def test_local_ui_startup_marks_old_active_chats_interrupted(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "chat-old",
        context_id="context-old",
        job_name="",
        prompt="Old request",
    )
    cache.close()

    with (
        patch("prompta.web._daemon_is_running", return_value=False),
        patch("prompta.web.time.sleep"),
    ):
        orphaned = _reconcile_orphaned_local_chats(
            path,
            tmp_path / "state.json",
        )

    store = ReadOnlyChatStore(path)
    chat = store.conversation("chat-old")
    assert orphaned == 1
    assert chat is not None
    assert chat["status"] == "interrupted"
    assert all(message["status"] == "complete" for message in chat["messages"])


def test_local_ui_startup_leaves_active_chats_for_running_scheduler(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "chat-live",
        context_id="context-live",
        job_name="",
        prompt="Live request",
    )
    cache.close()

    with patch("prompta.web._daemon_is_running", return_value=True):
        orphaned = _reconcile_orphaned_local_chats(
            path,
            tmp_path / "state.json",
        )

    store = ReadOnlyChatStore(path)
    chat = store.conversation("chat-live")
    assert orphaned == 0
    assert chat is not None
    assert chat["status"] == "active"


def test_local_ui_startup_waits_for_scheduler_lock(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "chat-racing",
        context_id="context-racing",
        job_name="",
        prompt="Still running",
    )
    cache.close()

    with (
        patch("prompta.web._daemon_is_running", side_effect=[False, True]) as running,
        patch("prompta.web.time.sleep") as sleep,
    ):
        orphaned = _reconcile_orphaned_local_chats(
            path,
            tmp_path / "state.json",
        )

    store = ReadOnlyChatStore(path)
    chat = store.conversation("chat-racing")
    assert orphaned == 0
    assert chat is not None
    assert chat["status"] == "active"
    assert running.call_count == 2
    sleep.assert_called_once()


def test_wait_for_local_scheduler_tolerates_restart_gap(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"

    with (
        patch(
            "prompta.web._daemon_is_running",
            side_effect=[False, False, True],
        ) as running,
        patch("prompta.web.time.sleep") as sleep,
    ):
        assert _wait_for_local_scheduler(state_path) is True

    assert running.call_count == 3
    assert sleep.call_count == 2


def test_image_attachment_preview_persists_and_enriches_cached_message(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    raw = [
        {
            "name": "red.png",
            "type": "image/png",
            "data": base64.b64encode(b"fake-png-bytes").decode(),
        }
    ]
    saved: list[str] = []
    try:
        saved = server.save_attachments(
            raw,
            client_id="image-client",
            message="Keep working on Kite",
        )
        record = server._image_previews["image-client"]
        preview = record["images"][0]
        preview_id = preview["id"]

        server._bind_image_previews(
            "image-client",
            "chat-1",
            "Keep working on Kite",
        )
        chat = server.conversation("chat-1")

        assert chat is not None
        assert chat["messages"][0]["attachments"] == [
            {
                "id": preview_id,
                "name": "red.png",
                "type": "image/png",
            }
        ]
        assert server.image_preview(preview_id) == (b"fake-png-bytes", "image/png")
        assert json.loads(server._image_preview_path.read_text())["records"]["image-client"][
            "conversation_id"
        ] == "chat-1"
    finally:
        for target in saved:
            Path(target).unlink(missing_ok=True)
        server.server_close()


def test_image_attachment_preview_http_route(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    raw = [
        {
            "name": "blue.png",
            "type": "image/png",
            "data": base64.b64encode(b"preview-png").decode(),
        }
    ]
    saved: list[str] = []
    thread = Thread(target=server.serve_forever, daemon=True)
    try:
        saved = server.save_attachments(
            raw,
            client_id="preview-client",
            message="Preview it",
        )
        preview_id = server._image_previews["preview-client"]["images"][0]["id"]
        thread.start()
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/api/attachment-previews/{preview_id}",
            timeout=2,
        ) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "image/png"
            assert response.read() == b"preview-png"
    finally:
        server.shutdown()
        server.server_close()
        if thread.is_alive():
            thread.join(timeout=2)
        for target in saved:
            Path(target).unlink(missing_ok=True)


def test_chat_http_route_accepts_attachment_only_message(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    server.send_jobs.submit = MagicMock(  # type: ignore[method-assign]
        return_value={
            "send_id": "attachment-only-send",
            "status": "queued",
            "conversation_id": "",
        }
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    saved: list[str] = []
    try:
        thread.start()
        payload = json.dumps(
            {
                "message": "",
                "client_id": "attachment-only-client",
                "attachments": [
                    {
                        "name": "notes.txt",
                        "type": "text/plain",
                        "data": base64.b64encode(b"attachment-only").decode(),
                    }
                ],
            }
        ).encode()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/chats",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            body = json.loads(response.read())
            assert response.status == HTTPStatus.ACCEPTED
            assert body["ok"] is True
            assert body["send_id"] == "attachment-only-send"

        call = server.send_jobs.submit.call_args  # type: ignore[attr-defined]
        assert call.kwargs["operation"] == "once"
        assert call.kwargs["message"] == ""
        assert call.kwargs["client_id"] == "attachment-only-client"
        saved = list(call.kwargs["attachments"])
        assert len(saved) == 1
        assert Path(saved[0]).read_bytes() == b"attachment-only"
    finally:
        for target in saved:
            Path(target).unlink(missing_ok=True)
        server.shutdown()
        server.server_close()
        if thread.is_alive():
            thread.join(timeout=2)


def test_send_job_registry_calls_success_hook_with_client_id() -> None:
    succeeded = MagicMock()
    sender = MagicMock(return_value="chat-new")

    registry = SendJobRegistry(sender, on_success=succeeded)
    queued = registry.submit(
        operation="once",
        message="Hello",
        client_id="client-success",
    )

    deadline = time.monotonic() + 1.0
    result = registry.get(queued["send_id"])
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(queued["send_id"])

    assert result is not None
    assert result["status"] == "succeeded"
    succeeded.assert_called_once_with("client-success", "chat-new", "Hello")

    duplicate = registry.submit(
        operation="once",
        message="Hello",
        client_id="client-success",
    )

    assert duplicate["send_id"] == queued["send_id"]
    assert sender.call_count == 1
    assert succeeded.call_count == 2
    succeeded.assert_called_with("client-success", "chat-new", "Hello")


def test_local_ui_rejects_send_when_backend_cannot_start(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with (
            patch("prompta.web._wait_for_local_scheduler", return_value=False),
            patch("prompta.web._start_local_scheduler_service", return_value=False),
            pytest.raises(RuntimeError, match="Prompta backend is unavailable"),
        ):
            server._send("once", "Hello", "")
    finally:
        server.server_close()


def test_local_ui_starts_backend_before_send(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with (
            patch("prompta.web._wait_for_local_scheduler", side_effect=[False, True]) as wait,
            patch("prompta.web._start_local_scheduler_service", return_value=True) as start,
            patch(
                "prompta.web._send_once_via_control",
                AsyncMock(return_value="chat-control"),
            ) as control,
        ):
            result = server._send("once", "Hello", "")
    finally:
        server.server_close()

    assert result == "chat-control"
    assert wait.call_count == 2
    start.assert_called_once_with()
    control.assert_awaited_once_with(tmp_path / "state.json", "Hello", [])


def test_local_ui_rejects_send_when_started_backend_never_becomes_ready(
    tmp_path: Path,
) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with (
            patch("prompta.web._wait_for_local_scheduler", return_value=False),
            patch("prompta.web._start_local_scheduler_service", return_value=True),
            pytest.raises(RuntimeError, match="Prompta backend is unavailable"),
        ):
            server._send("once", "Hello", "")
    finally:
        server.server_close()


def test_local_ui_uses_control_socket_when_backend_is_running(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with (
            patch("prompta.web._wait_for_local_scheduler", return_value=True),
            patch(
                "prompta.web._send_once_via_control",
                AsyncMock(return_value="chat-control"),
            ) as control,
        ):
            result = server._send("once", "Hello", "")
    finally:
        server.server_close()

    assert result == "chat-control"
    control.assert_awaited_once_with(tmp_path / "state.json", "Hello", [])


def test_static_bundle_contains_historical_activity_probe() -> None:
    bundle = (Path(__file__).parents[1] / "src" / "prompta" / "static" / "app.js").read_text()
    assert "Checking whether ChatGPT is still running" in bundle
    assert "/probe" in bundle


def test_probe_conversation_routes_to_own_node(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with patch.object(server, "_sync", return_value=2) as sync:
            chat, message_count = server.probe_conversation("chat-1")
    finally:
        server.server_close()

    assert chat["id"] == "chat-1"
    assert message_count == 2
    sync.assert_called_once_with("chat-1")


def test_stop_conversation_routes_to_own_node(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with patch.object(server, "_stop", return_value="chat-1") as stop:
            result = server.stop_conversation("chat-1")
    finally:
        server.server_close()

    assert result == "chat-1"
    stop.assert_called_once_with("chat-1")


def test_stop_conversation_routes_to_remote_node(tmp_path: Path) -> None:
    local_path = tmp_path / "local.sqlite3"
    remote_path = tmp_path / "remote.sqlite3"
    _seed_cache(remote_path)
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        ReadOnlyChatStore(local_path),
        tmp_path / "state.json",
        extra_nodes=[("remote-node", ReadOnlyChatStore(remote_path), "remote-node")],
    )
    target = server.extra_nodes["remote-node"]
    try:
        with patch.object(target, "_stop", return_value="chat-1") as stop:
            result = server.stop_conversation("remote-node::chat-1")
    finally:
        server.server_close()

    assert result == "chat-1"
    stop.assert_called_once_with("chat-1")


def test_send_job_registry_returns_before_sender_finishes() -> None:
    release = Event()

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        assert operation == "once"
        assert message == "Hello"
        assert conversation_id == ""
        assert release.wait(timeout=1.0)
        return "chat-new"

    registry = SendJobRegistry(sender)
    queued = registry.submit(operation="once", message="Hello")

    assert queued["send_id"]
    assert queued["status"] in {"queued", "running"}
    assert queued["conversation_id"] == ""

    release.set()
    deadline = time.monotonic() + 1.0
    result = registry.get(queued["send_id"])
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(queued["send_id"])

    assert result is not None
    assert result["status"] == "succeeded"
    assert result["conversation_id"] == "chat-new"
    assert result["error"] == ""


def test_send_job_registry_persists_send_before_acknowledging_it(tmp_path: Path) -> None:
    release = Event()
    started = Event()
    recovery_path = tmp_path / "ui-send-retries.json"

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        started.set()
        assert release.wait(timeout=1.0)
        return "chat-new"

    registry = SendJobRegistry(sender, recovery_path=recovery_path)
    queued = registry.submit(
        operation="once",
        message="Durable hello",
        client_id="browser-durable-1",
    )

    assert started.wait(timeout=1.0)
    persisted = json.loads(recovery_path.read_text())
    assert persisted["jobs"] == [
        {
            "send_id": queued["send_id"],
            "operation": "once",
            "message": "Durable hello",
            "conversation_id": "",
            "attachments": [],
            "client_id": "browser-durable-1",
            "status": "running",
            "retry_at": 0.0,
            "retry_attempt": 0,
            "created_at": queued["created_at"],
        }
    ]

    release.set()
    deadline = time.monotonic() + 1.0
    result = registry.get(queued["send_id"])
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(queued["send_id"])

    assert result is not None
    assert result["status"] == "succeeded"
    receipt = json.loads(recovery_path.read_text())["jobs"][0]
    assert receipt["send_id"] == queued["send_id"]
    assert receipt["status"] == "succeeded"
    assert receipt["conversation_id"] == "chat-new"
    assert receipt["client_id"] == "browser-durable-1"
    assert receipt["attachments"] == []
    assert receipt["finished_at"] >= receipt["created_at"]


def test_send_job_registry_restores_queued_send_after_restart(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    send_id = "queued-before-restart"
    created_at = time.time() - 10
    recovery_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "send_id": send_id,
                        "operation": "once",
                        "message": "Resume queued send",
                        "conversation_id": "",
                        "attachments": [],
                        "client_id": "browser-queued-restart",
                        "status": "queued",
                        "retry_at": 0.0,
                        "retry_attempt": 0,
                        "created_at": created_at,
                    }
                ]
            }
        )
    )
    calls = 0

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        nonlocal calls
        calls += 1
        assert operation == "once"
        assert message == "Resume queued send"
        assert conversation_id == ""
        assert attachments == []
        return "chat-restored-queued"

    registry = SendJobRegistry(sender, recovery_path=recovery_path)
    deadline = time.monotonic() + 1.0
    result = registry.get(send_id)
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(send_id)

    assert result is not None
    assert result["status"] == "succeeded"
    assert result["conversation_id"] == "chat-restored-queued"
    assert calls == 1
    receipt = json.loads(recovery_path.read_text())["jobs"][0]
    assert receipt["status"] == "succeeded"
    assert receipt["conversation_id"] == "chat-restored-queued"


def test_send_job_registry_dead_letters_inflight_send_after_restart(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    recovery_path.write_text(json.dumps({"jobs": [{
        "send_id": "running-before-restart",
        "operation": "reply",
        "message": "Possibly delivered",
        "conversation_id": "chat-1",
        "attachments": [],
        "client_id": "browser-running-restart",
        "status": "running",
        "retry_at": 0.0,
        "retry_attempt": 1,
        "created_at": time.time() - 10,
    }]}))
    sender = MagicMock(return_value="chat-1")

    registry = SendJobRegistry(sender, recovery_path=recovery_path)

    sender.assert_not_called()
    result = registry.get("running-before-restart")
    assert result is not None
    assert result["status"] == "dead_lettered"
    assert "in-flight send" in result["error"]
    persisted = json.loads(recovery_path.read_text())["jobs"][0]
    assert persisted["status"] == "dead_lettered"
    assert "in-flight send" in persisted["last_error"]


def test_send_job_registry_does_not_multiply_one_shared_rate_limit() -> None:
    registry = SendJobRegistry(lambda *_args: "unused")

    with patch("prompta.core.random.uniform", return_value=0.0):
        first_delay, first_attempt = registry._record_rate_limit(
            RateLimitError("Try again in 5 minutes", retry_after=300)
        )
        second_delay, second_attempt = registry._record_rate_limit(
            RateLimitError("Try again in 5 minutes", retry_after=300)
        )

    assert first_attempt == 1
    assert second_attempt == 1
    assert first_delay == pytest.approx(300.0, abs=0.05)
    assert 0 < second_delay <= first_delay


def test_send_job_registry_keeps_rate_limited_send_pending_and_retries(tmp_path: Path) -> None:
    calls = 0
    sleeping = Event()
    release = Event()
    attachment = tmp_path / "kept-during-backoff.txt"
    attachment.write_text("payload")

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RateLimitError("Try again in 2 minutes", retry_after=120)
        return "chat-new"

    registry_ref: list[SendJobRegistry] = []

    def sleeper(delay: float) -> None:
        assert delay == pytest.approx(300.0, abs=0.01)
        sleeping.set()
        assert release.wait(timeout=1.0)
        registry = registry_ref[0]
        with registry._rate_limit_lock:
            registry._rate_limit_backoff.blocked_until = 0.0

    recovery_path = tmp_path / "ui-send-retries.json"
    registry = SendJobRegistry(sender, sleeper=sleeper, recovery_path=recovery_path)
    registry_ref.append(registry)
    with patch("prompta.core.random.uniform", return_value=0.0):
        queued = registry.submit(
            operation="once",
            message="Hello",
            attachments=[str(attachment)],
        )
        assert sleeping.wait(timeout=1.0)
        limited = registry.get(queued["send_id"])
        assert limited is not None
        assert limited["status"] == "rate_limited"
        assert limited["retry_after_seconds"] == 300
        assert limited["retry_attempt"] == 1
        assert attachment.exists()
        recovery = json.loads(recovery_path.read_text())
        assert recovery["jobs"][0]["send_id"] == queued["send_id"]
        assert recovery["jobs"][0]["message"] == "Hello"

        release.set()
        deadline = time.monotonic() + 1.0
        result = registry.get(queued["send_id"])
        while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
            time.sleep(0.01)
            result = registry.get(queued["send_id"])

    assert result is not None
    assert result["status"] == "succeeded"
    assert result["conversation_id"] == "chat-new"
    assert calls == 2
    assert not attachment.exists()
    assert not recovery_path.exists()


def test_send_job_registry_restores_rate_limited_send_after_restart(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    send_id = "restored-send"
    recovery_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "send_id": send_id,
                        "operation": "once",
                        "message": "Resume me",
                        "conversation_id": "",
                        "attachments": [],
                        "client_id": "browser-restored",
                        "retry_at": time.time() - 1,
                        "retry_attempt": 1,
                        "created_at": time.time() - 10,
                    }
                ]
            }
        )
    )
    calls = 0

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        nonlocal calls
        calls += 1
        assert operation == "once"
        assert message == "Resume me"
        assert conversation_id == ""
        assert attachments == []
        return "chat-restored"

    registry = SendJobRegistry(sender, recovery_path=recovery_path)
    deadline = time.monotonic() + 1.0
    result = registry.get(send_id)
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(send_id)

    assert result is not None
    assert result["status"] == "succeeded"
    assert result["conversation_id"] == "chat-restored"
    assert calls == 1
    receipt = json.loads(recovery_path.read_text())["jobs"][0]
    assert receipt["status"] == "succeeded"
    duplicate = registry.submit(
        operation="once",
        message="Resume me",
        client_id="browser-restored",
    )
    assert duplicate["send_id"] == send_id


def test_send_job_registry_restores_generic_retry_after_restart(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    send_id = "retry-before-restart"
    recovery_path.write_text(json.dumps({"jobs": [{
        "send_id": send_id,
        "operation": "reply",
        "message": "Resume retry",
        "conversation_id": "chat-1",
        "attachments": [],
        "client_id": "browser-retry-restart",
        "status": "retrying",
        "retry_at": time.time() - 1,
        "retry_attempt": 2,
        "created_at": time.time() - 10,
        "last_error": "browser temporarily unavailable",
    }]}))
    calls = 0

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        nonlocal calls
        calls += 1
        return "chat-1"

    registry = SendJobRegistry(sender, recovery_path=recovery_path)
    deadline = time.monotonic() + 1.0
    result = registry.get(send_id)
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(send_id)

    assert result is not None
    assert result["status"] == "succeeded"
    assert calls == 1
    receipt = json.loads(recovery_path.read_text())["jobs"][0]
    assert receipt["status"] == "succeeded"


def test_send_job_registry_deduplicates_succeeded_send_after_restart(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    first_sender = MagicMock(return_value="chat-durable-success")
    first_registry = SendJobRegistry(first_sender, recovery_path=recovery_path)
    queued = first_registry.submit(
        operation="once",
        message="Send exactly once",
        client_id="browser-success-restart",
    )

    deadline = time.monotonic() + 1.0
    result = first_registry.get(queued["send_id"])
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = first_registry.get(queued["send_id"])

    assert result is not None
    assert result["status"] == "succeeded"
    first_sender.assert_called_once()

    restarted_sender = MagicMock(return_value="chat-duplicate")
    restarted = SendJobRegistry(restarted_sender, recovery_path=recovery_path)
    restored = restarted.get(queued["send_id"])
    assert restored is not None
    assert restored["status"] == "succeeded"
    assert restored["conversation_id"] == "chat-durable-success"

    duplicate = restarted.submit(
        operation="once",
        message="Send exactly once",
        client_id="browser-success-restart",
    )

    assert duplicate["send_id"] == queued["send_id"]
    assert duplicate["status"] == "succeeded"
    restarted_sender.assert_not_called()


def test_send_job_registry_does_not_replay_dead_letters(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    recovery_path.write_text(json.dumps({"jobs": [{
        "send_id": "dead-before-restart",
        "operation": "reply",
        "message": "Do not replay",
        "conversation_id": "chat-1",
        "attachments": [],
        "client_id": "browser-dead-restart",
        "status": "dead_lettered",
        "retry_at": 0.0,
        "retry_attempt": 5,
        "created_at": time.time() - 10,
        "last_error": "browser unavailable",
    }]}))
    calls = 0

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        nonlocal calls
        calls += 1
        return "chat-1"

    registry = SendJobRegistry(sender, recovery_path=recovery_path)
    time.sleep(0.03)

    assert calls == 0
    dead_letter = registry.get("dead-before-restart")
    assert dead_letter is not None
    assert dead_letter["status"] == "dead_lettered"
    assert dead_letter["error"] == "browser unavailable"
    duplicate = registry.submit(
        operation="reply",
        message="Do not replay",
        conversation_id="chat-1",
        client_id="browser-dead-restart",
    )
    assert duplicate["send_id"] == "dead-before-restart"
    assert duplicate["status"] == "dead_lettered"
    assert calls == 0
    persisted = json.loads(recovery_path.read_text())
    assert persisted["jobs"][0]["status"] == "dead_lettered"


def test_send_job_registry_cleans_attachments_when_dead_letters_are_evicted(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    registry = SendJobRegistry(lambda *_args: "unused", recovery_path=recovery_path)
    attachments = []
    for index in range(3):
        attachment = tmp_path / f"dead-{index}.txt"
        attachment.write_text(f"payload-{index}")
        attachments.append(attachment)

    with patch("prompta.send_jobs._DEAD_LETTER_LIMIT", 2):
        for index, attachment in enumerate(attachments):
            registry._remember_recoverable(
                send_id=f"dead-{index}",
                operation="reply",
                message=f"dead message {index}",
                conversation_id="chat-1",
                attachments=[str(attachment)],
                client_id="",
                created_at=float(index + 1),
                status="dead_lettered",
                retry_attempt=5,
                last_error="browser unavailable",
            )

    assert not attachments[0].exists()
    assert attachments[1].exists()
    assert attachments[2].exists()
    persisted = json.loads(recovery_path.read_text())
    assert [job["send_id"] for job in persisted["jobs"]] == ["dead-1", "dead-2"]


def test_send_job_registry_reuses_client_id(tmp_path: Path) -> None:
    calls = 0

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        nonlocal calls
        calls += 1
        return "chat-new"

    registry = SendJobRegistry(sender)
    first = registry.submit(operation="once", message="Hello", client_id="browser-send-1")
    retry_attachment = tmp_path / "retry-attachment.txt"
    retry_attachment.write_text("unused retry upload")
    second = registry.submit(
        operation="once",
        message="Hello",
        attachments=[str(retry_attachment)],
        client_id="browser-send-1",
    )

    assert second["send_id"] == first["send_id"]
    assert not retry_attachment.exists()
    deadline = time.monotonic() + 1.0
    result = registry.get(first["send_id"])
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(first["send_id"])
    assert result is not None
    assert result["status"] == "succeeded"
    assert calls == 1


def test_send_job_registry_reuses_client_id_concurrently() -> None:
    calls = 0
    calls_lock = Lock()

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return "chat-new"

    registry = SendJobRegistry(sender)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        jobs = list(
            executor.map(
                lambda _: registry.submit(
                    operation="once",
                    message="Hello",
                    client_id="browser-send-concurrent",
                ),
                range(8),
            )
        )

    assert len({job["send_id"] for job in jobs}) == 1
    send_id = jobs[0]["send_id"]
    deadline = time.monotonic() + 1.0
    result = registry.get(send_id)
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(send_id)
    assert result is not None
    assert result["status"] == "succeeded"
    assert calls == 1


def test_send_job_registry_retries_transient_background_error() -> None:
    calls = 0
    sleeps: list[float] = []

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("browser session unavailable")
        return "chat-1"

    registry = SendJobRegistry(sender, sleeper=sleeps.append)
    queued = registry.submit(operation="reply", message="Continue", conversation_id="chat-1")

    deadline = time.monotonic() + 1.0
    result = registry.get(queued["send_id"])
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(queued["send_id"])

    assert result is not None
    assert result["status"] == "succeeded"
    assert calls == 3
    assert sleeps == [2.0, 4.0]


def test_send_job_registry_dead_letters_exhausted_send(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    attachment = tmp_path / "keep-me.txt"
    attachment.write_text("payload")
    calls = 0

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("browser session unavailable")

    registry = SendJobRegistry(sender, sleeper=lambda _delay: None, recovery_path=recovery_path)
    queued = registry.submit(
        operation="reply",
        message="Continue",
        conversation_id="chat-1",
        attachments=[str(attachment)],
    )

    deadline = time.monotonic() + 1.0
    result = registry.get(queued["send_id"])
    while result is not None and result["status"] != "dead_lettered" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(queued["send_id"])

    assert result is not None
    assert result["status"] == "dead_lettered"
    assert result["conversation_id"] == "chat-1"
    assert result["error"] == "browser session unavailable"
    assert result["retry_attempt"] == 5
    assert calls == 5
    assert attachment.exists()
    persisted = json.loads(recovery_path.read_text())
    assert persisted["jobs"] == [
        {
            "send_id": queued["send_id"],
            "operation": "reply",
            "message": "Continue",
            "conversation_id": "chat-1",
            "attachments": [str(attachment)],
            "client_id": "",
            "status": "dead_lettered",
            "retry_at": 0.0,
            "retry_attempt": 5,
            "created_at": queued["created_at"],
            "last_error": "browser session unavailable",
        }
    ]


def test_read_only_store_lists_and_reads_cached_chat(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)

    chats = store.conversations()
    chat = store.conversation("chat-1")

    assert chats[0]["id"] == "chat-1"
    assert chats[0]["status"] == "active"
    assert chats[0]["prompt"] == "Keep working on Kite"
    assert chats[0]["message_count"] == 2
    assert "Implemented" in chats[0]["preview"]
    assert chat is not None
    assert chat["job_name"] == "kite-roadmap"
    assert [message["role"] for message in chat["messages"]] == ["user", "assistant"]


def test_read_only_store_clears_stale_streaming_status_for_finished_chat(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    cache = ChatCache(path)
    with cache.connection:
        cache.connection.execute(
            "UPDATE conversations SET status = 'complete', completed_at = updated_at WHERE id = ?",
            ("chat-1",),
        )
        cache.connection.execute(
            "UPDATE messages SET status = 'streaming' WHERE conversation_id = ? AND role = 'assistant'",
            ("chat-1",),
        )
    cache.close()

    store = ReadOnlyChatStore(path)
    chat = store.conversation("chat-1")

    assert chat is not None
    assert chat["status"] == "complete"
    assert all(message["status"] == "complete" for message in chat["messages"])


def test_read_only_store_compacts_tool_heavy_sidebar_preview(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "chat-preview",
        context_id="context-preview",
        job_name="",
        prompt="Keep going",
    )
    tool_payload = "x" * 50_000
    fence = chr(96) * 3
    assistant = (
        "Readable summary before tools.\n\n"
        f"{fence}tool-call: execute_python\n"
        f'{{"code":"{tool_payload}"}}\n'
        f"{fence}\n\n"
        "Readable summary after tools."
    )
    cache.write_snapshot(
        "chat-preview",
        {
            "title": "Preview test",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep going"},
                {"id": "a1", "role": "assistant", "content": assistant},
            ],
        },
    )
    cache.close()

    store = ReadOnlyChatStore(path)
    chats = store.conversations()
    chat = store.conversation("chat-preview")

    assert chats[0]["preview"] == "Readable summary before tools. Readable summary after tools."
    assert len(chats[0]["preview"]) <= 1024
    assert chat is not None
    assert chat["messages"][-1]["content"] == assistant


def test_read_only_store_searches_message_content(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)

    assert [chat["id"] for chat in store.conversations(query="Implemented")] == ["chat-1"]
    assert store.conversations(query="not present") == []
    assert store.conversations(query="%") == []
    assert store.conversations(query="_") == []


def test_read_only_store_does_not_create_missing_database(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    store = ReadOnlyChatStore(path)

    assert store.conversations() == []
    assert store.conversation("missing") is None
    assert store.stats() == {"exists": False, "total": 0, "active": 0}
    assert not path.exists()


def test_read_only_store_tolerates_corrupt_database(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    path.write_bytes(b"not a sqlite database\x00PROMPTA")
    store = ReadOnlyChatStore(path)

    assert store.conversations() == []
    assert store.conversation("missing") is None
    assert store.stats() == {"exists": False, "total": 0, "active": 0}


def test_read_only_store_change_token_changes_after_cache_write(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "chat-token",
        context_id="context-token",
        job_name="",
        prompt="Token test",
    )
    cache.close()
    store = ReadOnlyChatStore(path)
    before = store.change_token()

    cache = ChatCache(path)
    cache.write_snapshot(
        "chat-token",
        {
            "title": "Token test",
            "messages": [
                {"id": "u1", "role": "user", "content": "Token test"},
                {"id": "a1", "role": "assistant", "content": "Changed"},
            ],
            "streaming": True,
        },
    )
    cache.close()

    assert store.change_token() != before


def test_ui_serves_manifest_and_sse_refresh_event(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base_url}/", timeout=2) as response:
            assert response.status == 200
            index_html = response.read().decode()
            assert '<div class="composer-status" id="composerStatus">' in index_html
            assert 'id="composerStatus" hidden' not in index_html
            assert 'id="logsButton"' not in index_html
            assert 'data-slash-command="/logs"' in index_html

        with urlopen(Request(f"{base_url}/", method="HEAD"), timeout=2) as response:
            assert response.status == 200
            assert response.read() == b""
            assert int(response.headers["Content-Length"]) == len(index_html.encode())

        with urlopen(f"{base_url}/manifest.json", timeout=2) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "application/manifest+json"
            manifest = json.loads(response.read().decode())
            assert manifest["name"] == f"Prompta · {server.display_name}"
            assert manifest["short_name"] == f"Prompta {server.display_name}"
            assert manifest["display"] == "standalone"
            assert manifest["start_url"] == "./"
            assert manifest["scope"] == "./"

        with urlopen(f"{base_url}/api/health", timeout=2) as response:
            assert response.status == 200
            health = json.loads(response.read().decode())
            assert "head" in health
            assert len(health["head"]) <= 8
            assert health["server"] == "nox"
            assert health["online"] is True
            assert "nodes" not in health

        with urlopen(Request(f"{base_url}/api/events", method="HEAD"), timeout=2) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "text/event-stream"
            assert response.read() == b""

        with urlopen(f"{base_url}/api/events", timeout=2) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "text/event-stream"
            lines = [response.readline().decode() for _ in range(5)]
            assert "event: refresh\n" in lines
            data_line = next(line for line in lines if line.startswith("data: "))
            event_payload = json.loads(data_line.removeprefix("data: "))
            assert event_payload["head"] == health["head"]

            store.log_path.write_text("changed\n")
            assert response.readline().decode() == "event: refresh\n"
            assert response.readline().decode().startswith("data: ")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_start_local_scheduler_service_handles_systemctl_timeout() -> None:
    with patch(
        "prompta.web.subprocess.run",
        side_effect=subprocess.TimeoutExpired(["systemctl"], 10),
    ):
        assert _start_local_scheduler_service() is False


def test_schedule_every_persists_exact_interval_job(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        store,
        tmp_path / "state.json",
        jobs_path=jobs_path,
    )
    try:
        with patch("prompta.web.subprocess.run", return_value=MagicMock(returncode=0)):
            result = server.schedule_every("fix bugs", 30)

        payload = json.loads(jobs_path.read_text())
        saved = payload["jobs"][result["name"]]
        assert saved["prompt"] == "fix bugs"
        assert saved["interval_seconds"] == 1800
        assert saved["exact_interval"] is True
        assert result["scheduler_started"] is True
        assert result["interval_minutes"] == 30
    finally:
        server.server_close()


def test_schedule_every_rejects_nonfinite_interval(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        store,
        tmp_path / "state.json",
        jobs_path=tmp_path / "jobs.json",
    )
    try:
        with pytest.raises(ValueError, match="finite"):
            server.schedule_every("fix bugs", float("nan"))
        with pytest.raises(ValueError, match="finite"):
            server.schedule_every("fix bugs", float("inf"))
    finally:
        server.server_close()


def test_schedule_at_rejects_nonfinite_timestamp(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        store,
        tmp_path / "state.json",
        jobs_path=tmp_path / "jobs.json",
    )
    try:
        with pytest.raises(ValueError, match="finite"):
            server.schedule_at("fix bugs", float("nan"))
        with pytest.raises(ValueError, match="finite"):
            server.schedule_at("fix bugs", float("inf"))
    finally:
        server.server_close()


def test_read_only_store_reads_recent_glass_logs(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    logs = tmp_path / "prompta-glass.log"
    logs.write_text("\n".join(f"line {index}" for index in range(8)) + "\n")
    store = ReadOnlyChatStore(path, logs, journal_unit="")

    payload = store.logs(limit=3)

    assert payload["exists"] is True
    assert payload["lines"] == ["line 5", "line 6", "line 7"]
    assert payload["updated_at"] is not None
    assert payload["source"] == "file"


def test_read_only_store_reports_missing_glass_logs(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(
        tmp_path / "chats.sqlite3",
        tmp_path / "missing.log",
        journal_unit="",
    )

    assert store.logs() == {
        "exists": False,
        "lines": [],
        "updated_at": None,
        "source": "none",
    }


def test_read_only_store_falls_back_to_prompta_journal(tmp_path: Path) -> None:
    logs = tmp_path / "prompta-nox.log"
    logs.write_text("stale synced line\n")
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3", logs)
    completed = MagicMock(
        returncode=0,
        stdout=(
            "2026-09-21T08:47:49+1200 nox prompta[1]: line one\n"
            "2026-09-21T08:47:50+1200 nox prompta[1]: line two\n"
            "2026-09-21T08:47:51+1200 nox prompta[1]: line three\n"
        ),
        stderr="",
    )

    with patch("prompta.web.subprocess.run", return_value=completed) as journal:
        payload = store.logs(limit=2)

    assert payload["exists"] is True
    assert payload["source"] == "journal"
    assert payload["lines"] == [
        "2026-09-21T08:47:50+1200 nox prompta[1]: line two",
        "2026-09-21T08:47:51+1200 nox prompta[1]: line three",
    ]
    assert payload["updated_at"] == datetime.fromisoformat("2026-09-21T08:47:51+1200").timestamp()
    journal.assert_called_once()
    argv = journal.call_args.args[0]
    assert argv[:5] == ["journalctl", "--user", "-u", "prompta.service", "-n"]
    assert journal.call_args.kwargs["timeout"] == 2.0


def test_read_only_store_treats_empty_journal_as_missing(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3", tmp_path / "missing.log")
    completed = MagicMock(returncode=0, stdout="-- No entries --\n", stderr="")

    with patch("prompta.web.subprocess.run", return_value=completed):
        payload = store.logs()

    assert payload == {
        "exists": False,
        "lines": [],
        "updated_at": None,
        "source": "none",
    }


def test_read_only_store_keeps_unparseable_journal_poll_stable(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3", tmp_path / "missing.log")
    completed = MagicMock(returncode=0, stdout="unexpected journal line\n", stderr="")

    with patch("prompta.web.subprocess.run", return_value=completed):
        first = store.logs()
        second = store.logs()

    assert first == second == {
        "exists": True,
        "lines": ["unexpected journal line"],
        "updated_at": None,
        "source": "journal",
    }


def test_read_only_store_hides_request_placeholder_messages(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "chat-placeholder",
        context_id="context-placeholder",
        job_name="",
        prompt="Do work",
    )
    cache.write_snapshot(
        "chat-placeholder",
        {
            "title": "Work",
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
            ],
            "streaming": True,
        },
    )
    with cache.connection:
        cache.connection.execute(
            """
            INSERT INTO messages (
                conversation_id, message_key, ordinal, role, content, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "chat-placeholder",
                "request-placeholder-request-chat-placeholder-0",
                1,
                "assistant",
                "Thinking",
                "streaming",
                1.0,
                1.0,
            ),
        )

    store = ReadOnlyChatStore(path)
    chats = store.conversations()
    chat = store.conversation("chat-placeholder")
    cache.close()

    assert chats[0]["message_count"] == 1
    assert chats[0]["preview"] == "Do work"
    assert store.conversations(query="Thinking") == []
    assert chat is not None
    assert [(message["role"], message["content"]) for message in chat["messages"]] == [
        ("user", "Do work")
    ]


def test_read_only_store_falls_back_to_saved_prompt_for_empty_chat(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "chat-empty",
        context_id="context-empty",
        job_name="",
        prompt="This prompt must remain visible",
    )
    cache.connection.execute(
        "DELETE FROM messages WHERE conversation_id = ?",
        ("chat-empty",),
    )
    cache.connection.commit()

    store = ReadOnlyChatStore(path)
    chats = store.conversations()
    chat = store.conversation("chat-empty")
    cache.close()

    assert chats[0]["message_count"] == 1
    assert chats[0]["preview"] == "This prompt must remain visible"
    assert chat is not None
    assert [(message["role"], message["content"]) for message in chat["messages"]] == [
        ("user", "This prompt must remain visible")
    ]


def test_read_only_store_event_fingerprint_changes_with_cache(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    store = ReadOnlyChatStore(path)

    before = store.event_fingerprint()
    cache.start(
        "chat-event",
        context_id="context-event",
        job_name="event-test",
        prompt="Initial prompt",
    )
    after_start = store.event_fingerprint()
    cache.write_snapshot(
        "chat-event",
        {
            "title": "Event test",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Initial prompt"},
                {"id": "a1", "role": "assistant", "content": "Working"},
            ],
        },
    )
    after_message = store.event_fingerprint()
    cache.close()

    assert after_start != before
    assert after_message != after_start


def test_ui_server_exposes_server_identity_and_manifest(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        store,
        tmp_path / "state.json",
        server_name="glass",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = "127.0.0.1"
    port = server.server_port
    try:
        with urlopen(f"http://{host}:{port}/", timeout=2) as response:
            index = response.read().decode()
        with urlopen(f"http://{host}:{port}/manifest.webmanifest", timeout=2) as response:
            manifest = json.loads(response.read())
            manifest_type = response.headers.get_content_type()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert "Prompta · Glass" in index
    assert "__PROMPTA_SERVER_NAME__" not in index
    assert manifest["name"] == "Prompta · Glass"
    assert manifest["short_name"] == "Prompta · Glass"
    assert manifest["start_url"] == "./"
    assert manifest_type == "application/manifest+json"

def test_jobs_cli_add_maps_to_prompta_cli(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    jobs_path = tmp_path / "jobs.json"
    state_path = tmp_path / "state.json"
    server = PromptaUIServer(("127.0.0.1", 0), store, state_path, jobs_path)
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    try:
        with (
            patch("prompta.web.subprocess.run", return_value=completed) as run_cli,
            patch("prompta.web._start_local_scheduler_service", return_value=True) as start,
            patch.object(server, "scheduled_jobs", return_value={"jobs": [], "server": "nox"}),
        ):
            result = server._run_job_cli(
                "add",
                {
                    "name": "kite-roadmap",
                    "prompt": "Keep working on Kite",
                    "interval_minutes": 30,
                    "exact_interval": True,
                },
            )
    finally:
        server.server_close()

    run_cli.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "prompta.core",
            "add",
            "kite-roadmap",
            "Keep working on Kite",
            "--interval-minutes",
            "30.0",
            "--exact-interval",
            "--jobs-file",
            str(jobs_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    start.assert_called_once_with()
    assert result["command"][:4] == ["prompta", "add", "kite-roadmap", "Keep working on Kite"]


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("pause", ["pause", "kite-roadmap"]),
        ("resume", ["resume", "kite-roadmap"]),
        ("remove", ["remove", "kite-roadmap"]),
    ],
)
def test_jobs_cli_named_actions_map_to_prompta_cli(
    tmp_path: Path,
    action: str,
    expected: list[str],
) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    jobs_path = tmp_path / "jobs.json"
    state_path = tmp_path / "state.json"
    server = PromptaUIServer(("127.0.0.1", 0), store, state_path, jobs_path)
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    try:
        with (
            patch("prompta.web.subprocess.run", return_value=completed) as run_cli,
            patch("prompta.web._start_local_scheduler_service", return_value=True),
            patch.object(server, "scheduled_jobs", return_value={"jobs": [], "server": "nox"}),
        ):
            server._run_job_cli(action, {"name": "kite-roadmap"})
    finally:
        server.server_close()

    command = run_cli.call_args.args[0]
    assert command[:3] == [sys.executable, "-m", "prompta.core"]
    assert command[3:5] == expected
    assert command[-2:] == (
        ["--state", str(state_path)]
        if action in {"pause", "resume"}
        else ["--jobs-file", str(jobs_path)]
    )


def test_run_job_cli_rejects_boolean_interval(tmp_path: Path) -> None:
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        ReadOnlyChatStore(tmp_path / "chats.sqlite3"),
        tmp_path / "state.json",
        tmp_path / "jobs.json",
    )
    try:
        with pytest.raises(ValueError, match="Interval minutes must be a number"):
            server._run_job_cli(
                "add",
                {"name": "bad-interval", "prompt": "Do work", "interval_minutes": True},
            )
    finally:
        server.server_close()


def test_scheduled_jobs_reads_cli_job_file_and_state(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    state_path = tmp_path / "state.json"
    jobs_path.write_text(
        json.dumps(
            {
                "jobs": {
                    "daily-check": {
                        "prompt": "Check the build",
                        "interval_seconds": 1800,
                        "daily_at": "09:30",
                    }
                }
            }
        )
    )
    state_path.write_text(
        json.dumps(
            {
                "jobs": {
                    "daily-check": {
                        "paused": True,
                        "status": "healthy",
                        "next_due_at_epoch": 1234,
                    }
                }
            }
        )
    )
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        ReadOnlyChatStore(tmp_path / "chats.sqlite3"),
        state_path,
        jobs_path,
    )
    try:
        result = server.scheduled_jobs()
    finally:
        server.server_close()

    assert result["jobs"] == [
        {
            "name": "daily-check",
            "prompt": "Check the build",
            "interval_minutes": 30.0,
            "daily_at": "09:30",
            "run_at_epoch": None,
            "exact_interval": False,
            "paused": True,
            "status": "paused",
            "next_due_at_epoch": 1234.0,
        }
    ]
