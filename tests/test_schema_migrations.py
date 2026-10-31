"""Data-preserving adoption, transactional failure, and concurrent schema startup."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, inspect

from prompta.persistence import metadata
from prompta.reply_contracts import ManualReplyStore, replies
from prompta.response_store import ResponseStore, results
from prompta.schema_migrations import SchemaFamily, migration_config, upgrade_database, upgrade_path


@pytest.mark.parametrize("family", ["runtime", "results", "ownership"])
def test_fresh_database_reaches_head_and_repeated_startup_is_a_noop(
    tmp_path: Path, family: SchemaFamily
) -> None:
    path = tmp_path / f"{family}.sqlite3"
    upgrade_path(path, family)
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            f"SELECT version_num FROM alembic_{family}_version"
        ).fetchone() == (f"{family}_0002",)
        before = connection.iterdump()
        snapshot = list(before)
    upgrade_path(path, family)
    with sqlite3.connect(path) as connection:
        assert list(connection.iterdump()) == snapshot
    assert path.stat().st_mode & 0o077 == 0
    assert path.parent.stat().st_mode & 0o077 == 0


def test_old_runtime_keeps_job_order_delivery_and_account_read_gate(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE scheduled_jobs (
                name VARCHAR PRIMARY KEY, prompt TEXT NOT NULL,
                interval_seconds FLOAT NOT NULL, daily_at VARCHAR,
                exact_interval BOOLEAN NOT NULL, run_at_epoch FLOAT
            );
            INSERT INTO scheduled_jobs VALUES ('z-old', 'private first', 600, NULL, 1, NULL);
            INSERT INTO scheduled_jobs VALUES ('a-new', 'private second', 900, NULL, 0, NULL);
            CREATE TABLE scheduler_state (
                scope VARCHAR NOT NULL, name VARCHAR NOT NULL, key VARCHAR NOT NULL,
                value_json TEXT NOT NULL, PRIMARY KEY (scope, name, key)
            );
            INSERT INTO scheduler_state VALUES ('scheduler', '', 'rate_limit_backoff', '{"until":99999}');
            INSERT INTO scheduler_state VALUES ('job', 'z-old', 'paused', 'true');
        """)
    upgrade_path(path, "runtime")
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT rowid, name, prompt, images_json, pin_chat FROM scheduled_jobs ORDER BY rowid"
        ).fetchall() == [
            (1, "z-old", "private first", "[]", 0),
            (2, "a-new", "private second", "[]", 0),
        ]
        assert connection.execute(
            "SELECT value_json FROM account_state WHERE key = 'rate_limit_backoff'"
        ).fetchone() == ('{"until":99999}',)
        connection.execute("UPDATE account_state SET value_json = '{\"until\":123456}'")
    upgrade_path(path, "runtime")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT value_json FROM account_state").fetchone() == (
            '{"until":123456}',
        )
    engine = create_engine(f"sqlite:///{path}")
    try:
        for table in metadata.tables.values():
            assert {column["name"] for column in inspect(engine).get_columns(table.name)} == set(
                table.columns.keys()
            )
    finally:
        engine.dispose()


def test_unversioned_current_results_preserve_private_transcripts_and_receipts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chat-results.sqlite3"
    store = ResponseStore(path)
    store.ensure_queued("saved-run", "private prompt", now=100)
    store.set_local_pin("saved-run", pinned=True)
    store.engine.dispose()
    # Simulate a deployed, current schema with no Alembic revision marker.
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE alembic_results_version")
    replies_store = ManualReplyStore(path)
    assert replies_store.responses.detail("saved-run") is not None
    assert [row["send_id"] for row in replies_store.responses.local_pinned_runs()] == ["saved-run"]
    assert set(inspect(replies_store.engine).get_table_names()) >= {results.name, replies.name}


def test_legacy_reply_and_result_columns_gain_defaults_without_losing_branches(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chat-results.sqlite3"
    engine = create_engine(f"sqlite:///{path}")
    # Install only the historical baseline, including its version marker.
    config = migration_config("results")
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        config.attributes["connection"] = connection
        command.upgrade(config, "results_0001")
        connection.exec_driver_sql("""
            INSERT INTO manual_reply_turns VALUES
            ('reply-one', 'saved-run', 'verified-chat', 'exact-parent',
             'private reply', 'private answer', 'message-one', 'outcome_unknown',
             'old-owner', 500, 100, 200)
        """)
    upgrade_database(engine, "results")
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT conversation_id, parent_id, status, tool_calls_json, response_parent_id, queued_by_user FROM manual_reply_turns"
        ).one()
        assert tuple(row) == ("verified-chat", "exact-parent", "outcome_unknown", "[]", "", 0)
    engine.dispose()


def test_owned_tab_upgrade_does_not_revive_expired_activity(tmp_path: Path) -> None:
    path = tmp_path / "owned-tabs.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE owned_tabs (target_id TEXT PRIMARY KEY, opened_at REAL NOT NULL)"
        )
        connection.execute("INSERT INTO owned_tabs VALUES ('old-target', 123)")
    upgrade_path(path, "ownership")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM owned_tabs").fetchone() == ("old-target", 123, 123)
        connection.execute("UPDATE owned_tabs SET last_activity_at = 456")
    upgrade_path(path, "ownership")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT last_activity_at FROM owned_tabs").fetchone() == (456,)


def test_failed_upgrade_rolls_back_ddl_and_version_marker(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "runtime.sqlite3"
    original = command.upgrade

    def fail_after_upgrade(config: Config, revision: str) -> None:
        original(config, revision)
        raise RuntimeError("simulated interrupted migration")

    with monkeypatch.context() as patch:
        patch.setattr(command, "upgrade", fail_after_upgrade)
        with pytest.raises(RuntimeError, match="simulated"):
            upgrade_path(path, "runtime")
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            == []
        )
    upgrade_path(path, "runtime")


def test_simultaneous_store_startup_serializes_alembic_contexts(tmp_path: Path) -> None:
    path = tmp_path / "shared.sqlite3"

    def initialize(index: int) -> None:
        upgrade_path(path, "results" if index % 2 else "runtime")

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(initialize, range(12)))
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_runtime_version").fetchone() == (
            "runtime_0002",
        )
        assert connection.execute("SELECT version_num FROM alembic_results_version").fetchone() == (
            "results_0002",
        )


def test_unknown_future_revision_fails_without_rewriting_data(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    upgrade_path(path, "ownership")
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO owned_tabs VALUES ('kept', 100, 200)")
        connection.execute("UPDATE alembic_ownership_version SET version_num = 'future_revision'")
    with pytest.raises(CommandError, match="future_revision"):
        upgrade_path(path, "ownership")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM owned_tabs").fetchone() == ("kept", 100, 200)


def test_separate_processes_adopt_one_database_without_racing(tmp_path: Path) -> None:
    import subprocess
    import sys

    path = tmp_path / "multiprocess.sqlite3"
    program = (
        "from pathlib import Path; import sys; "
        "from prompta.schema_migrations import upgrade_path; "
        "upgrade_path(Path(sys.argv[1]), 'results')"
    )
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", program, str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        for _ in range(4)
    ]
    try:
        for worker in workers:
            _, stderr = worker.communicate(timeout=20)
            assert worker.returncode == 0, stderr.decode()
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.wait()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_results_version").fetchone() == (
            "results_0002",
        )


def test_migration_cli_upgrades_default_stores_in_a_private_state_directory(tmp_path: Path) -> None:
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, "-m", "prompta.schema_migrations", "--state-dir", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    for filename, family in (
        ("runtime.sqlite3", "runtime"),
        ("ui-send-jobs.sqlite3", "runtime"),
        ("chat-results.sqlite3", "results"),
        ("owned-tabs.sqlite3", "ownership"),
    ):
        with sqlite3.connect(tmp_path / filename) as connection:
            assert connection.execute(
                f"SELECT version_num FROM alembic_{family}_version"
            ).fetchone() == (f"{family}_0002",)
