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
    cache.close()

    assert conversations[0]["status"] == "complete"
    assert conversations[0]["job_name"] == "flux"
    assert messages[-1]["content"] == "Finished"
    assert messages[-1]["status"] == "complete"
    assert path.stat().st_mode & 0o777 == 0o600


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
