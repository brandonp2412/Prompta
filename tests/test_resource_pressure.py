from prompta.resource_pressure import ResourceLimits, evaluate_resource_admission

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


def test_resource_admission_defers_on_sustained_memory_pressure() -> None:
    allowed, reason = evaluate(
        psi="""some avg10=7.50 avg60=4.00 avg300=1.00 total=1000
full avg10=0.20 avg60=0.10 avg300=0.00 total=100
""",
    )

    assert allowed is False
    assert "memory PSI some" in reason


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
