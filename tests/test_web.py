from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Event, Thread
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.request import urlopen

import pytest

from prompta.cache import ChatCache
from prompta.web import PromptaUIServer, ReadOnlyChatStore, SendJobRegistry, _remote_control


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


def test_remote_control_uses_user_ssh_config() -> None:
    completed = MagicMock(
        returncode=0,
        stdout='{"ok": true, "conversation_id": "chat-id"}\n',
        stderr="",
    )
    with patch("prompta.web.subprocess.run", return_value=completed) as run:
        result = _remote_control(
            "glass",
            operation="reply",
            conversation_id="chat-id",
            message="Continue",
        )

    assert result == "chat-id"
    argv = run.call_args.args[0]
    assert argv[:3] == ["ssh", "-F", str(Path.home() / ".ssh" / "config")]
    assert run.call_args.kwargs["timeout"] > 10 * 60


def test_remote_control_surfaces_concise_remote_error() -> None:
    completed = MagicMock(
        returncode=0,
        stdout='{"ok": false, "error": "ChatGPT send timed out"}\n',
        stderr="",
    )
    with (
        patch("prompta.web.subprocess.run", return_value=completed),
        pytest.raises(RuntimeError, match="ChatGPT send timed out"),
    ):
        _remote_control(
            "glass",
            operation="reply",
            conversation_id="chat-id",
            message="Continue",
        )


def test_local_ui_uses_direct_send_when_scheduler_is_stopped(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with (
            patch("prompta.web._daemon_is_running", return_value=False),
            patch("prompta.web._send_direct", AsyncMock(return_value="chat-direct")) as direct,
        ):
            result = server._send("once", "Hello", "")
    finally:
        server.server_close()

    assert result == "chat-direct"
    direct.assert_awaited_once_with(
        tmp_path / "state.json",
        tmp_path / "chats.sqlite3",
        "Hello",
        conversation_id="",
    )


def test_local_ui_uses_control_socket_when_scheduler_is_running(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    try:
        with (
            patch("prompta.web._daemon_is_running", return_value=True),
            patch(
                "prompta.web._send_once_via_control",
                AsyncMock(return_value="chat-control"),
            ) as control,
            patch("prompta.web._send_direct", AsyncMock()) as direct,
        ):
            result = server._send("once", "Hello", "")
    finally:
        server.server_close()

    assert result == "chat-control"
    control.assert_awaited_once_with(tmp_path / "state.json", "Hello")
    direct.assert_not_awaited()


def test_send_job_registry_returns_before_sender_finishes() -> None:
    release = Event()

    def sender(operation: str, message: str, conversation_id: str) -> str:
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


def test_send_job_registry_surfaces_background_error() -> None:
    def sender(operation: str, message: str, conversation_id: str) -> str:
        raise RuntimeError("browser session unavailable")

    registry = SendJobRegistry(sender)
    queued = registry.submit(operation="reply", message="Continue", conversation_id="chat-1")

    deadline = time.monotonic() + 1.0
    result = registry.get(queued["send_id"])
    while result is not None and result["status"] != "failed" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = registry.get(queued["send_id"])

    assert result is not None
    assert result["status"] == "failed"
    assert result["conversation_id"] == "chat-1"
    assert result["error"] == "browser session unavailable"


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


def test_read_only_store_searches_message_content(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)

    assert [chat["id"] for chat in store.conversations(query="Implemented")] == ["chat-1"]
    assert store.conversations(query="not present") == []


def test_read_only_store_does_not_create_missing_database(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    store = ReadOnlyChatStore(path)

    assert store.conversations() == []
    assert store.conversation("missing") is None
    assert store.stats() == {"exists": False, "total": 0, "active": 0}
    assert not path.exists()


def test_read_only_store_reads_recent_glass_logs(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    logs = tmp_path / "prompta-glass.log"
    logs.write_text("\n".join(f"line {index}" for index in range(8)) + "\n")
    store = ReadOnlyChatStore(path, logs)

    payload = store.logs(limit=3)

    assert payload["exists"] is True
    assert payload["lines"] == ["line 5", "line 6", "line 7"]
    assert payload["updated_at"] is not None


def test_read_only_store_reports_missing_glass_logs(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "chats.sqlite3", tmp_path / "missing.log")

    assert store.logs() == {"exists": False, "lines": [], "updated_at": None}


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
