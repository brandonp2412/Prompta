from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from prompta.cache import ChatCache


def test_conversation_double_checked_defaults_false_and_can_be_marked(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-audited",
        context_id="context-1",
        job_name="once",
        prompt="Do the work",
    )

    before = cache.connection.execute(
        "SELECT double_checked FROM conversations WHERE id = ?",
        ("conversation-audited",),
    ).fetchone()
    assert before is not None
    assert before["double_checked"] == 0

    assert cache.mark_double_checked("conversation-audited") is True
    after = cache.connection.execute(
        "SELECT double_checked FROM conversations WHERE id = ?",
        ("conversation-audited",),
    ).fetchone()
    assert after is not None
    assert after["double_checked"] == 1

    assert cache.mark_double_checked("conversation-audited", checked=False) is True
    reset = cache.connection.execute(
        "SELECT double_checked FROM conversations WHERE id = ?",
        ("conversation-audited",),
    ).fetchone()
    cache.close()

    assert reset is not None
    assert reset["double_checked"] == 0


def test_cache_migration_adds_double_checked_to_existing_database(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-before-migration",
        context_id="context-1",
        job_name="once",
        prompt="Existing work",
    )
    cache.connection.execute("ALTER TABLE conversations DROP COLUMN double_checked")
    cache.connection.commit()
    cache.close()

    migrated = ChatCache(path)
    columns = {
        str(row["name"])
        for row in migrated.connection.execute("PRAGMA table_info(conversations)").fetchall()
    }
    row = migrated.connection.execute(
        "SELECT double_checked FROM conversations WHERE id = ?",
        ("conversation-before-migration",),
    ).fetchone()
    migrated.close()

    assert "double_checked" in columns
    assert row is not None
    assert row["double_checked"] == 0


def test_cache_creates_indexes_for_sidebar_and_structured_event_queries(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")

    conversation_indexes = {
        str(row["name"])
        for row in cache.connection.execute("PRAGMA index_list(conversations)").fetchall()
    }
    source_event_indexes = {
        str(row["name"])
        for row in cache.connection.execute("PRAGMA index_list(source_events)").fetchall()
    }
    message_indexes = {
        str(row["name"])
        for row in cache.connection.execute("PRAGMA index_list(messages)").fetchall()
    }
    assert "conversations_created_idx" in conversation_indexes
    assert "messages_incomplete_search_idx" in message_indexes
    assert "source_events_message_observed_idx" in source_event_indexes
    assert "source_events_conversation_source_created_idx" in source_event_indexes

    sidebar_plan = cache.connection.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT id
        FROM conversations
        ORDER BY created_at DESC, id
        LIMIT 20
        """
    ).fetchall()
    assert any("conversations_created_idx" in str(row["detail"]) for row in sidebar_plan)

    source_plan = cache.connection.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT MAX(source_created_at)
        FROM source_events
        WHERE conversation_id = ?
        """,
        ("chat-1",),
    ).fetchall()
    cache.close()

    assert any(
        "source_events_conversation_source_created_idx" in str(row["detail"]) for row in source_plan
    )


def test_completed_snapshot_trusts_end_turn_final_text_over_corrupt_dom_merge(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    conversation_id = "conversation-completed-final"
    cache.start(
        conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Check timestamps",
    )
    final_text = (
        "Fixed and deployed.\n\n"
        "Root cause was timestamp state becoming stale during DOM reconciliation."
    )
    snapshot = {
        "title": "Completed final",
        "path": f"/c/{conversation_id}",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Check timestamps"},
            {
                "id": "a1",
                "role": "assistant",
                "content": (
                    "Fixed and deployed.\n\n"
                    "Root cause was timestamptimestamp derivation commitDOM refresh fix"
                ),
            },
        ],
        "source_events": [
            {
                "id": "a1:dom-prose",
                "role": "assistant",
                "recipient": "all",
                "content_type": "text",
                "parts": ["Fixed and deployed.\n\nRoot cause was timestamp"],
                "create_time": 1.0,
                "end_turn": None,
            },
            {
                "id": "a1",
                "role": "assistant",
                "recipient": "all",
                "content_type": "text",
                "parts": [final_text],
                "create_time": 2.0,
                "end_turn": True,
            },
        ],
    }

    cache.write_snapshot(conversation_id, snapshot, complete=True)

    row = cache.connection.execute(
        "SELECT content FROM messages WHERE conversation_id = ? AND message_key = ?",
        (conversation_id, "a1"),
    ).fetchone()
    cache.close()

    assert row is not None
    assert row["content"] == final_text


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


def test_source_events_keep_canonical_order_across_reordered_snapshots(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    conversation_id = "conversation-canonical-source-order"
    cache.start(
        conversation_id,
        context_id="context-canonical-source-order",
        job_name="",
        prompt="Do work",
    )
    events = [
        {
            "id": "text-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["First text"],
            "create_time": 1.0,
            "end_turn": False,
        },
        {
            "id": "call-1",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps({"path": "/Test MCP/link/first", "args": {"step": 1}}),
            "create_time": 2.0,
            "end_turn": False,
        },
        {
            "id": "text-2",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Between tools"],
            "create_time": 3.0,
            "end_turn": False,
        },
        {
            "id": "call-2",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps({"path": "/Test MCP/link/second", "args": {"step": 2}}),
            "create_time": 4.0,
            "end_turn": False,
        },
    ]
    snapshot = {
        "title": "Work",
        "streaming": True,
        "messages": [
            {"id": "u1", "role": "user", "content": "Do work"},
            {"id": "a1", "role": "assistant", "content": "Working"},
        ],
        "source_events": events,
    }
    cache.write_snapshot(conversation_id, snapshot)

    revised_call = {**events[1], "reasoning_title": "Updated tool metadata"}
    cache.write_snapshot(
        conversation_id,
        {
            **snapshot,
            "source_events": [events[0], events[2], revised_call, events[3]],
        },
    )

    rows = cache.connection.execute(
        """
        SELECT ordinal, raw_json
        FROM source_events
        WHERE conversation_id = ? AND message_key = ?
        ORDER BY ordinal, rowid
        """,
        (conversation_id, "a1"),
    ).fetchall()
    cache.close()

    assert [row["ordinal"] for row in rows] == [0, 1, 2, 3, 4]
    assert [json.loads(row["raw_json"])["id"] for row in rows] == [
        "text-1",
        "call-1",
        "call-1",
        "text-2",
        "call-2",
    ]


def test_completed_message_recovers_observed_stream_order_on_read(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-complete-order",
        context_id="context-complete-order",
        job_name="",
        prompt="Do work",
    )
    fence = chr(96) * 3
    first_tool = (
        f'{fence}tool:Test MCP · first\n{{"created_at": 20.0, "status": "completed"}}\n{fence}'
    )
    second_tool = (
        f'{fence}tool:Test MCP · second\n{{"created_at": 40.0, "status": "completed"}}\n{fence}'
    )
    grouped_content = "\n\n".join(["Intro text", "Between tools", first_tool, second_tool])
    cache.write_snapshot(
        "conversation-complete-order",
        {
            "title": "Work",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": grouped_content},
            ],
        },
    )
    for index, (observed_at, parts) in enumerate(
        [
            (10.0, ["Intro text"]),
            (30.0, ["Intro text", "Between tools"]),
        ],
        start=1,
    ):
        event = {
            "id": f"observation-{index}:dom-prose",
            "parts": parts,
        }
        cache.connection.execute(
            """
            INSERT INTO source_events (
                conversation_id, message_key, event_key, ordinal, raw_json, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "conversation-complete-order",
                "a1",
                f"observation-{index}:dom-prose:source",
                index,
                json.dumps(event),
                observed_at,
            ),
        )
    cache.connection.commit()

    message = cache.messages("conversation-complete-order")[-1]
    cache.close()

    assert message["status"] == "complete"
    content = message["content"]
    assert content.index("Intro text") < content.index("Test MCP · first")
    assert content.index("Test MCP · first") < content.index("Between tools")
    assert content.index("Between tools") < content.index("Test MCP · second")


def test_live_snapshot_keeps_dom_order_when_source_prose_has_no_timestamp(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-dom-prose",
        context_id="context-dom-prose",
        job_name="",
        prompt="Do work",
    )
    fence = chr(96) * 3
    tool = f"{fence}tool:Test MCP · inspect\nCalled tool\n{fence}"
    visible_content = "\n\n".join(["Visible intro", tool, "Visible follow-up"])
    source_events = [
        {
            "id": "call-1",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps({"path": "/Test MCP/link_123/inspect", "args": {}}),
            "create_time": 2.0,
        },
        {
            "id": "__prompta_live_assistant_abc__:dom-prose",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Visible intro", "Visible follow-up"],
            "text": "",
            "create_time": None,
            "end_turn": None,
        },
    ]

    cache.write_snapshot(
        "conversation-dom-prose",
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": visible_content},
            ],
            "source_events": source_events,
        },
    )

    content = cache.messages("conversation-dom-prose")[-1]["content"]
    cache.close()

    assert content == visible_content
    assert content.index("Visible intro") < content.index("Test MCP · inspect")
    assert content.index("Test MCP · inspect") < content.index("Visible follow-up")


def test_snapshot_promotes_transient_structured_tools_to_durable_assistant(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-tool-handoff",
        context_id="context-tool-handoff",
        job_name="",
        prompt="Do work",
    )
    transient_key = "__prompta_live_assistant_tool_handoff__"
    fence = chr(96) * 3
    invocation = {
        "id": "call-1",
        "role": "assistant",
        "recipient": "api_tool.call_tool",
        "content_type": "code",
        "text": json.dumps({"path": "/Test MCP/link_123/inspect", "args": {"target": "kite"}}),
        "create_time": 2.0,
    }
    result = {
        "id": "result-1",
        "role": "tool",
        "recipient": "all",
        "content_type": "text",
        "text": json.dumps({"ok": True}),
        "create_time": 3.0,
        "invoked_resource": {
            "resource_uri": "/Test MCP/link_123/inspect",
            "app_name": "Test MCP",
        },
    }
    cache.write_snapshot(
        "conversation-tool-handoff",
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": transient_key,
                    "role": "assistant",
                    "content": f"{fence}tool:tool\nCalled tool\n{fence}",
                },
            ],
            "source_events": [invocation, result],
        },
    )

    final_event = {
        "id": "final-1",
        "role": "assistant",
        "recipient": "all",
        "content_type": "text",
        "text": "Done",
        "parts": ["Done"],
        "create_time": 4.0,
        "end_turn": True,
    }
    cache.write_snapshot(
        "conversation-tool-handoff",
        {
            "title": "Work",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": "a1",
                    "role": "assistant",
                    "content": f"{fence}tool:tool\nCalled tool\n{fence}\n\nDone",
                },
            ],
            "source_events": [final_event],
        },
        complete=True,
    )

    calls = cache.connection.execute(
        """
        SELECT message_key, connector, action, status, result_json
        FROM tool_calls
        WHERE conversation_id = ?
        ORDER BY ordinal
        """,
        ("conversation-tool-handoff",),
    ).fetchall()
    parts = cache.connection.execute(
        """
        SELECT message_key, kind, content
        FROM message_parts
        WHERE conversation_id = ?
        ORDER BY ordinal
        """,
        ("conversation-tool-handoff",),
    ).fetchall()
    stale_counts = [
        cache.connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE conversation_id = ? AND message_key = ?",
            ("conversation-tool-handoff", transient_key),
        ).fetchone()[0]
        for table in ("source_events", "message_parts", "tool_calls")
    ]
    cache.close()

    assert len(calls) == 1
    assert calls[0]["message_key"] == "a1"
    assert calls[0]["connector"] == "Test MCP"
    assert calls[0]["action"] == "inspect"
    assert calls[0]["status"] == "completed"
    assert json.loads(calls[0]["result_json"]) == {"ok": True}
    assert [part["kind"] for part in parts] == ["tool_call", "final_text"]
    assert all(part["message_key"] == "a1" for part in parts)
    assert "Test MCP · inspect" in parts[0]["content"]
    assert parts[1]["content"] == "Done"
    assert stale_counts == [0, 0, 0]


def test_snapshot_handoff_retains_latest_meaningful_dom_prose(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    conversation_id = "conversation-dom-prose-handoff"
    transient_key = "__prompta_live_assistant_dom_handoff__"
    cache.start(
        conversation_id,
        context_id="context-dom-prose-handoff",
        job_name="",
        prompt="Do work",
    )
    invocation = {
        "id": "call-1",
        "role": "assistant",
        "recipient": "api_tool.call_tool",
        "content_type": "code",
        "text": json.dumps({"path": "/Test MCP/link_123/inspect", "args": {}}),
        "create_time": 2.0,
    }
    result = {
        "id": "result-1",
        "role": "tool",
        "recipient": "all",
        "content_type": "text",
        "text": json.dumps({"ok": True}),
        "create_time": 3.0,
        "invoked_resource": {
            "resource_uri": "/Test MCP/link_123/inspect",
            "app_name": "Test MCP",
        },
    }
    dom_prose = {
        "id": f"{transient_key}:dom-prose",
        "role": "assistant",
        "recipient": "all",
        "content_type": "text",
        "parts": ["Visible progress"],
        "text": "",
        "create_time": None,
        "end_turn": None,
    }
    fence = chr(96) * 3
    cache.write_snapshot(
        conversation_id,
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": transient_key,
                    "role": "assistant",
                    "content": (f"Visible progress\n\n{fence}tool:tool\nCalled tool\n{fence}"),
                },
            ],
            "source_events": [invocation, result, dom_prose],
        },
    )

    interruption = {
        **dom_prose,
        "id": "a1:dom-prose",
        "parts": ["Connection interrupted. Waiting for the complete answer"],
    }
    cache.write_snapshot(
        conversation_id,
        {
            "title": "Work",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": "a1",
                    "role": "assistant",
                    "content": f"{fence}tool:tool\nCalled tool\n{fence}",
                },
            ],
            "source_events": [interruption],
        },
    )

    durable_parts = cache.connection.execute(
        """
        SELECT kind, content
        FROM message_parts
        WHERE conversation_id = ? AND message_key = ?
        ORDER BY ordinal
        """,
        (conversation_id, "a1"),
    ).fetchall()
    durable_dom_rows = cache.connection.execute(
        """
        SELECT COUNT(*)
        FROM source_events
        WHERE conversation_id = ?
          AND message_key = ?
          AND event_key LIKE '%:dom-prose:%'
        """,
        (conversation_id, "a1"),
    ).fetchone()[0]
    transient_rows = cache.connection.execute(
        """
        SELECT COUNT(*)
        FROM source_events
        WHERE conversation_id = ? AND message_key = ?
        """,
        (conversation_id, transient_key),
    ).fetchone()[0]
    cache.close()

    assert any(
        row["kind"] == "assistant_text" and "Visible progress" in row["content"]
        for row in durable_parts
    )
    assert any(row["kind"] == "tool_call" for row in durable_parts)
    assert durable_dom_rows >= 1
    assert transient_rows == 0


def test_streaming_snapshot_never_reorders_already_visible_blocks(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-stable-stream",
        context_id="context-stable-stream",
        job_name="",
        prompt="Do work",
    )
    first_snapshot = {
        "title": "Work",
        "streaming": True,
        "messages": [
            {"id": "u1", "role": "user", "content": "Do work"},
            {"id": "a1", "role": "assistant", "content": "Visible intro"},
        ],
    }
    cache.write_snapshot("conversation-stable-stream", first_snapshot)

    fence = chr(96) * 3
    tool = f'{fence}tool:Test MCP · inspect\n{{"created_at": 2.0, "status": "completed"}}\n{fence}'
    reordered = "\n\n".join([tool, "Visible intro", "Visible follow-up"])
    cache.write_snapshot(
        "conversation-stable-stream",
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": reordered},
            ],
        },
    )

    content = cache.messages("conversation-stable-stream")[-1]["content"]
    cache.close()

    assert content == "\n\n".join(["Visible intro", tool, "Visible follow-up"])


def test_streaming_snapshot_appends_prose_growth_after_existing_tool(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-append-stream",
        context_id="context-append-stream",
        job_name="",
        prompt="Do work",
    )
    cache.write_snapshot(
        "conversation-append-stream",
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": "Visible intro"},
            ],
        },
    )

    fence = chr(96) * 3
    tool = f'{fence}tool:Test MCP · inspect\n{{"created_at": 2.0, "status": "running"}}\n{fence}'
    cache.write_snapshot(
        "conversation-append-stream",
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": f"{tool}\n\nVisible intro"},
            ],
        },
    )
    cache.write_snapshot(
        "conversation-append-stream",
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": "a1",
                    "role": "assistant",
                    "content": f"{tool}\n\nVisible intro Visible follow-up",
                },
            ],
        },
    )

    content = cache.messages("conversation-append-stream")[-1]["content"]
    cache.close()

    assert content == "\n\n".join(["Visible intro", tool, "Visible follow-up"])


def test_streaming_snapshot_recovers_legacy_tool_first_cache_from_dom_history(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-recover-stream",
        context_id="context-recover-stream",
        job_name="",
        prompt="Do work",
    )
    dom_prose = {
        "id": "a1:dom-prose",
        "role": "assistant",
        "recipient": "all",
        "content_type": "text",
        "parts": ["Visible intro"],
        "text": "",
        "create_time": None,
        "end_turn": None,
    }
    cache.write_snapshot(
        "conversation-recover-stream",
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": "Visible intro"},
            ],
            "source_events": [dom_prose],
        },
    )

    first_observed = float(
        cache.connection.execute(
            """
            SELECT observed_at
            FROM source_events
            WHERE conversation_id = ?
              AND message_key = ?
              AND event_key LIKE '%:dom-prose:%'
            ORDER BY observed_at
            LIMIT 1
            """,
            ("conversation-recover-stream", "a1"),
        ).fetchone()["observed_at"]
    )
    fence = chr(96) * 3
    tool = (
        f"{fence}tool:Test MCP · inspect\n"
        f'{{"created_at": {first_observed + 1.0}, "status": "completed"}}\n'
        f"{fence}"
    )
    legacy_reordered = "\n\n".join(["**Tool activity**", "Thinking", tool, "Visible intro"])
    with cache.connection:
        cache.connection.execute(
            """
            UPDATE messages
            SET content = ?, status = 'streaming'
            WHERE conversation_id = ? AND message_key = ?
            """,
            (legacy_reordered, "conversation-recover-stream", "a1"),
        )

    repaired_cached = cache.messages("conversation-recover-stream")[-1]["content"]
    assert repaired_cached == "\n\n".join(["Visible intro", tool])

    incoming = "\n\n".join([tool, "Visible intro", "Visible follow-up"])
    cache.write_snapshot(
        "conversation-recover-stream",
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": incoming},
            ],
        },
    )

    content = cache.messages("conversation-recover-stream")[-1]["content"]
    cache.close()

    assert content == "\n\n".join(["Visible intro", tool, "Visible follow-up"])


def test_completed_snapshot_moves_fallback_final_text_after_late_tool_blocks(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-final-order",
        context_id="context-final-order",
        job_name="",
        prompt="Do work",
    )
    fence = chr(96) * 3
    first = f"{fence}tool:One\n{{}}\n{fence}"
    second = f"{fence}tool:Two\n{{}}\n{fence}"
    misordered = "\n\n".join([first, "Final answer", second])
    snapshot = {
        "title": "Work",
        "path": "/c/conversation-final-order",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Do work"},
            {"id": "a1", "role": "assistant", "content": misordered},
        ],
    }

    cache.write_snapshot("conversation-final-order", snapshot)
    live_content = cache.messages("conversation-final-order")[-1]["content"]
    cache.write_snapshot("conversation-final-order", snapshot, complete=True)
    completed_content = cache.messages("conversation-final-order")[-1]["content"]
    cache.close()

    assert live_content.index("Final answer") < live_content.index("tool:Two")
    assert completed_content.index("tool:Two") < completed_content.index("Final answer")


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


def test_cache_excludes_stale_active_conversation_from_restart_recovery(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "stale-active-chat",
        context_id="context-stale",
        job_name="",
        prompt="Old work",
    )
    cache.write_snapshot(
        "stale-active-chat",
        {
            "path": "/c/stale-active-chat",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Old work"},
                {"id": "a1", "role": "assistant", "content": "Still the same old response"},
            ],
        },
    )
    stale_at = time.time() - 60 * 60
    fresh_observation_at = time.time()
    with cache.connection:
        cache.connection.execute(
            "UPDATE conversations SET created_at = ?, updated_at = ? WHERE id = ?",
            (stale_at, fresh_observation_at, "stale-active-chat"),
        )
        cache.connection.execute(
            """
            UPDATE messages
            SET created_at = ?,
                updated_at = ?,
                activity_at = ?,
                source_created_at = CASE WHEN role = 'assistant' THEN ? ELSE NULL END
            WHERE conversation_id = ?
            """,
            (
                stale_at,
                fresh_observation_at,
                fresh_observation_at,
                stale_at,
                "stale-active-chat",
            ),
        )

    assert abs(cache.last_message_activity_at("stale-active-chat") - stale_at) < 0.001

    rows = cache.recoverable_conversations(
        interrupted_after=time.time() - 60,
        activity_after=time.time() - 40 * 60,
    )

    assert rows == []
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


def test_final_assistant_preserves_live_dom_prose_when_message_id_changes(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    conversation_id = "conversation-live-prose-handoff"
    transient_key = "__prompta_live_assistant_handoff__"
    cache.start(
        conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Do work",
    )

    cache.write_snapshot(
        conversation_id,
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": transient_key,
                    "role": "assistant",
                    "content": "Starting the work",
                },
            ],
            "source_events": [
                {
                    "id": f"{transient_key}:dom-prose",
                    "role": "assistant",
                    "recipient": "all",
                    "content_type": "text",
                    "parts": ["Starting the work"],
                    "text": "",
                    "create_time": None,
                    "end_turn": None,
                }
            ],
        },
    )
    cache.write_snapshot(
        conversation_id,
        {
            "title": "Work",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": transient_key,
                    "role": "assistant",
                    "content": "Starting the work\n\nChecks now pass",
                },
            ],
            "source_events": [
                {
                    "id": f"{transient_key}:dom-prose",
                    "role": "assistant",
                    "recipient": "all",
                    "content_type": "text",
                    "parts": ["Starting the work", "Checks now pass"],
                    "text": "",
                    "create_time": None,
                    "end_turn": None,
                }
            ],
        },
    )

    fence = chr(96) * 3
    tool = f"{fence}tool:Glass · execute_python\n{{}}\n{fence}"
    cache.write_snapshot(
        conversation_id,
        {
            "title": "Work",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {
                    "id": "final-assistant-id",
                    "role": "assistant",
                    "content": f"{tool}\n\nImplemented",
                },
            ],
            "source_events": [
                {
                    "id": "final-assistant-id:dom-prose",
                    "role": "assistant",
                    "recipient": "all",
                    "content_type": "text",
                    "parts": ["Implemented"],
                    "text": "",
                    "create_time": None,
                    "end_turn": True,
                }
            ],
        },
        complete=True,
    )

    messages = cache.messages(conversation_id)
    cache.close()

    assert [(message["message_key"], message["status"]) for message in messages] == [
        ("u1", "complete"),
        ("final-assistant-id", "complete"),
    ]
    content = messages[-1]["content"]
    assert content.count("Starting the work") == 1
    assert content.count("Checks now pass") == 1
    assert "Glass · execute_python" in content
    assert content.endswith("Implemented")


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


def test_cache_migration_removes_live_assistant_copy_of_following_user(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="Question",
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
                    "__prompta_live_assistant_user_copy__",
                    0,
                    "assistant",
                    "[https://example.test](https://example.test)",
                    "complete",
                    5.0,
                    5.0,
                ),
                (
                    "conversation-1",
                    "u1",
                    1,
                    "user",
                    "https://example.test",
                    "complete",
                    1.0,
                    1.0,
                ),
            ],
        )
    cache.close()

    reopened = ChatCache(path)
    messages = reopened.messages("conversation-1")
    reopened.close()

    keys = [message["message_key"] for message in messages]
    assert "__prompta_live_assistant_user_copy__" not in keys
    assert "u1" in keys


def test_cache_keeps_real_live_assistant_when_later_user_repeats_text(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-1",
        context_id="context-1",
        job_name="",
        prompt="Question",
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
                    "__prompta_live_assistant_real__",
                    0,
                    "assistant",
                    "Same text",
                    "complete",
                    1.0,
                    1.0,
                ),
                (
                    "conversation-1",
                    "u1",
                    1,
                    "user",
                    "Same text",
                    "complete",
                    2.0,
                    2.0,
                ),
            ],
        )
    cache.close()

    reopened = ChatCache(path)
    messages = reopened.messages("conversation-1")
    reopened.close()

    keys = [message["message_key"] for message in messages]
    assert "__prompta_live_assistant_real__" in keys
    assert "u1" in keys


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
