from pathlib import Path


def test_ui_stays_available_when_worker_restarts() -> None:
    unit = Path("systemd/prompta-ui.service").read_text()

    assert "Wants=prompta.service prompta-delivery-worker.service" in unit
    assert "Requires=prompta.service" not in unit
    assert "PartOf=prompta.service" not in unit


def test_delivery_worker_is_independently_restartable() -> None:
    unit = Path("systemd/prompta-delivery-worker.service").read_text()

    assert "ExecStart=%h/prompta/.venv/bin/prompta-delivery-worker" in unit
    assert "Restart=always" in unit
    assert "PartOf=prompta-ui.service" not in unit
    assert "Requires=prompta-ui.service" not in unit
