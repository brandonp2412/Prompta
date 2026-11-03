"""Immutable releases with immediate worker replacement and durable chat recovery."""
from __future__ import annotations

import fcntl
import json
import logging
import os
import subprocess
import tarfile
import time
import uuid
from pathlib import Path

from prompta.deployment_gate import DeploymentGate

logger = logging.getLogger(__name__)
WORKERS = ("prompta-delivery-worker", "prompta-manual-reply-worker")
MODULES = ("prompta.delivery_worker", "prompta.manual_reply_worker")
LEGACY_WORKERS = tuple(f"{worker}.service" for worker in WORKERS)
FRONTENDS = ("prompta-ui.service", "prompta-scheduler.service")


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def current_workers(state_dir: Path) -> tuple[str, ...]:
    path = state_dir / "worker-generation.json"
    if not path.exists():
        return LEGACY_WORKERS
    value = json.loads(path.read_text())
    units = value.get("units") if isinstance(value, dict) else None
    if not isinstance(units, list) or len(units) != 2 or not all(
        isinstance(unit, str) and unit.startswith("prompta-") and unit.endswith(".service")
        for unit in units
    ):
        raise ValueError("Invalid active worker generation")
    return tuple(str(unit) for unit in units)


def all_worker_units() -> tuple[str, ...]:
    output = run("systemctl", "--user", "list-units", "--all", "--plain", "--no-legend",
                 "prompta-delivery-worker*.service", "prompta-manual-reply-worker*.service")
    return tuple(dict.fromkeys(line.split()[0] for line in output.splitlines() if line.strip()))


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def snapshot(repo: Path, revision: str, target: Path, archive_path: Path | None = None) -> None:
    """Archive tracked code; neither checkout nor dependencies are changed."""
    target.mkdir(parents=True, mode=0o700)
    archive = target / "source.tar"
    try:
        if archive_path is None:
            run("git", "archive", "--format=tar", f"--output={archive}", revision, cwd=repo)
        with tarfile.open(archive_path or archive) as source:
            source.extractall(target, filter="data")
    finally:
        archive.unlink(missing_ok=True)
    # Console entry points can point into an editable checkout. Always use -m
    # with this release's PYTHONPATH instead, including migrations.
    run("buildq", "--wait", "--", "uv", "sync", "--frozen", "--no-dev",
        "--project", str(target), cwd=target)


def unit_definition(release: Path, worker: str, module: str) -> str:
    definition = (release / "systemd" / f"{worker}.service").read_text()
    definition = definition.replace("%h/prompta", str(release))
    definition = definition.replace(
        f"ExecStart={release}/.venv/bin/prompta-delivery-worker",
        f"ExecStart={release}/.venv/bin/python -m {module}",
    )
    definition = definition.replace(
        "Environment=PYTHONUNBUFFERED=1",
        f"Environment=PYTHONUNBUFFERED=1\nEnvironment=PROMPTA_WORKER_GENERATION={release.name}",
    )
    definition = definition.replace("WantedBy=prompta.target", "WantedBy=default.target")
    return definition


def configure_frontends(release: Path, config: Path) -> None:
    for unit, module in (
        ("prompta-ui.service", "prompta.web"),
        ("prompta-scheduler.service", "prompta.scheduler_service"),
        ("prompta-browser-watchdog.service", "prompta.browser_watchdog"),
    ):
        directory = config / f"{unit}.d"
        directory.mkdir(parents=True, exist_ok=True)
        arguments = " --host 127.0.0.1 --port 8765" if module == "prompta.web" else ""
        (directory / "release.conf").write_text(
            "[Service]\n"
            f"WorkingDirectory={release}\nEnvironment=PYTHONPATH={release}\n"
            f"ExecStart=\nExecStart={release}/.venv/bin/python -m {module}{arguments}\n"
        )


def sync_checkout(repo: Path) -> bool:
    """The bootstrap checkout stays pinned until its original owners exit."""
    for unit in LEGACY_WORKERS:
        state = run("systemctl", "--user", "show", "-p", "ActiveState", "--value", unit)
        if state not in {"inactive", "failed"}:
            return False
    run("git", "merge", "--ff-only", "origin/main", cwd=repo)
    return True


def schedule_checkout_sync(repo: Path, release: Path, config: Path) -> None:
    """Retry after reboot too; never mutate the bootstrap workers' source files."""
    (config / "prompta-checkout-sync.service").write_text(
        "[Unit]\nDescription=Advance Prompta checkout after original workers drain\n"
        "[Service]\nType=oneshot\n"
        f"WorkingDirectory={release}\nEnvironment=PYTHONPATH={release}\n"
        f"ExecStart={release}/.venv/bin/python -m scripts.deploy_guarded --repo {repo} --sync-checkout\n"
    )
    (config / "prompta-checkout-sync.timer").write_text(
        "[Unit]\nDescription=Retry safe Prompta checkout advancement\n"
        "[Timer]\nOnActiveSec=30\nOnUnitActiveSec=30\n"
        "[Install]\nWantedBy=timers.target\n"
    )
    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", "--now", "prompta-checkout-sync.timer")


def deploy(
    repo: Path, gate: DeploymentGate, *, archive_path: Path | None = None, revision: str | None = None,
) -> bool:
    from scripts.deploy_guarded import (
        record_interrupted_work,
        request_pause,
        stop_workers,
        verify_recorded_work,
        verify_services,
    )

    state_dir = gate.pause_path.parent
    config = Path.home() / ".config/systemd/user"
    config.mkdir(parents=True, exist_ok=True)
    with (repo / ".git/prompta-main-merge.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        run("git", "fetch", "origin", "main", cwd=repo)
        if run("git", "status", "--porcelain", "--untracked-files=no", cwd=repo):
            raise RuntimeError("Installed checkout has local modifications")
        revision = revision or run("git", "rev-parse", "origin/main", cwd=repo)
        generation = revision[:12] + "-" + uuid.uuid4().hex[:8]
        release = state_dir / "releases" / generation
        if archive_path is None:
            snapshot(repo, revision, release)
        else:
            snapshot(repo, revision, release, archive_path)
        old_units = current_workers(state_dir)
        new_units = tuple(f"{worker}-{generation}.service" for worker in WORKERS)
        for worker, module, unit in zip(WORKERS, MODULES, new_units, strict=True):
            (config / unit).write_text(unit_definition(release, worker, module))
            # Keep host settings (browser endpoint, watchdog budget, startup
            # conditions) without inheriting the old generation's retirement.
            overrides = config / f"{unit}.d"
            for source in sorted((config / f"{worker}.service.d").glob("*.conf")):
                if source.name in {"draining.conf", "release.conf"}:
                    continue
                overrides.mkdir(parents=True, exist_ok=True)
                (overrides / source.name).write_text(
                    source.read_text().replace("%h/prompta", str(release))
                )
        request_pause(gate)
        retired = False
        try:
            record_interrupted_work(gate)
            # Once stopping begins, any failure must leave admission paused.
            retired = True
            stop_workers()
            env = os.environ.copy()
            env["PYTHONPATH"] = str(release)
            subprocess.run(
                [str(release / ".venv/bin/python"), "-m", "prompta.schema_migrations",
                 "--state-dir", str(state_dir)], cwd=release, env=env, check=True,
            )
            subprocess.run(
                [str(release / ".venv/bin/python"), "-m", "scripts.deploy_guarded",
                 "--state", str(state_dir / "runtime.sqlite3"), "--prepare-recovery"],
                cwd=release, env=env, check=True,
            )
            run("systemctl", "--user", "daemon-reload")
            run("systemctl", "--user", "start", *new_units)
            # Recovery slots are durable before any new owner can admit work.
            if not verify_services(units=new_units, check_http=False, ready_dir=release):
                raise RuntimeError("New worker generation failed startup")
            atomic_json(state_dir / "worker-handover.json", {
                "started_at": time.time(), "revision": revision,
                "retiring_units": list(old_units), "new_units": list(new_units),
                "release": str(release), "status": "prepared",
            })
            run("systemctl", "--user", "disable", *old_units)
            atomic_json(state_dir / "worker-generation.json", {
                "revision": revision, "release": str(release), "units": list(new_units),
            })
            run("systemctl", "--user", "enable", *new_units)
            configure_frontends(release, config)
            run("systemctl", "--user", "daemon-reload")
            run("systemctl", "--user", "restart", *FRONTENDS)
            if not verify_services(units=(*FRONTENDS, *new_units)):
                raise RuntimeError("New generation health verification failed; admission stays paused")
            if not verify_recorded_work(gate):
                raise RuntimeError("Interrupted work verification failed; admission stays paused")
            schedule_checkout_sync(repo, release, config)
            atomic_json(state_dir / "worker-handover.json", {
                "completed_at": time.time(), "revision": revision,
                "retiring_units": list(old_units), "new_units": list(new_units),
                "release": str(release), "status": "serving",
            })
            gate.pause_path.unlink()
            logger.info("New generation serving: %s; previous owners stopped: %s", generation, old_units)
            return True
        except BaseException:
            if not retired:
                run("systemctl", "--user", "stop", "--no-block", *new_units)
                gate.pause_path.unlink(missing_ok=True)
            # After stopping owners, leave the durable pause and inventory in place.
            raise
