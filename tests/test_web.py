from __future__ import annotations

from pathlib import Path

from prompta.cache import ChatCache
from prompta.web import ReadOnlyChatStore


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
