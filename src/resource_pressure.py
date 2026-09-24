from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResourceLimits:
    min_available_memory_fraction: float = 0.20
    max_load_per_cpu: float = 0.85
    max_cpu_psi_some_avg10: float = 50.0
    max_memory_psi_some_avg10: float = 20.0
    max_memory_psi_full_avg10: float = 10.0
    min_swap_free_fraction: float = 0.10

    @classmethod
    def from_env(cls) -> ResourceLimits:
        defaults = cls()
        return cls(
            min_available_memory_fraction=_env_float(
                "PROMPTA_MIN_AVAILABLE_MEMORY_FRACTION",
                defaults.min_available_memory_fraction,
            ),
            max_load_per_cpu=_env_float(
                "PROMPTA_MAX_LOAD_PER_CPU",
                defaults.max_load_per_cpu,
            ),
            max_cpu_psi_some_avg10=_env_float(
                "PROMPTA_MAX_CPU_PSI_SOME_AVG10",
                defaults.max_cpu_psi_some_avg10,
            ),
            max_memory_psi_some_avg10=_env_float(
                "PROMPTA_MAX_MEMORY_PSI_SOME_AVG10",
                defaults.max_memory_psi_some_avg10,
            ),
            max_memory_psi_full_avg10=_env_float(
                "PROMPTA_MAX_MEMORY_PSI_FULL_AVG10",
                defaults.max_memory_psi_full_avg10,
            ),
            min_swap_free_fraction=_env_float(
                "PROMPTA_MIN_SWAP_FREE_FRACTION",
                defaults.min_swap_free_fraction,
            ),
        )


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _meminfo(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        parts = raw.split()
        if not parts:
            continue
        try:
            values[key] = int(parts[0])
        except ValueError:
            continue
    return values


def _psi_avg10(text: str, kind: str) -> float:
    for line in text.splitlines():
        parts = line.split()
        if not parts or parts[0] != kind:
            continue
        for part in parts[1:]:
            if not part.startswith("avg10="):
                continue
            try:
                return float(part.split("=", 1)[1])
            except ValueError:
                return 0.0
    return 0.0


def evaluate_resource_admission(
    *,
    meminfo_text: str,
    memory_pressure_text: str,
    cpu_pressure_text: str = "",
    load1: float,
    cpu_count: int,
    limits: ResourceLimits,
) -> tuple[bool, str]:
    mem = _meminfo(meminfo_text)
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", total)
    if total > 0:
        available_fraction = available / total
        if available_fraction < limits.min_available_memory_fraction:
            return (
                False,
                f"available RAM {available_fraction:.0%} < "
                f"{limits.min_available_memory_fraction:.0%}",
            )

    cpu_pressure_available = bool(cpu_pressure_text.strip())
    if cpu_pressure_available:
        cpu_some_avg10 = _psi_avg10(cpu_pressure_text, "some")
        if cpu_some_avg10 > limits.max_cpu_psi_some_avg10:
            return (
                False,
                f"CPU PSI some avg10 {cpu_some_avg10:.1f}% > {limits.max_cpu_psi_some_avg10:.1f}%",
            )
    else:
        # Linux load average is a lagging signal and can stay elevated for minutes
        # after contention has cleared. Keep it only as a fallback for hosts that
        # do not expose CPU PSI.
        cpus = max(1, cpu_count)
        load_per_cpu = load1 / cpus
        if load_per_cpu > limits.max_load_per_cpu:
            return (
                False,
                f"load {load1:.1f} across {cpus} CPUs "
                f"({load_per_cpu:.0%}) > {limits.max_load_per_cpu:.0%}",
            )

    some_avg10 = _psi_avg10(memory_pressure_text, "some")
    if some_avg10 > limits.max_memory_psi_some_avg10:
        return (
            False,
            f"memory PSI some avg10 {some_avg10:.1f}% > {limits.max_memory_psi_some_avg10:.1f}%",
        )

    full_avg10 = _psi_avg10(memory_pressure_text, "full")
    if full_avg10 > limits.max_memory_psi_full_avg10:
        return (
            False,
            f"memory PSI full avg10 {full_avg10:.1f}% > {limits.max_memory_psi_full_avg10:.1f}%",
        )

    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", swap_total)
    if total > 0 and swap_total > 0:
        available_fraction = available / total
        swap_free_fraction = swap_free / swap_total
        if available_fraction < 0.30 and swap_free_fraction < limits.min_swap_free_fraction:
            return (
                False,
                f"swap free {swap_free_fraction:.0%} < "
                f"{limits.min_swap_free_fraction:.0%} while RAM is tight",
            )

    return True, ""


class ResourceAdmission:
    def __init__(
        self,
        limits: ResourceLimits | None = None,
        *,
        proc_root: Path = Path("/proc"),
    ) -> None:
        self.limits = limits or ResourceLimits.from_env()
        self.proc_root = proc_root
        self._blocked = False
        self._reason = ""

    def _active_limits(self) -> ResourceLimits:
        if not self._blocked:
            return self.limits
        return ResourceLimits(
            min_available_memory_fraction=min(
                1.0, self.limits.min_available_memory_fraction + 0.05
            ),
            max_load_per_cpu=max(0.0, self.limits.max_load_per_cpu - 0.10),
            max_cpu_psi_some_avg10=max(0.0, self.limits.max_cpu_psi_some_avg10 * 0.75),
            max_memory_psi_some_avg10=max(0.0, self.limits.max_memory_psi_some_avg10 * 0.75),
            max_memory_psi_full_avg10=max(0.0, self.limits.max_memory_psi_full_avg10 * 0.75),
            min_swap_free_fraction=min(1.0, self.limits.min_swap_free_fraction + 0.05),
        )

    def __call__(self) -> tuple[bool, str]:
        try:
            meminfo_text = (self.proc_root / "meminfo").read_text()
            pressure_path = self.proc_root / "pressure/memory"
            memory_pressure_text = pressure_path.read_text() if pressure_path.exists() else ""
            cpu_pressure_path = self.proc_root / "pressure/cpu"
            cpu_pressure_text = cpu_pressure_path.read_text() if cpu_pressure_path.exists() else ""
            load1 = os.getloadavg()[0]
            cpu_count = os.cpu_count() or 1
        except OSError:
            if self._blocked:
                return False, self._reason
            return True, ""

        allowed, reason = evaluate_resource_admission(
            meminfo_text=meminfo_text,
            memory_pressure_text=memory_pressure_text,
            cpu_pressure_text=cpu_pressure_text,
            load1=load1,
            cpu_count=cpu_count,
            limits=self._active_limits(),
        )
        if allowed:
            self._blocked = False
            self._reason = ""
            return True, ""
        self._blocked = True
        self._reason = reason
        return False, reason
