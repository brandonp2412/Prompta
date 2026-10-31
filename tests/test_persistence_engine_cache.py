"""Database cache eviction must close idle SQLite connections without waiting for GC."""

from __future__ import annotations

from pathlib import Path

import pytest

from prompta.persistence import create_database


def test_database_engine_cache_disposes_evicted_connections(tmp_path: Path) -> None:
    descriptor_dir = Path("/proc/self/fd")
    if not descriptor_dir.is_dir():
        pytest.skip("Descriptor inspection requires Linux")

    baseline = len(list(descriptor_dir.iterdir()))
    first = create_database(tmp_path / "first.sqlite3")
    assert create_database(tmp_path / "first.sqlite3") is first
    for index in range(75):
        engine = create_database(tmp_path / f"state-{index}.sqlite3")
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1

    assert len(list(descriptor_dir.iterdir())) <= baseline + 40
