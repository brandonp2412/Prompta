from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from prompta.config import WorkingHours


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

    with pytest.raises(ValueError, match="working_hours.start"):
        WorkingHours.load(path)
