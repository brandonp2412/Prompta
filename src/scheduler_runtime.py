from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from sqlalchemy import Table, delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.elements import ColumnElement

from .jobs import PromptJob, load_jobs
from .persistence import account_state, create_database, scheduler_state
from .rate_limit import RateLimitBackoff, RateLimitError
from .scheduler_policy import (
    due_in as calculate_due_in,
)
from .scheduler_policy import (
    failure_retry_remaining as calculate_failure_retry_remaining,
)
from .scheduler_policy import (
    initial_due_at,
    initial_jitter_window,
    recurring_delay,
    recurring_jitter_cap,
)
from .strict_types import string_object_dict

logger = logging.getLogger(__name__)


class SchedulerRuntime:
    def __init__(self, state_path: Path, jobs_file: Path) -> None:
        self.state_path = state_path
        self.jobs_file = jobs_file
        self.backoffs: dict[str, RateLimitBackoff] = {}
        self.read_backoff = RateLimitBackoff()
        self.failure_retry_until: dict[str, float] = {}
        self.restore_backoffs()

    def _connect_state(self) -> Engine:
        return create_database(self.state_path)

    @staticmethod
    def _upsert_state(connection: Connection, table: Table, rows: list[dict[str, str]]) -> None:
        if not rows:
            return
        statement = insert(table).values(rows)
        if table is scheduler_state:
            statement = statement.on_conflict_do_update(
                index_elements=[
                    scheduler_state.c.scope,
                    scheduler_state.c.name,
                    scheduler_state.c.key,
                ],
                set_={"value_json": statement.excluded.value_json},
            )
        else:
            statement = statement.on_conflict_do_update(
                index_elements=[account_state.c.key],
                set_={"value_json": statement.excluded.value_json},
            )
        connection.execute(statement)

    @staticmethod
    def _state_rows(scope: str, name: str, updates: Mapping[str, object]) -> list[dict[str, str]]:
        return [
            {
                "scope": scope,
                "name": name,
                "key": str(key),
                "value_json": json.dumps(value, ensure_ascii=False),
            }
            for key, value in updates.items()
        ]

    def load_state(self) -> dict[str, object]:
        engine = self._connect_state()
        try:
            with engine.connect() as connection:
                rows = connection.execute(select(scheduler_state)).mappings().all()
        except (OSError, SQLAlchemyError):
            logger.warning("Could not read Prompta scheduler state", exc_info=True)
            return {}
        finally:
            engine.dispose()
        scheduler: dict[str, object] = {}
        jobs: dict[str, dict[str, object]] = {}
        for row in rows:
            try:
                value: object = json.loads(str(row["value_json"]))
            except (TypeError, json.JSONDecodeError):
                continue
            if row["scope"] == "scheduler":
                scheduler[str(row["key"])] = value
            elif row["scope"] == "job":
                jobs.setdefault(str(row["name"]), {})[str(row["key"])] = value
        result: dict[str, object] = {}
        if scheduler:
            result["scheduler"] = scheduler
        if jobs:
            result["jobs"] = jobs
        return result

    def write_state(self, state: dict[str, object]) -> None:
        rows: list[dict[str, str]] = []
        raw_scheduler = state.get("scheduler")
        if isinstance(raw_scheduler, dict):
            scheduler_updates = {str(key): value for key, value in raw_scheduler.items()}
            rows.extend(self._state_rows("scheduler", "", scheduler_updates))
        raw_jobs = state.get("jobs")
        if isinstance(raw_jobs, dict):
            for name, values in raw_jobs.items():
                if isinstance(values, dict):
                    job_updates = {str(key): value for key, value in values.items()}
                    rows.extend(self._state_rows("job", str(name), job_updates))
        engine = self._connect_state()
        try:
            with engine.begin() as connection:
                connection.execute(delete(scheduler_state))
                self._upsert_state(connection, scheduler_state, rows)
        finally:
            engine.dispose()

    def _read_state(
        self,
        table: Table,
        conditions: Sequence[ColumnElement[bool]] = (),
        *,
        strict: bool = False,
    ) -> dict[str, object]:
        engine = self._connect_state()
        try:
            with engine.connect() as connection:
                rows = (
                    connection.execute(select(table.c.key, table.c.value_json).where(*conditions))
                    .mappings()
                    .all()
                )
        except (OSError, SQLAlchemyError):
            if strict:
                raise
            return {}
        finally:
            engine.dispose()
        values: dict[str, object] = {}
        for row in rows:
            try:
                values[str(row["key"])] = json.loads(str(row["value_json"]))
            except (TypeError, json.JSONDecodeError):
                continue
        return values

    def job_state(self, name: str) -> dict[str, object]:
        return self._read_state(
            scheduler_state,
            (scheduler_state.c.scope == "job", scheduler_state.c.name == name),
        )

    def update_job_state(self, name: str, updates: dict[str, object]) -> None:
        if not updates:
            return
        engine = self._connect_state()
        try:
            with engine.begin() as connection:
                self._upsert_state(
                    connection, scheduler_state, self._state_rows("job", name, updates)
                )
        finally:
            engine.dispose()

    def set_job_paused(self, name: str, paused: bool) -> bool:
        if name not in load_jobs(self.jobs_file):
            return False
        self.update_job_state(name, {"paused": paused})
        return True

    def set_jobs_paused(self, names: Sequence[str], paused: bool) -> int:
        unique_names = list(dict.fromkeys(names))
        if not unique_names:
            return 0
        existing = load_jobs(self.jobs_file)
        unknown = [name for name in unique_names if name not in existing]
        if unknown:
            raise ValueError("Unknown job: " + unknown[0])
        rows: list[dict[str, str]] = []
        for name in unique_names:
            rows.extend(self._state_rows("job", name, {"paused": paused}))
        engine = self._connect_state()
        try:
            with engine.begin() as connection:
                self._upsert_state(connection, scheduler_state, rows)
        finally:
            engine.dispose()
        return len(unique_names)

    def set_all_jobs_paused(self, paused: bool) -> int:
        return self.set_jobs_paused(list(load_jobs(self.jobs_file)), paused)

    def clear_job_state(self, name: str) -> None:
        engine = self._connect_state()
        try:
            with engine.begin() as connection:
                connection.execute(
                    delete(scheduler_state).where(
                        scheduler_state.c.scope == "job", scheduler_state.c.name == name
                    )
                )
        finally:
            engine.dispose()

    def clear_all_job_state(self) -> None:
        engine = self._connect_state()
        try:
            with engine.begin() as connection:
                connection.execute(delete(scheduler_state).where(scheduler_state.c.scope == "job"))
        finally:
            engine.dispose()

    def scheduler_state(self, *, strict: bool = False) -> dict[str, object]:
        return self._read_state(
            scheduler_state,
            (scheduler_state.c.scope == "scheduler", scheduler_state.c.name == ""),
            strict=strict,
        )

    def update_scheduler_state(self, updates: dict[str, object]) -> None:
        if not updates:
            return
        engine = self._connect_state()
        try:
            with engine.begin() as connection:
                self._upsert_state(
                    connection, scheduler_state, self._state_rows("scheduler", "", updates)
                )
        finally:
            engine.dispose()

    def account_state(self, *, strict: bool = False) -> dict[str, object]:
        return self._read_state(account_state, strict=strict)

    def update_account_state(self, updates: dict[str, object]) -> None:
        if not updates:
            return
        rows = [
            {"key": str(key), "value_json": json.dumps(value, ensure_ascii=False)}
            for key, value in updates.items()
        ]
        engine = self._connect_state()
        try:
            with engine.begin() as connection:
                self._upsert_state(connection, account_state, rows)
        finally:
            engine.dispose()

    def _durable_read_backoff(self) -> RateLimitBackoff:
        backoff = RateLimitBackoff()
        snapshot = string_object_dict(
            self.account_state(strict=True).get("read_rate_limit_backoff")
        )
        if snapshot is not None:
            backoff.restore(snapshot)
        return backoff

    def read_backoff_remaining(self) -> float:
        backoff = self._durable_read_backoff()
        remaining = backoff.remaining()
        if remaining <= 0:
            state = self.account_state()
            if state.get("read_rate_limit_reason"):
                self.update_account_state({"read_rate_limit_reason": ""})
        return remaining

    def read_backoff_status(self) -> tuple[float, int]:
        backoff = self._durable_read_backoff()
        return backoff.remaining(), backoff.attempts

    def record_read_success(self) -> None:
        """Clear stale read throttling only after its minimum cooldown elapsed."""
        remaining, attempts = self.read_backoff_status()
        if attempts and remaining <= 0:
            self.clear_read_rate_limit()

    def clear_read_rate_limit(self) -> None:
        self.read_backoff.reset()
        snapshot = self.read_backoff.snapshot()
        self.update_account_state(
            {
                "read_rate_limit_backoff": snapshot,
                "read_rate_limit_reason": "",
                "read_rate_limit_updated_at": time.time(),
            }
        )
        self.update_scheduler_state({"read_rate_limit_backoff": snapshot})

    def set_resource_admission(self, allowed: bool, reason: str = "") -> None:
        self.update_account_state(
            {
                "resource_blocked": not allowed,
                "resource_reason": "" if allowed else str(reason),
                "resource_updated_at": time.time(),
            }
        )

    def account_admission_status(self) -> dict[str, object]:
        state = self.account_state()
        if bool(state.get("resource_blocked")):
            return {
                "blocked": True,
                "kind": "resource_pressure",
                "reason": str(state.get("resource_reason") or "Host resource pressure"),
                "retry_after_seconds": 0,
                "retry_at_epoch": 0.0,
            }
        return {
            "blocked": False,
            "kind": "",
            "reason": "",
            "retry_after_seconds": 0,
            "retry_at_epoch": 0.0,
        }

    def read_admission_status(self) -> dict[str, object]:
        remaining, attempts = self.read_backoff_status()
        state = self.account_state()
        return {
            "blocked": remaining > 0,
            "kind": "rate_limit" if remaining > 0 else "",
            "reason": str(state.get("read_rate_limit_reason") or "") if remaining > 0 else "",
            "retry_after_seconds": max(1, int(remaining + 0.999)) if remaining > 0 else 0,
            "retry_at_epoch": time.time() + remaining if remaining > 0 else 0.0,
            "attempts": attempts,
        }

    def restore_backoffs(self) -> None:
        state = self.load_state()
        scheduler = state.get("scheduler")
        if isinstance(scheduler, dict):
            snapshot = string_object_dict(scheduler.get("read_rate_limit_backoff"))
            if snapshot is not None:
                self.read_backoff.restore(snapshot)
        jobs = state.get("jobs")
        if not isinstance(jobs, dict):
            return
        for name, job_state in jobs.items():
            if not isinstance(job_state, dict):
                continue
            snapshot = string_object_dict(job_state.get("rate_limit_backoff"))
            if snapshot is None:
                continue
            backoff = RateLimitBackoff()
            backoff.restore(snapshot)
            if backoff.attempts:
                self.backoffs[str(name)] = backoff

    def persist_read_backoff(self) -> None:
        snapshot = self.read_backoff.snapshot()
        self.update_account_state({"read_rate_limit_backoff": snapshot})
        self.update_scheduler_state({"read_rate_limit_backoff": snapshot})

    def record_read_rate_limit(self, exc: RateLimitError) -> float:
        wall_time = time.time()
        engine = self._connect_state()
        try:
            with engine.begin() as connection:
                value_json = connection.execute(
                    select(account_state.c.value_json).where(
                        account_state.c.key == "read_rate_limit_backoff"
                    )
                ).scalar_one_or_none()
                backoff = RateLimitBackoff()
                if value_json is not None:
                    try:
                        decoded: object = json.loads(str(value_json))
                    except (TypeError, json.JSONDecodeError):
                        decoded = {}
                    snapshot = string_object_dict(decoded) or {}
                    backoff.restore(snapshot, wall_time=wall_time)
                remaining = backoff.record(float(exc.retry_after))
                snapshot = backoff.snapshot(wall_time=wall_time)
                updates = {
                    "read_rate_limit_backoff": snapshot,
                    "read_rate_limit_reason": str(exc),
                    "read_rate_limit_updated_at": wall_time,
                }
                rows = [
                    {"key": key, "value_json": json.dumps(value, ensure_ascii=False)}
                    for key, value in updates.items()
                ]
                self._upsert_state(connection, account_state, rows)
        finally:
            engine.dispose()
        self.read_backoff.restore(snapshot)
        self.update_scheduler_state({"read_rate_limit_backoff": snapshot})
        return remaining

    def ensure_initial_schedules(self, jobs: list[PromptJob], now: float) -> None:
        for job in jobs:
            state = self.job_state(job.name)
            due_at = initial_due_at(job, state, now=now)
            if due_at is None:
                continue
            if job.run_at_epoch is None and job.daily_at is None:
                jitter_window = initial_jitter_window(job)
                jitter_seconds = random.uniform(0.0, jitter_window) if jitter_window > 0 else 0.0
                due_at = initial_due_at(
                    job,
                    state,
                    now=now,
                    jitter_seconds=jitter_seconds,
                )
                assert due_at is not None
            self.update_job_state(job.name, {"initial_due_at_epoch": due_at})
            if job.run_at_epoch is not None:
                logger.info(
                    "Prompta job=%s one-time send scheduled for %s",
                    job.name,
                    datetime.fromtimestamp(due_at).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
                )
            elif job.daily_at is not None:
                logger.info(
                    "Prompta job=%s initial daily send scheduled for %s",
                    job.name,
                    datetime.fromtimestamp(due_at).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
                )
            else:
                logger.info("Prompta job=%s initial start delayed by %.0fs", job.name, due_at - now)

    @staticmethod
    def next_delay(job: PromptJob) -> float:
        jitter_cap = recurring_jitter_cap(job)
        jitter_seconds = random.uniform(0.0, jitter_cap) if jitter_cap > 0 else 0.0
        return recurring_delay(job, jitter_seconds=jitter_seconds)

    def failure_retry_remaining(self, name: str, now: float) -> float:
        state = self.job_state(name)
        return calculate_failure_retry_remaining(
            persisted_retry_until=state.get("failure_retry_until_epoch"),
            in_memory_retry_until=self.failure_retry_until.get(name, 0.0),
            now=now,
        )

    def read_jobs(self) -> dict[str, PromptJob]:
        return load_jobs(self.jobs_file)

    def due_in(self, job: PromptJob, now: float | None = None) -> float:
        current = time.time() if now is None else now
        return calculate_due_in(job, self.job_state(job.name), now=current)
