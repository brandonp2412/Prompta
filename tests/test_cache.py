from __future__ import annotations

import sqlite3
from pathlib import Path

from prompta.cache import ChatCache


def test_cache_tracks_streaming_then_completed_conversation(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="flux",
        prompt="Do work",
    )

    streaming = {
        "title": "Flux work",
        "path": "/c/conversation-1",
        "streaming": True,
        "messages": [
            {"id": "u1", "role": "user", "content": "Do work"},
            {"id": "a1", "role": "assistant", "content": "Starting"},
        ],
    }
    cache.write_snapshot("conversation-1", streaming)

    streaming["streaming"] = False
    streaming["messages"][1]["content"] = "Finished"
    cache.write_snapshot("conversation-1", streaming, complete=True)

    conversations = cache.recent_conversations()
    messages = cache.messages("conversation-1")
    metadata = cache.metadata("conversation-1")
    cache.close()

    assert conversations[0]["status"] == "complete"
    assert conversations[0]["job_name"] == "flux"
    assert messages[-1]["content"] == "Finished"
    assert messages[-1]["status"] == "complete"
    assert metadata["url"] == "https://chatgpt.com/c/conversation-1"
    assert path.stat().st_mode & 0o777 == 0o600


def test_snapshot_promotes_transient_web_route_to_canonical_url(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "WEB:transient",
        context_id="context-1",
        job_name="",
        prompt="Do work",
    )

    cache.write_snapshot(
        "WEB:transient",
        {
            "title": "Work",
            "path": "/c/6aae32ba-f3b4-83ec-bdf9-d34b777de6ce",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": "Done"},
            ],
        },
        complete=True,
    )

    metadata = cache.metadata("WEB:transient")
    cache.close()

    assert metadata["url"] == "https://chatgpt.com/c/6aae32ba-f3b4-83ec-bdf9-d34b777de6ce"


def test_cache_marks_previous_active_conversations_interrupted(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="kite",
        prompt="Keep working",
    )
    assert cache.mark_orphaned_active() == 1
    cache.close()

    connection = sqlite3.connect(path)
    status = connection.execute(
        "SELECT status FROM conversations WHERE id = 'conversation-1'"
    ).fetchone()[0]
    connection.close()

    assert status == "interrupted"


def test_cache_seeds_prompt_before_first_browser_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="Keep this visible even if the browser dies",
    )

    messages = cache.messages("conversation-1")
    cache.close()

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Keep this visible even if the browser dies"
    assert messages[0]["status"] == "complete"


def test_snapshot_replaces_seed_and_removes_transient_messages(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="Do work",
    )

    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": "request-placeholder-request-conversation-1-0",
                    "role": "assistant",
                    "content": "Thinking",
                },
            ],
        },
    )
    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Work",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": "Finished"},
            ],
        },
        complete=True,
    )

    messages = cache.messages("conversation-1")
    cache.close()

    assert [(message["message_key"], message["content"]) for message in messages] == [
        ("u1", "Do work"),
        ("a1", "Finished"),
    ]


def test_request_placeholder_is_never_persisted(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="Do work",
    )
    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": "request-placeholder-request-conversation-1-0",
                    "role": "assistant",
                    "content": "Thinking",
                },
            ],
        },
    )

    messages = cache.messages("conversation-1")
    cache.close()

    assert [(message["message_key"], message["content"]) for message in messages] == [
        ("u1", "Do work"),
    ]


def test_partial_snapshot_does_not_delete_previous_canonical_turns(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="First question",
    )
    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Long chat",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "First question"},
                {"id": "a1", "role": "assistant", "content": "First answer"},
                {"id": "u2", "role": "user", "content": "Second question"},
                {"id": "a2", "role": "assistant", "content": "Second answer"},
            ],
        },
        complete=True,
    )

    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Long chat",
            "streaming": True,
            "messages": [
                {"id": "u2", "role": "user", "content": "Second question"},
                {
                    "id": "__prompta_live_assistant_turn2__",
                    "role": "assistant",
                    "content": "Second answer, continuing",
                },
            ],
        },
    )

    messages = cache.messages("conversation-1")
    cache.close()

    assert [(message["message_key"], message["content"]) for message in messages] == [
        ("u1", "First question"),
        ("a1", "First answer"),
        ("u2", "Second question"),
        ("a2", "Second answer, continuing"),
    ]


def test_cache_migration_backfills_prompt_for_legacy_empty_conversation(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="Legacy prompt",
    )
    cache.connection.execute(
        "DELETE FROM messages WHERE conversation_id = ?",
        ("conversation-1",),
    )
    cache.connection.commit()
    cache.close()

    reopened = ChatCache(path)
    messages = reopened.messages("conversation-1")
    reopened.close()

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Legacy prompt"
