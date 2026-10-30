"""Private, payload-free change signals for Prompta's local web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

FileVersion = tuple[int, int, int]
TopicVersion = tuple[FileVersion, ...]


def _version(path: Path) -> FileVersion:
    try:
        info = path.stat()
    except OSError:
        # A transient filesystem error must not tear down every SSE stream.
        # The next successful stat will restore a distinct revision.
        return (0, 0, 0)
    return (info.st_ino, info.st_size, info.st_mtime_ns)


def _database_files(path: Path) -> tuple[Path, Path]:
    return path, Path(f"{path}-wal")


@dataclass(frozen=True)
class LiveRevisions:
    jobs: TopicVersion
    chats: TopicVersion


class LocalEventSignals:
    """Observe writes across processes without reading or transmitting private records."""

    def __init__(self, jobs_path: Path, state_path: Path) -> None:
        self._job_files = tuple(dict.fromkeys((
            *_database_files(jobs_path), *_database_files(state_path),
        )))
        self._chat_files = (
            *_database_files(state_path.parent / "chat-results.sqlite3"),
            *_database_files(state_path.parent / "ui-send-jobs.sqlite3"),
        )

    def snapshot(self) -> LiveRevisions:
        return LiveRevisions(
            jobs=tuple(_version(path) for path in self._job_files),
            chats=tuple(_version(path) for path in self._chat_files),
        )
