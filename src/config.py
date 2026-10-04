from __future__ import annotations

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
