from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cache import ChatCache
from .git_diff import GitDiffService, GitSnapshot
from .structured_capture import tool_calls_from_source_events

logger = logging.getLogger(__name__)

_PATCH_LIMIT_CHARS = 250_000
_RUNNING_STATUSES = frozenset({"queued", "pending", "running", "started", "in_progress"})


@dataclass(frozen=True)
class _PendingToolDiff:
    snapshot: GitSnapshot
    cwd: Path
    message_key: str


class ToolDiffCapture:
    """Best-effort Git diff capture around repository-aware mutating tool calls."""

    def __init__(
        self,
        cache: ChatCache,
        *,
        git_service: GitDiffService | None = None,
        patch_limit_chars: int = _PATCH_LIMIT_CHARS,
    ) -> None:
        self.cache = cache
        self.git_service = git_service or GitDiffService()
        self.patch_limit_chars = max(1, patch_limit_chars)
        self._pending: dict[tuple[str, str], _PendingToolDiff] = {}
        self._serena_projects: dict[tuple[str, str], Path] = {}

    def observe_snapshot(self, conversation_id: str, snapshot: dict[str, Any]) -> None:
        """Observe tool lifecycle state without allowing diff capture to disrupt tracking."""
        try:
            self._observe_snapshot(conversation_id, snapshot)
        except Exception:
            logger.exception(
                "Prompta tool diff capture failed conversation=%s",
                conversation_id,
            )

    def _observe_snapshot(self, conversation_id: str, snapshot: dict[str, Any]) -> None:
        source_events = snapshot.get("source_events")
        if not isinstance(source_events, list):
            return
        calls = tool_calls_from_source_events(
            [event for event in source_events if isinstance(event, dict)]
        )
        for call in calls:
            try:
                self._observe_call(conversation_id, call)
            except Exception:
                logger.exception(
                    "Prompta tool diff capture failed conversation=%s call=%s",
                    conversation_id,
                    call.get("call_key"),
                )

    def _observe_call(self, conversation_id: str, call: dict[str, Any]) -> None:
        connector = str(call.get("connector") or "").strip()
        action = str(call.get("action") or "").strip()
        arguments = call.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}

        self._remember_serena_project(conversation_id, connector, action, arguments)
        if not self._is_code_capable(connector, action):
            return

        call_key = str(call.get("call_key") or "").strip()
        if not call_key:
            return
        pending_key = (conversation_id, call_key)
        status = str(call.get("status") or "").strip().casefold()
        result_event_key = str(call.get("result_event_key") or "").strip()

        if status in _RUNNING_STATUSES and not result_event_key:
            if pending_key in self._pending:
                return
            cwd = self._execution_path(conversation_id, connector, action, arguments)
            if cwd is None:
                return
            before = self.git_service.snapshot(cwd)
            if before is None:
                return
            message_key = self.cache.tool_call_message_key(conversation_id, call_key)
            if not message_key:
                return
            self._pending[pending_key] = _PendingToolDiff(
                snapshot=before,
                cwd=cwd,
                message_key=message_key,
            )
            return

        if pending_key not in self._pending:
            return
        pending = self._pending.pop(pending_key)
        after = self.git_service.snapshot(pending.cwd)
        if after is None or after.tree_id == pending.snapshot.tree_id:
            return
        diff = self.git_service.compare(pending.snapshot, after)
        if diff is None or diff.summary.files_changed <= 0:
            return

        message_key = self.cache.tool_call_message_key(conversation_id, call_key)
        if not message_key:
            message_key = pending.message_key
        patch_text, truncated = self._bounded_patch(diff.patch)
        repository_root = pending.snapshot.repository_root or pending.snapshot.repo_root
        self.cache.record_tool_call_diff(
            conversation_id,
            message_key,
            call_key,
            before_tree_id=pending.snapshot.tree_id,
            after_tree_id=after.tree_id,
            patch_text=patch_text,
            changed_file_count=diff.summary.files_changed,
            additions=diff.summary.insertions,
            deletions=diff.summary.deletions,
            truncated=truncated,
            repository_root=str(repository_root),
            worktree_path=str(pending.snapshot.repo_root),
        )

    def _remember_serena_project(
        self,
        conversation_id: str,
        connector: str,
        action: str,
        arguments: dict[str, Any],
    ) -> None:
        if "serena" not in connector.casefold() or action.casefold() != "activate_project":
            return
        session_id = str(arguments.get("session_id") or "").strip()
        project = self._path_value(arguments.get("project"))
        if session_id and project is not None:
            self._serena_projects[(conversation_id, session_id)] = project

    def _execution_path(
        self,
        conversation_id: str,
        connector: str,
        action: str,
        arguments: dict[str, Any],
    ) -> Path | None:
        direct = self._context_path(arguments)
        if direct is not None:
            return direct
        if "serena" in connector.casefold() and action.casefold() == "serena_repl":
            session_id = str(arguments.get("session_id") or "").strip()
            if session_id:
                return self._serena_projects.get((conversation_id, session_id))
        return None

    @classmethod
    def _context_path(cls, arguments: dict[str, Any]) -> Path | None:
        for key in (
            "cwd",
            "working_dir",
            "working_directory",
            "workdir",
            "worktree_path",
            "worktree",
            "repository_root",
            "repo_root",
            "repository",
            "repo",
            "project_path",
            "project",
        ):
            path = cls._path_value(arguments.get(key))
            if path is not None:
                return path
        for key in ("execution_context", "context"):
            nested = arguments.get(key)
            if isinstance(nested, dict):
                path = cls._context_path(nested)
                if path is not None:
                    return path
        return None

    @staticmethod
    def _path_value(value: Any) -> Path | None:
        if isinstance(value, dict):
            for key in ("path", "root", "cwd", "worktree", "directory", "dir"):
                nested = value.get(key)
                if isinstance(nested, str) and nested.strip():
                    value = nested
                    break
            else:
                return None
        if not isinstance(value, str) or not value.strip():
            return None
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            return None
        try:
            return candidate.resolve()
        except OSError:
            return None

    @staticmethod
    def _is_code_capable(connector: str, action: str) -> bool:
        connector_name = connector.casefold()
        action_name = action.casefold()
        combined = f"{connector_name} {action_name}"
        if action_name == "execute_python":
            return True
        if "serena" in connector_name and action_name == "serena_repl":
            return True
        if "opencode" in combined:
            return True
        return any(
            marker in action_name
            for marker in (
                "execute_shell",
                "shell_command",
                "run_command",
                "exec_command",
                "terminal_exec",
            )
        )

    def _bounded_patch(self, patch: str) -> tuple[str, bool]:
        if len(patch) <= self.patch_limit_chars:
            return patch, False
        marker = "\n... [truncated by Prompta]\n"
        keep = max(0, self.patch_limit_chars - len(marker))
        return patch[:keep] + marker, True
