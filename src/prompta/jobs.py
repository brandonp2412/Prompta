from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

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


def load_jobs(path: Path) -> dict[str, PromptJob]:
    target = path.expanduser()
    try:
        payload = json.loads(target.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    jobs_raw = payload.get("jobs", payload)
    if not isinstance(jobs_raw, dict):
        return {}
    jobs: dict[str, PromptJob] = {}
    for name, value in jobs_raw.items():
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
            continue
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
        if str(name).strip() and prompt.strip():
            jobs[str(name)] = PromptJob(
                str(name), prompt, max(0.0, interval), daily_at, exact_interval, run_at_epoch
            )
    return jobs


def _write_jobs(path: Path, jobs: dict[str, PromptJob]) -> None:
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "jobs": {
            name: {
                "prompt": job.prompt,
                "interval_seconds": job.interval_seconds,
                **({"daily_at": job.daily_at} if job.daily_at is not None else {}),
                **({"exact_interval": True} if job.exact_interval else {}),
                **({"run_at_epoch": job.run_at_epoch} if job.run_at_epoch is not None else {}),
            }
            for name, job in sorted(jobs.items())
        }
    }
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(target)


def add_job(
    path: Path,
    name: str,
    prompt: str,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    daily_at: str | None = None,
    exact_interval: bool = False,
    run_at_epoch: float | None = None,
) -> None:
    if not name.strip():
        raise ValueError("prompta job name is empty")
    if not prompt.strip():
        raise ValueError("prompta prompt is empty")
    jobs = load_jobs(path)
    normalised_daily_at = _normalise_daily_at(daily_at) if daily_at is not None else None
    normalised_run_at = float(run_at_epoch) if run_at_epoch is not None else None
    if normalised_run_at is not None and normalised_run_at <= 0:
        raise ValueError("run_at_epoch must be a positive Unix timestamp")
    jobs[name] = PromptJob(
        name,
        prompt,
        max(0.0, interval_seconds),
        normalised_daily_at,
        exact_interval,
        normalised_run_at,
    )
    _write_jobs(path, jobs)


def remove_job(path: Path, name: str) -> None:
    jobs = load_jobs(path)
    jobs.pop(name, None)
    _write_jobs(path, jobs)


def clear_jobs(path: Path) -> None:
    try:
        path.expanduser().unlink()
    except FileNotFoundError:
        pass
