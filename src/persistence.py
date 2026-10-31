from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine

from .schema_migrations import upgrade_database

STATE_DIR = Path.home() / ".local" / "state" / "prompta"
DEFAULT_RUNTIME_PATH = STATE_DIR / "runtime.sqlite3"
metadata = MetaData()
scheduled_jobs = Table(
    "scheduled_jobs",
    metadata,
    Column("name", String, primary_key=True),
    Column("prompt", Text, nullable=False),
    Column("interval_seconds", Float, nullable=False),
    Column("daily_at", String),
    Column("exact_interval", Boolean, nullable=False, default=False),
    Column("run_at_epoch", Float),
    Column("pin_chat", Boolean, nullable=False, default=False),
    Column("source_revision", String, nullable=False, default=""),
    Column("mutex_group", String, nullable=False, default=""),
    Column("images_json", Text, nullable=False, default="[]"),
)
scheduler_state = Table(
    "scheduler_state",
    metadata,
    Column("scope", String, primary_key=True),
    Column("name", String, primary_key=True, default=""),
    Column("key", String, primary_key=True),
    Column("value_json", Text, nullable=False),
)
account_state = Table(
    "account_state",
    metadata,
    Column("key", String, primary_key=True),
    Column("value_json", Text, nullable=False),
)
job_deliveries = Table(
    "job_deliveries",
    metadata,
    Column("sequence", Integer, primary_key=True, autoincrement=True),
    Column("send_id", String, nullable=False, unique=True),
    Column("message", Text, nullable=False),
    Column("images_json", Text, nullable=False, default="[]"),
    Column("pin_chat", Boolean, nullable=False, default=False),
    Column("client_id", String, nullable=False, default=""),
    Column("status", String, nullable=False, default="queued"),
    Column("error", Text, nullable=False, default=""),
    Column("last_error", Text, nullable=False, default=""),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
    Column("retry_at", Float, nullable=False, default=0),
    Column("retry_attempt", Integer, nullable=False, default=0),
    Column("finished_at", Float, nullable=False, default=0),
    Column("lease_owner", String, nullable=False, default=""),
    Column("lease_acquired_at", Float, nullable=False, default=0),
    Column("lease_expires_at", Float, nullable=False, default=0),
)
Index(
    "job_deliveries_client_id",
    job_deliveries.c.client_id,
    unique=True,
    sqlite_where=job_deliveries.c.client_id != "",
)
Index(
    "job_deliveries_claimable",
    job_deliveries.c.status,
    job_deliveries.c.retry_at,
    job_deliveries.c.lease_expires_at,
    job_deliveries.c.sequence,
)
service_health = Table(
    "service_health",
    metadata,
    Column("service", String, primary_key=True),
    Column("heartbeat_at", Float, nullable=False, default=0),
    Column("activity", String, nullable=False, default=""),
    Column("activity_started_at", Float, nullable=False, default=0),
)


def create_database(path: Path, *, timeout: float = 5.0) -> Engine:
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.parent.chmod(0o700)
    descriptor = os.open(target, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(descriptor)
    target.chmod(0o600)
    return _database_engine(str(target.resolve()), timeout)


@lru_cache(maxsize=32)
def _database_engine(path: str, timeout: float) -> Engine:
    engine = create_engine(
        f"sqlite:///{path}", connect_args={"timeout": timeout, "check_same_thread": False}
    )
    upgrade_database(engine, "runtime")
    return engine
