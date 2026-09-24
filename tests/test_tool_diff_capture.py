from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from prompta.cache import ChatCache
from prompta.git_diff import GitDiffService, GitSnapshot
from prompta.tool_diff_capture import ToolDiffCapture
from prompta.web_store import ReadOnlyChatStore


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def init_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "prompta-tests@example.invalid")
    git(repo, "config", "user.name", "Prompta Tests")
    (repo / "changed.txt").write_text("before\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    return repo


def tool_events(
    connector: str,
    action: str,
    arguments: dict[str, Any],
    *,
    call_id: str,
    completed: bool,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {
            "id": call_id,
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps(
                {
                    "path": f"/{connector}/link_123/{action}",
                    "args": arguments,
                }
            ),
            "connector_tool_payload": json.dumps(arguments),
            "create_time": 100.0,
            "end_turn": False,
        }
    ]
    if completed:
        events.append(
            {
                "id": f"{call_id}-result",
                "role": "tool",
                "recipient": "assistant",
                "content_type": "code",
                "text": json.dumps({"text": "done"}),
                "invoked_resource": {
                    "app_name": connector,
                    "resource_uri": f"/asdk_app_123/link_123/{action}",
                },
                "create_time": 101.0,
                "end_turn": False,
            }
        )
    return events


def snapshot(events: list[dict[str, Any]], *, complete: bool = False) -> dict[str, Any]:
    return {
        "title": "Diff capture",
        "path": "/c/test",
        "messages": [
            {"id": "u1", "role": "user", "content": "Change the code"},
            {"id": "a1", "role": "assistant", "content": "Working"},
        ],
        "source_events": events,
        "streaming": not complete,
    }


def start(cache: ChatCache, conversation_id: str) -> None:
    cache.start(
        conversation_id,
        context_id=f"context-{conversation_id}",
        job_name="",
        prompt="Change the code",
    )


def persist_and_observe(
    cache: ChatCache,
    capture: ToolDiffCapture,
    conversation_id: str,
    value: dict[str, Any],
) -> None:
    cache.write_snapshot(conversation_id, value)
    capture.observe_snapshot(conversation_id, value)


def test_python_call_captures_diff_and_identical_tree_persists_nothing(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    cache = ChatCache(tmp_path / "chats.sqlite3")
    capture = ToolDiffCapture(cache)

    start(cache, "python-change")
    running = snapshot(
        tool_events(
            "Glass",
            "execute_python",
            {"cwd": str(repo), "code": "mutate()"},
            call_id="python-call",
            completed=False,
        )
    )
    persist_and_observe(cache, capture, "python-change", running)

    (repo / "changed.txt").write_text("after python\n", encoding="utf-8")
    completed = snapshot(
        tool_events(
            "Glass",
            "execute_python",
            {"cwd": str(repo), "code": "mutate()"},
            call_id="python-call",
            completed=True,
        ),
        complete=True,
    )
    persist_and_observe(cache, capture, "python-change", completed)

    row = cache.connection.execute(
        """
        SELECT patch_text, changed_file_count, additions, deletions,
               repository_root, worktree_path
        FROM tool_call_diffs
        WHERE conversation_id = ?
        """,
        ("python-change",),
    ).fetchone()
    assert row is not None
    assert row["changed_file_count"] == 1
    assert row["additions"] == 1
    assert row["deletions"] == 1
    assert "after python" in row["patch_text"]
    assert row["repository_root"] == str(repo.resolve())
    assert row["worktree_path"] == str(repo.resolve())

    start(cache, "python-identical")
    unchanged_running = snapshot(
        tool_events(
            "Glass",
            "execute_python",
            {"cwd": str(repo), "code": "print('read only')"},
            call_id="python-read",
            completed=False,
        )
    )
    persist_and_observe(cache, capture, "python-identical", unchanged_running)
    unchanged_complete = snapshot(
        tool_events(
            "Glass",
            "execute_python",
            {"cwd": str(repo), "code": "print('read only')"},
            call_id="python-read",
            completed=True,
        ),
        complete=True,
    )
    persist_and_observe(cache, capture, "python-identical", unchanged_complete)

    count = cache.connection.execute(
        "SELECT COUNT(*) FROM tool_call_diffs WHERE conversation_id = ?",
        ("python-identical",),
    ).fetchone()[0]
    cache.close()

    assert count == 0


def test_serena_repl_uses_activated_project_context(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    cache = ChatCache(tmp_path / "chats.sqlite3")
    capture = ToolDiffCapture(cache)
    conversation_id = "serena-change"
    session_id = "session-123"
    start(cache, conversation_id)

    activated = snapshot(
        tool_events(
            "Glass Serena",
            "activate_project",
            {"project": str(repo), "session_id": session_id},
            call_id="activate",
            completed=True,
        )
    )
    persist_and_observe(cache, capture, conversation_id, activated)

    repl_running_events = [
        *activated["source_events"],
        *tool_events(
            "Glass Serena",
            "serena_repl",
            {"session_id": session_id, "code": "s.edit.replace_content(...)"},
            call_id="serena-call",
            completed=False,
        ),
    ]
    repl_running = snapshot(repl_running_events)
    persist_and_observe(cache, capture, conversation_id, repl_running)

    (repo / "changed.txt").write_text("after serena\n", encoding="utf-8")
    repl_completed_events = [
        *activated["source_events"],
        *tool_events(
            "Glass Serena",
            "serena_repl",
            {"session_id": session_id, "code": "s.edit.replace_content(...)"},
            call_id="serena-call",
            completed=True,
        ),
    ]
    repl_completed = snapshot(repl_completed_events, complete=True)
    persist_and_observe(cache, capture, conversation_id, repl_completed)

    row = cache.connection.execute(
        """
        SELECT d.patch_text, c.action
        FROM tool_call_diffs AS d
        JOIN tool_calls AS c
          ON c.conversation_id = d.conversation_id
         AND c.message_key = d.message_key
         AND c.call_key = d.call_key
        WHERE d.conversation_id = ?
        """,
        (conversation_id,),
    ).fetchone()
    cache.close()

    assert row is not None
    assert row["action"] == "serena_repl"
    assert "after serena" in row["patch_text"]


def test_concurrent_calls_keep_unrelated_worktrees_isolated(tmp_path: Path) -> None:
    worktree_a = init_repo(tmp_path, "worktree-a")
    worktree_b = init_repo(tmp_path, "worktree-b")

    cache = ChatCache(tmp_path / "chats.sqlite3")
    capture = ToolDiffCapture(cache)

    for conversation_id, cwd, call_id in (
        ("conversation-a", worktree_a, "call-a"),
        ("conversation-b", worktree_b, "call-b"),
    ):
        start(cache, conversation_id)
        running = snapshot(
            tool_events(
                "Glass",
                "execute_python",
                {"cwd": str(cwd), "code": "mutate()"},
                call_id=call_id,
                completed=False,
            )
        )
        persist_and_observe(cache, capture, conversation_id, running)

    (worktree_a / "changed.txt").write_text("only a\n", encoding="utf-8")
    (worktree_b / "changed.txt").write_text("only b\n", encoding="utf-8")

    for conversation_id, cwd, call_id in (
        ("conversation-b", worktree_b, "call-b"),
        ("conversation-a", worktree_a, "call-a"),
    ):
        completed = snapshot(
            tool_events(
                "Glass",
                "execute_python",
                {"cwd": str(cwd), "code": "mutate()"},
                call_id=call_id,
                completed=True,
            ),
            complete=True,
        )
        persist_and_observe(cache, capture, conversation_id, completed)

    rows = cache.connection.execute(
        """
        SELECT conversation_id, patch_text, repository_root, worktree_path
        FROM tool_call_diffs
        ORDER BY conversation_id
        """
    ).fetchall()
    cache.close()

    assert len(rows) == 2
    assert "only a" in rows[0]["patch_text"]
    assert "only b" not in rows[0]["patch_text"]
    assert "only b" in rows[1]["patch_text"]
    assert "only a" not in rows[1]["patch_text"]
    assert rows[0]["repository_root"] == str(worktree_a.resolve())
    assert rows[1]["repository_root"] == str(worktree_b.resolve())
    assert rows[0]["worktree_path"] == str(worktree_a.resolve())
    assert rows[1]["worktree_path"] == str(worktree_b.resolve())


def test_diff_preview_end_to_end_isolates_tool_change_from_preexisting_dirty_state(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path)
    tracked_dirty = repo / "preexisting-dirty.txt"
    tracked_dirty.write_text("clean baseline\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "add dirty baseline")
    tracked_dirty.write_text("dirty before tool\n", encoding="utf-8")
    untracked_dirty = repo / "preexisting-untracked.txt"
    untracked_dirty.write_text("also dirty before tool\n", encoding="utf-8")

    database = tmp_path / "chats.sqlite3"
    cache = ChatCache(database)
    capture = ToolDiffCapture(cache)
    conversation_id = "end-to-end-diff"
    start(cache, conversation_id)

    mutating_running_events = tool_events(
        "Glass",
        "execute_python",
        {"cwd": str(repo), "code": "mutate()"},
        call_id="mutating-call",
        completed=False,
    )
    persist_and_observe(
        cache,
        capture,
        conversation_id,
        snapshot(mutating_running_events),
    )

    (repo / "changed.txt").write_text("changed by tool\n", encoding="utf-8")
    (repo / "tool-created.txt").write_text("created by tool\n", encoding="utf-8")

    mutating_completed_events = tool_events(
        "Glass",
        "execute_python",
        {"cwd": str(repo), "code": "mutate()"},
        call_id="mutating-call",
        completed=True,
    )
    persist_and_observe(
        cache,
        capture,
        conversation_id,
        snapshot(mutating_completed_events),
    )

    read_only_running_events = [
        *mutating_completed_events,
        *tool_events(
            "Glass",
            "execute_python",
            {"cwd": str(repo), "code": "print('read only')"},
            call_id="read-only-call",
            completed=False,
        ),
    ]
    persist_and_observe(
        cache,
        capture,
        conversation_id,
        snapshot(read_only_running_events),
    )
    read_only_completed_events = [
        *mutating_completed_events,
        *tool_events(
            "Glass",
            "execute_python",
            {"cwd": str(repo), "code": "print('read only')"},
            call_id="read-only-call",
            completed=True,
        ),
    ]
    persist_and_observe(
        cache,
        capture,
        conversation_id,
        snapshot(read_only_completed_events, complete=True),
    )

    diff_rows = cache.connection.execute(
        """
        SELECT call_key, patch_text, changed_file_count, additions, deletions
        FROM tool_call_diffs
        WHERE conversation_id = ?
        ORDER BY call_key
        """,
        (conversation_id,),
    ).fetchall()
    cache.close()

    assert len(diff_rows) == 1
    assert diff_rows[0]["call_key"] == "tool-mutating-call"
    assert diff_rows[0]["changed_file_count"] == 2
    assert diff_rows[0]["additions"] == 2
    assert diff_rows[0]["deletions"] == 1
    patch = str(diff_rows[0]["patch_text"])
    assert "changed.txt" in patch
    assert "tool-created.txt" in patch
    assert "preexisting-dirty.txt" not in patch
    assert "preexisting-untracked.txt" not in patch

    chat = ReadOnlyChatStore(database).conversation(conversation_id)
    assert chat is not None
    calls = [
        call
        for message in chat["messages"]
        for call in message.get("tool_calls", [])
        if isinstance(call, dict)
    ]
    calls_by_key = {str(call["call_key"]): call for call in calls}
    assert set(calls_by_key) == {"tool-mutating-call", "tool-read-only-call"}
    assert calls_by_key["tool-mutating-call"]["code_diff"]["patch_text"] == patch
    assert "code_diff" not in calls_by_key["tool-read-only-call"]


def test_capture_failures_are_best_effort(tmp_path: Path) -> None:
    class BrokenGitService(GitDiffService):
        def snapshot(self, cwd: Path) -> GitSnapshot | None:
            raise RuntimeError(f"cannot snapshot {cwd}")

    repo = init_repo(tmp_path)
    cache = ChatCache(tmp_path / "chats.sqlite3")
    start(cache, "broken-capture")
    capture = ToolDiffCapture(cache, git_service=BrokenGitService())
    running = snapshot(
        tool_events(
            "Glass",
            "execute_python",
            {"cwd": str(repo), "code": "mutate()"},
            call_id="broken-call",
            completed=False,
        )
    )
    cache.write_snapshot("broken-capture", running)

    capture.observe_snapshot("broken-capture", running)
    cache.close()
