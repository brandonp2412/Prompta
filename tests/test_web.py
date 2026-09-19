from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from prompta.cache import ChatCache
from prompta.web import ReadOnlyChatStore, _remote_control


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
    completed = MagicMock(returncode=0, stdout="chat-id\n", stderr="")
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


def test_read_only_store_lists_and_reads_cached_chat(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    _seed_cache(path)
    store = ReadOnlyChatStore(path)

    chats = store.conversations()
    chat = store.conversation("chat-1")

    assert chats[0]["id"] == "chat-1"
    assert chats[0]["status"] == "active"
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
