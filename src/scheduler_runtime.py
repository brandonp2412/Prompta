from __future__ import annotations

import json
import logging
import random
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from .jobs import PromptJob, _next_daily_epoch, load_jobs
from .persistence import (
    DEFAULT_RUNTIME_PATH,
    LEGACY_STATE_PATH,
    connect_sqlite,
    is_sqlite_file,
    read_legacy_json,
    remove_legacy_json,
)
from .rate_limit import RateLimitBackoff, RateLimitError

logger = logging.getLogger(__name__)


class DeliveryIntent(TypedDict):
    id: int
    idempotency_key: str
    job_name: str
    prompt: str
    job_prompt_sha256: str
    interval_seconds: float
    daily_at: str | None
    exact_interval: bool
    one_time: bool
    queued_at: float
    attempt_count: int


_MIN_SEND_GAP_SECONDS = 60.0
_INITIAL_DELAY_CAP_SECONDS = 30 * 60.0
_RECURRING_JITTER_FRACTION = 0.20
_RECURRING_JITTER_CAP_SECONDS = 5 * 60.0


class SchedulerRuntime:
    def __init__(self, state_path: Path, jobs_file: Path) -> None:
        self.state_path = state_path
        self.jobs_file = jobs_file
        self.backoffs: dict[str, RateLimitBackoff] = {}
        self.global_backoff = RateLimitBackoff()
        self.failure_retry_until: dict[str, float] = {}
        self.restore_backoffs()

    def _migration_candidates(self) -> list[Path]:
        target = self.state_path.expanduser()
        candidates: list[Path] = []
        if target.exists() and not is_sqlite_file(target):
            candidates.append(target)
        if target == DEFAULT_RUNTIME_PATH and LEGACY_STATE_PATH not in candidates:
            candidates.append(LEGACY_STATE_PATH)
        return candidates

    def _connect_state(self) -> sqlite3.Connection:
        target = self.state_path.expanduser()
        legacy_payloads: list[tuple[Path, object]] = []
        for candidate in self._migration_candidates():
            payload = read_legacy_json(candidate)
            if payload is not None:
                legacy_payloads.append((candidate, payload))

        if target.exists() and not is_sqlite_file(target):
            target.unlink(missing_ok=True)

        connection = connect_sqlite(target)
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
            CREATE TABLE IF NOT EXISTS delivery_intents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT NOT NULL UNIQUE,
                job_name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                job_prompt_sha256 TEXT NOT NULL,
                interval_seconds REAL NOT NULL,
                daily_at TEXT,
                exact_interval INTEGER NOT NULL DEFAULT 0,
                one_time INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'queued',
                queued_at REAL NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_attempt_at REAL NOT NULL DEFAULT 0,
                available_at REAL NOT NULL DEFAULT 0,
                conversation_id TEXT NOT NULL DEFAULT '',
                last_error TEXT NOT NULL DEFAULT '',
                completed_at REAL NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS delivery_intents_pending "
            "ON delivery_intents(status, available_at, id)"
        )
        existing = int(connection.execute("SELECT COUNT(*) FROM scheduler_state").fetchone()[0])
        if existing == 0:
            for _legacy_path, payload in legacy_payloads:
                if not isinstance(payload, dict):
                    continue
                self._write_state_to_connection(connection, payload)
                existing = int(
                    connection.execute("SELECT COUNT(*) FROM scheduler_state").fetchone()[0]
                )
                if existing:
                    logger.info("Migrated Prompta scheduler state into SQLite")
                    break

        for legacy_path, _payload in legacy_payloads:
            remove_legacy_json(legacy_path)
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

    def enqueue_delivery_intent(
        self,
        job: PromptJob,
        *,
        prompt: str,
        job_prompt_sha256: str,
        idempotency_key: str,
        queued_at: float,
    ) -> tuple[int, bool]:
        """Persist one scheduled delivery and its scheduler decision atomically."""
        with self._connect_state() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id FROM delivery_intents WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return int(existing["id"]), False
            cursor = connection.execute(
                """
                INSERT INTO delivery_intents(
                    idempotency_key, job_name, prompt, job_prompt_sha256,
                    interval_seconds, daily_at, exact_interval, one_time, queued_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    idempotency_key,
                    job.name,
                    prompt,
                    job_prompt_sha256,
                    float(job.interval_seconds),
                    job.daily_at,
                    int(job.exact_interval),
                    int(job.run_at_epoch is not None),
                    queued_at,
                ),
            )
            if cursor.lastrowid is None:
                raise sqlite3.DatabaseError("delivery intent insert did not return an id")
            intent_id = int(cursor.lastrowid)
            self._write_job_updates(
                connection,
                job.name,
                {
                    "last_enqueued_at": queued_at,
                    "last_delivery_intent_id": intent_id,
                    "status": "queued",
                    "status_message": "",
                    "status_at": queued_at,
                },
            )
            return intent_id, True

    def has_queued_delivery(self, job_name: str) -> bool:
        with self._connect_state() as connection:
            row = connection.execute(
                "SELECT 1 FROM delivery_intents WHERE job_name = ? AND status = 'queued' LIMIT 1",
                (job_name,),
            ).fetchone()
        return row is not None

    def pending_delivery_intents(self, now: float, *, limit: int = 50) -> list[DeliveryIntent]:
        with self._connect_state() as connection:
            rows = connection.execute(
                """
                SELECT id, idempotency_key, job_name, prompt, job_prompt_sha256,
                       interval_seconds, daily_at, exact_interval, one_time, queued_at, attempt_count
                FROM delivery_intents
                WHERE status = 'queued' AND available_at <= ?
                ORDER BY id
                LIMIT ?
                """,
                (now, max(1, limit)),
            ).fetchall()
        return [
            DeliveryIntent(
                id=int(row["id"]),
                idempotency_key=str(row["idempotency_key"]),
                job_name=str(row["job_name"]),
                prompt=str(row["prompt"]),
                job_prompt_sha256=str(row["job_prompt_sha256"]),
                interval_seconds=float(row["interval_seconds"]),
                daily_at=str(row["daily_at"]) if row["daily_at"] is not None else None,
                exact_interval=bool(row["exact_interval"]),
                one_time=bool(row["one_time"]),
                queued_at=float(row["queued_at"]),
                attempt_count=int(row["attempt_count"]),
            )
            for row in rows
        ]

    def next_delivery_intent(self, now: float) -> DeliveryIntent | None:
        pending = self.pending_delivery_intents(now, limit=1)
        return pending[0] if pending else None

    def mark_delivery_attempt(self, intent_id: int, attempted_at: float) -> None:
        with self._connect_state() as connection:
            connection.execute(
                """
                UPDATE delivery_intents
                SET attempt_count = attempt_count + 1, last_attempt_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (attempted_at, intent_id),
            )

    def defer_delivery(
        self,
        intent_id: int,
        *,
        error: str,
        available_at: float,
    ) -> None:
        with self._connect_state() as connection:
            connection.execute(
                """
                UPDATE delivery_intents
                SET last_error = ?, available_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (error, available_at, intent_id),
            )

    def mark_delivery_uncertain(
        self,
        intent_id: int,
        job_name: str,
        *,
        attempted_at: float,
        error: str,
    ) -> None:
        with self._connect_state() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE delivery_intents
                SET status = 'uncertain', last_error = ?, completed_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (error, attempted_at, intent_id),
            )
            self._write_job_updates(
                connection,
                job_name,
                {
                    "last_uncertain_send_at": attempted_at,
                    "status": "failing",
                    "status_message": error,
                    "status_at": attempted_at,
                },
            )

    def complete_delivery(
        self,
        intent_id: int,
        job_name: str,
        *,
        conversation_id: str,
        sent_at: float,
        job_updates: dict[str, Any],
    ) -> None:
        with self._connect_state() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE delivery_intents
                SET status = 'delivered', conversation_id = ?, completed_at = ?,
                    available_at = 0, last_error = ''
                WHERE id = ? AND status = 'queued'
                """,
                (conversation_id, sent_at, intent_id),
            )
            self._write_job_updates(connection, job_name, job_updates)

    def delivery_intents(self, job_name: str | None = None) -> list[dict[str, Any]]:
        with self._connect_state() as connection:
            if job_name is None:
                rows = connection.execute("SELECT * FROM delivery_intents ORDER BY id").fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM delivery_intents WHERE job_name = ? ORDER BY id",
                    (job_name,),
                ).fetchall()
        return [dict(row) for row in rows]

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
        self.update_scheduler_state({"rate_limit_backoff": self.global_backoff.snapshot()})

    def record_global_rate_limit(self, exc: RateLimitError) -> float:
        remaining = self.global_backoff.remaining()
        if remaining > 0:
            return remaining
        delay = self.global_backoff.record(float(exc.retry_after))
        self.persist_global_backoff()
        return delay

    def send_gap_remaining(self, now: float) -> float:
        try:
            last_attempt_at = float(self.scheduler_state().get("last_attempt_at") or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, last_attempt_at + _MIN_SEND_GAP_SECONDS - now)

    def ensure_initial_schedules(self, jobs: list[PromptJob], now: float) -> None:
        for job in jobs:
            state = self.job_state(job.name)
            if any(
                state.get(key)
                for key in (
                    "last_sent_at",
                    "last_uncertain_send_at",
                    "last_enqueued_at",
                    "initial_due_at_epoch",
                    "next_due_at_epoch",
                )
            ):
                continue
            if job.run_at_epoch is not None:
                due_at = float(job.run_at_epoch)
                self.update_job_state(job.name, {"initial_due_at_epoch": due_at})
                logger.info(
                    "Prompta job=%s one-time send scheduled for %s",
                    job.name,
                    datetime.fromtimestamp(due_at).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
                )
                continue
            if job.daily_at is not None:
                due_at = _next_daily_epoch(job.daily_at, now, include_now=True)
                self.update_job_state(job.name, {"initial_due_at_epoch": due_at})
                logger.info(
                    "Prompta job=%s initial daily send scheduled for %s",
                    job.name,
                    datetime.fromtimestamp(due_at).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
                )
                continue
            window = min(max(0.0, job.interval_seconds), _INITIAL_DELAY_CAP_SECONDS)
            delay = random.uniform(0.0, window) if window > 0 else 0.0
            self.update_job_state(job.name, {"initial_due_at_epoch": now + delay})
            logger.info("Prompta job=%s initial start delayed by %.0fs", job.name, delay)

    @staticmethod
    def next_delay(job: PromptJob) -> float:
        interval = max(0.0, job.interval_seconds)
        if job.exact_interval:
            return interval
        jitter_cap = min(_RECURRING_JITTER_CAP_SECONDS, interval * _RECURRING_JITTER_FRACTION)
        return interval + (random.uniform(0.0, jitter_cap) if jitter_cap > 0 else 0.0)

    def failure_retry_remaining(self, name: str, now: float) -> float:
        state = self.job_state(name)
        try:
            persisted = float(state.get("failure_retry_until_epoch") or 0.0)
        except (TypeError, ValueError):
            persisted = 0.0
        in_memory = self.failure_retry_until.get(name, 0.0)
        return max(0.0, max(persisted, in_memory) - now)

    def mark_failure(self, name: str, message: str, *, retry_until: float | None = None) -> None:
        updates: dict[str, Any] = {
            "status": "failing",
            "status_message": message,
            "status_at": time.time(),
        }
        if retry_until is not None:
            updates["failure_retry_until_epoch"] = retry_until
        self.update_job_state(name, updates)

    def read_jobs(self) -> dict[str, PromptJob]:
        return load_jobs(self.jobs_file)

    def due_in(self, job: PromptJob, now: float | None = None) -> float:
        state = self.job_state(job.name)
        current = time.time() if now is None else now
        try:
            last_sent_at = float(state.get("last_sent_at") or 0.0)
            last_uncertain_send_at = float(state.get("last_uncertain_send_at") or 0.0)
            next_due_at = float(state.get("next_due_at_epoch") or 0.0)
            initial_due_at = float(state.get("initial_due_at_epoch") or 0.0)
        except (TypeError, ValueError):
            return 0.0
        last_attempt_at = max(last_sent_at, last_uncertain_send_at)
        if job.run_at_epoch is not None:
            if last_attempt_at > 0:
                return float("inf")
            due_at = initial_due_at if initial_due_at > 0 else float(job.run_at_epoch)
            return max(0.0, due_at - current)
        if next_due_at > 0 and last_sent_at >= last_uncertain_send_at:
            return max(0.0, next_due_at - current)
        if last_attempt_at > 0:
            if job.daily_at is not None:
                return max(0.0, _next_daily_epoch(job.daily_at, last_attempt_at) - current)
            return max(0.0, last_attempt_at + max(0.0, job.interval_seconds) - current)
        if initial_due_at > 0:
            return max(0.0, initial_due_at - current)
        return 0.0
