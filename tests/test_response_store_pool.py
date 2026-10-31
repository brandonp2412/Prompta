"""Transient response stores must not reserve one SQLite descriptor each."""

from __future__ import annotations

from pathlib import Path

import pytest

from prompta.response_store import ResponseStore


def test_response_stores_leave_no_idle_sqlite_connections(tmp_path: Path) -> None:
    descriptor_dir = Path("/proc/self/fd")
    if not descriptor_dir.is_dir():
        pytest.skip("Descriptor inspection requires Linux")

    baseline = len(list(descriptor_dir.iterdir()))
    stores: list[ResponseStore] = []
    for index in range(60):
        path = tmp_path / str(index) / "chat-results.sqlite3"
        stores.append(ResponseStore(path))
        stores[-1].ensure_queued(f"synthetic-{index}", "Synthetic prompt", now=10)

    assert len(list(descriptor_dir.iterdir())) <= baseline + 4
    assert len(stores) == 60
