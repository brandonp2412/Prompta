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
    failure_state_updates,
    initial_due_at,
    initial_jitter_window,
    recurring_delay,
    recurring_jitter_cap,
)
from .scheduler_policy import (
    send_gap_remaining as calculate_send_gap_remaining,
)
from .strict_types import string_object_dict

logger = logging.getLogger(__name__)


_SEND_GAP_SECONDS = 10.0


class SchedulerRuntime:
    def __init__(self, state_path: Path, jobs_file: Path) -> None:
        self.state_path = state_path
        self.jobs_file = jobs_file
        self.backoffs: dict[str, RateLimitBackoff] = {}
        self.global_backoff = RateLimitBackoff()
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
        self, table: Table, conditions: Sequence[ColumnElement[bool]] = ()
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

    def set_all_jobs_paused(self, paused: bool) -> int:
        names = list(load_jobs(self.jobs_file))
        for name in names:
            self.update_job_state(name, {"paused": paused})
        return len(names)

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

    def scheduler_state(self) -> dict[str, object]:
        return self._read_state(
            scheduler_state,
            (scheduler_state.c.scope == "scheduler", scheduler_state.c.name == ""),
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

    def account_state(self) -> dict[str, object]:
        return self._read_state(account_state)

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

    def _durable_global_backoff(self) -> RateLimitBackoff:
        backoff = RateLimitBackoff()
        snapshot = string_object_dict(self.account_state().get("rate_limit_backoff"))
        if snapshot is not None:
            backoff.restore(snapshot)
        return backoff

    def global_backoff_remaining(self) -> float:
        backoff = self._durable_global_backoff()
        remaining = backoff.remaining()
        if remaining <= 0:
            state = self.account_state()
            if state.get("rate_limit_reason"):
                self.update_account_state({"rate_limit_reason": ""})
        return remaining

    def global_backoff_status(self) -> tuple[float, int]:
        backoff = self._durable_global_backoff()
        return backoff.remaining(), backoff.attempts

    def clear_global_rate_limit(self) -> None:
        self.global_backoff.reset()
        snapshot = self.global_backoff.snapshot()
        self.update_account_state(
            {
                "rate_limit_backoff": snapshot,
                "rate_limit_reason": "",
                "rate_limit_updated_at": time.time(),
            }
        )
        self.update_scheduler_state({"rate_limit_backoff": snapshot})

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
        backoff = RateLimitBackoff()
        snapshot = string_object_dict(state.get("rate_limit_backoff"))
        if snapshot is not None:
            backoff.restore(snapshot)
        remaining = backoff.remaining()
        if remaining > 0:
            reason = str(state.get("rate_limit_reason") or "ChatGPT account throttling is active")
            return {
                "blocked": True,
                "kind": "rate_limit",
                "reason": reason,
                "retry_after_seconds": max(1, int(remaining + 0.999)),
                "retry_at_epoch": time.time() + remaining,
            }
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

    def restore_backoffs(self) -> None:
        state = self.load_state()
        scheduler = state.get("scheduler")
        if isinstance(scheduler, dict):
            snapshot = string_object_dict(scheduler.get("rate_limit_backoff"))
            if snapshot is not None:
                self.global_backoff.restore(snapshot)
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

    def persist_backoff(self, name: str, backoff: RateLimitBackoff) -> None:
        self.update_job_state(name, {"rate_limit_backoff": backoff.snapshot()})

    def persist_global_backoff(self) -> None:
        snapshot = self.global_backoff.snapshot()
        self.update_account_state({"rate_limit_backoff": snapshot})
        self.update_scheduler_state({"rate_limit_backoff": snapshot})

    def record_global_rate_limit(self, exc: RateLimitError) -> float:
        wall_time = time.time()
        engine = self._connect_state()
        try:
            with engine.begin() as connection:
                value_json = connection.execute(
                    select(account_state.c.value_json).where(
                        account_state.c.key == "rate_limit_backoff"
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
                remaining = backoff.remaining()
                if remaining <= 0:
                    remaining = backoff.record(float(exc.retry_after))
                snapshot = backoff.snapshot(wall_time=wall_time)
                updates = {
                    "rate_limit_backoff": snapshot,
                    "rate_limit_reason": str(exc),
                    "rate_limit_updated_at": wall_time,
                }
                rows = [
                    {"key": key, "value_json": json.dumps(value, ensure_ascii=False)}
                    for key, value in updates.items()
                ]
                self._upsert_state(connection, account_state, rows)
        finally:
            engine.dispose()
        self.global_backoff.restore(snapshot)
        self.update_scheduler_state({"rate_limit_backoff": snapshot})
        return remaining

    def send_gap_remaining(self, now: float) -> float:
        return calculate_send_gap_remaining(
            last_attempt_at=self.scheduler_state().get("last_attempt_at"),
            gap_seconds=_SEND_GAP_SECONDS,
            now=now,
        )

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

    def mark_failure(
        self,
        name: str,
        message: str,
        *,
        retry_until: float | None = None,
        now: float | None = None,
    ) -> None:
        self.update_job_state(
            name,
            failure_state_updates(
                message,
                status_at=time.time() if now is None else now,
                retry_until=retry_until,
            ),
        )

    def read_jobs(self) -> dict[str, PromptJob]:
        return load_jobs(self.jobs_file)

    def due_in(self, job: PromptJob, now: float | None = None) -> float:
        current = time.time() if now is None else now
        return calculate_due_in(job, self.job_state(job.name), now=current)
