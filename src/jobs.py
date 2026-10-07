from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError

from .persistence import create_database, scheduled_jobs

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
    mutex_group: str = ""


def load_jobs(path: Path) -> dict[str, PromptJob]:
    engine = create_database(path)
    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(select(scheduled_jobs).order_by(scheduled_jobs.c.name))
                .mappings()
                .all()
            )
    except (OSError, SQLAlchemyError):
        logger.warning("Could not read Prompta scheduled jobs from %s", path, exc_info=True)
        return {}
    finally:
        engine.dispose()

    return {
        str(row["name"]): PromptJob(
            str(row["name"]),
            str(row["prompt"]),
            max(0.0, float(row["interval_seconds"])),
            str(row["daily_at"]) if row["daily_at"] is not None else None,
            bool(row["exact_interval"]),
            float(row["run_at_epoch"]) if row["run_at_epoch"] is not None else None,
            str(row["source_revision"] or ""),
            str(row["mutex_group"] or ""),
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
    mutex_group: str = "",
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
        mutex_group.strip(),
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
    mutex_group: str = "",
) -> None:
    job = normalise_job_definition(
        name,
        prompt,
        interval_seconds,
        daily_at,
        exact_interval,
        run_at_epoch,
        source_revision if source_revision is not None else current_source_revision(),
        mutex_group,
    )

    engine = create_database(path)
    try:
        values = {
            "name": job.name,
            "prompt": job.prompt,
            "interval_seconds": job.interval_seconds,
            "daily_at": job.daily_at,
            "exact_interval": job.exact_interval,
            "run_at_epoch": job.run_at_epoch,
            "source_revision": job.source_revision,
            "mutex_group": job.mutex_group,
        }
        statement = insert(scheduled_jobs).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[scheduled_jobs.c.name],
            set_={
                key: getattr(statement.excluded, key)
                for key in values
                if key not in {"name", "source_revision"}
            },
        )
        with engine.begin() as connection:
            connection.execute(statement)
    finally:
        engine.dispose()


def update_job_prompt(path: Path, name: str, prompt: str) -> bool:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("prompta job name is empty")
    if not prompt.strip():
        raise ValueError("prompta prompt is empty")

    engine = create_database(path)
    try:
        with engine.begin() as connection:
            result = connection.execute(
                update(scheduled_jobs)
                .where(scheduled_jobs.c.name == normalized_name)
                .values(prompt=prompt)
            )
            return result.rowcount > 0
    finally:
        engine.dispose()


def remove_job(path: Path, name: str) -> None:
    engine = create_database(path)
    try:
        with engine.begin() as connection:
            connection.execute(delete(scheduled_jobs).where(scheduled_jobs.c.name == name))
    finally:
        engine.dispose()


def clear_jobs(path: Path) -> None:
    engine = create_database(path)
    try:
        with engine.begin() as connection:
            connection.execute(delete(scheduled_jobs))
    finally:
        engine.dispose()
