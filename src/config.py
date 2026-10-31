from __future__ import annotations

import tomllib
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Annotated, ClassVar, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "prompta" / "config.toml"


def _local_time(value: object) -> time:
    if isinstance(value, time):
        parsed = value
    elif isinstance(value, str):
        parsed = time.fromisoformat(value)
    else:
        raise ValueError("Time must be HH:MM")
    if parsed.second or parsed.microsecond or parsed.tzinfo is not None:
        raise ValueError("Time must be HH:MM without seconds or timezone")
    return parsed


def _timezone(value: str) -> str:
    value = value.strip()
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Timezone must be a known IANA timezone") from exc
    return value


LocalTime = Annotated[time, BeforeValidator(_local_time)]
Timezone = Annotated[str, AfterValidator(_timezone)]
PositiveInt = Annotated[int, Field(gt=0)]
SafePrefix = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_.-]+$")]


class SettingsSection(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    section: ClassVar[str]
    required_when_enabled: ClassVar[tuple[str, ...]] = ()
    enabled_by_default: ClassVar[bool] = False

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> Self:
        try:
            with path.expanduser().open("rb") as config_file:
                section: object = tomllib.load(config_file).get(cls.section)
        except FileNotFoundError:
            return cls()
        if section is None:
            return cls()
        try:
            if isinstance(section, dict) and cls.enabled_by_default:
                section = {"enabled": True, **section}
            return cls.model_validate(section)
        except ValueError as exc:
            raise ValueError(f"Invalid {cls.section} configuration: {exc}") from exc

    @model_validator(mode="before")
    @classmethod
    def enabled_fields(cls, value: object) -> object:
        if not cls.required_when_enabled or not isinstance(value, dict):
            return value
        enabled = value.get("enabled", False)
        if enabled is False:
            return {"enabled": False}
        if enabled is True:
            missing = set(cls.required_when_enabled) - value.keys()
            if missing:
                raise ValueError("Missing settings: " + ", ".join(sorted(missing)))
        return {**value, "enabled": enabled}


class ParallelismSettings(SettingsSection):
    """Maximum simultaneous scheduled jobs; omitted means unlimited."""

    section = "parallelism"
    max_workers: PositiveInt | None = None


class StageConcurrencySettings(SettingsSection):
    section = "stage_concurrency"
    required_when_enabled = (
        "job_prefixes",
        "timezone",
        "night_start",
        "night_end",
        "day_limit",
        "night_limit",
    )
    enabled: bool = False
    job_prefixes: tuple[SafePrefix, ...] = ()
    timezone: Timezone = "UTC"
    night_start: LocalTime = time(0, 0)
    night_end: LocalTime = time(0, 0)
    day_limit: PositiveInt = 1
    night_limit: PositiveInt = 1

    @model_validator(mode="before")
    @classmethod
    def prefix_sequence(cls, value: object) -> object:
        if isinstance(value, dict):
            prefixes = value.get("job_prefixes")
            if isinstance(prefixes, list):
                return {**value, "job_prefixes": tuple(prefixes)}
        return value

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.enabled:
            if not self.job_prefixes or len(set(self.job_prefixes)) != len(self.job_prefixes):
                raise ValueError("job_prefixes must be nonempty and unique")
            if self.night_start == self.night_end:
                raise ValueError("night start and end must differ")
        return self

    def limit_at(self, now: float) -> int | None:
        if not self.enabled:
            return None
        local = datetime.fromtimestamp(now, ZoneInfo(self.timezone)).time()
        if self.night_start < self.night_end:
            night = self.night_start <= local < self.night_end
        else:
            night = local >= self.night_start or local < self.night_end
        return self.night_limit if night else self.day_limit


class WorkingHours(SettingsSection):
    section = "working_hours"
    required_when_enabled = ("start", "end", "timezone")
    enabled_by_default = True
    enabled: bool = False
    start: LocalTime = time(0, 0)
    end: LocalTime = time(0, 0)
    timezone: Timezone = "UTC"

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


class ConnectorApproval(SettingsSection):
    section = "connector_approval"
    enabled: bool = False
