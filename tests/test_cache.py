from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from prompta.cache import ChatCache


def test_live_snapshot_uses_source_event_timeline_for_assistant_content(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="Do work",
    )
    source_events = [
        {
            "id": "text-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["First text"],
            "text": "",
            "create_time": 1.0,
            "end_turn": False,
        },
        {
            "id": "call-1",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps({"path": "/Test MCP/link_123/first", "args": {"step": 1}}),
            "create_time": 2.0,
        },
        {
            "id": "text-2",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Between tools"],
            "text": "",
            "create_time": 3.0,
            "end_turn": False,
        },
        {
            "id": "call-2",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps({"path": "/Test MCP/link_123/second", "args": {"step": 2}}),
            "create_time": 4.0,
        },
        {
            "id": "result-1",
            "role": "tool",
            "recipient": "all",
            "content_type": "code",
            "text": json.dumps(
                {
                    "type": "mcpToolCall",
                    "appContext": {"appName": "Test MCP", "actionName": "first"},
                    "arguments": {"step": 1},
                    "status": "completed",
                }
            ),
            "create_time": 5.0,
        },
        {
            "id": "result-2",
            "role": "tool",
            "recipient": "all",
            "content_type": "code",
            "text": json.dumps(
                {
                    "type": "mcpToolCall",
                    "appContext": {"appName": "Test MCP", "actionName": "second"},
                    "arguments": {"step": 2},
                    "status": "completed",
                }
            ),
            "create_time": 6.0,
        },
    ]
    fence = chr(96) * 3
    grouped_content = (
        "First text\n\nBetween tools\n\n"
        f"{fence}tool:Test MCP · first\nCalled tool\n{fence}\n\n"
        f"{fence}tool:Test MCP · second\nCalled tool\n{fence}"
    )

    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": grouped_content},
            ],
            "source_events": source_events,
        },
    )

    content = cache.messages("conversation-1")[-1]["content"]
    cache.close()

    assert content.index("First text") < content.index("Test MCP · first")
    assert content.index("Test MCP · first") < content.index("Between tools")
    assert content.index("Between tools") < content.index("Test MCP · second")


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


def test_cache_persists_compact_sidebar_preview(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-preview",
        context_id="context-preview",
        job_name="",
        prompt="Keep going",
    )
    fence = chr(96) * 3
    tool_payload = "x" * 50_000
    assistant = (
        "Useful start.\n\n"
        f"{fence}tool-call: execute_python\n"
        f'{{"code":"{tool_payload}"}}\n'
        f"{fence}\n\n"
        "Useful end."
    )
    cache.write_snapshot(
        "conversation-preview",
        {
            "title": "Preview",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep going"},
                {"id": "a1", "role": "assistant", "content": assistant},
            ],
        },
    )
    row = cache.connection.execute(
        "SELECT preview FROM conversations WHERE id = ?",
        ("conversation-preview",),
    ).fetchone()
    cache.close()

    assert row is not None
    assert row["preview"] == "Useful start. Useful end."


def test_cache_quarantines_corrupt_database_and_recreates_cache(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    path.write_bytes(b"not a sqlite database")
    wal_path = Path(f"{path}-wal")
    shm_path = Path(f"{path}-shm")
    wal_path.write_bytes(b"stale wal")
    shm_path.write_bytes(b"stale shm")

    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="Recovered",
    )
    messages = cache.messages("conversation-1")
    cache.close()

    quarantined = sorted(tmp_path.glob("chats.sqlite3.corrupt-*"))
    quarantined_databases = [
        candidate for candidate in quarantined if not candidate.name.endswith(("-wal", "-shm"))
    ]
    assert len(quarantined_databases) == 1
    quarantine = quarantined_databases[0]
    assert quarantine.read_bytes() == b"not a sqlite database"
    assert Path(f"{quarantine}-wal").read_bytes() == b"stale wal"
    assert Path(f"{quarantine}-shm").read_bytes() == b"stale shm"
    assert path.exists()
    assert messages[0]["content"] == "Recovered"


def test_snapshot_does_not_reopen_completed_conversation_without_resume(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="Do work",
    )
    snapshot = {
        "title": "Work",
        "path": "/c/conversation-1",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Do work"},
            {"id": "a1", "role": "assistant", "content": "Done"},
        ],
    }
    cache.write_snapshot("conversation-1", snapshot, complete=True)
    completed = cache.connection.execute(
        "SELECT status, completed_at FROM conversations WHERE id = ?",
        ("conversation-1",),
    ).fetchone()
    assert completed is not None
    completed_at = completed["completed_at"]

    # ChatGPT can mutate harmless DOM metadata immediately after a turn settles.
    # A retained-tab refresh must not make the conversation look active again.
    snapshot["title"] = "Work renamed"
    cache.write_snapshot("conversation-1", snapshot)

    retained = cache.connection.execute(
        "SELECT status, completed_at FROM conversations WHERE id = ?",
        ("conversation-1",),
    ).fetchone()
    assert retained is not None
    assert retained["status"] == "complete"
    assert retained["completed_at"] == completed_at

    # An explicit reply/recovery resume is the only path that should reopen it.
    cache.resume("conversation-1", context_id="context-2")
    cache.write_snapshot("conversation-1", snapshot)
    resumed = cache.connection.execute(
        "SELECT status, completed_at FROM conversations WHERE id = ?",
        ("conversation-1",),
    ).fetchone()
    cache.close()

    assert resumed is not None
    assert resumed["status"] == "active"
    assert resumed["completed_at"] is None


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


def test_cache_migration_removes_seeded_prompt_after_real_user_message(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="Do work",
    )
    with cache.connection:
        cache.connection.execute(
            """
            INSERT INTO messages (
                conversation_id, message_key, ordinal, role, content, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, 'user', ?, 'complete', 2, 2)
            """,
            ("conversation-1", "real-user-message", 0, "Do work"),
        )
    cache.close()

    reopened = ChatCache(path)
    messages = reopened.messages("conversation-1")
    reopened.close()

    assert [(message["message_key"], message["role"]) for message in messages] == [
        ("real-user-message", "user"),
    ]


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


def test_cache_lists_active_and_recent_interrupted_streaming_conversations(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "active-chat",
        context_id="context-active",
        job_name="active-job",
        prompt="Keep working",
    )
    cache.start(
        "interrupted-chat",
        context_id="context-interrupted",
        job_name="",
        prompt="Still working",
    )
    cache.write_snapshot(
        "interrupted-chat",
        {
            "path": "/c/interrupted-chat",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Still working"},
                {"id": "a1", "role": "assistant", "content": "Working"},
            ],
        },
    )
    cache.mark_interrupted("interrupted-chat")
    cache.start(
        "old-interrupted-chat",
        context_id="context-old",
        job_name="",
        prompt="Old work",
    )
    cache.write_snapshot(
        "old-interrupted-chat",
        {
            "path": "/c/old-interrupted-chat",
            "streaming": True,
            "messages": [
                {"id": "u2", "role": "user", "content": "Old work"},
                {"id": "a2", "role": "assistant", "content": "Working"},
            ],
        },
    )
    cache.mark_interrupted("old-interrupted-chat")
    with cache.connection:
        cache.connection.execute(
            "UPDATE conversations SET updated_at = 1 WHERE id = ?",
            ("old-interrupted-chat",),
        )

    rows = cache.recoverable_conversations(interrupted_after=time.time() - 60)

    assert {row["id"] for row in rows} == {"active-chat", "interrupted-chat"}
    cache.close()


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


def test_snapshot_with_middle_gap_is_treated_as_partial(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="First question",
    )
    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Virtualized chat",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "First question"},
                {"id": "a1", "role": "assistant", "content": "First answer"},
                {"id": "u2", "role": "user", "content": "Second question"},
            ],
        },
    )

    # The DOM still starts with the first message, but virtualization dropped u2
    # before a newer turn appeared. This is not a complete history snapshot.
    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Virtualized chat",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "First question"},
                {"id": "a1", "role": "assistant", "content": "First answer"},
                {"id": "u3", "role": "user", "content": "Third question"},
                {"id": "a3", "role": "assistant", "content": "Third answer"},
            ],
        },
    )

    messages = cache.messages("conversation-1")
    cache.close()

    assert [(message["message_key"], message["ordinal"]) for message in messages] == [
        ("u1", 0),
        ("a1", 1),
        ("u2", 2),
        ("u3", 3),
        ("a3", 4),
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


def test_full_snapshot_collapses_stale_same_turn_assistant_sibling(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
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
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": "a1-tool-state",
                    "role": "assistant",
                    "content": "Called tool",
                },
                {
                    "id": "a1-final",
                    "role": "assistant",
                    "content": "Finished with the tool result",
                },
            ],
        },
        complete=True,
    )

    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Work",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": "a1-final",
                    "role": "assistant",
                    "content": "Finished with the tool result",
                },
            ],
        },
        complete=True,
    )

    messages = cache.messages("conversation-1")
    cache.close()

    assert [
        (message["message_key"], message["ordinal"], message["content"]) for message in messages
    ] == [
        ("u1", 0, "Do work"),
        ("a1-final", 1, "Finished with the tool result"),
    ]


def test_missing_only_assistant_in_user_turn_still_marks_snapshot_partial(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="First question",
    )
    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Virtualized chat",
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

    # The first turn's only assistant is absent. That is virtualization, not a
    # duplicate sibling, so it must stay cached.
    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Virtualized chat",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "First question"},
                {"id": "u2", "role": "user", "content": "Second question"},
                {"id": "a2", "role": "assistant", "content": "Second answer"},
            ],
        },
    )

    messages = cache.messages("conversation-1")
    cache.close()

    assert [(message["message_key"], message["ordinal"]) for message in messages] == [
        ("u1", 0),
        ("a1", 1),
        ("u2", 2),
        ("a2", 3),
    ]


def test_final_assistant_replaces_streaming_row_when_message_id_changes(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
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
                    "id": "temporary-assistant-id",
                    "role": "assistant",
                    "content": "Working",
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
                {
                    "id": "final-assistant-id",
                    "role": "assistant",
                    "content": "Working and finished",
                },
            ],
        },
        complete=True,
    )

    messages = cache.messages("conversation-1")
    cache.close()

    assert [(message["message_key"], message["status"]) for message in messages] == [
        ("u1", "complete"),
        ("final-assistant-id", "complete"),
    ]


def test_full_snapshot_removes_old_streaming_copy_from_completed_turn(tmp_path: Path) -> None:
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
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "First question"},
                {
                    "id": "__prompta_live_assistant_old__",
                    "role": "assistant",
                    "content": "Old streaming text that does not match the final answer",
                },
            ],
        },
    )
    cache.write_snapshot(
        "conversation-1",
        {
            "title": "Long chat",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "First question"},
                {"id": "a1", "role": "assistant", "content": "Final first answer"},
                {"id": "u2", "role": "user", "content": "Second question"},
                {
                    "id": "__prompta_live_assistant_current__",
                    "role": "assistant",
                    "content": "Current answer",
                },
            ],
        },
    )

    messages = cache.messages("conversation-1")
    cache.close()

    assert [(message["message_key"], message["status"]) for message in messages] == [
        ("u1", "complete"),
        ("a1", "complete"),
        ("u2", "complete"),
        ("__prompta_live_assistant_current__", "streaming"),
    ]


def test_cache_migration_removes_superseded_streaming_copies(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="First question",
    )
    with cache.connection:
        cache.connection.executemany(
            """
            INSERT INTO messages (
                conversation_id, message_key, ordinal, role, content, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "conversation-1",
                    "__prompta_live_assistant_old__",
                    1,
                    "assistant",
                    "Stale streaming copy",
                    "streaming",
                    1.0,
                    1.0,
                ),
                (
                    "conversation-1",
                    "a1",
                    2,
                    "assistant",
                    "Canonical answer",
                    "complete",
                    2.0,
                    2.0,
                ),
                (
                    "conversation-1",
                    "u2",
                    3,
                    "user",
                    "Next question",
                    "complete",
                    3.0,
                    3.0,
                ),
                (
                    "conversation-1",
                    "__prompta_live_assistant_current__",
                    4,
                    "assistant",
                    "Still generating",
                    "streaming",
                    4.0,
                    4.0,
                ),
            ],
        )
    cache.close()

    reopened = ChatCache(path)
    messages = reopened.messages("conversation-1")
    reopened.close()

    keys = [message["message_key"] for message in messages]
    assert "__prompta_live_assistant_old__" not in keys
    assert "__prompta_live_assistant_current__" in keys


def test_cache_migration_removes_request_placeholders(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="Do work",
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
                "conversation-1",
                "request-placeholder-request-conversation-1-0",
                1,
                "assistant",
                "Thinking",
                "streaming",
                1.0,
                1.0,
            ),
        )
    cache.close()

    cache = ChatCache(path)
    messages = cache.messages("conversation-1")
    cache.close()

    assert all(
        not message["message_key"].startswith("request-placeholder-") for message in messages
    )


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


def test_cache_recognizes_sqlite_corruption_error_codes() -> None:
    corrupt = sqlite3.DatabaseError("opaque sqlite failure")
    corrupt.sqlite_errorcode = sqlite3.SQLITE_CORRUPT  # type: ignore[attr-defined]
    notadb = sqlite3.DatabaseError("opaque sqlite failure")
    notadb.sqlite_errorcode = sqlite3.SQLITE_NOTADB  # type: ignore[attr-defined]

    assert ChatCache._is_corruption_error(corrupt) is True
    assert ChatCache._is_corruption_error(notadb) is True


def test_cache_quarantines_corrupt_database_and_recovers(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    corrupt_bytes = b"not a sqlite database\x00PROMPTA"
    path.write_bytes(corrupt_bytes)
    (tmp_path / "chats.sqlite3-wal").write_bytes(b"broken wal")
    (tmp_path / "chats.sqlite3-shm").write_bytes(b"broken shm")

    cache = ChatCache(path)
    cache.start(
        "conversation-after-recovery",
        context_id="context-1",
        job_name="recovery",
        prompt="Keep working",
    )
    cache.close()

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("SELECT COUNT(*) FROM conversations").fetchone() == (1,)
    finally:
        connection.close()

    archived_databases = [
        candidate
        for candidate in tmp_path.glob("chats.sqlite3.corrupt-*")
        if not candidate.name.endswith(("-wal", "-shm"))
    ]
    assert len(archived_databases) == 1
    assert archived_databases[0].read_bytes() == corrupt_bytes
