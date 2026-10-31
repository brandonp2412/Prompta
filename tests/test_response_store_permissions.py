"""SQLite WAL/SHM cleanup races must not reject a fresh chat request."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from prompta.response_store import ResponseStore


def test_response_store_tolerates_disappearing_sqlite_sidecars(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    chmod = Path.chmod

    def disappearing_sidecar(path: Path, mode: int) -> None:
        if str(path).endswith(("-wal", "-shm")):
            raise FileNotFoundError("SQLite removed its temporary sidecar")
        chmod(path, mode)

    with patch.object(Path, "chmod", disappearing_sidecar):
        store._secure_files()


def test_response_store_does_not_hide_missing_primary_database(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    with patch.object(Path, "chmod", side_effect=FileNotFoundError("Database missing")):
        with pytest.raises(FileNotFoundError, match="Database missing"):
            store._secure_files()
