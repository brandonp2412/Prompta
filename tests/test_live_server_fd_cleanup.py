"""Repeated browser-test servers must release their SQLite pool handles."""

from __future__ import annotations

from pathlib import Path

import pytest
from live_server import LiveServer


def test_live_server_close_releases_database_file_descriptors(tmp_path: Path) -> None:
    fd_dir = Path("/proc/self/fd")
    if not fd_dir.is_dir():
        pytest.skip("Descriptor inspection requires Linux")

    baseline = len(list(fd_dir.iterdir()))
    for index in range(20):
        directory = tmp_path / str(index)
        directory.mkdir()
        app = LiveServer(
            ("127.0.0.1", 0),
            state_path=directory / "state.sqlite3",
            jobs_path=directory / "jobs.sqlite3",
        )
        app.server_close()

    assert len(list(fd_dir.iterdir())) <= baseline + 2
