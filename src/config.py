from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Annotated, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "prompta" / "config.toml"


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


class StageConcurrencySettings(SettingsSection):
    """Global fresh-chat concurrency limit for once and scheduled jobs."""

    section = "stage_concurrency"
    required_when_enabled = ("max_workers",)
    enabled: bool = False
    max_workers: PositiveInt = 1

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> Self:
        """Bridge installed legacy caps until their config file is migrated.

        Old time windows are never applied. The former global parallelism cap
        takes precedence so a guarded code rollout cannot briefly run unlimited.
        """
        try:
            with path.expanduser().open("rb") as config_file:
                raw = tomllib.load(config_file)
        except FileNotFoundError:
            return cls()
        stage = raw.get(cls.section)
        parallelism = raw.get("parallelism")
        legacy_stage = (
            isinstance(stage, dict) and "max_workers" not in stage and "day_limit" in stage
        )
        legacy_parallelism = parallelism is not None and (
            stage is None or isinstance(stage, dict) and "max_workers" not in stage
        )
        if legacy_stage or legacy_parallelism:
            legacy_max = parallelism.get("max_workers") if isinstance(parallelism, dict) else None
            if parallelism is not None and (
                not isinstance(parallelism, dict) or legacy_max is None
            ):
                raise ValueError("Invalid legacy parallelism cap")
            if legacy_max is None and isinstance(stage, dict):
                day = stage.get("day_limit")
                night = stage.get("night_limit")
                if type(day) is not int or type(night) is not int:
                    raise ValueError("Invalid legacy stage concurrency limit")
                legacy_max = max(day, night)
            enabled = legacy_max is not None or (
                isinstance(stage, dict) and stage.get("enabled") is True
            )
            try:
                return cls.model_validate(
                    {"enabled": enabled, "max_workers": legacy_max if legacy_max is not None else 1}
                )
            except ValueError as exc:
                raise ValueError(f"Invalid legacy stage concurrency cap: {exc}") from exc
        return super().load(path)

    @property
    def active_limit(self) -> int | None:
        return self.max_workers if self.enabled else None


class ConnectorApproval(SettingsSection):
    section = "connector_approval"
    enabled: bool = False
