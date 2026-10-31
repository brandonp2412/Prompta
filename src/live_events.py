"""Private, payload-free change signals for Prompta's local web UI."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

FileVersion = tuple[int, int, int]
TopicVersion = tuple[FileVersion, ...]


def _version(path: Path) -> FileVersion:
    try:
        info = path.stat()
    except OSError:
        # A transient stat failure must not tear down SSE; a later readable
        # snapshot will restore the revision.
        return (0, 0, 0)
    return (info.st_ino, info.st_size, info.st_mtime_ns)


def _database_files(path: Path) -> tuple[Path, Path]:
    return path, Path(f"{path}-wal")


def _job_state_version(path: Path) -> FileVersion | None:
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1) as conn:
            digest = hashlib.blake2b(digest_size=8)
            count = 0
            for table, fields, order in (
                ("scheduler_state", "scope, name, key, value_json", "scope, name, key"),
                ("account_state", "key, value_json", "key"),
            ):
                digest.update(table.encode())
                for row in conn.execute(f"SELECT {fields} FROM {table} ORDER BY {order}"):
                    count += 1
                    for field in row:
                        data = str(field).encode()
                        digest.update(len(data).to_bytes(4, "big"))
                        digest.update(data)
        return (1, count, int.from_bytes(digest.digest(), "big"))
    except (OSError, sqlite3.Error):
        return None


@dataclass(frozen=True)
class LiveRevisions:
    jobs: TopicVersion
    chats: TopicVersion


class LocalEventSignals:
    """Observe writes across processes without reading or transmitting private records."""

    def __init__(self, jobs_path: Path, state_path: Path) -> None:
        self._job_files = _database_files(jobs_path)
        self._state_path = state_path
        self._state_files = _database_files(state_path)
        self._state_file_versions: TopicVersion | None = None
        self._state_revision: FileVersion = (0, 0, 0)
        self._lock = Lock()
        self._chat_files = (
            *_database_files(state_path.parent / "chat-results.sqlite3"),
            *_database_files(state_path.parent / "ui-send-jobs.sqlite3"),
        )

    def snapshot(self) -> LiveRevisions:
        with self._lock:
            files = tuple(_version(path) for path in self._state_files)
            if files != self._state_file_versions:
                state = _job_state_version(self._state_path) if any(part != (0, 0, 0) for part in files) else None
                if state is not None:
                    self._state_revision = state
                    self._state_file_versions = files
            return LiveRevisions(
                jobs=(*(_version(path) for path in self._job_files), self._state_revision),
                chats=tuple(_version(path) for path in self._chat_files),
            )
