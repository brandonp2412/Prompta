from __future__ import annotations

import logging
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from .persistence import connect_sqlite

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 40 * 60


@lru_cache(maxsize=1)
def current_source_revision() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    revision = completed.stdout.strip().lower()
    if completed.returncode != 0 or re.fullmatch(r"[0-9a-f]{7,64}", revision) is None:
        return ""
    return revision


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
    source_revision: str = ""


def _connect(path: Path) -> sqlite3.Connection:
    connection = connect_sqlite(path.expanduser())
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            name TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            interval_seconds REAL NOT NULL,
            daily_at TEXT,
            exact_interval INTEGER NOT NULL DEFAULT 0 CHECK (exact_interval IN (0, 1)),
            run_at_epoch REAL,
            source_revision TEXT NOT NULL DEFAULT ''
        )
        """
    )
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(scheduled_jobs)").fetchall()
    }
    if "source_revision" not in columns:
        connection.execute(
            "ALTER TABLE scheduled_jobs ADD COLUMN source_revision TEXT NOT NULL DEFAULT ''"
        )
    return connection


def load_jobs(path: Path) -> dict[str, PromptJob]:
    try:
        with _connect(path) as connection:
            rows = connection.execute(
                """
                SELECT name, prompt, interval_seconds, daily_at, exact_interval, run_at_epoch,
                       source_revision
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
            str(row["source_revision"] or ""),
        )
        for row in rows
    }


def normalise_job_definition(
    name: str,
    prompt: str,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    daily_at: str | None = None,
    exact_interval: bool = False,
    run_at_epoch: float | None = None,
    source_revision: str = "",
) -> PromptJob:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("prompta job name is empty")
    if not prompt.strip():
        raise ValueError("prompta prompt is empty")
    normalised_daily_at = _normalise_daily_at(daily_at) if daily_at is not None else None
    normalised_run_at = float(run_at_epoch) if run_at_epoch is not None else None
    if normalised_run_at is not None and normalised_run_at <= 0:
        raise ValueError("run_at_epoch must be a positive Unix timestamp")
    return PromptJob(
        normalized_name,
        prompt,
        max(0.0, interval_seconds),
        normalised_daily_at,
        bool(exact_interval),
        normalised_run_at,
        source_revision.strip().lower(),
    )


def add_job(
    path: Path,
    name: str,
    prompt: str,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    daily_at: str | None = None,
    exact_interval: bool = False,
    run_at_epoch: float | None = None,
    source_revision: str | None = None,
) -> None:
    job = normalise_job_definition(
        name,
        prompt,
        interval_seconds,
        daily_at,
        exact_interval,
        run_at_epoch,
        source_revision if source_revision is not None else current_source_revision(),
    )

    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO scheduled_jobs (
                name, prompt, interval_seconds, daily_at, exact_interval, run_at_epoch,
                source_revision
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                prompt = excluded.prompt,
                interval_seconds = excluded.interval_seconds,
                daily_at = excluded.daily_at,
                exact_interval = excluded.exact_interval,
                run_at_epoch = excluded.run_at_epoch
            """,
            (
                job.name,
                job.prompt,
                job.interval_seconds,
                job.daily_at,
                int(job.exact_interval),
                job.run_at_epoch,
                job.source_revision,
            ),
        )


def update_job_prompt(path: Path, name: str, prompt: str) -> bool:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("prompta job name is empty")
    if not prompt.strip():
        raise ValueError("prompta prompt is empty")

    with _connect(path) as connection:
        cursor = connection.execute(
            "UPDATE scheduled_jobs SET prompt = ? WHERE name = ?",
            (prompt, normalized_name),
        )
        return cursor.rowcount > 0


def remove_job(path: Path, name: str) -> None:
    with _connect(path) as connection:
        connection.execute("DELETE FROM scheduled_jobs WHERE name = ?", (name,))


def clear_jobs(path: Path) -> None:
    with _connect(path) as connection:
        connection.execute("DELETE FROM scheduled_jobs")
