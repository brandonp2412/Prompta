from pathlib import Path


def test_ui_stays_available_when_workers_restart() -> None:
    unit = Path("systemd/prompta-ui.service").read_text()

    assert "Wants=prompta.service prompta-delivery-worker.service prompta-scheduler.service" in unit
    assert "Requires=prompta.service" not in unit
    assert "PartOf=prompta.service" not in unit
    assert "Requires=prompta-scheduler.service" not in unit


def test_delivery_worker_is_independently_restartable() -> None:
    unit = Path("systemd/prompta-delivery-worker.service").read_text()

    assert "ExecStart=%h/prompta/.venv/bin/prompta-delivery-worker" in unit
    assert "Restart=always" in unit
    assert "PartOf=prompta-ui.service" not in unit
    assert "Requires=prompta-ui.service" not in unit


def test_scheduler_is_pure_independent_producer_service() -> None:
    unit = Path("systemd/prompta-scheduler.service").read_text()

    assert "ExecStart=%h/prompta/.venv/bin/prompta-scheduler" in unit
    assert "Restart=always" in unit
    assert "prompta-delivery-worker.service" not in unit
    assert "prompta-browser.service" not in unit
    assert "prompta.service" not in unit


def test_browser_backend_service_no_longer_describes_itself_as_scheduler() -> None:
    unit = Path("systemd/prompta.service").read_text()

    assert "Description=Prompta browser/control backend" in unit
