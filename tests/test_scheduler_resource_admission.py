from pathlib import Path

from prompta.delivery_worker import DeliveryAdmission
from prompta.jobs import add_job
from prompta.scheduler_runtime import SchedulerRuntime


class FakeResourceAdmission:
    def __init__(self, allowed: bool, reason: str = "") -> None:
        self.allowed = allowed
        self.reason = reason

    def __call__(self) -> tuple[bool, str]:
        return self.allowed, self.reason


def test_delivery_admission_blocks_host_pressure(tmp_path: Path) -> None:
    state = tmp_path / "runtime.sqlite3"
    add_job(state, "job", "work", 1800)
    runtime = SchedulerRuntime(state, state)
    admission = DeliveryAdmission(
        runtime,
        resource_admission=FakeResourceAdmission(False, "host is busy"),
    )

    allowed, reason, retry_after = admission()

    assert allowed is False
    assert reason == "host is busy"
    assert retry_after == 0.0


def test_delivery_admission_allows_healthy_host(tmp_path: Path) -> None:
    state = tmp_path / "runtime.sqlite3"
    runtime = SchedulerRuntime(state, state)
    admission = DeliveryAdmission(runtime, resource_admission=FakeResourceAdmission(True))

    allowed, reason, retry_after = admission()

    assert allowed is True
    assert reason == ""
    assert retry_after == 0.0
