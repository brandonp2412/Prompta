from pathlib import Path


def test_ui_stays_available_when_worker_restarts() -> None:
    unit = Path("systemd/prompta-ui.service").read_text()

    assert "Wants=prompta.service" in unit
    assert "Requires=prompta.service" not in unit
    assert "PartOf=prompta.service" not in unit
