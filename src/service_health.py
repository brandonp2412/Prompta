from __future__ import annotations

import json
import os
import socket
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from sqlalchemy import case, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError

from .persistence import create_database, service_health
from .strict_types import float_value

SERVICE_STALE_AFTER_SECONDS = {
    "ui": 20.0,
    "scheduler": 20.0,
    "delivery_worker": 20.0,
    "browser": 30.0,
}


def build_service_health_snapshot(
    rows: Iterable[Mapping[str, object]],
    *,
    now: float,
    stale_after_seconds: Mapping[str, float] = SERVICE_STALE_AFTER_SECONDS,
) -> dict[str, dict[str, object]]:
    stored = {str(row["service"]): row for row in rows}
    services: dict[str, dict[str, object]] = {}
    for service, stale_after in stale_after_seconds.items():
        row = stored.get(service)
        heartbeat_at = float_value(row["heartbeat_at"]) if row is not None else 0.0
        activity = str(row["activity"] or "") if row is not None else ""
        activity_started_at = float_value(row["activity_started_at"]) if row is not None else 0.0
        heartbeat_age = max(0.0, now - heartbeat_at) if heartbeat_at > 0 else None
        activity_age = max(0.0, now - activity_started_at) if activity_started_at > 0 else None
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


class ServiceHealthStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self._initialize()

    def _initialize(self) -> None:
        engine = create_database(self.path)
        engine.dispose()

    def beat(self, service: str, *, now: float | None = None) -> bool:
        at = time.time() if now is None else float(now)
        try:
            engine = create_database(self.path)
            statement = insert(service_health).values(service=service, heartbeat_at=at)
            with engine.begin() as connection:
                connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=[service_health.c.service],
                        set_={"heartbeat_at": statement.excluded.heartbeat_at},
                    )
                )
            return True
        except (OSError, SQLAlchemyError):
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
            engine = create_database(self.path)
            statement = insert(service_health).values(
                service=service, heartbeat_at=at, activity=activity, activity_started_at=at
            )
            with engine.begin() as connection:
                connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=[service_health.c.service],
                        set_={
                            key: getattr(statement.excluded, key)
                            for key in ("heartbeat_at", "activity", "activity_started_at")
                        },
                    )
                )
            return True
        except (OSError, SQLAlchemyError):
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
            engine = create_database(self.path)
            statement = insert(service_health).values(service=service, heartbeat_at=at)
            with engine.begin() as connection:
                connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=[service_health.c.service],
                        set_={
                            "heartbeat_at": statement.excluded.heartbeat_at,
                            "activity": case(
                                (service_health.c.activity == activity, ""),
                                else_=service_health.c.activity,
                            ),
                            "activity_started_at": case(
                                (service_health.c.activity == activity, 0),
                                else_=service_health.c.activity_started_at,
                            ),
                        },
                    )
                )
            return True
        except (OSError, SQLAlchemyError):
            return False

    def snapshot(self, *, now: float | None = None) -> dict[str, dict[str, object]]:
        current = time.time() if now is None else float(now)
        try:
            engine = create_database(self.path)
            with engine.connect() as connection:
                rows = connection.execute(select(service_health)).mappings().all()
        except (OSError, SQLAlchemyError):
            rows = []

        return build_service_health_snapshot(rows, now=current)


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
