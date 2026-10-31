from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from prompta.config import ParallelismSettings, StageConcurrencySettings, WorkingHours


def _epoch(local: str) -> float:
    return datetime.fromisoformat(local).replace(tzinfo=ZoneInfo("Pacific/Auckland")).timestamp()


def test_missing_config_disables_working_hours(tmp_path: Path) -> None:
    working_hours = WorkingHours.load(tmp_path / "missing.toml")

    assert working_hours.enabled is False
    assert working_hours.admission(now=_epoch("2026-10-05T12:00")) == (True, "", 0.0)


def test_overnight_working_hours_allow_only_configured_window(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[working_hours]
enabled = true
start = "22:30"
end = "08:00"
timezone = "Pacific/Auckland"
""",
        encoding="utf-8",
    )
    working_hours = WorkingHours.load(path)

    assert working_hours.admission(now=_epoch("2026-10-05T22:30"))[0] is True
    assert working_hours.admission(now=_epoch("2026-10-06T07:59"))[0] is True

    allowed, reason, retry_after = working_hours.admission(now=_epoch("2026-10-05T08:00"))
    assert allowed is False
    assert "22:30-08:00 Pacific/Auckland" in reason
    assert retry_after == pytest.approx(14.5 * 60 * 60)

    allowed, _reason, retry_after = working_hours.admission(now=_epoch("2026-10-05T22:29"))
    assert allowed is False
    assert retry_after == pytest.approx(60.0)


def test_equal_start_and_end_means_all_day() -> None:
    working_hours = WorkingHours(
        enabled=True,
        start=datetime.strptime("08:00", "%H:%M").time(),
        end=datetime.strptime("08:00", "%H:%M").time(),
        timezone="Pacific/Auckland",
    )

    assert working_hours.admission(now=_epoch("2026-10-05T12:00")) == (True, "", 0.0)


def test_invalid_working_hours_fail_closed_on_startup(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[working_hours]
start = "25:00"
end = "08:00"
timezone = "Pacific/Auckland"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"working_hours[\s\S]*start"):
        WorkingHours.load(path)


def test_connector_approval_defaults_off_and_requires_boolean(tmp_path: Path) -> None:
    from prompta.config import ConnectorApproval

    config = tmp_path / "config.toml"
    assert not ConnectorApproval.load(config).enabled
    config.write_text('[connector_approval]\nenabled = true\n')
    assert ConnectorApproval.load(config).enabled
    config.write_text('[connector_approval]\nenabled = "true"\n')
    with pytest.raises(ValueError, match="boolean"):
        ConnectorApproval.load(config)


def test_parallelism_defaults_to_unlimited_and_accepts_a_positive_cap(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    assert ParallelismSettings.load(path).max_workers is None
    path.write_text("[parallelism]\n", encoding="utf-8")
    assert ParallelismSettings.load(path).max_workers is None
    path.write_text("[parallelism]\nmax_workers = 3\n", encoding="utf-8")
    assert ParallelismSettings.load(path).max_workers == 3


@pytest.mark.parametrize("value", ["0", "-1", "true", '"3"', "2.5"])
def test_parallelism_invalid_limits_fail_closed(tmp_path: Path, value: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f"[parallelism]\nmax_workers = {value}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"parallelism[\s\S]*max_workers"):
        ParallelismSettings.load(path)


def test_parallelism_rejects_non_table(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('parallelism = "unlimited"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="parallelism"):
        ParallelismSettings.load(path)


def test_missing_stage_concurrency_config_has_no_special_limit(tmp_path: Path) -> None:
    assert StageConcurrencySettings.load(tmp_path / "missing.toml").limit_at(
        _epoch("2026-10-29T23:00")
    ) is None
    path = tmp_path / "config.toml"
    path.write_text("[stage_concurrency]\nenabled = false\n", encoding="utf-8")
    assert StageConcurrencySettings.load(path).limit_at(_epoch("2026-10-29T23:00")) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("day_limit", "0"),
        ("night_limit", "true"),
        ("night_start", '"25:00"'),
        ("night_end", '"22:30"'),
        ("timezone", '"Unknown/Timezone"'),
        ("job_prefixes", '["bad/%"]'),
        ("job_prefixes", '[]'),
    ],
)
def test_invalid_parallelism_setting_fails_closed(
    tmp_path: Path, field: str, value: str
) -> None:
    path = tmp_path / "config.toml"
    settings = {
        "enabled": "true",
        "job_prefixes": '["prompta-chat-ui-", "prompta-mobile-ux-v2-"]',
        "timezone": '"Pacific/Auckland"',
        "night_start": '"22:30"',
        "night_end": '"07:00"',
        "day_limit": "1",
        "night_limit": "3",
    }
    settings[field] = value
    path.write_text(
        "[stage_concurrency]\n" + "".join(f"{key} = {setting}\n" for key, setting in settings.items()),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        StageConcurrencySettings.load(path)
