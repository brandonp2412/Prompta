from __future__ import annotations

import json
import os
import socket
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from .persistence import connect_sqlite

SERVICE_STALE_AFTER_SECONDS = {
    "ui": 20.0,
    "scheduler": 20.0,
    "delivery_worker": 20.0,
    "conversation_worker": 120.0,
    "browser": 30.0,
}


class ServiceHealthStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS service_health (
                    service TEXT PRIMARY KEY,
                    heartbeat_at REAL NOT NULL DEFAULT 0,
                    activity TEXT NOT NULL DEFAULT '',
                    activity_started_at REAL NOT NULL DEFAULT 0
                )
                """
            )

    def beat(self, service: str, *, now: float | None = None) -> bool:
        at = time.time() if now is None else float(now)
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO service_health(service, heartbeat_at)
                    VALUES (?, ?)
                    ON CONFLICT(service) DO UPDATE SET heartbeat_at = excluded.heartbeat_at
                    """,
                    (service, at),
                )
            return True
        except (OSError, sqlite3.DatabaseError):
            return False

    def begin_activity(
        self,
        service: str,
        activity: str,
        *,
        now: float | None = None,
    ) -> bool:
        at = time.time() if now is None else float(now)
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO service_health(
                        service,
                        heartbeat_at,
                        activity,
                        activity_started_at
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(service) DO UPDATE SET
                        heartbeat_at = excluded.heartbeat_at,
                        activity = excluded.activity,
                        activity_started_at = excluded.activity_started_at
                    """,
                    (service, at, activity, at),
                )
            return True
        except (OSError, sqlite3.DatabaseError):
            return False

    def end_activity(
        self,
        service: str,
        activity: str,
        *,
        now: float | None = None,
    ) -> bool:
        at = time.time() if now is None else float(now)
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO service_health(service, heartbeat_at)
                    VALUES (?, ?)
                    ON CONFLICT(service) DO UPDATE SET
                        heartbeat_at = excluded.heartbeat_at,
                        activity = CASE
                            WHEN service_health.activity = ? THEN ''
                            ELSE service_health.activity
                        END,
                        activity_started_at = CASE
                            WHEN service_health.activity = ? THEN 0
                            ELSE service_health.activity_started_at
                        END
                    """,
                    (service, at, activity, activity),
                )
            return True
        except (OSError, sqlite3.DatabaseError):
            return False

    def snapshot(self, *, now: float | None = None) -> dict[str, dict[str, Any]]:
        current = time.time() if now is None else float(now)
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT service, heartbeat_at, activity, activity_started_at FROM service_health"
                ).fetchall()
        except (OSError, sqlite3.DatabaseError):
            rows = []

        stored = {str(row["service"]): row for row in rows}
        services: dict[str, dict[str, Any]] = {}
        for service, stale_after in SERVICE_STALE_AFTER_SECONDS.items():
            row = stored.get(service)
            heartbeat_at = float(row["heartbeat_at"] or 0.0) if row is not None else 0.0
            activity = str(row["activity"] or "") if row is not None else ""
            activity_started_at = (
                float(row["activity_started_at"] or 0.0) if row is not None else 0.0
            )
            heartbeat_age = max(0.0, current - heartbeat_at) if heartbeat_at > 0 else None
            activity_age = (
                max(0.0, current - activity_started_at) if activity_started_at > 0 else None
            )
            services[service] = {
                "heartbeat_at": heartbeat_at,
                "heartbeat_age_seconds": heartbeat_age,
                "stale_after_seconds": stale_after,
                "stale": heartbeat_age is None or heartbeat_age > stale_after,
                "activity": activity,
                "activity_started_at": activity_started_at,
                "activity_age_seconds": activity_age,
            }
        return services


def systemd_notify(message: str) -> bool:
    address = os.environ.get("NOTIFY_SOCKET", "")
    if not address:
        return False
    if address.startswith("@"):
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notify_socket:
            notify_socket.connect(address)
            notify_socket.sendall(message.encode())
        return True
    except OSError:
        return False


def notify_watchdog() -> bool:
    return systemd_notify("WATCHDOG=1")


def browser_page_count(
    debugger_address: str = "127.0.0.1:9222",
    *,
    timeout_seconds: float = 0.75,
) -> tuple[bool, int | None]:
    try:
        with urlopen(
            f"http://{debugger_address}/json/list",
            timeout=max(0.05, timeout_seconds),
        ) as response:
            payload = json.load(response)
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False, None

    if not isinstance(payload, list):
        return False, None
    pages = sum(1 for item in payload if isinstance(item, dict) and item.get("type") == "page")
    return True, pages
