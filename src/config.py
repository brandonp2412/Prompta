from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Annotated, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = Path(
    os.environ.get("PROMPTA_CONFIG_PATH") or Path.home() / ".config" / "prompta" / "config.toml"
)


PositiveInt = Annotated[int, Field(gt=0)]


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
    """Single global fresh-chat concurrency cap; omission means unlimited."""

    section = "parallelism"
    required_when_enabled = ("max_workers",)
    enabled_by_default = True
    enabled: bool = False
    max_workers: PositiveInt = 1

    @property
    def active_limit(self) -> int | None:
        return self.max_workers if self.enabled else None


class ConnectorApproval(SettingsSection):
    section = "connector_approval"
    enabled: bool = False
