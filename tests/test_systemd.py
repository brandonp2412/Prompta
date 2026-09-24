from pathlib import Path


def test_ui_is_not_coupled_to_workers_or_legacy_monolith() -> None:
    unit = Path("systemd/prompta-ui.service").read_text()

    assert "prompta.service" not in unit
    assert "prompta-delivery-worker.service" not in unit
    assert "prompta-scheduler.service" not in unit
    assert "prompta-conversation-worker.service" not in unit
    assert "WatchdogSec=30s" in unit
    assert "NotifyAccess=main" in unit
    assert "WantedBy=prompta.target" in unit


def test_delivery_worker_is_independently_restartable() -> None:
    unit = Path("systemd/prompta-delivery-worker.service").read_text()

    assert "ExecStart=%h/prompta/.venv/bin/prompta-delivery-worker" in unit
    assert "Restart=always" in unit
    assert "prompta-browser.service" in unit
    assert "WatchdogSec=45s" in unit
    assert "NotifyAccess=main" in unit
    assert "prompta.service" not in unit
    assert "PartOf=prompta-ui.service" not in unit
    assert "Requires=prompta-ui.service" not in unit


def test_conversation_worker_is_independently_restartable() -> None:
    unit = Path("systemd/prompta-conversation-worker.service").read_text()

    assert "ExecStart=%h/prompta/.venv/bin/prompta-conversation-worker" in unit
    assert "Restart=always" in unit
    assert "prompta-browser.service" in unit
    assert "WatchdogSec=120s" in unit
    assert "NotifyAccess=main" in unit
    assert "prompta-delivery-worker.service" not in unit
    assert "prompta-scheduler.service" not in unit
    assert "prompta.service" not in unit
    assert "PartOf=prompta-ui.service" not in unit
    assert "Requires=prompta-ui.service" not in unit


def test_scheduler_is_pure_independent_producer_service() -> None:
    unit = Path("systemd/prompta-scheduler.service").read_text()

    assert "ExecStart=%h/prompta/.venv/bin/prompta-scheduler" in unit
    assert "Restart=always" in unit
    assert "WatchdogSec=30s" in unit
    assert "NotifyAccess=main" in unit
    assert "prompta-delivery-worker.service" not in unit
    assert "prompta-browser.service" not in unit
    assert "prompta.service" not in unit


def test_browser_has_independent_restart_and_resource_boundaries() -> None:
    unit = Path("systemd/prompta-browser.service").read_text()

    assert "Restart=always" in unit
    assert "MemoryHigh=3G" in unit
    assert "MemoryMax=6G" in unit
    assert "TasksMax=768" in unit
    assert "PartOf=prompta-ui.service" not in unit
    assert "Requires=prompta-ui.service" not in unit


def test_target_starts_split_stack_without_legacy_monolith() -> None:
    target = Path("systemd/prompta.target").read_text()

    for unit in (
        "prompta-ui.service",
        "prompta-scheduler.service",
        "prompta-delivery-worker.service",
        "prompta-conversation-worker.service",
        "prompta-browser.service",
    ):
        assert unit in target
    assert "prompta.service" not in target
    assert "WantedBy=default.target" in target
