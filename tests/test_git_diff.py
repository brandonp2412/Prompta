from __future__ import annotations

import subprocess
from pathlib import Path

from prompta.git_diff import GitDiffService


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "prompta-tests@example.invalid")
    git(repo, "config", "user.name", "Prompta Tests")
    (repo / ".gitignore").write_text("*.ignored\n", encoding="utf-8")
    (repo / "stable.txt").write_text("base\n", encoding="utf-8")
    (repo / "changed.txt").write_text("before\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    return repo


def test_diff_excludes_unchanged_preexisting_dirty_and_untracked_files(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    service = GitDiffService()

    (repo / "stable.txt").write_text("staged version\n", encoding="utf-8")
    git(repo, "add", "stable.txt")
    (repo / "stable.txt").write_text("pre-existing dirty version\n", encoding="utf-8")
    (repo / "pre-existing.txt").write_text("untracked before snapshot\n", encoding="utf-8")
    (repo / "cache.ignored").write_text("ignored before snapshot\n", encoding="utf-8")
    cached_before = git(repo, "diff", "--cached", "--binary")

    before = service.snapshot(repo)

    assert before is not None
    assert git(repo, "diff", "--cached", "--binary") == cached_before

    (repo / "changed.txt").write_text("after\n", encoding="utf-8")
    (repo / "cache.ignored").write_text("ignored after snapshot\n", encoding="utf-8")
    result = service.diff(before, repo)

    assert result is not None
    assert result.summary.files_changed == 1
    assert result.summary.modified == 1
    assert result.summary.added == 0
    assert result.summary.deleted == 0
    assert result.summary.renamed == 0
    assert result.summary.insertions == 1
    assert result.summary.deletions == 1
    assert "changed.txt" in result.patch
    assert "stable.txt" not in result.patch
    assert "pre-existing.txt" not in result.patch
    assert "cache.ignored" not in result.patch
    assert git(repo, "diff", "--cached", "--binary") == cached_before


def test_diff_detects_rename_and_reports_summary(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    service = GitDiffService()
    old_path = repo / "stable.txt"
    old_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
    git(repo, "add", "stable.txt")
    git(repo, "commit", "-m", "rename fixture")
    before = service.snapshot(repo)
    assert before is not None

    old_path.rename(repo / "renamed.txt")
    result = service.diff(before, repo)

    assert result is not None
    assert result.summary.files_changed == 1
    assert result.summary.renamed == 1
    assert result.summary.added == 0
    assert result.summary.modified == 0
    assert result.summary.deleted == 0
    assert result.summary.insertions == 0
    assert result.summary.deletions == 0
    assert "rename from stable.txt" in result.patch
    assert "rename to renamed.txt" in result.patch


def test_diff_includes_new_nonignored_untracked_file(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    service = GitDiffService()
    before = service.snapshot(repo)
    assert before is not None

    (repo / "new-file.txt").write_text("new\n", encoding="utf-8")
    result = service.diff(before, repo)

    assert result is not None
    assert result.summary.files_changed == 1
    assert result.summary.added == 1
    assert "new-file.txt" in result.patch


def test_snapshot_baselines_preexisting_untracked_file_as_modified(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    service = GitDiffService()
    untracked = repo / "scratch.txt"
    untracked.write_text("before\n", encoding="utf-8")
    before = service.snapshot(repo)
    assert before is not None

    untracked.write_text("after\n", encoding="utf-8")
    result = service.diff(before, repo)

    assert result is not None
    assert result.summary.files_changed == 1
    assert result.summary.added == 0
    assert result.summary.modified == 1
    assert "scratch.txt" in result.patch


def test_snapshot_is_safe_for_non_git_directory(tmp_path: Path) -> None:
    service = GitDiffService()

    assert service.snapshot(tmp_path) is None
