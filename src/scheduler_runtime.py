from __future__ import annotations

import json
import logging
import random
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .jobs import PromptJob, load_jobs
from .persistence import connect_sqlite
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


    def _connect_state(self) -> sqlite3.Connection:
        connection = connect_sqlite(self.state_path.expanduser())
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduler_state (
                scope TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                PRIMARY KEY (scope, name, key)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS account_state (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO account_state(key, value_json)
            SELECT 'rate_limit_backoff', value_json
            FROM scheduler_state
            WHERE scope = 'scheduler' AND name = '' AND key = 'rate_limit_backoff'
            ON CONFLICT(key) DO NOTHING
            """
        )
        connection.commit()
        return connection

    @staticmethod
    def _write_state_to_connection(
        connection: sqlite3.Connection,
        state: dict[str, Any],
    ) -> None:
        rows: list[tuple[str, str, str, str]] = []
        scheduler = state.get("scheduler")
        if isinstance(scheduler, dict):
            rows.extend(
                ("scheduler", "", str(key), json.dumps(value, ensure_ascii=False))
                for key, value in scheduler.items()
            )
        jobs = state.get("jobs")
        if isinstance(jobs, dict):
            for name, raw_state in jobs.items():
                if not isinstance(raw_state, dict):
                    continue
                rows.extend(
                    ("job", str(name), str(key), json.dumps(value, ensure_ascii=False))
                    for key, value in raw_state.items()
                )
        if rows:
            connection.executemany(
                """
                INSERT INTO scheduler_state(scope, name, key, value_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope, name, key) DO UPDATE SET
                    value_json = excluded.value_json
                """,
                rows,
            )
        connection.commit()

    def load_state(self) -> dict[str, Any]:
        try:
            with self._connect_state() as connection:
                rows = connection.execute(
                    "SELECT scope, name, key, value_json FROM scheduler_state"
                ).fetchall()
        except (OSError, sqlite3.DatabaseError):
            logger.warning("Could not read Prompta scheduler state", exc_info=True)
            return {}

        state: dict[str, Any] = {}
        for row in rows:
            try:
                value = json.loads(str(row["value_json"]))
            except (TypeError, json.JSONDecodeError):
                continue
            scope = str(row["scope"])
            key = str(row["key"])
            if scope == "scheduler":
                state.setdefault("scheduler", {})[key] = value
            elif scope == "job":
                state.setdefault("jobs", {}).setdefault(str(row["name"]), {})[key] = value
        return state

    def write_state(self, state: dict[str, Any]) -> None:
        with self._connect_state() as connection:
            connection.execute("DELETE FROM scheduler_state")
            self._write_state_to_connection(connection, state)

    def job_state(self, name: str) -> dict[str, Any]:
        try:
            with self._connect_state() as connection:
                rows = connection.execute(
                    """
                    SELECT key, value_json
                    FROM scheduler_state
                    WHERE scope = 'job' AND name = ?
                    """,
                    (name,),
                ).fetchall()
        except (OSError, sqlite3.DatabaseError):
            return {}
        result: dict[str, Any] = {}
        for row in rows:
            try:
                result[str(row["key"])] = json.loads(str(row["value_json"]))
            except (TypeError, json.JSONDecodeError):
                continue
        return result

    def update_job_state(self, name: str, updates: dict[str, Any]) -> None:
        if not updates:
            return
        with self._connect_state() as connection:
            connection.executemany(
                """
                INSERT INTO scheduler_state(scope, name, key, value_json)
                VALUES ('job', ?, ?, ?)
                ON CONFLICT(scope, name, key) DO UPDATE SET
                    value_json = excluded.value_json
                """,
                [
                    (name, str(key), json.dumps(value, ensure_ascii=False))
                    for key, value in updates.items()
                ],
            )

    def set_job_paused(self, name: str, paused: bool) -> bool:
        if name not in load_jobs(self.jobs_file):
            return False
        self.update_job_state(name, {"paused": paused})
        return True

    def set_all_jobs_paused(self, paused: bool) -> int:
        names = list(load_jobs(self.jobs_file))
        if not names:
            return 0
        value_json = json.dumps(paused, ensure_ascii=False)
        with self._connect_state() as connection:
            connection.executemany(
                """
                INSERT INTO scheduler_state(scope, name, key, value_json)
                VALUES ('job', ?, 'paused', ?)
                ON CONFLICT(scope, name, key) DO UPDATE SET
                    value_json = excluded.value_json
                """,
                [(name, value_json) for name in names],
            )
        return len(names)

    def clear_job_state(self, name: str) -> None:
        with self._connect_state() as connection:
            connection.execute(
                "DELETE FROM scheduler_state WHERE scope = 'job' AND name = ?",
                (name,),
            )

    def clear_all_job_state(self) -> None:
        with self._connect_state() as connection:
            connection.execute("DELETE FROM scheduler_state WHERE scope = 'job'")

    def scheduler_state(self) -> dict[str, Any]:
        try:
            with self._connect_state() as connection:
                rows = connection.execute(
                    """
                    SELECT key, value_json
                    FROM scheduler_state
                    WHERE scope = 'scheduler' AND name = ''
                    """
                ).fetchall()
        except (OSError, sqlite3.DatabaseError):
            return {}
        result: dict[str, Any] = {}
        for row in rows:
            try:
                result[str(row["key"])] = json.loads(str(row["value_json"]))
            except (TypeError, json.JSONDecodeError):
                continue
        return result

    def update_scheduler_state(self, updates: dict[str, Any]) -> None:
        if not updates:
            return
        with self._connect_state() as connection:
            connection.executemany(
                """
                INSERT INTO scheduler_state(scope, name, key, value_json)
                VALUES ('scheduler', '', ?, ?)
                ON CONFLICT(scope, name, key) DO UPDATE SET
                    value_json = excluded.value_json
                """,
                [
                    (str(key), json.dumps(value, ensure_ascii=False))
                    for key, value in updates.items()
                ],
            )

    def account_state(self) -> dict[str, Any]:
        try:
            with self._connect_state() as connection:
                rows = connection.execute("SELECT key, value_json FROM account_state").fetchall()
        except (OSError, sqlite3.DatabaseError):
            return {}
        result: dict[str, Any] = {}
        for row in rows:
            try:
                result[str(row["key"])] = json.loads(str(row["value_json"]))
            except (TypeError, json.JSONDecodeError):
                continue
        return result

    def update_account_state(self, updates: dict[str, Any]) -> None:
        if not updates:
            return
        with self._connect_state() as connection:
            connection.executemany(
                """
                INSERT INTO account_state(key, value_json)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
                """,
                [
                    (str(key), json.dumps(value, ensure_ascii=False))
                    for key, value in updates.items()
                ],
            )

    def _durable_global_backoff(self) -> RateLimitBackoff:
        backoff = RateLimitBackoff()
        snapshot = self.account_state().get("rate_limit_backoff")
        if isinstance(snapshot, dict):
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

    def account_admission_status(self) -> dict[str, Any]:
        state = self.account_state()
        backoff = RateLimitBackoff()
        snapshot = state.get("rate_limit_backoff")
        if isinstance(snapshot, dict):
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

    @staticmethod
    def _write_job_updates(
        connection: sqlite3.Connection,
        name: str,
        updates: dict[str, Any],
    ) -> None:
        if not updates:
            return
        connection.executemany(
            """
            INSERT INTO scheduler_state(scope, name, key, value_json)
            VALUES ('job', ?, ?, ?)
            ON CONFLICT(scope, name, key) DO UPDATE SET
                value_json = excluded.value_json
            """,
            [
                (name, str(key), json.dumps(value, ensure_ascii=False))
                for key, value in updates.items()
            ],
        )


    def restore_backoffs(self) -> None:
        state = self.load_state()
        scheduler = state.get("scheduler")
        if isinstance(scheduler, dict):
            snapshot = scheduler.get("rate_limit_backoff")
            if isinstance(snapshot, dict):
                self.global_backoff.restore(snapshot)
        jobs = state.get("jobs")
        if not isinstance(jobs, dict):
            return
        for name, job_state in jobs.items():
            if not isinstance(job_state, dict):
                continue
            snapshot = job_state.get("rate_limit_backoff")
            if not isinstance(snapshot, dict):
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
        with self._connect_state() as connection:
            connection.commit()
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT value_json FROM account_state WHERE key = 'rate_limit_backoff'"
            ).fetchone()
            backoff = RateLimitBackoff()
            if row is not None:
                try:
                    snapshot = json.loads(str(row["value_json"]))
                except (TypeError, json.JSONDecodeError):
                    snapshot = {}
                if isinstance(snapshot, dict):
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
            connection.executemany(
                """
                INSERT INTO account_state(key, value_json)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
                """,
                [(key, json.dumps(value, ensure_ascii=False)) for key, value in updates.items()],
            )
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
