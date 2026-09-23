from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

UI_METADATA_DB = "ui-metadata.sqlite3"


@contextmanager
def metadata_connection(path: Path) -> Iterator[sqlite3.Connection]:
    expanded = path.expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(expanded, timeout=30.0)
    os.chmod(expanded, 0o600)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def ensure_import_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata_imports (
            source TEXT PRIMARY KEY,
            imported_at REAL NOT NULL
        )
        """
    )


def import_recorded(connection: sqlite3.Connection, source: str) -> bool:
    ensure_import_table(connection)
    return (
        connection.execute(
            "SELECT 1 FROM metadata_imports WHERE source = ?",
            (source,),
        ).fetchone()
        is not None
    )


def record_import(connection: sqlite3.Connection, source: str) -> None:
    ensure_import_table(connection)
    connection.execute(
        """
        INSERT OR IGNORE INTO metadata_imports(source, imported_at)
        VALUES (?, ?)
        """,
        (source, time.time()),
    )


class BrowserOwnershipStore:
    """SQLite bookkeeping for browser pages owned by Prompta."""

    _LEGACY_IMPORT = "browser-owned-contexts-json"

    def __init__(self, profile: Path) -> None:
        expanded = profile.expanduser().resolve()
        self.path = expanded.with_name(f"{expanded.name}.metadata.sqlite3")
        self.legacy_path = expanded.with_name(f"{expanded.name}.owned-contexts.json")
        self._migrate()
        self._import_legacy_json()

    def _migrate(self) -> None:
        with metadata_connection(self.path) as connection:
            ensure_import_table(connection)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS browser_owned_contexts (
                    kind TEXT NOT NULL,
                    identifier TEXT NOT NULL,
                    PRIMARY KEY(kind, identifier)
                )
                """
            )

    def _import_legacy_json(self) -> None:
        try:
            payload = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, list):
            return

        legacy_targets = {
            value.strip()
            for value in payload
            if isinstance(value, str) and value.strip()
        }
        imported = False
        with metadata_connection(self.path) as connection:
            if not import_recorded(connection, self._LEGACY_IMPORT):
                connection.executemany(
                    """
                    INSERT OR IGNORE INTO browser_owned_contexts(kind, identifier)
                    VALUES ('legacy_target', ?)
                    """,
                    [(target,) for target in sorted(legacy_targets)],
                )
                record_import(connection, self._LEGACY_IMPORT)
            imported = import_recorded(connection, self._LEGACY_IMPORT)
        if imported:
            try:
                self.legacy_path.unlink(missing_ok=True)
            except OSError:
                pass

    def legacy_targets(self) -> set[str]:
        with metadata_connection(self.path) as connection:
            rows = connection.execute(
                """
                SELECT identifier
                FROM browser_owned_contexts
                WHERE kind = 'legacy_target'
                """
            ).fetchall()
        return {str(row["identifier"]) for row in rows}

    def replace_legacy_targets(self, targets: set[str]) -> None:
        with metadata_connection(self.path) as connection:
            connection.execute(
                "DELETE FROM browser_owned_contexts WHERE kind = 'legacy_target'"
            )
            connection.executemany(
                """
                INSERT INTO browser_owned_contexts(kind, identifier)
                VALUES ('legacy_target', ?)
                """,
                [(target,) for target in sorted(targets)],
            )

    def remember_marker(self, marker: str) -> None:
        if not marker:
            return
        with metadata_connection(self.path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO browser_owned_contexts(kind, identifier)
                VALUES ('window_marker', ?)
                """,
                (marker,),
            )

    def forget_marker(self, marker: str) -> None:
        if not marker:
            return
        with metadata_connection(self.path) as connection:
            connection.execute(
                """
                DELETE FROM browser_owned_contexts
                WHERE kind = 'window_marker' AND identifier = ?
                """,
                (marker,),
            )

    def replace_markers(self, markers: set[str]) -> None:
        with metadata_connection(self.path) as connection:
            connection.execute(
                "DELETE FROM browser_owned_contexts WHERE kind = 'window_marker'"
            )
            connection.executemany(
                """
                INSERT INTO browser_owned_contexts(kind, identifier)
                VALUES ('window_marker', ?)
                """,
                [(marker,) for marker in sorted(markers)],
            )

    def markers(self) -> set[str]:
        with metadata_connection(self.path) as connection:
            rows = connection.execute(
                """
                SELECT identifier
                FROM browser_owned_contexts
                WHERE kind = 'window_marker'
                """
            ).fetchall()
        return {str(row["identifier"]) for row in rows}
