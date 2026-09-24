from unittest.mock import patch

from prompta.resource_pressure import (
    ResourceAdmission,
    ResourceLimits,
    evaluate_resource_admission,
)

HEALTHY_MEMINFO = """MemTotal:       16000000 kB
MemAvailable:   8000000 kB
SwapTotal:      24000000 kB
SwapFree:       18000000 kB
"""

HEALTHY_PSI = """some avg10=0.20 avg60=0.15 avg300=0.10 total=1000
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
"""


def evaluate(
    *,
    meminfo: str = HEALTHY_MEMINFO,
    psi: str = HEALTHY_PSI,
    cpu_psi: str = "",
    load1: float = 4.0,
    cpus: int = 14,
) -> tuple[bool, str]:
    return evaluate_resource_admission(
        meminfo_text=meminfo,
        memory_pressure_text=psi,
        cpu_pressure_text=cpu_psi,
        load1=load1,
        cpu_count=cpus,
        limits=ResourceLimits(),
    )


def test_resource_admission_allows_healthy_host() -> None:
    assert evaluate() == (True, "")


def test_resource_admission_defers_when_available_ram_falls_below_twenty_percent() -> None:
    allowed, reason = evaluate(
        meminfo=HEALTHY_MEMINFO.replace("8000000", "2500000"),
    )

    assert allowed is False
    assert "available RAM" in reason


def test_resource_admission_defers_when_cpu_load_is_saturated() -> None:
    allowed, reason = evaluate(load1=13.0)

    assert allowed is False
    assert "load 13.0" in reason


def test_resource_admission_prefers_current_cpu_psi_over_stale_load_average() -> None:
    allowed, reason = evaluate(
        cpu_psi="""some avg10=0.10 avg60=0.20 avg300=0.30 total=1000
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
""",
        load1=18.5,
    )

    assert allowed is True
    assert reason == ""


def test_resource_admission_defers_on_sustained_cpu_pressure() -> None:
    allowed, reason = evaluate(
        cpu_psi="""some avg10=65.00 avg60=50.00 avg300=30.00 total=1000
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
""",
        load1=1.0,
    )

    assert allowed is False
    assert "CPU PSI some" in reason


def test_resource_admission_allows_mild_memory_pressure() -> None:
    allowed, reason = evaluate(
        psi="""some avg10=7.50 avg60=4.00 avg300=1.00 total=1000
full avg10=2.00 avg60=1.00 avg300=0.50 total=100
""",
    )

    assert allowed is True
    assert reason == ""


def test_resource_admission_defers_on_sustained_memory_pressure() -> None:
    allowed, reason = evaluate(
        psi="""some avg10=25.00 avg60=20.00 avg300=10.00 total=1000
full avg10=2.00 avg60=1.00 avg300=0.50 total=100
""",
    )

    assert allowed is False
    assert "memory PSI some" in reason


def test_resource_admission_defers_on_severe_full_memory_pressure() -> None:
    allowed, reason = evaluate(
        psi="""some avg10=15.00 avg60=10.00 avg300=5.00 total=1000
full avg10=12.00 avg60=8.00 avg300=4.00 total=100
""",
    )

    assert allowed is False
    assert "memory PSI full" in reason


def test_resource_admission_defers_when_swap_is_nearly_exhausted_and_ram_is_tight() -> None:
    allowed, reason = evaluate(
        meminfo="""MemTotal:       16000000 kB
MemAvailable:   4000000 kB
SwapTotal:      24000000 kB
SwapFree:        1000000 kB
""",
    )

    assert allowed is False
    assert "swap free" in reason


def test_resource_admission_does_not_penalize_old_swap_usage_when_ram_is_healthy() -> None:
    allowed, reason = evaluate(
        meminfo="""MemTotal:       16000000 kB
MemAvailable:   8000000 kB
SwapTotal:      24000000 kB
SwapFree:        1000000 kB
""",
    )

    assert allowed is True
    assert reason == ""


def _write_proc_pressure(
    root,
    *,
    available_kb: int = 8_000_000,
    memory_some: float = 0.2,
) -> None:
    (root / "pressure").mkdir(exist_ok=True)
    (root / "meminfo").write_text(
        f"""MemTotal:       16000000 kB
MemAvailable:   {available_kb} kB
SwapTotal:      24000000 kB
SwapFree:       18000000 kB
"""
    )
    (root / "pressure/memory").write_text(
        f"""some avg10={memory_some:.2f} avg60=0.10 avg300=0.10 total=1000
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
"""
    )
    (root / "pressure/cpu").write_text(
        """some avg10=0.10 avg60=0.10 avg300=0.10 total=1000
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
"""
    )


def test_resource_admission_ram_hysteresis_requires_recovery_margin(tmp_path) -> None:
    _write_proc_pressure(tmp_path, available_kb=3_000_000)
    admission = ResourceAdmission(proc_root=tmp_path)
    with (
        patch("prompta.resource_pressure.os.getloadavg", return_value=(1.0, 1.0, 1.0)),
        patch("prompta.resource_pressure.os.cpu_count", return_value=8),
    ):
        allowed, _reason = admission()
        assert allowed is False

        _write_proc_pressure(tmp_path, available_kb=3_600_000)
        allowed, _reason = admission()
        assert allowed is False

        _write_proc_pressure(tmp_path, available_kb=4_800_000)
        assert admission() == (True, "")


def test_resource_admission_psi_hysteresis_requires_recovery_margin(tmp_path) -> None:
    _write_proc_pressure(tmp_path, memory_some=25.0)
    admission = ResourceAdmission(proc_root=tmp_path)
    with (
        patch("prompta.resource_pressure.os.getloadavg", return_value=(1.0, 1.0, 1.0)),
        patch("prompta.resource_pressure.os.cpu_count", return_value=8),
    ):
        allowed, _reason = admission()
        assert allowed is False

        _write_proc_pressure(tmp_path, memory_some=18.0)
        allowed, _reason = admission()
        assert allowed is False

        _write_proc_pressure(tmp_path, memory_some=10.0)
        assert admission() == (True, "")
