from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .persistence import (
    DEFAULT_RUNTIME_PATH,
    LEGACY_JOBS_PATH,
    connect_sqlite,
    is_sqlite_file,
    read_legacy_json,
    remove_legacy_json,
)

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 40 * 60


def _normalise_daily_at(value: str) -> str:
    candidate = value.strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", candidate):
        raise ValueError("daily time must be HH:MM in 24-hour local time")
    return candidate


def _next_daily_epoch(daily_at: str, now: float, *, include_now: bool = False) -> float:
    hour, minute = (int(part) for part in _normalise_daily_at(daily_at).split(":"))
    current = datetime.fromtimestamp(now)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    candidate_epoch = candidate.timestamp()
    if candidate_epoch < now or (candidate_epoch == now and not include_now):
        candidate = candidate + timedelta(days=1)
        candidate_epoch = candidate.timestamp()
    return candidate_epoch


@dataclass(frozen=True)
class PromptJob:
    name: str
    prompt: str
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    daily_at: str | None = None
    exact_interval: bool = False
    run_at_epoch: float | None = None


def _job_from_legacy(name: object, value: object) -> PromptJob | None:
    if isinstance(value, str):
        prompt = value
        interval = DEFAULT_INTERVAL_SECONDS
    elif isinstance(value, dict):
        prompt = str(value.get("prompt") or "")
        try:
            raw_interval = value.get("interval_seconds")
            interval = DEFAULT_INTERVAL_SECONDS if raw_interval is None else float(raw_interval)
        except (TypeError, ValueError):
            interval = DEFAULT_INTERVAL_SECONDS
    else:
        return None

    daily_at = None
    exact_interval = False
    run_at_epoch: float | None = None
    if isinstance(value, dict):
        exact_interval = value.get("exact_interval") is True
        if value.get("run_at_epoch") is not None:
            try:
                run_at_epoch = float(value["run_at_epoch"])
            except (TypeError, ValueError):
                logger.warning("Ignoring invalid run_at_epoch for Prompta job=%s", name)
        if value.get("daily_at") is not None:
            try:
                daily_at = _normalise_daily_at(str(value["daily_at"]))
            except ValueError:
                logger.warning("Ignoring invalid daily_at for Prompta job=%s", name)

    normalized_name = str(name).strip()
    if not normalized_name or not prompt.strip():
        return None
    return PromptJob(
        normalized_name,
        prompt,
        max(0.0, interval),
        daily_at,
        exact_interval,
        run_at_epoch,
    )


def _legacy_jobs(payload: object) -> dict[str, PromptJob]:
    if not isinstance(payload, dict):
        return {}
    jobs_raw = payload.get("jobs", payload)
    if not isinstance(jobs_raw, dict):
        return {}
    jobs: dict[str, PromptJob] = {}
    for name, value in jobs_raw.items():
        job = _job_from_legacy(name, value)
        if job is not None:
            jobs[job.name] = job
    return jobs


def _migration_candidates(path: Path) -> list[Path]:
    target = path.expanduser()
    candidates: list[Path] = []
    if target.exists() and not is_sqlite_file(target):
        candidates.append(target)
    if target == DEFAULT_RUNTIME_PATH and LEGACY_JOBS_PATH not in candidates:
        candidates.append(LEGACY_JOBS_PATH)
    return candidates


def _connect(path: Path) -> sqlite3.Connection:
    target = path.expanduser()
    legacy_payloads: list[tuple[Path, object]] = []
    for candidate in _migration_candidates(target):
        payload = read_legacy_json(candidate)
        if payload is not None:
            legacy_payloads.append((candidate, payload))

    # A caller may still pass a historical *.json path. Convert that file in-place
    # to SQLite after capturing its legacy payload.
    if target.exists() and not is_sqlite_file(target):
        target.unlink(missing_ok=True)

    connection = connect_sqlite(target)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            name TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            interval_seconds REAL NOT NULL,
            daily_at TEXT,
            exact_interval INTEGER NOT NULL DEFAULT 0 CHECK (exact_interval IN (0, 1)),
            run_at_epoch REAL
        )
        """
    )
    existing = int(connection.execute("SELECT COUNT(*) FROM scheduled_jobs").fetchone()[0])
    if existing == 0:
        for _legacy_path, payload in legacy_payloads:
            jobs = _legacy_jobs(payload)
            if not jobs:
                continue
            connection.executemany(
                """
                INSERT INTO scheduled_jobs (
                    name, prompt, interval_seconds, daily_at, exact_interval, run_at_epoch
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        job.name,
                        job.prompt,
                        job.interval_seconds,
                        job.daily_at,
                        int(job.exact_interval),
                        job.run_at_epoch,
                    )
                    for job in jobs.values()
                ],
            )
            connection.commit()
            existing = len(jobs)
            logger.info("Migrated %d Prompta scheduled job(s) into SQLite", existing)
            break

    for legacy_path, _payload in legacy_payloads:
        remove_legacy_json(legacy_path)
    return connection


def load_jobs(path: Path) -> dict[str, PromptJob]:
    try:
        with _connect(path) as connection:
            rows = connection.execute(
                """
                SELECT name, prompt, interval_seconds, daily_at, exact_interval, run_at_epoch
                FROM scheduled_jobs
                ORDER BY name
                """
            ).fetchall()
    except (OSError, sqlite3.DatabaseError):
        logger.warning("Could not read Prompta scheduled jobs from %s", path, exc_info=True)
        return {}

    return {
        str(row["name"]): PromptJob(
            str(row["name"]),
            str(row["prompt"]),
            max(0.0, float(row["interval_seconds"])),
            str(row["daily_at"]) if row["daily_at"] is not None else None,
            bool(row["exact_interval"]),
            float(row["run_at_epoch"]) if row["run_at_epoch"] is not None else None,
        )
        for row in rows
    }


def add_job(
    path: Path,
    name: str,
    prompt: str,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    daily_at: str | None = None,
    exact_interval: bool = False,
    run_at_epoch: float | None = None,
) -> None:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("prompta job name is empty")
    if not prompt.strip():
        raise ValueError("prompta prompt is empty")
    normalised_daily_at = _normalise_daily_at(daily_at) if daily_at is not None else None
    normalised_run_at = float(run_at_epoch) if run_at_epoch is not None else None
    if normalised_run_at is not None and normalised_run_at <= 0:
        raise ValueError("run_at_epoch must be a positive Unix timestamp")

    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO scheduled_jobs (
                name, prompt, interval_seconds, daily_at, exact_interval, run_at_epoch
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                prompt = excluded.prompt,
                interval_seconds = excluded.interval_seconds,
                daily_at = excluded.daily_at,
                exact_interval = excluded.exact_interval,
                run_at_epoch = excluded.run_at_epoch
            """,
            (
                normalized_name,
                prompt,
                max(0.0, interval_seconds),
                normalised_daily_at,
                int(exact_interval),
                normalised_run_at,
            ),
        )


def remove_job(path: Path, name: str) -> None:
    with _connect(path) as connection:
        connection.execute("DELETE FROM scheduled_jobs WHERE name = ?", (name,))


def clear_jobs(path: Path) -> None:
    with _connect(path) as connection:
        connection.execute("DELETE FROM scheduled_jobs")
