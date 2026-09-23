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
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from prompta.cache import ChatCache
from prompta.control_server import ControlDeferredError, ControlUnavailableError
from prompta.core import RateLimitError
from prompta.jobs import load_jobs
from prompta.web import (
    PromptaUIHandler,
    PromptaUIServer,
    ReadOnlyChatStore,
    SendJobRegistry,
    _git_changelog,
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


def test_git_changelog_uses_commit_titles() -> None:
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="abc1234\tNewest change\ndef5678\tOlder change\n",
        stderr="",
    )
    with patch("prompta.web.subprocess.run", return_value=completed):
        assert _git_changelog() == [
            {"hash": "abc1234", "title": "Newest change"},
            {"hash": "def5678", "title": "Older change"},
        ]


def test_git_changelog_tolerates_unavailable_git() -> None:
    with patch("prompta.web.subprocess.run", side_effect=OSError("git unavailable")):
        assert _git_changelog() == []


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


def test_response_headers_allow_dynamic_styles_but_not_inline_scripts() -> None:
    handler = object.__new__(PromptaUIHandler)
    handler.send_response = MagicMock()  # type: ignore[method-assign]
    handler.send_header = MagicMock()  # type: ignore[method-assign]
    handler.end_headers = MagicMock()  # type: ignore[method-assign]

    handler._headers(HTTPStatus.OK, "text/html; charset=utf-8", 0)

    csp = next(
        call.args[1]
        for call in handler.send_header.call_args_list
        if call.args[0] == "Content-Security-Policy"
    )
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "script-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp


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


def test_ui_send_classifies_missing_backend_as_control_outage(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with (
            patch("prompta.web._wait_for_local_scheduler", return_value=False),
            patch("prompta.web._start_local_scheduler_service", return_value=False),
            pytest.raises(ControlUnavailableError, match="backend is unavailable"),
        ):
            server._send("once", "Hello", "", [])
    finally:
        server.server_close()


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
        assert server.image_previews._load_database()["image-client"]["conversation_id"] == "chat-1"
        assert not server.image_previews.legacy_path.exists()
    finally:
        for target in saved:
            Path(target).unlink(missing_ok=True)
        server.server_close()


def test_ui_conversation_detail_drops_unused_structured_payload() -> None:
    original = {
        "id": "chat-heavy",
        "state_events": [{"type": "tool", "payload": "large"}],
        "messages": [
            {
                "message_key": "assistant-1",
                "role": "assistant",
                "content": "Visible response",
                "status": "complete",
                "parts": [{"type": "tool", "payload": "large"}],
                "tool_calls": [{"name": "execute_python", "output": "large"}],
                "source_event_count": 42,
                "version_count": 3,
                "attachments": [{"id": "preview-1", "type": "image/png"}],
            }
        ],
    }

    compact = PromptaUIServer._compact_conversation_detail(original)

    assert "state_events" not in compact
    assert compact["messages"] == [
        {
            "message_key": "assistant-1",
            "role": "assistant",
            "content": "Visible response",
            "status": "complete",
            "attachments": [{"id": "preview-1", "type": "image/png"}],
        }
    ]
    assert "state_events" in original
    assert "tool_calls" in original["messages"][0]


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


def test_mark_all_read_http_route(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    thread = Thread(target=server.serve_forever, daemon=True)
    try:
        thread.start()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/chats/read-all",
            data=b"{}",
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            body = json.loads(response.read())
            assert response.status == HTTPStatus.OK
            assert body["ok"] is True
            assert isinstance(body["read_at"], float)
    finally:
        server.shutdown()
        server.server_close()
        if thread.is_alive():
            thread.join(timeout=2)


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


def test_send_job_registry_exposes_pending_new_chat_receipts_before_conversation_id() -> None:
    release = Event()

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        assert operation == "once"
        assert conversation_id == ""
        assert release.wait(timeout=1.0)
        return "chat-new"

    registry = SendJobRegistry(sender)
    queued = registry.submit(
        operation="once",
        message="Stay visible while queued",
        client_id="client-pending-sidebar",
    )
    receipts = registry.list_conversation_receipts()
    release.set()

    assert [receipt["send_id"] for receipt in receipts] == [queued["send_id"]]
    assert receipts[0]["conversation_id"] == ""
    assert receipts[0]["status"] in {"queued", "running"}


def test_send_job_registry_exposes_recent_successful_new_chat_receipts() -> None:
    registry = SendJobRegistry(MagicMock(return_value="chat-new"))
    queued = registry.submit(
        operation="once",
        message="Persist in the sidebar",
        client_id="client-sidebar",
    )

    deadline = time.monotonic() + 1.0
    result = registry.get(queued["send_id"])
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(queued["send_id"])

    assert result is not None
    assert result["status"] == "succeeded"
    receipts = registry.list_conversation_receipts()
    assert [receipt["send_id"] for receipt in receipts] == [queued["send_id"]]
    assert receipts[0]["conversation_id"] == "chat-new"
    assert receipts[0]["message"] == "Persist in the sidebar"


def test_ui_server_exposes_pending_new_chat_before_chatgpt_assigns_an_id(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    receipt = {
        "send_id": "send-pending",
        "operation": "once",
        "message": "Stay in the sidebar",
        "client_id": "client-pending",
        "status": "queued",
        "conversation_id": "",
        "created_at": 1_000.0,
        "updated_at": 1_001.0,
        "queue_position": 3,
    }
    server.send_jobs.list_conversation_receipts = MagicMock(  # type: ignore[method-assign]
        return_value=[receipt]
    )
    pending_id = "pending-new-client-pending"
    try:
        chats = server.conversations()
        chat = server.conversation(pending_id)
    finally:
        server.server_close()

    assert [item["id"] for item in chats] == [pending_id]
    assert chats[0]["_pending_send"] is True
    assert chats[0]["status"] == "pending"
    assert chats[0]["created_at"] == 1_000.0
    assert chat is not None
    assert chat["id"] == pending_id
    assert chat["messages"][0]["content"] == "Stay in the sidebar"
    assert chat["messages"][1]["pending_activity"] is True
    assert chat["messages"][1]["pending_activity_label"] == "queued · #3"


def test_ui_server_pending_new_chat_rate_limit_shows_backoff_duration(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    receipt = {
        "send_id": "send-limited",
        "operation": "once",
        "message": "Back off visibly",
        "client_id": "client-limited",
        "status": "rate_limited",
        "conversation_id": "",
        "created_at": 1_000.0,
        "updated_at": 1_001.0,
        "retry_at": 1_300.0,
        "retry_after_seconds": 300,
    }
    server.send_jobs.list_conversation_receipts = MagicMock(  # type: ignore[method-assign]
        return_value=[receipt]
    )
    pending_id = "pending-new-client-limited"
    try:
        with patch("prompta.web.time.time", return_value=1_180.0):
            chat = server.conversation(pending_id)
    finally:
        server.server_close()

    assert chat is not None
    assert chat["messages"][1]["pending_activity_label"] == "rate limited · retry in 2m"


def test_ui_server_keeps_successful_new_chat_visible_before_cache_adopts_it(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    receipt = {
        "send_id": "send-sidebar",
        "operation": "once",
        "message": "Persist in the sidebar",
        "client_id": "client-sidebar",
        "status": "succeeded",
        "conversation_id": "WEB:new-chat",
        "created_at": 1_000.0,
        "updated_at": 1_005.0,
    }
    server.send_jobs.list_conversation_receipts = MagicMock(  # type: ignore[method-assign]
        return_value=[receipt]
    )
    try:
        chats = server.conversations()
        chat = server.conversation("WEB:new-chat")
    finally:
        server.server_close()

    assert chats == [
        {
            "id": "WEB:new-chat",
            "job_name": "new chat",
            "prompt": "Persist in the sidebar",
            "url": "",
            "title": "Persist in the sidebar",
            "status": "pending",
            "created_at": 1_000.0,
            "updated_at": 1_005.0,
            "completed_at": None,
            "last_message_at": 1_000.0,
            "preview": "Persist in the sidebar",
            "message_count": 1,
            "_pending_send": True,
            "_send_id": "send-sidebar",
            "_client_id": "client-sidebar",
            "unread": False,
        }
    ]
    assert chat is not None
    assert chat["id"] == "WEB:new-chat"
    assert chat["_pending_send"] is True
    assert chat["messages"][0]["role"] == "user"
    assert chat["messages"][0]["content"] == "Persist in the sidebar"


def test_ui_server_prefers_durable_chat_over_send_receipt(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        ReadOnlyChatStore(path),
        tmp_path / "state.json",
    )
    server.send_jobs.list_conversation_receipts = MagicMock(  # type: ignore[method-assign]
        return_value=[
            {
                "send_id": "send-sidebar",
                "operation": "once",
                "message": "Temporary title",
                "client_id": "client-sidebar",
                "status": "succeeded",
                "conversation_id": "chat-1",
                "created_at": 1_000.0,
                "updated_at": 1_005.0,
            }
        ]
    )
    try:
        chats = server.conversations()
        chat = server.conversation("chat-1")
    finally:
        server.server_close()

    assert [item["id"] for item in chats].count("chat-1") == 1
    durable = next(item for item in chats if item["id"] == "chat-1")
    assert "_pending_send" not in durable
    assert chat is not None
    assert "_pending_send" not in chat
    assert chat["title"] == "Kite roadmap work"


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


def test_probe_conversation_uses_local_backend(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with patch.object(server, "_sync", return_value=2) as sync:
            chat, message_count, verified = server.probe_conversation("chat-1")
    finally:
        server.server_close()

    assert chat["id"] == "chat-1"
    assert message_count == 2
    assert verified is True
    sync.assert_called_once_with("chat-1")


def test_probe_conversation_returns_cached_chat_when_live_probe_is_inconclusive(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with patch.object(
            server,
            "_sync",
            side_effect=RuntimeError("ChatGPT conversation did not expose any messages"),
        ):
            chat, message_count, verified = server.probe_conversation("chat-1")
    finally:
        server.server_close()

    assert chat["id"] == "chat-1"
    assert message_count == len(chat["messages"])
    assert verified is False


def test_probe_conversation_propagates_real_backend_failure(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with (
            patch.object(server, "_sync", side_effect=RuntimeError("browser crashed")),
            pytest.raises(RuntimeError, match="browser crashed"),
        ):
            server.probe_conversation("chat-1")
    finally:
        server.server_close()


def test_stop_conversation_uses_local_backend(tmp_path: Path) -> None:
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


def test_send_job_registry_restores_before_starting_worker(tmp_path: Path) -> None:
    events: list[str] = []
    recovery_path = tmp_path / "ui-send-retries.json"

    with (
        patch.object(
            SendJobRegistry,
            "_restore_recoverable",
            autospec=True,
            side_effect=lambda _registry: events.append("restore"),
        ),
        patch("prompta.send_jobs.threading.Thread") as thread_class,
    ):
        thread_class.return_value.start.side_effect = lambda: events.append("start")
        SendJobRegistry(lambda *_args: "unused", recovery_path=recovery_path)

    assert events == ["restore", "start"]


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
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    assert queue_path.exists()
    persisted = {"jobs": registry._database_records()}
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
    receipt = registry._database_records()[0]
    assert receipt["send_id"] == queued["send_id"]
    assert receipt["status"] == "succeeded"
    assert receipt["conversation_id"] == "chat-new"
    assert receipt["client_id"] == "browser-durable-1"
    assert receipt["attachments"] == []
    assert receipt["finished_at"] >= receipt["created_at"]

    restarted = SendJobRegistry(lambda *_args: "unexpected", recovery_path=recovery_path)
    restored = restarted.get(queued["send_id"])
    assert restored is not None
    assert restored["status"] == "succeeded"
    assert restored["conversation_id"] == "chat-new"


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
    receipt = registry._database_records()[0]
    assert receipt["status"] == "succeeded"
    assert receipt["conversation_id"] == "chat-restored-queued"


def test_send_job_registry_dead_letters_inflight_send_after_restart(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    recovery_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
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
                    }
                ]
            }
        )
    )
    sender = MagicMock(return_value="chat-1")

    registry = SendJobRegistry(sender, recovery_path=recovery_path)

    sender.assert_not_called()
    result = registry.get("running-before-restart")
    assert result is not None
    assert result["status"] == "dead_lettered"
    assert "in-flight send" in result["error"]
    persisted = registry._database_records()[0]
    assert persisted["status"] == "dead_lettered"
    assert "in-flight send" in persisted["last_error"]


def test_send_job_registry_does_not_restore_cancelled_send(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    recovery_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "send_id": "cancelled-before-restart",
                        "operation": "reply",
                        "message": "Do not deliver",
                        "conversation_id": "chat-1",
                        "attachments": [],
                        "client_id": "browser-cancelled-restart",
                        "status": "cancelled",
                        "retry_at": 0.0,
                        "retry_attempt": 0,
                        "created_at": time.time() - 10,
                        "finished_at": time.time() - 5,
                    }
                ]
            }
        )
    )
    sender = MagicMock(return_value="chat-1")

    registry = SendJobRegistry(sender, recovery_path=recovery_path)

    sender.assert_not_called()
    result = registry.get("cancelled-before-restart")
    assert result is not None
    assert result["status"] == "cancelled"
    persisted = registry._database_records()[0]
    assert persisted["status"] == "cancelled"


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
        assert delay == pytest.approx(120.0, abs=0.01)
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
        assert limited["retry_after_seconds"] == 120
        assert limited["retry_attempt"] == 1
        assert attachment.exists()
        recovery = {"jobs": registry._database_records()}
        assert recovery["jobs"][0]["send_id"] == queued["send_id"]
        assert recovery["jobs"][0]["message"] == "Hello"

        release.set()
        deadline = time.monotonic() + 1.0
        result = registry.get(queued["send_id"])
        while (
            result is not None and result["status"] != "succeeded" and time.monotonic() < deadline
        ):
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
    receipt = registry._database_records()[0]
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
    recovery_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
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
                    }
                ]
            }
        )
    )
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
    receipt = registry._database_records()[0]
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


def test_send_job_registry_replays_legacy_pre_send_control_outage_dead_letter(
    tmp_path: Path,
) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    send_id = "legacy-control-outage"
    recovery_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "send_id": send_id,
                        "operation": "once",
                        "message": "Previously stranded",
                        "conversation_id": "",
                        "attachments": [],
                        "client_id": "browser-legacy-outage",
                        "status": "dead_lettered",
                        "retry_at": 0.0,
                        "retry_attempt": 5,
                        "created_at": time.time() - 10,
                        "last_error": (
                            "Prompta scheduler is running but its control socket is unavailable: "
                            "/home/test/.local/state/prompta/control.sock"
                        ),
                    }
                ]
            }
        )
    )
    sender = MagicMock(return_value="chat-recovered")

    registry = SendJobRegistry(sender, recovery_path=recovery_path)
    deadline = time.monotonic() + 1.0
    result = registry.get(send_id)
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(send_id)

    assert result is not None
    assert result["status"] == "succeeded"
    assert result["conversation_id"] == "chat-recovered"
    assert result["retry_attempt"] == 0
    sender.assert_called_once_with("once", "Previously stranded", "", [])
    persisted = registry._database_records()[0]
    assert persisted["status"] == "succeeded"
    assert persisted["conversation_id"] == "chat-recovered"


def test_send_job_registry_keeps_uncertain_restart_dead_letter_terminal(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    recovery_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "send_id": "unknown-delivery-state",
                        "operation": "reply",
                        "message": "May already have been sent",
                        "conversation_id": "chat-1",
                        "attachments": [],
                        "client_id": "browser-unknown-delivery",
                        "status": "dead_lettered",
                        "retry_at": 0.0,
                        "retry_attempt": 0,
                        "created_at": time.time() - 10,
                        "last_error": (
                            "Delivery state unknown after Prompta restarted during an in-flight send"
                        ),
                    }
                ]
            }
        )
    )
    sender = MagicMock(return_value="chat-1")

    registry = SendJobRegistry(sender, recovery_path=recovery_path)
    time.sleep(0.03)

    sender.assert_not_called()
    result = registry.get("unknown-delivery-state")
    assert result is not None
    assert result["status"] == "dead_lettered"
    assert "Delivery state unknown" in result["error"]


def test_send_job_registry_does_not_replay_dead_letters(tmp_path: Path) -> None:
    recovery_path = tmp_path / "ui-send-retries.json"
    recovery_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
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
                    }
                ]
            }
        )
    )
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
    persisted = {"jobs": registry._database_records()}
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
    persisted = {"jobs": registry._database_records()}
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


def test_send_job_registry_coalesces_queued_replies_for_same_conversation(tmp_path: Path) -> None:
    blocker_started = Event()
    release_blocker = Event()
    calls: list[tuple[str, str, str]] = []

    def sender(
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str],
    ) -> str:
        del attachments
        calls.append((operation, message, conversation_id))
        if message == "blocker":
            blocker_started.set()
            assert release_blocker.wait(timeout=1.0)
            return "chat-blocker"
        return conversation_id

    registry = SendJobRegistry(
        sender,
        recovery_path=tmp_path / "coalesced-send-recovery.json",
    )
    registry.submit(operation="once", message="blocker")
    assert blocker_started.wait(timeout=1.0)

    first = registry.submit(
        operation="reply",
        message="first pending post",
        conversation_id="chat-pending",
    )
    second = registry.submit(
        operation="reply",
        message="second pending post",
        conversation_id="chat-pending",
    )

    assert second["send_id"] == first["send_id"]
    queued = registry.get(first["send_id"])
    assert queued is not None
    assert queued["message"] == "first pending post\nsecond pending post"

    release_blocker.set()
    deadline = time.monotonic() + 1.0
    result = registry.get(first["send_id"])
    while result is not None and result["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(first["send_id"])

    assert result is not None
    assert result["status"] == "succeeded"
    assert calls == [
        ("once", "blocker", ""),
        ("reply", "first pending post\nsecond pending post", "chat-pending"),
    ]


def test_send_job_registry_processes_sends_in_fifo_order() -> None:
    first_started = Event()
    release_first = Event()
    calls: list[str] = []
    calls_lock = Lock()

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        del operation, conversation_id, attachments
        with calls_lock:
            calls.append(message)
        if message == "first":
            first_started.set()
            assert release_first.wait(timeout=1.0)
        return f"chat-{message}"

    registry = SendJobRegistry(sender)
    first = registry.submit(operation="once", message="first")
    assert first_started.wait(timeout=1.0)
    second = registry.submit(operation="once", message="second")
    third = registry.submit(operation="once", message="third")

    time.sleep(0.05)
    assert calls == ["first"]
    queued_second = registry.get(second["send_id"])
    assert queued_second is not None
    assert queued_second["status"] == "queued"
    assert queued_second["queue_position"] == 1
    queued_third = registry.get(third["send_id"])
    assert queued_third is not None
    assert queued_third["status"] == "queued"
    assert queued_third["queue_position"] == 2
    receipts = {job["message"]: job for job in registry.list_conversation_receipts()}
    assert receipts["second"]["queue_position"] == 1
    assert receipts["third"]["queue_position"] == 2
    assert receipts["second"]["queue_eta_seconds"] == pytest.approx(300, abs=2)
    assert receipts["third"]["queue_eta_seconds"] == pytest.approx(600, abs=2)

    release_first.set()
    deadline = time.monotonic() + 1.0
    first_result = registry.get(first["send_id"])
    second_result = registry.get(second["send_id"])
    third_result = registry.get(third["send_id"])
    while (
        (first_result is None or first_result["status"] != "succeeded")
        or (second_result is None or second_result["status"] != "succeeded")
        or (third_result is None or third_result["status"] != "succeeded")
    ) and time.monotonic() < deadline:
        time.sleep(0.01)
        first_result = registry.get(first["send_id"])
        second_result = registry.get(second["send_id"])
        third_result = registry.get(third["send_id"])

    assert calls == ["first", "second", "third"]
    assert first_result is not None and first_result["status"] == "succeeded"
    assert second_result is not None and second_result["status"] == "succeeded"
    assert third_result is not None and third_result["status"] == "succeeded"


def test_send_job_registry_can_bump_pending_send_to_front(tmp_path: Path) -> None:
    first_started = Event()
    release_first = Event()
    calls: list[str] = []

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        del operation, conversation_id, attachments
        calls.append(message)
        if message == "first":
            first_started.set()
            assert release_first.wait(timeout=1.0)
        return f"chat-{message}"

    registry = SendJobRegistry(sender, recovery_path=tmp_path / "ui-send-retries.json")
    first = registry.submit(operation="once", message="first")
    assert first_started.wait(timeout=1.0)
    second = registry.submit(operation="once", message="second")
    third = registry.submit(operation="once", message="third")

    bumped = registry.bump_to_front(third["send_id"])
    assert bumped is not None
    assert bumped["queue_position"] == 1

    queued_second = registry.get(second["send_id"])
    assert queued_second is not None
    assert queued_second["queue_position"] == 2

    release_first.set()
    deadline = time.monotonic() + 1.0
    results = [registry.get(item["send_id"]) for item in (first, second, third)]
    while (
        any(result is None or result["status"] != "succeeded" for result in results)
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
        results = [registry.get(item["send_id"]) for item in (first, second, third)]

    assert calls == ["first", "third", "second"]
    assert all(result is not None and result["status"] == "succeeded" for result in results)


def test_send_job_registry_estimates_queued_eta_from_active_rate_limit() -> None:
    first_started = Event()
    release_first = Event()

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        del operation, conversation_id, attachments
        if message == "first":
            first_started.set()
            assert release_first.wait(timeout=1.0)
        return f"chat-{message}"

    registry = SendJobRegistry(sender)
    first = registry.submit(operation="once", message="first")
    assert first_started.wait(timeout=1.0)
    second = registry.submit(operation="once", message="second")
    third = registry.submit(operation="once", message="third")

    now = time.time()
    with registry._lock:
        registry._jobs[first["send_id"]].update(
            status="rate_limited",
            retry_at=now + 120,
            retry_after_seconds=300,
            retry_attempt=1,
        )
        second_job = registry._job_with_queue_position_locked(registry._jobs[second["send_id"]])
        third_job = registry._job_with_queue_position_locked(registry._jobs[third["send_id"]])

    assert second_job["queue_position"] == 2
    assert third_job["queue_position"] == 3
    assert second_job["queue_eta_seconds"] == pytest.approx(420, abs=2)
    assert third_job["queue_eta_seconds"] == pytest.approx(720, abs=2)
    assert second_job["queue_eta_at"] == pytest.approx(now + 420, abs=2)
    assert third_job["queue_eta_at"] == pytest.approx(now + 720, abs=2)

    release_first.set()


def test_send_job_registry_deferred_head_does_not_block_runnable_jobs(tmp_path: Path) -> None:
    calls: list[str] = []

    def sender(
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str],
    ) -> str:
        del operation, conversation_id, attachments
        calls.append(message)
        if message == "busy reply":
            raise ControlDeferredError("conversation still active", retry_after=30)
        return f"chat-{message}"

    registry = SendJobRegistry(
        sender,
        recovery_path=tmp_path / "ui-send-retries.json",
    )
    first = registry.submit(
        operation="reply",
        message="busy reply",
        conversation_id="chat-busy",
    )

    deadline = time.monotonic() + 1.0
    first_result = registry.get(first["send_id"])
    while (
        first_result is not None
        and first_result["status"] != "retrying"
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
        first_result = registry.get(first["send_id"])

    assert first_result is not None
    assert first_result["status"] == "retrying"
    assert first_result["retry_after_seconds"] >= 29

    second = registry.submit(operation="once", message="independent new chat")
    deadline = time.monotonic() + 1.0
    second_result = registry.get(second["send_id"])
    while (
        second_result is not None
        and second_result["status"] != "succeeded"
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
        second_result = registry.get(second["send_id"])

    assert second_result is not None
    assert second_result["status"] == "succeeded"
    assert second_result["conversation_id"] == "chat-independent new chat"
    assert calls == ["busy reply", "independent new chat"]
    first_result = registry.get(first["send_id"])
    assert first_result is not None
    assert first_result["status"] == "retrying"


def test_send_job_registry_backend_outage_head_does_not_block_runnable_jobs(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def sender(
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str],
    ) -> str:
        del operation, conversation_id, attachments
        calls.append(message)
        if message == "backend unavailable":
            raise ControlUnavailableError("control socket unavailable")
        return f"chat-{message}"

    registry = SendJobRegistry(
        sender,
        recovery_path=tmp_path / "ui-send-retries.json",
    )
    first = registry.submit(operation="once", message="backend unavailable")

    deadline = time.monotonic() + 1.0
    first_result = registry.get(first["send_id"])
    while (
        first_result is not None
        and first_result["status"] != "retrying"
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
        first_result = registry.get(first["send_id"])

    assert first_result is not None
    assert first_result["status"] == "retrying"

    second = registry.submit(operation="once", message="independent runnable")
    deadline = time.monotonic() + 1.0
    second_result = registry.get(second["send_id"])
    while (
        second_result is not None
        and second_result["status"] != "succeeded"
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
        second_result = registry.get(second["send_id"])

    assert second_result is not None
    assert second_result["status"] == "succeeded"
    assert calls == ["backend unavailable", "independent runnable"]


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


def test_send_job_registry_keeps_control_outages_queued_until_backend_recovers() -> None:
    calls = 0
    sleeps: list[float] = []

    def sender(operation: str, message: str, conversation_id: str, attachments: list[str]) -> str:
        nonlocal calls
        calls += 1
        if calls <= 6:
            raise ControlUnavailableError("scheduler control socket unavailable")
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
    assert calls == 7
    assert sleeps == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0]
    assert result["retry_attempt"] == 0


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
    while (
        result is not None and result["status"] != "dead_lettered" and time.monotonic() < deadline
    ):
        time.sleep(0.01)
        result = registry.get(queued["send_id"])

    assert result is not None
    assert result["status"] == "dead_lettered"
    assert result["conversation_id"] == "chat-1"
    assert result["error"] == "browser session unavailable"
    assert result["retry_attempt"] == 5
    assert calls == 5
    assert attachment.exists()
    persisted = {"jobs": registry._database_records()}
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


def test_sidebar_window_is_selected_by_creation_time_not_response_activity(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    for conversation_id in ("older-with-late-response", "newer-chat"):
        cache.start(
            conversation_id,
            context_id=f"context-{conversation_id}",
            job_name="",
            prompt=conversation_id,
        )
    with cache.connection:
        cache.connection.execute(
            "UPDATE conversations SET created_at = 10, updated_at = 10000 WHERE id = ?",
            ("older-with-late-response",),
        )
        cache.connection.execute(
            "UPDATE conversations SET created_at = 20, updated_at = 20 WHERE id = ?",
            ("newer-chat",),
        )
    cache.close()

    store = ReadOnlyChatStore(path)

    assert [chat["id"] for chat in store.conversations(limit=1)] == ["newer-chat"]


def test_ui_server_orders_pinned_then_pending_then_created(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    for conversation_id, created_at in (("pinned-old", 10), ("newer", 40), ("older", 30)):
        cache.start(
            conversation_id,
            context_id=f"context-{conversation_id}",
            job_name="",
            prompt=conversation_id,
        )
        with cache.connection:
            cache.connection.execute(
                "UPDATE conversations SET created_at = ?, updated_at = ? WHERE id = ?",
                (created_at, created_at, conversation_id),
            )
    cache.close()

    store = ReadOnlyChatStore(path)
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    server.send_jobs.list_conversation_receipts = MagicMock(  # type: ignore[method-assign]
        return_value=[
            {
                "send_id": "pending-send",
                "operation": "once",
                "message": "pending",
                "client_id": "pending-client",
                "status": "queued",
                "conversation_id": "",
                "created_at": 20.0,
                "updated_at": 9999.0,
            }
        ]
    )
    try:
        chats = server.conversations(limit=3, include_ids=["pinned-old"])
        page = server.conversation_page(limit=2, include_ids=["pinned-old"])
    finally:
        server.server_close()

    assert [chat["id"] for chat in chats] == [
        "pinned-old",
        "pending-new-pending-client",
        "newer",
        "older",
    ]
    assert page["has_more"] is True
    assert [chat["id"] for chat in page["chats"]] == [
        "pinned-old",
        "pending-new-pending-client",
        "newer",
    ]


def test_pinned_chat_is_included_outside_bounded_sidebar_limit(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    for conversation_id in ("old-pinned", "recent-one", "recent-two"):
        cache.start(
            conversation_id,
            context_id=f"context-{conversation_id}",
            job_name="",
            prompt=conversation_id,
        )
    with cache.connection:
        cache.connection.execute(
            "UPDATE conversations SET created_at = 10, updated_at = 10 WHERE id = ?",
            ("old-pinned",),
        )
        cache.connection.execute(
            "UPDATE conversations SET created_at = 20, updated_at = 20 WHERE id = ?",
            ("recent-one",),
        )
        cache.connection.execute(
            "UPDATE conversations SET created_at = 30, updated_at = 30 WHERE id = ?",
            ("recent-two",),
        )
    cache.close()

    store = ReadOnlyChatStore(path)
    store_rows = store.conversations(limit=1, include_ids=["old-pinned"])
    assert {chat["id"] for chat in store_rows} == {"old-pinned", "recent-two"}

    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        chats = server.conversations(limit=1, include_ids=["old-pinned"])
    finally:
        server.server_close()

    assert {chat["id"] for chat in chats} == {"old-pinned", "recent-two"}


def test_read_only_store_hides_delivery_timeout_ui_noise(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "chat-timeout",
        context_id="context-timeout",
        job_name="",
        prompt="Keep working",
    )
    noisy_content = (
        "Progress before timeout.\n\n"
        "Message delivery timed out. Please try again.\n\n"
        "Progress after retry."
    )
    cache.write_snapshot(
        "chat-timeout",
        {
            "title": "Recovered delivery",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep working"},
                {"id": "a1", "role": "assistant", "content": noisy_content},
            ],
        },
    )
    persisted = cache.connection.execute(
        "SELECT content FROM messages WHERE conversation_id = ? AND message_key = ?",
        ("chat-timeout", "a1"),
    ).fetchone()
    assert persisted is not None
    assert "Message delivery timed out" not in str(persisted["content"])

    with cache.connection:
        cache.connection.execute(
            "UPDATE messages SET content = ? WHERE conversation_id = ? AND message_key = ?",
            (noisy_content, "chat-timeout", "a1"),
        )
    cache.close()

    chat = ReadOnlyChatStore(path).conversation("chat-timeout")

    assert chat is not None
    content = chat["messages"][-1]["content"]
    assert content == "Progress before timeout.\n\n\nProgress after retry."
    assert "Message delivery timed out" not in content


def test_read_only_store_hides_legacy_delivery_timeout_sidebar_preview(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "chat-timeout-preview",
        context_id="context-timeout-preview",
        job_name="",
        prompt="Keep working on the roadmap",
    )
    with cache.connection:
        cache.connection.execute(
            "UPDATE conversations SET preview = ? WHERE id = ?",
            ("Message delivery timed out. Please try again.", "chat-timeout-preview"),
        )
    cache.close()

    chats = ReadOnlyChatStore(path).conversations()
    chat = next(item for item in chats if item["id"] == "chat-timeout-preview")

    assert chat["preview"] == "Keep working on the roadmap"


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


def test_read_only_store_change_token_ignores_log_writes(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)
    before = store.change_token()

    store.log_path.write_text("log-only change\n")

    assert store.change_token() == before


def test_ui_serves_manifest_and_sse_refresh_event(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)
    with patch("prompta.web.socket.gethostname", return_value="nox.presley.nz"):
        server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base_url}/", timeout=2) as response:
            assert response.status == 200
            index_html = response.read().decode()
            assert '<div id="app" data-server-name="Nox"></div>' in index_html
            assert '<script type="module" src="./app.js"></script>' in index_html

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

        with urlopen(f"{base_url}/api/changelog", timeout=2) as response:
            assert response.status == 200
            changelog = json.loads(response.read().decode())
            assert changelog["changes"]
            assert len(changelog["changes"]) <= 100
            assert changelog["changes"][0]["title"]
            assert changelog["changes"][0]["hash"]
            assert changelog["total"] >= len(changelog["changes"])
            assert changelog["has_more"] is (changelog["total"] > len(changelog["changes"]))

        with urlopen(f"{base_url}/api/changelog?limit=2", timeout=2) as response:
            changelog_page = json.loads(response.read().decode())
            assert len(changelog_page["changes"]) == min(2, changelog_page["total"])
            assert changelog_page["has_more"] is (changelog_page["total"] > 2)

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

            path.touch()
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

        saved = load_jobs(jobs_path)[result["name"]]
        assert saved.prompt == "fix bugs"
        assert saved.interval_seconds == 1800
        assert saved.exact_interval is True
        assert result["scheduler_started"] is True
        assert result["interval_minutes"] == 30
    finally:
        server.server_close()


def test_schedule_api_deduplicates_and_exposes_jobs(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        store,
        tmp_path / "state.json",
        jobs_path=jobs_path,
    )
    start_scheduler = MagicMock(return_value=True)
    server.job_service.start_scheduler = start_scheduler
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:

        def post_schedule(prompt: str, interval_minutes: float) -> tuple[int, dict[str, object]]:
            request = Request(
                f"{base_url}/api/schedule",
                data=json.dumps({"prompt": prompt, "interval_minutes": interval_minutes}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read())

        first_status, first = post_schedule("fix bugs", 30)
        duplicate_status, duplicate = post_schedule("  Fix   Bugs  ", 30)
        second_status, second = post_schedule("fix bugs", 60)

        with urlopen(f"{base_url}/api/jobs", timeout=2) as response:
            jobs_payload = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert first_status == HTTPStatus.CREATED
    assert first["created"] is True
    assert duplicate_status == HTTPStatus.OK
    assert duplicate["created"] is False
    assert duplicate["name"] == first["name"]
    assert second_status == HTTPStatus.CREATED
    assert second["created"] is True
    assert second["name"] != first["name"]
    assert len(jobs_payload["jobs"]) == 2
    assert sorted(job["interval_minutes"] for job in jobs_payload["jobs"]) == [30.0, 60.0]
    assert {job["name"] for job in jobs_payload["jobs"]} == {first["name"], second["name"]}
    assert start_scheduler.call_count == 3


def test_schedule_api_returns_clear_interval_validation_error(tmp_path: Path) -> None:
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        ReadOnlyChatStore(tmp_path / "missing.sqlite3"),
        tmp_path / "state.json",
        jobs_path=tmp_path / "jobs.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/schedule",
            data=json.dumps({"prompt": "fix bugs", "interval_minutes": 0.05}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2)
        payload = json.loads(error.value.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert error.value.code == HTTPStatus.BAD_REQUEST
    assert payload["error"] == "Schedule interval must be at least 6 seconds"


def test_schedule_every_rejects_invalid_interval_and_prompt(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        store,
        tmp_path / "state.json",
        jobs_path=tmp_path / "jobs.json",
    )
    try:
        with pytest.raises(ValueError, match="finite value greater than zero"):
            server.schedule_every("fix bugs", float("nan"))
        with pytest.raises(ValueError, match="finite value greater than zero"):
            server.schedule_every("fix bugs", float("inf"))
        with pytest.raises(ValueError, match="finite value greater than zero"):
            server.schedule_every("fix bugs", 0)
        with pytest.raises(ValueError, match="at least 6 seconds"):
            server.schedule_every("fix bugs", 0.09)
        with pytest.raises(ValueError, match="cannot exceed 30 days"):
            server.schedule_every("fix bugs", 60 * 24 * 31)
        with pytest.raises(ValueError, match="prompt is required"):
            server.schedule_every("   ", 30)
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


def test_read_only_store_reads_recent_nox_logs(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    logs = tmp_path / "prompta-nox.log"
    logs.write_text("\n".join(f"line {index}" for index in range(8)) + "\n")
    store = ReadOnlyChatStore(path, logs, journal_unit="")

    payload = store.logs(limit=3)

    assert payload["exists"] is True
    assert payload["lines"] == ["line 5", "line 6", "line 7"]
    assert payload["updated_at"] is not None
    assert payload["source"] == "file"


def test_read_only_store_reports_missing_nox_logs(tmp_path: Path) -> None:
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

    assert (
        first
        == second
        == {
            "exists": True,
            "lines": ["unexpected journal line"],
            "updated_at": None,
            "source": "journal",
        }
    )


def test_read_only_store_tracks_real_message_activity_for_broken_chat_detection(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)

    with patch("prompta.cache.time.time", return_value=1_000.0):
        cache.start(
            "chat-health",
            context_id="context-health",
            job_name="",
            prompt="Keep working",
        )

    snapshot = {
        "title": "Health check",
        "streaming": True,
        "messages": [
            {"id": "u1", "role": "user", "content": "Keep working"},
            {"id": "a1", "role": "assistant", "content": "Working"},
        ],
    }

    with patch("prompta.cache.time.time", return_value=2_000.0):
        cache.write_snapshot("chat-health", snapshot)

    with patch("prompta.cache.time.time", return_value=5_000.0):
        cache.write_snapshot("chat-health", snapshot)

    unchanged = cache.connection.execute(
        "SELECT role, activity_at FROM messages WHERE conversation_id = ? ORDER BY ordinal",
        ("chat-health",),
    ).fetchall()
    assert [(row["role"], row["activity_at"]) for row in unchanged] == [
        ("user", 2_000.0),
        ("assistant", 2_000.0),
    ]

    changed_snapshot = {
        **snapshot,
        "messages": [
            snapshot["messages"][0],
            {"id": "a1", "role": "assistant", "content": "Still working"},
        ],
    }
    with patch("prompta.cache.time.time", return_value=5_001.0):
        cache.write_snapshot("chat-health", changed_snapshot)

    store = ReadOnlyChatStore(path)
    summary = next(item for item in store.conversations() if item["id"] == "chat-health")
    detail = store.conversation("chat-health")
    cache.close()

    assert summary["last_user_at"] == 2_000.0
    assert summary["last_assistant_at"] == 5_001.0
    assert detail is not None
    assistant = next(message for message in detail["messages"] if message["role"] == "assistant")
    assert assistant["activity_at"] == 5_001.0


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


def test_ui_server_defaults_identity_to_local_hostname(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    with patch("prompta.web.socket.gethostname", return_value="nox.presley.nz"):
        server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        assert server.host_name == "nox"
        assert server.display_name == "Nox"
    finally:
        server.server_close()


def test_service_worker_prefers_network_updates_with_offline_shell_fallback() -> None:
    script = (
        Path(__file__).resolve().parents[1] / "src" / "prompta" / "static" / "sw.js"
    ).read_text()

    network_fetch = script.index("const response = await fetch(event.request);")
    cache_fallback = script.index("const cached = await caches.match(event.request);")
    assert network_fetch < cache_fallback
    assert 'const BUILD_ID = "__PROMPTA_UI_HEAD__";' in script
    assert 'const CACHE_NAME = "prompta-shell-" + (BUILD_ID || "dev");' in script
    assert "client.navigate(client.url)" not in script
    assert "url.pathname.startsWith(apiPrefix)" in script
    assert "await cache.put(event.request, response.clone())" in script
    assert 'const shell = await caches.match(assetUrl("./"));' in script


def test_service_worker_response_is_versioned_to_deployed_head(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch("prompta.web._UI_HEAD", "deadbeef"):
            with urlopen(f"http://127.0.0.1:{server.server_port}/sw.js", timeout=2) as response:
                script = response.read().decode()
                content_type = response.headers.get_content_type()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert 'const BUILD_ID = "deadbeef";' in script
    assert "__PROMPTA_UI_HEAD__" not in script
    assert content_type == "text/javascript"


def test_ui_server_exposes_server_identity_and_manifest(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    with patch("prompta.web.socket.gethostname", return_value="nox.presley.nz"):
        server = PromptaUIServer(
            ("127.0.0.1", 0),
            store,
            tmp_path / "state.json",
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

    assert "<title>Prompta · Nox</title>" in index
    assert '<meta name="application-name" content="Prompta · Nox">' in index
    assert '<meta name="apple-mobile-web-app-title" content="Prompta Nox">' in index
    assert '<div id="app" data-server-name="Nox"></div>' in index
    assert "__PROMPTA_SERVER_NAME__" not in index
    assert manifest["name"] == "Prompta · Nox"
    assert manifest["short_name"] == "Prompta Nox"
    assert manifest["id"] == "./"
    assert manifest["start_url"] == "./"
    assert manifest["scope"] == "./"
    assert manifest["display"] == "standalone"
    assert manifest["background_color"] == "#212121"
    assert manifest["theme_color"] == "#212121"
    assert manifest["icons"] == [
        {
            "src": "./icon.svg",
            "sizes": "any",
            "type": "image/svg+xml",
            "purpose": "any maskable",
        }
    ]
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


def test_event_stream_sends_presence_heartbeat(tmp_path: Path) -> None:
    with patch("prompta.web.socket.gethostname", return_value="nox.presley.nz"):
        server = PromptaUIServer(
            ("127.0.0.1", 0),
            ReadOnlyChatStore(tmp_path / "missing.sqlite3"),
            tmp_path / "state.json",
        )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch("prompta.web._EVENT_HEARTBEAT_SECONDS", 0.01):
            with urlopen(
                f"http://127.0.0.1:{server.server_port}/api/events", timeout=2
            ) as response:
                lines = []
                heartbeat_seen = False
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    line = response.readline().decode()
                    lines.append(line)
                    if heartbeat_seen and line.startswith("data: "):
                        break
                    heartbeat_seen = line == "event: heartbeat" + chr(10)
        assert "event: refresh" + chr(10) in lines
        heartbeat_index = lines.index("event: heartbeat" + chr(10))
        heartbeat = json.loads(lines[heartbeat_index + 1].removeprefix("data: "))
        assert heartbeat == {"server": "nox", "online": True}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_read_only_store_hides_network_error_ui_noise(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "chat-network-error",
        context_id="context-network-error",
        job_name="",
        prompt="Keep working",
    )
    noisy_content = (
        "Progress before retry.\n\n"
        + "A network error occurred. Please check your connection and try again. If this issue persists please contact us through our help center at help.openai.com."
        + "\n\nProgress after retry."
    )
    cache.write_snapshot(
        "chat-network-error",
        {
            "title": "Recovered network error",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep working"},
                {"id": "a1", "role": "assistant", "content": noisy_content},
            ],
        },
    )

    persisted = cache.connection.execute(
        "SELECT content FROM messages WHERE conversation_id = ? AND message_key = ?",
        ("chat-network-error", "a1"),
    ).fetchone()
    assert persisted is not None
    assert "A network error occurred" not in str(persisted["content"])

    with cache.connection:
        cache.connection.execute(
            "UPDATE conversations SET preview = ? WHERE id = ?",
            (
                "A network error occurred. Please check your connection and try again. If this issue persists please contact us through our help center at help.openai.com.",
                "chat-network-error",
            ),
        )
    cache.close()

    store = ReadOnlyChatStore(path)
    chat = store.conversation("chat-network-error")
    chats = store.conversations()
    sidebar_chat = next(item for item in chats if item["id"] == "chat-network-error")

    assert chat is not None
    assert "A network error occurred" not in chat["messages"][-1]["content"]
    assert sidebar_chat["preview"] == "Progress before retry. Progress after retry."


def test_read_only_store_hides_combined_connection_interruption_from_legacy_chat(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "chat-connection-interrupted",
        context_id="context-connection-interrupted",
        job_name="",
        prompt="Keep working",
    )
    cache.write_snapshot(
        "chat-connection-interrupted",
        {
            "title": "Interrupted response",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep working"},
                {
                    "id": "a1",
                    "role": "assistant",
                    "content": "Useful progress.\n\nConnection interrupted. Waiting for the complete answer",
                },
            ],
        },
    )
    with cache.connection:
        cache.connection.execute(
            "UPDATE conversations SET preview = ? WHERE id = ?",
            (
                "Useful progress. Connection interrupted. Waiting for the complete answer",
                "chat-connection-interrupted",
            ),
        )
    cache.close()

    store = ReadOnlyChatStore(path)
    chat = store.conversation("chat-connection-interrupted")
    sidebar_chat = next(
        item for item in store.conversations() if item["id"] == "chat-connection-interrupted"
    )

    assert chat is not None
    assert chat["messages"][-1]["content"] == "Useful progress."
    assert sidebar_chat["preview"] == "Useful progress."
