from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_GIT_TIMEOUT_SECONDS = 30
_SHORTSTAT_INSERTIONS_RE = re.compile(r"(\d+) insertions?\(\+\)")
_SHORTSTAT_DELETIONS_RE = re.compile(r"(\d+) deletions?\(-\)")


@dataclass(frozen=True)
class GitSnapshot:
    repo_root: Path
    tree_id: str


@dataclass(frozen=True)
class GitDiffSummary:
    files_changed: int
    insertions: int
    deletions: int
    added: int
    modified: int
    deleted: int
    renamed: int


@dataclass(frozen=True)
class GitDiff:
    patch: str
    summary: GitDiffSummary


class GitDiffService:
    """Safely snapshots worktree contents and compares snapshots without using the real index."""

    def snapshot(self, cwd: Path) -> GitSnapshot | None:
        repo_root = self._repo_root(cwd)
        if repo_root is None:
            return None

        try:
            with tempfile.TemporaryDirectory(prefix="prompta-git-index-") as temp_dir:
                env = self._git_env(Path(temp_dir) / "index")
                head = self._run_git(
                    repo_root,
                    ["rev-parse", "--verify", "HEAD"],
                    env=env,
                )
                read_tree_args = (
                    ["read-tree", "HEAD"] if head is not None else ["read-tree", "--empty"]
                )
                if self._run_git(repo_root, read_tree_args, env=env) is None:
                    return None
                if self._run_git(repo_root, ["add", "-A", "--", "."], env=env) is None:
                    return None
                tree_id = self._run_git(repo_root, ["write-tree"], env=env)
        except (OSError, subprocess.SubprocessError):
            return None

        if tree_id is None:
            return None
        tree_id = tree_id.strip().lower()
        if re.fullmatch(r"[0-9a-f]{40,64}", tree_id) is None:
            return None
        return GitSnapshot(repo_root=repo_root, tree_id=tree_id)

    def diff(self, before: GitSnapshot, cwd: Path) -> GitDiff | None:
        after = self.snapshot(cwd)
        if after is None:
            return None
        return self.compare(before, after)

    def compare(self, before: GitSnapshot, after: GitSnapshot) -> GitDiff | None:
        if before.repo_root.resolve() != after.repo_root.resolve():
            return None

        root = before.repo_root
        common = [
            "--no-ext-diff",
            "--no-textconv",
            "--find-renames",
            before.tree_id,
            after.tree_id,
            "--",
        ]
        try:
            patch = self._run_git(root, ["diff", "--binary", "--no-color", *common])
            name_status = self._run_git(root, ["diff", "--name-status", "-z", *common])
            shortstat = self._run_git(root, ["diff", "--shortstat", *common])
        except (OSError, subprocess.SubprocessError):
            return None
        if patch is None or name_status is None or shortstat is None:
            return None

        counts = self._status_counts(name_status)
        if counts is None:
            return None
        added, modified, deleted, renamed = counts
        return GitDiff(
            patch=patch,
            summary=GitDiffSummary(
                files_changed=added + modified + deleted + renamed,
                insertions=self._shortstat_count(shortstat, _SHORTSTAT_INSERTIONS_RE),
                deletions=self._shortstat_count(shortstat, _SHORTSTAT_DELETIONS_RE),
                added=added,
                modified=modified,
                deleted=deleted,
                renamed=renamed,
            ),
        )

    def _repo_root(self, cwd: Path) -> Path | None:
        try:
            root = self._run_git(cwd, ["rev-parse", "--show-toplevel"])
        except (OSError, subprocess.SubprocessError):
            return None
        if root is None:
            return None
        candidate = Path(root.strip())
        if not candidate.is_absolute():
            candidate = cwd / candidate
        try:
            return candidate.resolve()
        except OSError:
            return None

    @staticmethod
    def _git_env(index_path: Path | None = None) -> dict[str, str]:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["LC_ALL"] = "C"
        if index_path is not None:
            env["GIT_INDEX_FILE"] = str(index_path)
        return env

    @staticmethod
    def _run_git(
        cwd: Path,
        args: list[str],
        *,
        env: dict[str, str] | None = None,
    ) -> str | None:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=env or GitDiffService._git_env(),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            return None
        return completed.stdout

    @staticmethod
    def _status_counts(name_status: str) -> tuple[int, int, int, int] | None:
        tokens = name_status.split("\0")
        if tokens and tokens[-1] == "":
            tokens.pop()

        added = modified = deleted = renamed = 0
        index = 0
        while index < len(tokens):
            status = tokens[index]
            index += 1
            if not status:
                return None
            code = status[0]
            path_count = 2 if code in {"R", "C"} else 1
            if index + path_count > len(tokens):
                return None
            index += path_count

            if code == "A" or code == "C":
                added += 1
            elif code == "D":
                deleted += 1
            elif code == "R":
                renamed += 1
            else:
                modified += 1

        return added, modified, deleted, renamed

    @staticmethod
    def _shortstat_count(shortstat: str, pattern: re.Pattern[str]) -> int:
        match = pattern.search(shortstat)
        return int(match.group(1)) if match else 0
