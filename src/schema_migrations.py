"""Versioned, transactional upgrades for each private SQLite database family."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from threading import RLock
from typing import Literal

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

SchemaFamily = Literal["runtime", "results", "ownership"]
_MIGRATIONS = Path(__file__).with_name("migrations")
# Alembic's context/op proxies are process-global. SQLite's write lock provides
# cross-process serialization; this lock also protects those proxies in threads.
_MIGRATION_LOCK = RLock()


def migration_config(family: SchemaFamily) -> Config:
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS))
    config.set_main_option("path_separator", "os")
    config.set_main_option("version_locations", str(_MIGRATIONS / family))
    config.set_main_option("version_table", f"alembic_{family}_version")
    return config


def upgrade_database(engine: Engine, family: SchemaFamily) -> None:
    with _MIGRATION_LOCK, engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        config = migration_config(family)
        version_table = config.get_main_option("version_table")
        current = MigrationContext.configure(
            connection, opts={"version_table": version_table}
        ).get_current_revision()
        head = ScriptDirectory.from_config(config).get_current_head()
        if current == head:
            return
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def upgrade_path(path: Path, family: SchemaFamily) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(descriptor)
    path.chmod(0o600)
    engine = create_engine(f"sqlite:///{path.resolve()}", connect_args={"timeout": 30})
    try:
        upgrade_database(engine, family)
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upgrade Prompta's private SQLite schemas")
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".local/state/prompta")
    parser.add_argument("--database", type=Path, help="Upgrade one custom database path")
    parser.add_argument("--family", choices=("runtime", "results", "ownership"))
    args = parser.parse_args()
    if args.database is not None:
        if args.family not in ("runtime", "results", "ownership"):
            parser.error("--database requires --family")
        upgrade_path(args.database, args.family)
        return
    if args.family is not None:
        parser.error("--family requires --database")
    for filename, family in (
        ("runtime.sqlite3", "runtime"),
        ("ui-send-jobs.sqlite3", "runtime"),
        ("chat-results.sqlite3", "results"),
        ("owned-tabs.sqlite3", "ownership"),
    ):
        upgrade_path(args.state_dir / filename, family)


if __name__ == "__main__":
    main()
