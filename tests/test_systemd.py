from pathlib import Path


def test_obsolete_services_are_removed() -> None:
    assert not Path("systemd/prompta.service").exists()
    assert not Path("systemd/prompta-conversation-worker.service").exists()


def test_ui_is_jobs_only_and_independent() -> None:
    unit = Path("systemd/prompta-ui.service").read_text()

    assert "prompta-ui --host 127.0.0.1 --port 8765" in unit
    assert "--cache" not in unit
    assert "--logs" not in unit
    assert "--preserve-active" not in unit
    assert "conversation" not in unit.lower()
    assert "WatchdogSec=30s" in unit
    assert "WantedBy=prompta.target" in unit


def test_delivery_worker_is_independently_restartable() -> None:
    unit = Path("systemd/prompta-delivery-worker.service").read_text()

    assert "ExecStart=%h/prompta/.venv/bin/prompta-delivery-worker" in unit
    assert "Restart=always" in unit
    assert "prompta-browser.service" in unit
    assert "WatchdogSec=45s" in unit
    assert "NotifyAccess=main" in unit
    assert "prompta-conversation-worker.service" not in unit


def test_scheduler_is_pure_independent_producer_service() -> None:
    unit = Path("systemd/prompta-scheduler.service").read_text()

    assert "ExecStart=%h/prompta/.venv/bin/prompta-scheduler" in unit
    assert "Restart=always" in unit
    assert "WatchdogSec=30s" in unit
    assert "NotifyAccess=main" in unit
    assert "prompta-delivery-worker.service" not in unit
    assert "prompta-browser.service" not in unit


def test_browser_has_independent_restart_and_resource_boundaries() -> None:
    unit = Path("systemd/prompta-browser.service").read_text()

    assert "Restart=always" in unit
    assert "MemoryHigh=3G" in unit
    assert "MemoryMax=6G" in unit
    assert "TasksMax=768" in unit
    assert "--disable-component-update" in unit
    assert "--password-store=basic" in unit
    assert "--ozone-platform=x11" in unit
    assert "PartOf=prompta-ui.service" not in unit
    assert "Requires=prompta-ui.service" not in unit


def test_target_starts_only_jobs_stack() -> None:
    target = Path("systemd/prompta.target").read_text()

    for unit in (
        "prompta-ui.service",
        "prompta-scheduler.service",
        "prompta-delivery-worker.service",
        "prompta-browser.service",
    ):
        assert unit in target
    assert "prompta-conversation-worker.service" not in target
    assert "prompta.service" not in target
    assert "WantedBy=default.target" in target
