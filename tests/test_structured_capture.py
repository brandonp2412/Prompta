from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from prompta.cache import ChatCache
from prompta.conversation_snapshot import CONVERSATION_SNAPSHOT_SCRIPT
from prompta.structured_capture import (
    message_parts_from_source_events,
    tool_calls_from_source_events,
)
from prompta.structured_store import persist_structured_capture
from prompta.web_store import ReadOnlyChatStore


def _source_events(result_text: str = "RESULT") -> list[dict]:
    return [
        {
            "id": "reason-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Checking the stored conversation state"],
            "text": "",
            "reasoning_title": "Remembering",
            "create_time": 100.0,
            "end_turn": False,
        },
        {
            "id": "call-1",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps(
                {
                    "path": "/Glass Serena/link_123/serena_repl",
                    "args": {"expression": "1 + 1"},
                }
            ),
            "connector_tool_payload": json.dumps({"expression": "1 + 1"}),
            "reasoning_title": "Remembering",
            "create_time": 101.0,
            "end_turn": False,
        },
        {
            "id": "result-1",
            "role": "tool",
            "recipient": "assistant",
            "content_type": "code",
            "text": json.dumps({"text": json.dumps({"stdout": result_text})}),
            "invoked_resource": {
                "app_name": "Glass Serena",
                "resource_uri": "/asdk_app_123/link_123/serena_repl",
            },
            "create_time": 102.0,
            "end_turn": False,
        },
        {
            "id": "final-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Finished"],
            "text": "",
            "reasoning_title": "",
            "create_time": 103.0,
            "end_turn": True,
        },
    ]


def test_browser_source_capture_excludes_unfiltered_react_internals() -> None:
    assert "content:safeJsonValue(content)" not in CONVERSATION_SNAPSHOT_SCRIPT
    assert "metadata:safeJsonValue(metadata)" not in CONVERSATION_SNAPSHOT_SCRIPT
    assert (
        "if(role==='tool'||recipient==='api_tool.call_tool')return true;"
        in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "if(message?.end_turn===true)return true;" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const latestTurnUserIndex=latestTurnReactMessages.findLastIndex" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "latestTurnReactMessages=latestTurnReactMessages.slice(latestTurnUserIndex+1);" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert (
        "if(contentType==='text'||contentType==='multimodal_text')return Boolean(text);"
        in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "return Boolean(text&&visibleAgentText&&visibleAgentText.includes(text));" not in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "const sourceHasAssistantText=sourceEvents.some(event=>(" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "':dom-prose'" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "parts:[visibleProse]" in CONVERSATION_SNAPSHOT_SCRIPT


def test_browser_snapshot_does_not_replace_visible_prose_with_tool_only_react_content() -> None:
    assert "const reactVisible=normalise(reactOrdered);" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const reactKeepsVisibleText=!richPlain.length||richPlain.every(text=>" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "reactVisible.includes(visibleText)" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const needsReactFallback=Boolean(" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const reactHasVisibleText=reactHasVisibleAssistantText(agent,fallbackMessages);" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "reactOrdered&&reactHasVisibleText&&reactKeepsVisibleText" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert (
        "const content=(reactOrdered||fallbackContent).trim();" not in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "const rows=toolRows(agent);" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const prose=proseRows(agent,rows);" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const semantic=[...scope.querySelectorAll(proseBlockSelector)]" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )


def test_browser_snapshot_filters_transient_connection_noise_from_react_history() -> None:
    assert "const networkErrorNoise=/a network error occurred" in CONVERSATION_SNAPSHOT_SCRIPT
    assert (
        "connection interrupted\\.?(?:\\s*waiting for (?:the )?complete answer"
        in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert (
        "a network error occurred\\.?(?:\\s*please check your connection and try again"
        in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert ".replace(networkErrorNoise,'')" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const visibleText=cleanAssistantText(" in CONVERSATION_SNAPSHOT_SCRIPT


def test_browser_snapshot_interleaves_tool_calls_by_invocation_time() -> None:
    assert "prior?.createdAt||Number(message?.create_time)" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const timeline=textEntries.map(entry=>({" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "time:toolBlockTime(block)??" in CONVERSATION_SNAPSHOT_SCRIPT
    assert (
        "timeline.sort((left,right)=>left.time-right.time||left.order-right.order);"
        in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "const parts=[],finalTextParts=[];" not in CONVERSATION_SNAPSHOT_SCRIPT


def test_structured_capture_keeps_reasoning_tool_identity_and_full_result() -> None:
    result_text = "x" * 20_000
    events = _source_events(result_text)

    calls = tool_calls_from_source_events(events)
    parts = message_parts_from_source_events(events)

    assert len(calls) == 1
    assert calls[0]["connector"] == "Glass Serena"
    assert calls[0]["action"] == "serena_repl"
    assert calls[0]["summary"] == "Remembering"
    assert calls[0]["arguments"] == {"expression": "1 + 1"}
    assert calls[0]["result"]["stdout"] == result_text

    assert [part["kind"] for part in parts] == [
        "reasoning",
        "tool_call",
        "final_text",
    ]
    assert parts[0]["title"] == "Remembering"
    assert "Glass Serena · serena_repl" in parts[1]["content"]
    assert parts[-1]["content"] == "Finished"


def test_completed_tool_wrappers_keep_invocation_order_with_interleaved_text() -> None:
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
            "text": json.dumps({"path": "/Test MCP/link_123/first", "args": {"step": 1}}),
            "create_time": 2.0,
        },
        {
            "id": "text-2",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Between tools"],
            "create_time": 3.0,
            "end_turn": True,
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
            "create_time": 7.0,
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
            "create_time": 8.0,
        },
        {
            "id": "final-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Done"],
            "create_time": 9.0,
            "end_turn": True,
        },
    ]

    calls = tool_calls_from_source_events(events)
    parts = message_parts_from_source_events(events)
    content = "\n\n".join(part["content"] for part in parts)

    assert [call["created_at"] for call in calls] == [2.0, 4.0]
    assert [call["source_event_key"] for call in calls] == ["call-1", "call-2"]
    assert [call["result_event_key"] for call in calls] == ["result-1", "result-2"]
    assert [part["kind"] for part in parts] == [
        "assistant_text",
        "tool_call",
        "assistant_text",
        "tool_call",
        "final_text",
    ]
    assert content.index("First text") < content.index("Test MCP · first")
    assert content.index("Test MCP · first") < content.index("Between tools")
    assert content.index("Between tools") < content.index("Test MCP · second")
    assert content.index("Test MCP · second") < content.index("Done")


def test_snapshot_digest_includes_structured_source_events() -> None:
    base = {
        "title": "Structured",
        "path": "/c/chat",
        "streaming": False,
        "messages": [{"id": "a1", "role": "assistant", "content": "Same answer"}],
        "source_events": [
            {
                "id": "call-1",
                "role": "assistant",
                "recipient": "api_tool.call_tool",
                "reasoning_title": "Remembering",
                "connector_name": "",
            }
        ],
    }
    corrected = {
        **base,
        "source_events": [
            {
                **base["source_events"][0],
                "connector_name": "Glass Serena",
            }
        ],
    }

    assert ChatCache.digest(base) != ChatCache.digest(corrected)


def test_activity_history_is_persisted_without_changing_message_digest(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-state",
        context_id="context-state",
        job_name="",
        prompt="Track state",
    )
    snapshot = {
        "title": "State",
        "path": "/c/conversation-state",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Track state"},
            {"id": "a1", "role": "assistant", "content": "Working"},
        ],
    }
    digest = ChatCache.digest(snapshot)

    cache.record_state(
        "conversation-state",
        {
            "streaming": True,
            "complete": False,
            "transient": False,
            "failed": False,
            "turn_ended": False,
        },
    )
    cache.record_state(
        "conversation-state",
        {
            "streaming": False,
            "complete": True,
            "transient": False,
            "failed": False,
            "turn_ended": True,
        },
    )

    assert ChatCache.digest(snapshot) == digest
    rows = cache.connection.execute(
        """
        SELECT status, streaming, complete, turn_ended
        FROM conversation_state_events
        WHERE conversation_id = ?
        ORDER BY observed_at, id
        """,
        ("conversation-state",),
    ).fetchall()
    cache.close()

    assert [
        (row["status"], row["streaming"], row["complete"], row["turn_ended"]) for row in rows
    ] == [
        ("active", 0, 0, None),
        ("active", 1, 0, 0),
        ("active", 0, 1, 1),
    ]


def test_read_only_store_trusts_completed_structured_final_over_corrupt_cached_content(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    conversation_id = "conversation-corrupt-cached-content"
    cache.start(
        conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Inspect this",
    )
    snapshot = {
        "title": "Structured",
        "path": f"/c/{conversation_id}",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Inspect this"},
            {
                "id": "a1",
                "role": "assistant",
                "content": "Checking the stored conversation state\n\nFinished",
            },
        ],
        "source_events": [
            *_source_events(),
            {
                "id": "a1:dom-prose",
                "role": "assistant",
                "recipient": "all",
                "content_type": "text",
                "parts": ["Checking the stored conversation state"],
                "text": "",
                "create_time": None,
                "end_turn": None,
            },
        ],
    }
    cache.write_snapshot(conversation_id, snapshot, complete=True)
    cache.connection.execute(
        """
        UPDATE messages
        SET content = ?
        WHERE conversation_id = ? AND message_key = ?
        """,
        (
            "Checking the stored conversation state\n\n"
            "FinishedFinished timestamp derivation commitDOM refresh fix",
            conversation_id,
            "a1",
        ),
    )
    cache.connection.commit()
    cache.close()

    chat = ReadOnlyChatStore(path).conversation(conversation_id)

    assert chat is not None
    assistant = chat["messages"][-1]
    assert assistant["content"].endswith("Finished")
    assert assistant["parts_renderable"] is True
    assert "FinishedFinished" not in assistant["content"]
    assert "Glass Serena" in assistant["content"]

    sidebar = ReadOnlyChatStore(path).conversations()
    summary = next(item for item in sidebar if item["id"] == conversation_id)
    assert summary["preview"] == "Finished"


def test_read_only_store_does_not_drop_canonical_final_text_when_parts_are_stale(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    conversation_id = "conversation-stale-parts"
    cache.start(
        conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Inspect this",
    )
    fence = chr(96) * 3
    tool_block = (
        fence
        + "tool:Glass Serena · serena_repl\n"
        + json.dumps({"status": "completed"})
        + "\n"
        + fence
    )
    final_text = "Fixed and deployed to Nox."
    snapshot = {
        "title": "Structured",
        "path": f"/c/{conversation_id}",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Inspect this"},
            {
                "id": "a1",
                "role": "assistant",
                "content": tool_block + "\n\n" + final_text,
            },
        ],
        "source_events": _source_events(),
    }
    cache.write_snapshot(conversation_id, snapshot, complete=True)
    cache.connection.execute(
        """
        DELETE FROM message_parts
        WHERE conversation_id = ? AND message_key = ? AND kind = 'final_text'
        """,
        (conversation_id, "a1"),
    )
    cache.connection.commit()
    cache.close()

    chat = ReadOnlyChatStore(path).conversation(conversation_id)

    assert chat is not None
    assistant = chat["messages"][-1]
    assert final_text in assistant["content"]
    assert assistant["parts_renderable"] is False
    assert "Glass Serena · serena_repl" in assistant["content"]


def test_read_only_store_recovers_completed_turn_order_from_dom_observations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-observed-order",
        context_id="context-observed-order",
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
    grouped = "\n\n".join(
        ["Intro text", "Between tools", "Legacy uncaptured text", first_tool, second_tool]
    )
    cache.write_snapshot(
        "conversation-observed-order",
        {
            "title": "Work",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": grouped},
            ],
        },
    )
    with cache.connection:
        cache.connection.executemany(
            "INSERT INTO message_parts (conversation_id, message_key, part_key, ordinal, kind, content, source_created_at, source_event_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "conversation-observed-order",
                    "a1",
                    "intro-part",
                    0,
                    "assistant_text",
                    "Intro text",
                    10.0,
                    "intro-source",
                ),
                (
                    "conversation-observed-order",
                    "a1",
                    "between-part",
                    1,
                    "assistant_text",
                    "Between tools",
                    30.0,
                    "between-source",
                ),
            ],
        )
    for index, (observed_at, parts) in enumerate(
        [
            (30.0, ["Intro text"]),
            (50.0, ["Intro text", "Between tools", "Legacy uncaptured text"]),
        ],
        start=1,
    ):
        event = {
            "id": f"observation-{index}:dom-prose",
            "parts": parts,
        }
        with cache.connection:
            cache.connection.execute(
                "INSERT INTO source_events (conversation_id, message_key, event_key, ordinal, raw_json, observed_at, source_created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "conversation-observed-order",
                    "__prompta_live_assistant_legacy__",
                    f"observation-{index}:dom-prose:source",
                    index,
                    json.dumps(event),
                    observed_at,
                    observed_at,
                ),
            )
    with cache.connection:
        for index, source_created_at in enumerate((10.0, 40.0), start=1):
            cache.connection.execute(
                "INSERT INTO source_events (conversation_id, message_key, event_key, ordinal, raw_json, observed_at, source_created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "conversation-observed-order",
                    "a1",
                    f"canonical-marker-{index}",
                    100 + index,
                    json.dumps({"id": f"canonical-marker-{index}"}),
                    50.0 + index,
                    source_created_at,
                ),
            )
    cache.close()

    chat = ReadOnlyChatStore(path).conversation("conversation-observed-order")
    assert chat is not None
    assistant = chat["messages"][-1]
    assert assistant["status"] == "complete"
    content = assistant["content"]
    assert content.index("Intro text") < content.index("Test MCP · first")
    assert content.index("Test MCP · first") < content.index("Between tools")
    assert content.index("Between tools") < content.index("Test MCP · second")
    assert content.index("Test MCP · second") < content.index("Legacy uncaptured text")


def test_persist_structured_capture_collapses_repeated_logical_event_observations(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    conversation_id = "conversation-repeated-observations"
    message_key = "a1"
    cache.start(
        conversation_id,
        context_id="context-repeated-observations",
        job_name="",
        prompt="Inspect this",
    )
    cache.write_snapshot(
        conversation_id,
        {
            "title": "Repeated observations",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Inspect this"},
                {"id": message_key, "role": "assistant", "content": "Working"},
            ],
        },
    )
    wrapper = {
        "id": "tool-wrapper-1",
        "role": "tool",
        "recipient": "all",
        "content_type": "code",
        "text": json.dumps(
            {
                "type": "mcpToolCall",
                "appContext": {
                    "appName": "Glass Serena",
                    "actionName": "serena_repl",
                },
                "arguments": {"expression": "1 + 1"},
                "status": "completed",
                "result": {"value": 2},
            }
        ),
    }
    events = [
        {
            "id": f"{message_key}:dom-prose",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["First visible version"],
            "text": "",
        },
        wrapper,
        {
            "id": f"{message_key}:dom-prose",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Second visible version"],
            "text": "",
        },
        {
            **wrapper,
            "text": wrapper["text"].replace('"status": "completed"', '"status": "running"'),
        },
        {
            "id": f"{message_key}:dom-prose",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["#### ChatGPT said:"],
            "text": "",
        },
    ]

    with cache.connection:
        persist_structured_capture(
            cache.connection,
            conversation_id=conversation_id,
            message_key=message_key,
            source_events=events,
            observed_at=100.0,
        )

    parts = cache.connection.execute(
        """
        SELECT kind, content
        FROM message_parts
        WHERE conversation_id = ? AND message_key = ?
        ORDER BY ordinal
        """,
        (conversation_id, message_key),
    ).fetchall()
    tools = cache.connection.execute(
        """
        SELECT status
        FROM tool_calls
        WHERE conversation_id = ? AND message_key = ?
        """,
        (conversation_id, message_key),
    ).fetchall()
    cache.close()

    assert len(parts) == 2
    assert sum(str(row["kind"]) == "assistant_text" for row in parts) == 1
    assistant_part = next(row for row in parts if str(row["kind"]) == "assistant_text")
    assert assistant_part["content"] == "Second visible version"
    assert "ChatGPT said" not in str(assistant_part["content"])
    assert len(tools) == 1
    assert tools[0]["status"] == "running"


def test_read_only_store_recovers_transient_dom_prose_when_parts_are_tool_only(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    conversation_id = "conversation-tool-only-parts"
    durable_key = "a1"
    transient_key = "__prompta_live_assistant_recovery__"
    cache.start(
        conversation_id,
        context_id="context-tool-only-parts",
        job_name="",
        prompt="Inspect this",
    )
    invocation, result = _source_events()[1:3]
    fence = chr(96) * 3
    cache.write_snapshot(
        conversation_id,
        {
            "title": "Structured",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Inspect this"},
                {
                    "id": durable_key,
                    "role": "assistant",
                    "content": f"{fence}tool:tool\nCalled tool\n{fence}",
                },
            ],
            "source_events": [invocation, result],
        },
    )

    observations = [
        (99.0, ["Visible intro"]),
        (102.0, ["Visible intro", "Visible follow-up"]),
        (103.0, ["Connection interrupted. Waiting for the complete answer"]),
    ]
    with cache.connection:
        for index, (observed_at, parts) in enumerate(observations, start=1):
            event = {
                "id": f"{transient_key}:dom-prose",
                "parts": parts,
            }
            cache.connection.execute(
                """
                INSERT INTO source_events (
                    conversation_id, message_key, event_key, ordinal,
                    raw_json, observed_at, source_created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    transient_key,
                    f"{transient_key}:dom-prose:{index}",
                    index,
                    json.dumps(event),
                    observed_at,
                    observed_at,
                ),
            )
    kinds = [
        str(row["kind"])
        for row in cache.connection.execute(
            """
            SELECT kind
            FROM message_parts
            WHERE conversation_id = ? AND message_key = ?
            ORDER BY ordinal
            """,
            (conversation_id, durable_key),
        ).fetchall()
    ]
    cache.close()

    chat = ReadOnlyChatStore(path).conversation(conversation_id)

    assert kinds == ["tool_call"]
    assert chat is not None
    assistant = chat["messages"][-1]
    content = assistant["content"]
    assert assistant["parts_renderable"] is True
    assert [part["kind"] for part in assistant["parts"]] == [
        "assistant_text",
        "tool_call",
        "assistant_text",
    ]
    assert "Connection interrupted" not in content
    assert content.index("Visible intro") < content.index("Glass Serena · serena_repl")
    assert content.index("Glass Serena · serena_repl") < content.index("Visible follow-up")


def test_read_only_store_recovers_dom_prose_when_only_final_text_survived(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    conversation_id = "conversation-final-text-only-prose"
    durable_key = "a1"
    cache.start(
        conversation_id,
        context_id="context-final-text-only-prose",
        job_name="",
        prompt="Inspect this",
    )
    invocation, result, final = _source_events()[1:4]
    fence = chr(96) * 3
    cache.write_snapshot(
        conversation_id,
        {
            "title": "Structured",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Inspect this"},
                {
                    "id": durable_key,
                    "role": "assistant",
                    "content": f"{fence}tool:tool\nCalled tool\n{fence}\n\nFinished",
                },
            ],
            "source_events": [invocation, result, final],
        },
    )

    observations = [
        (99.0, ["Visible intro"]),
        (102.0, ["Visible follow-up"]),
        (104.0, ["Finished"]),
    ]
    with cache.connection:
        for index, (observed_at, parts) in enumerate(observations, start=1):
            event = {
                "id": f"{durable_key}:dom-prose",
                "parts": parts,
            }
            cache.connection.execute(
                """
                INSERT INTO source_events (
                    conversation_id, message_key, event_key, ordinal,
                    raw_json, observed_at, source_created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    durable_key,
                    f"{durable_key}:dom-prose:{index}",
                    10 + index,
                    json.dumps(event),
                    observed_at,
                    None,
                ),
            )
    cache.close()

    chat = ReadOnlyChatStore(path).conversation(conversation_id)

    assert chat is not None
    assistant = chat["messages"][-1]
    content = assistant["content"]
    assert assistant["parts_renderable"] is True
    assert [part["kind"] for part in assistant["parts"]] == [
        "assistant_text",
        "tool_call",
        "assistant_text",
        "final_text",
    ]
    assert content.count("Finished") == 1
    assert content.index("Visible intro") < content.index("Glass Serena · serena_repl")
    assert content.index("Glass Serena · serena_repl") < content.index("Visible follow-up")
    assert content.index("Visible follow-up") < content.index("Finished")


def test_read_only_store_keeps_late_recovered_prose_before_final_text(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    conversation_id = "conversation-late-dom-prose"
    durable_key = "a1"
    cache.start(
        conversation_id,
        context_id="context-late-dom-prose",
        job_name="",
        prompt="Inspect this",
    )
    invocation, result, final = _source_events()[1:4]
    final = {
        **final,
        "parts": ["Finished with urlcommit 5973e26https://example.test/commit/5973e26."],
    }
    fence = chr(96) * 3
    cache.write_snapshot(
        conversation_id,
        {
            "title": "Structured",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Inspect this"},
                {
                    "id": durable_key,
                    "role": "assistant",
                    "content": (f"{fence}tool:tool" + chr(10) + "Called tool" + chr(10) + fence),
                },
            ],
            "source_events": [invocation, result, final],
        },
    )

    late_observation = {
        "id": f"{durable_key}:dom-prose",
        "parts": [
            "Finished with commit 5973e26.",
            "I’ll inspect the affected conversation ordering.",
            "The UI restart completed and validation passed.",
        ],
    }
    with cache.connection:
        cache.connection.execute(
            """
            INSERT INTO source_events (
                conversation_id, message_key, event_key, ordinal,
                raw_json, observed_at, source_created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                durable_key,
                f"{durable_key}:dom-prose:late",
                20,
                json.dumps(late_observation),
                110.0,
                None,
            ),
        )
    cache.close()

    chat = ReadOnlyChatStore(path).conversation(conversation_id)

    assert chat is not None
    assistant = chat["messages"][-1]
    parts = assistant["parts"]
    content = assistant["content"]
    assert assistant["parts_renderable"] is True
    assert [part["kind"] for part in parts] == [
        "tool_call",
        "assistant_text",
        "assistant_text",
        "final_text",
    ]
    assert content.count("commit 5973e26") == 1
    assert content.index("I’ll inspect the affected conversation ordering.") < content.index(
        "The UI restart completed and validation passed."
    )
    assert content.index("The UI restart completed and validation passed.") < content.index(
        "Finished with"
    )


def test_read_only_store_prefers_rich_tools_over_transient_thinking_placeholder(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    conversation_id = "conversation-rich-tools-over-thinking"
    fence = chr(96) * 3
    invocation, result = _source_events()[1:3]
    cache.start(
        conversation_id,
        context_id="context-rich-tools-over-thinking",
        job_name="",
        prompt="Inspect this",
    )
    cache.write_snapshot(
        conversation_id,
        {
            "title": "Structured",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Inspect this"},
                {
                    "id": "a1",
                    "role": "assistant",
                    "content": f"Thinking\n\n{fence}tool:tool\nCalled tool\n{fence}",
                },
            ],
            "source_events": [invocation, result],
        },
        complete=True,
    )
    cache.close()

    chat = ReadOnlyChatStore(path).conversation(conversation_id)

    assert chat is not None
    assistant = chat["messages"][-1]
    assert assistant["parts_renderable"] is True
    assert [part["kind"] for part in assistant["parts"]] == ["tool_call"]
    assert "Glass Serena · serena_repl" in assistant["content"]
    assert "Called tool" not in assistant["content"]
    assert "Thinking" not in assistant["content"]


def test_active_conversation_uses_structured_order_for_completed_assistant_turn(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-active-completed-turn",
        context_id="context-active-completed-turn",
        job_name="",
        prompt="Inspect this",
    )
    cache.write_snapshot(
        "conversation-active-completed-turn",
        {
            "title": "Structured",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Inspect this"},
                {
                    "id": "a1",
                    "role": "assistant",
                    "content": "Checking the stored conversation state\n\nFinished",
                },
            ],
            "source_events": _source_events(),
        },
    )
    correct = cache.messages("conversation-active-completed-turn")[-1]["content"]
    fence = chr(96) * 3
    tool_start = correct.index(f"{fence}tool:")
    final_start = correct.rindex("\n\nFinished")
    tool_block = correct[tool_start:final_start]
    grouped = "\n\n".join(["Checking the stored conversation state", "Finished", tool_block])
    with cache.connection:
        cache.connection.execute(
            "UPDATE messages SET content = ? WHERE conversation_id = ? AND message_key = ?",
            (grouped, "conversation-active-completed-turn", "a1"),
        )
    cache.close()

    chat = ReadOnlyChatStore(path).conversation("conversation-active-completed-turn")
    assert chat is not None
    assert chat["status"] == "active"
    assistant = chat["messages"][-1]
    assert assistant["status"] == "complete"
    content = assistant["content"]
    assert content.index("Checking the stored conversation state") < content.index(
        "Glass Serena · serena_repl"
    )
    assert content.index("Glass Serena · serena_repl") < content.index("Finished")


def test_structured_parts_follow_parent_chain_when_text_times_are_turn_level() -> None:
    events = [
        {
            "id": "reason-1",
            "parent_id": "user-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["First update"],
            "reasoning_title": "Starting",
            "create_time": 100.0,
            "end_turn": False,
        },
        {
            "id": "call-1",
            "parent_id": "reason-1",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps(
                {
                    "type": "mcpToolCall",
                    "appContext": {"appName": "Glass", "actionName": "execute_python"},
                    "arguments": {"code": "print(1)"},
                    "status": "completed",
                }
            ),
            "create_time": 101.0,
            "end_turn": False,
        },
        {
            "id": "update-2",
            "parent_id": "call-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Second update"],
            "reasoning_title": "Continuing",
            "create_time": 100.0,
            "end_turn": False,
        },
        {
            "id": "call-2",
            "parent_id": "update-2",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps(
                {
                    "type": "mcpToolCall",
                    "appContext": {"appName": "Glass", "actionName": "execute_python"},
                    "arguments": {"code": "print(2)"},
                    "status": "completed",
                }
            ),
            "create_time": 102.0,
            "end_turn": False,
        },
        {
            "id": "final-1",
            "parent_id": "call-2",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Finished"],
            "create_time": 100.0,
            "end_turn": True,
        },
    ]

    parts = message_parts_from_source_events(events)

    assert [part["kind"] for part in parts] == [
        "reasoning",
        "tool_call",
        "reasoning",
        "tool_call",
        "final_text",
    ]
    assert [part["content"] for part in parts if part["kind"] != "tool_call"] == [
        "First update",
        "Second update",
        "Finished",
    ]


def test_structured_parts_ignore_dom_prose_when_timestamped_text_exists() -> None:
    events = _source_events()
    events.append(
        {
            "id": "a1:dom-prose",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Checking the stored conversation state", "Finished"],
            "text": "",
            "create_time": None,
            "end_turn": None,
        }
    )

    parts = message_parts_from_source_events(events)

    assert [part["kind"] for part in parts] == [
        "reasoning",
        "tool_call",
        "final_text",
    ]
    combined = "\n".join(str(part["content"]) for part in parts)
    assert combined.count("Checking the stored conversation state") == 1
    assert combined.count("Finished") == 1


def test_cache_persists_structured_events_parts_tools_and_message_versions(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-structured",
        context_id="context-1",
        job_name="",
        prompt="Inspect this",
    )
    events = _source_events()
    snapshot = {
        "title": "Structured",
        "path": "/c/conversation-structured",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Inspect this"},
            {
                "id": "a1",
                "role": "assistant",
                "content": "Checking the stored conversation state\n\nFinished",
            },
        ],
        "source_events": events,
    }
    cache.write_snapshot("conversation-structured", snapshot, complete=True)

    source_count = cache.connection.execute(
        "SELECT COUNT(*) FROM source_events WHERE conversation_id = ?",
        ("conversation-structured",),
    ).fetchone()[0]
    parts = cache.connection.execute(
        """
        SELECT kind, title, content
        FROM message_parts
        WHERE conversation_id = ? AND message_key = ?
        ORDER BY ordinal
        """,
        ("conversation-structured", "a1"),
    ).fetchall()
    tool = cache.connection.execute(
        """
        SELECT connector, action, summary, arguments_json, result_json
        FROM tool_calls
        WHERE conversation_id = ? AND message_key = ?
        """,
        ("conversation-structured", "a1"),
    ).fetchone()
    message = cache.connection.execute(
        """
        SELECT source_created_at
        FROM messages
        WHERE conversation_id = ? AND message_key = ?
        """,
        ("conversation-structured", "a1"),
    ).fetchone()
    version_count = cache.connection.execute(
        """
        SELECT COUNT(*)
        FROM message_versions
        WHERE conversation_id = ? AND message_key = ?
        """,
        ("conversation-structured", "a1"),
    ).fetchone()[0]

    assert source_count == 4
    assert [(row["kind"], row["title"]) for row in parts] == [
        ("reasoning", "Remembering"),
        ("tool_call", "Remembering"),
        ("final_text", ""),
    ]
    assert tool is not None
    assert tool["connector"] == "Glass Serena"
    assert tool["action"] == "serena_repl"
    assert tool["summary"] == "Remembering"
    assert json.loads(tool["arguments_json"]) == {"expression": "1 + 1"}
    assert json.loads(tool["result_json"]) == {"stdout": "RESULT"}
    assert message["source_created_at"] == 100.0
    assert version_count == 1

    chat = ReadOnlyChatStore(path).conversation("conversation-structured")
    assert chat is not None
    assistant = chat["messages"][-1]
    assert assistant["created_at"] == 100.0
    assert assistant["display_at"] == 103.0
    assert assistant["source_event_count"] == 4
    assert assistant["version_count"] == 1
    assert assistant["tool_calls"][0]["connector"] == "Glass Serena"
    assert "Glass Serena · serena_repl" in assistant["content"]
    assert assistant["content"].endswith("Finished")
    assert [event["status"] for event in chat["state_events"]] == ["active", "complete"]
    assert chat["state_events"][-1]["complete"] is True

    revised_events = _source_events()
    revised_events[-1] = {
        **revised_events[-1],
        "parts": ["Finished, revised"],
    }
    snapshot["messages"][1]["content"] = (
        "Checking the stored conversation state\n\nFinished, revised"
    )
    snapshot["source_events"] = revised_events
    cache.write_snapshot("conversation-structured", snapshot, complete=True)

    revised_source_count = cache.connection.execute(
        "SELECT COUNT(*) FROM source_events WHERE conversation_id = ?",
        ("conversation-structured",),
    ).fetchone()[0]
    revised_version_count = cache.connection.execute(
        """
        SELECT COUNT(*)
        FROM message_versions
        WHERE conversation_id = ? AND message_key = ?
        """,
        ("conversation-structured", "a1"),
    ).fetchone()[0]
    raw_final_events = cache.connection.execute(
        """
        SELECT raw_json
        FROM source_events
        WHERE conversation_id = ? AND message_key = ? AND raw_json LIKE '%final-1%'
        ORDER BY observed_at
        """,
        ("conversation-structured", "a1"),
    ).fetchall()
    cache.close()

    assert revised_source_count == 5
    assert revised_version_count == 2
    assert len(raw_final_events) == 2
    assert any("Finished" in row["raw_json"] for row in raw_final_events)
    assert any("Finished, revised" in row["raw_json"] for row in raw_final_events)


def test_tool_call_diff_persists_across_snapshot_refresh_and_is_read_with_tool_call(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    conversation_id = "conversation-diff"
    cache.start(
        conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Change the code",
    )
    snapshot = {
        "title": "Diff",
        "path": f"/c/{conversation_id}",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Change the code"},
            {"id": "a1", "role": "assistant", "content": "Finished"},
        ],
        "source_events": _source_events(),
    }
    cache.write_snapshot(conversation_id, snapshot, complete=True)
    tool = cache.connection.execute(
        """
        SELECT call_key
        FROM tool_calls
        WHERE conversation_id = ? AND message_key = ?
        """,
        (conversation_id, "a1"),
    ).fetchone()
    assert tool is not None
    call_key = str(tool["call_key"])

    cache.record_tool_call_diff(
        conversation_id,
        "a1",
        call_key,
        before_tree_id="a" * 40,
        after_tree_id="b" * 40,
        patch_text="diff --git a/app.py b/app.py\n+print('changed')\n",
        changed_file_count=1,
        additions=1,
        deletions=0,
        truncated=False,
        repository_root="/home/brandon/prompta",
        worktree_path="/home/brandon/worktrees/prompta-diff-previews",
        observed_at=200.0,
    )

    cache.write_snapshot(conversation_id, snapshot, complete=True)
    persisted = cache.connection.execute(
        """
        SELECT before_tree_id, after_tree_id, patch_text, changed_file_count,
               additions, deletions, truncated, repository_root, worktree_path,
               created_at, updated_at
        FROM tool_call_diffs
        WHERE conversation_id = ? AND message_key = ? AND call_key = ?
        """,
        (conversation_id, "a1", call_key),
    ).fetchone()
    assert persisted is not None
    assert persisted["before_tree_id"] == "a" * 40
    assert persisted["after_tree_id"] == "b" * 40
    assert persisted["changed_file_count"] == 1
    assert persisted["additions"] == 1
    assert persisted["deletions"] == 0
    assert persisted["truncated"] == 0
    assert persisted["created_at"] == 200.0
    assert persisted["updated_at"] == 200.0

    chat = ReadOnlyChatStore(path).conversation(conversation_id)
    assert chat is not None
    code_diff = chat["messages"][-1]["tool_calls"][0]["code_diff"]
    assert code_diff["before_tree_id"] == "a" * 40
    assert code_diff["after_tree_id"] == "b" * 40
    assert code_diff["patch_text"].endswith("+print('changed')\n")
    assert code_diff["changed_file_count"] == 1
    assert code_diff["additions"] == 1
    assert code_diff["deletions"] == 0
    assert code_diff["truncated"] is False
    assert code_diff["repository_root"] == "/home/brandon/prompta"
    assert code_diff["worktree_path"] == "/home/brandon/worktrees/prompta-diff-previews"

    cache.record_tool_call_diff(
        conversation_id,
        "a1",
        call_key,
        before_tree_id="a" * 40,
        after_tree_id="c" * 40,
        patch_text="truncated patch",
        changed_file_count=2,
        additions=3,
        deletions=1,
        truncated=True,
        repository_root="/home/brandon/prompta",
        worktree_path="/home/brandon/worktrees/prompta-diff-previews",
        observed_at=201.0,
    )
    updated = cache.connection.execute(
        """
        SELECT after_tree_id, changed_file_count, additions, deletions, truncated,
               created_at, updated_at
        FROM tool_call_diffs
        WHERE conversation_id = ? AND message_key = ? AND call_key = ?
        """,
        (conversation_id, "a1", call_key),
    ).fetchone()
    cache.close()

    assert updated is not None
    assert updated["after_tree_id"] == "c" * 40
    assert updated["changed_file_count"] == 2
    assert updated["additions"] == 3
    assert updated["deletions"] == 1
    assert updated["truncated"] == 1
    assert updated["created_at"] == 200.0
    assert updated["updated_at"] == 201.0


def test_tool_call_diff_schema_migrates_existing_cache(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-existing",
        context_id="context-1",
        job_name="",
        prompt="Existing data",
    )
    cache.connection.execute("DROP TABLE tool_call_diffs")
    cache.connection.commit()
    cache.close()

    migrated = ChatCache(path)
    tables = {
        str(row["name"])
        for row in migrated.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    conversation = migrated.connection.execute(
        "SELECT prompt FROM conversations WHERE id = ?",
        ("conversation-existing",),
    ).fetchone()
    migrated.close()

    assert "tool_call_diffs" in tables
    assert conversation is not None
    assert conversation["prompt"] == "Existing data"


def test_partial_structured_capture_preserves_known_assistant_text_parts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    conversation_id = "conversation-partial-structured"
    cache.start(
        conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Inspect this",
    )
    events = _source_events()
    snapshot = {
        "title": "Structured",
        "path": f"/c/{conversation_id}",
        "streaming": True,
        "messages": [
            {"id": "u1", "role": "user", "content": "Inspect this"},
            {
                "id": "a1",
                "role": "assistant",
                "content": "Checking the stored conversation state\n\nFinished",
            },
        ],
        "source_events": events,
    }
    cache.write_snapshot(conversation_id, snapshot)

    snapshot["streaming"] = False
    snapshot["source_events"] = [events[1], events[2]]
    cache.write_snapshot(conversation_id, snapshot, complete=True)

    parts = cache.connection.execute(
        """
        SELECT kind, content
        FROM message_parts
        WHERE conversation_id = ? AND message_key = ?
        ORDER BY ordinal
        """,
        (conversation_id, "a1"),
    ).fetchall()
    source_count = cache.connection.execute(
        "SELECT COUNT(*) FROM source_events WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()[0]
    cache.close()

    assert [row["kind"] for row in parts] == ["reasoning", "tool_call", "final_text"]
    assert parts[0]["content"] == "Checking the stored conversation state"
    assert parts[-1]["content"] == "Finished"
    assert source_count == 4

    chat = ReadOnlyChatStore(path).conversation(conversation_id)
    assert chat is not None
    assistant = chat["messages"][-1]
    assert "Checking the stored conversation state" in assistant["content"]
    assert "Glass Serena · serena_repl" in assistant["content"]
    assert assistant["content"].endswith("Finished")


def test_cache_skips_structured_capture_when_transient_target_is_deleted(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    conversation_id = "conversation-transient-structured"
    cache.start(
        conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Inspect this",
    )
    stable_snapshot = {
        "title": "Structured",
        "path": f"/c/{conversation_id}",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Inspect this"},
            {"id": "a1", "role": "assistant", "content": "Canonical response"},
        ],
    }
    cache.write_snapshot(conversation_id, stable_snapshot)

    transient_snapshot = {
        "title": "Structured",
        "path": f"/c/{conversation_id}",
        "streaming": True,
        "messages": [
            {"id": "u1", "role": "user", "content": "Inspect this"},
            {
                "id": "__prompta_live_assistant_transient",
                "role": "assistant",
                "content": "Different streaming draft",
            },
        ],
        "source_events": _source_events(),
    }
    cache.write_snapshot(conversation_id, transient_snapshot)

    transient = cache.connection.execute(
        """
        SELECT 1
        FROM messages
        WHERE conversation_id = ? AND message_key = ?
        """,
        (conversation_id, "__prompta_live_assistant_transient"),
    ).fetchone()
    transient_parts = cache.connection.execute(
        """
        SELECT COUNT(*)
        FROM message_parts
        WHERE conversation_id = ? AND message_key = ?
        """,
        (conversation_id, "__prompta_live_assistant_transient"),
    ).fetchone()[0]

    stable_snapshot["source_events"] = _source_events()
    cache.write_snapshot(conversation_id, stable_snapshot, complete=True)
    stable_parts = cache.connection.execute(
        """
        SELECT COUNT(*)
        FROM message_parts
        WHERE conversation_id = ? AND message_key = ?
        """,
        (conversation_id, "a1"),
    ).fetchone()[0]
    cache.close()

    assert transient is None
    assert transient_parts == 0
    assert stable_parts > 0


def test_structured_capture_ignores_network_error_banner_between_tool_activity() -> None:
    events = _source_events()
    events.insert(
        2,
        {
            "id": "network-error",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": [
                "A network error occurred. Please check your connection and try again. If this issue persists please contact us through our help center at help.openai.com."
            ],
            "text": "",
            "reasoning_title": "",
            "create_time": 101.5,
            "end_turn": False,
        },
    )

    parts = message_parts_from_source_events(events)
    combined = "\n".join(str(part.get("content") or "") for part in parts)

    assert "A network error occurred" not in combined
    assert "Checking the stored conversation state" in combined
    assert "Finished" in combined


def test_persist_structured_capture_coalesces_duplicate_part_keys(tmp_path: Path) -> None:
    path = tmp_path / "chats.sqlite3"
    ChatCache(path)
    events = [
        {
            "id": "same-event",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["earlier"],
            "text": "earlier",
            "create_time": 1.0,
            "end_turn": False,
        },
        {
            "id": "same-event",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["latest"],
            "text": "latest",
            "create_time": 2.0,
            "end_turn": True,
        },
    ]

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        persist_structured_capture(
            connection,
            conversation_id="conversation-duplicate-parts",
            message_key="assistant-1",
            source_events=events,
            observed_at=3.0,
        )
        rows = connection.execute(
            "SELECT part_key, content, end_turn FROM message_parts "
            "WHERE conversation_id = ? AND message_key = ?",
            ("conversation-duplicate-parts", "assistant-1"),
        ).fetchall()

    assert [tuple(row) for row in rows] == [("same-event", "latest", 1)]
