from pathlib import Path

import pytest

from prompta.config import ConcurrencySettings, ConnectorApproval


def test_connector_approval_defaults_off_and_requires_boolean(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    assert not ConnectorApproval.load(config).enabled
    config.write_text('[connector_approval]\nenabled = true\n')
    assert ConnectorApproval.load(config).enabled
    config.write_text('[connector_approval]\nenabled = "true"\n')
    with pytest.raises(ValueError, match="boolean"):
        ConnectorApproval.load(config)


def test_concurrency_disabled_by_default(tmp_path: Path) -> None:
    path = tmp_path / "missing.toml"
    assert ConcurrencySettings.load(path).active_limit is None
    path.write_text("[concurrency]\nenabled = false\n", encoding="utf-8")
    assert ConcurrencySettings.load(path).active_limit is None


def test_enabled_concurrency_has_one_global_limit(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[concurrency]\nenabled = true\nmax_workers = 3\n",
        encoding="utf-8",
    )
    settings = ConcurrencySettings.load(path)
    assert settings.enabled
    assert settings.active_limit == 3


def test_existing_concurrency_without_enabled_remains_capped(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[concurrency]\nmax_workers = 3\n", encoding="utf-8")
    assert ConcurrencySettings.load(path).active_limit == 3
    path.write_text("[concurrency]\nenabled = true\nmax_workers = 2\n", encoding="utf-8")
    assert ConcurrencySettings.load(path).active_limit == 2


def test_legacy_parallelism_keeps_its_limit_until_saved(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[parallelism]\nmax_workers = 7\n", encoding="utf-8")
    assert ConcurrencySettings.load(path).active_limit == 7


def test_new_concurrency_section_takes_precedence_over_legacy(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[parallelism]\nenabled = true\nmax_workers = 7\n"
        "[concurrency]\nenabled = false\n",
        encoding="utf-8",
    )
    assert ConcurrencySettings.load(path).active_limit is None


def test_invalid_legacy_parallelism_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[parallelism]\nmax_workers = 0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="concurrency"):
        ConcurrencySettings.load(path)


def test_invalid_concurrency_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[concurrency]\nmax_workers = 0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="concurrency"):
        ConcurrencySettings.load(path)


@pytest.mark.parametrize("value", ["0", "-1", "true", '"3"', "2.5"])
def test_concurrency_rejects_invalid_limits(tmp_path: Path, value: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        f"[concurrency]\nenabled = true\nmax_workers = {value}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"concurrency[\s\S]*max_workers"):
        ConcurrencySettings.load(path)


def test_concurrency_requires_explicit_cap_when_enabled(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[concurrency]\nenabled = true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="max_workers"):
        ConcurrencySettings.load(path)


@pytest.mark.parametrize(
    "legacy",
    [
        'job_prefixes = ["prefix-"]',
        'timezone = "Pacific/Auckland"',
        'night_start = "22:30"',
        'night_end = "07:00"',
        "day_limit = 1",
        "night_limit = 3",
    ],
)
def test_concurrency_rejects_old_scoped_and_time_fields(
    tmp_path: Path, legacy: str
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[concurrency]\nenabled = true\nmax_workers = 3\n" + legacy + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="concurrency"):
        ConcurrencySettings.load(path)


def test_concurrency_rejects_non_table(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('concurrency = "unlimited"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="concurrency"):
        ConcurrencySettings.load(path)
