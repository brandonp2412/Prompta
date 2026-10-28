from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "prompta" / "config.toml"


def _parse_local_time(value: object, *, key: str) -> time:
    if not isinstance(value, str):
        raise ValueError(f"{key} must be an HH:MM string")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be HH:MM in 24-hour local time") from exc
    if parsed.second or parsed.microsecond:
        raise ValueError(f"{key} must not include seconds")
    return parsed


@dataclass(frozen=True)
class StageConcurrencySettings:
    """Optional per-install admission policy; missing settings mean no special limit."""

    enabled: bool = False
    job_prefixes: tuple[str, ...] = ()
    timezone: str = "UTC"
    night_start: time = time(0, 0)
    night_end: time = time(0, 0)
    day_limit: int = 0
    night_limit: int = 0

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> StageConcurrencySettings:
        try:
            with path.expanduser().open("rb") as config_file:
                raw = tomllib.load(config_file)
        except FileNotFoundError:
            return cls()

        section = raw.get("stage_concurrency")
        if section is None:
            return cls()
        if not isinstance(section, dict):
            raise ValueError("[stage_concurrency] must be a table")
        enabled = section.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("stage_concurrency.enabled must be true or false")
        if not enabled:
            return cls()

        raw_prefixes = section.get("job_prefixes")
        if (
            not isinstance(raw_prefixes, list)
            or not raw_prefixes
            or any(
                not isinstance(prefix, str)
                or re.fullmatch(r"[a-zA-Z0-9_.-]+", prefix) is None
                for prefix in raw_prefixes
            )
        ):
            raise ValueError("stage_concurrency.job_prefixes must be nonempty safe names")
        prefixes = tuple(raw_prefixes)
        if len(set(prefixes)) != len(prefixes):
            raise ValueError("stage_concurrency.job_prefixes must be unique")

        timezone = section.get("timezone")
        if not isinstance(timezone, str) or not timezone.strip():
            raise ValueError("stage_concurrency.timezone must be an IANA timezone")
        timezone = timezone.strip()
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("stage_concurrency.timezone is invalid") from exc

        start = _parse_local_time(section.get("night_start"), key="stage_concurrency.night_start")
        end = _parse_local_time(section.get("night_end"), key="stage_concurrency.night_end")
        if start == end:
            raise ValueError("stage_concurrency night start and end must differ")

        day_limit = section.get("day_limit")
        night_limit = section.get("night_limit")
        for key, limit in (("day_limit", day_limit), ("night_limit", night_limit)):
            if type(limit) is not int or limit <= 0:
                raise ValueError(f"stage_concurrency.{key} must be a positive integer")
        return cls(True, prefixes, timezone, start, end, day_limit, night_limit)

    def limit_at(self, now: float) -> int | None:
        if not self.enabled:
            return None
        local = datetime.fromtimestamp(now, ZoneInfo(self.timezone)).time()
        if self.night_start < self.night_end:
            night = self.night_start <= local < self.night_end
        else:
            night = local >= self.night_start or local < self.night_end
        return self.night_limit if night else self.day_limit


@dataclass(frozen=True)
class WorkingHours:
    enabled: bool = False
    start: time = time(0, 0)
    end: time = time(0, 0)
    timezone: str = "UTC"

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> WorkingHours:
        try:
            with path.expanduser().open("rb") as config_file:
                raw = tomllib.load(config_file)
        except FileNotFoundError:
            return cls()

        section = raw.get("working_hours")
        if section is None:
            return cls()
        if not isinstance(section, dict):
            raise ValueError("[working_hours] must be a table")

        enabled = section.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("working_hours.enabled must be true or false")
        if not enabled:
            return cls()

        start = _parse_local_time(section.get("start"), key="working_hours.start")
        end = _parse_local_time(section.get("end"), key="working_hours.end")
        timezone_name = section.get("timezone")
        if not isinstance(timezone_name, str) or not timezone_name.strip():
            raise ValueError("working_hours.timezone must be an IANA timezone name")
        timezone_name = timezone_name.strip()
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                f"working_hours.timezone is not a known IANA timezone: {timezone_name}"
            ) from exc

        return cls(True, start, end, timezone_name)

    def admission(self, *, now: float | None = None) -> tuple[bool, str, float]:
        if not self.enabled or self.start == self.end:
            return True, "", 0.0

        zone = ZoneInfo(self.timezone)
        current = datetime.now(zone) if now is None else datetime.fromtimestamp(now, zone)
        local_time = current.timetz().replace(tzinfo=None)

        if self.start < self.end:
            allowed = self.start <= local_time < self.end
        else:
            allowed = local_time >= self.start or local_time < self.end

        if allowed:
            return True, "", 0.0

        next_start = datetime.combine(current.date(), self.start, tzinfo=zone)
        if next_start <= current:
            next_start += timedelta(days=1)
        retry_after = max(0.0, next_start.timestamp() - current.timestamp())
        return (
            False,
            f"Outside Prompta working hours ({self.start.strftime('%H:%M')}-"
            f"{self.end.strftime('%H:%M')} {self.timezone})",
            retry_after,
        )


@dataclass(frozen=True)
class ConnectorApproval:
    enabled: bool = False

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> ConnectorApproval:
        try:
            with path.expanduser().open("rb") as config_file:
                section = tomllib.load(config_file).get("connector_approval", {})
        except FileNotFoundError:
            return cls()
        if not isinstance(section, dict):
            raise ValueError("[connector_approval] must be a table")
        enabled = section.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("connector_approval.enabled must be true or false")
        return cls(enabled)
