"""Cooperative deployment pause for all browser-owning worker operations.

The pause marker prevents new admissions during deployment. Deployment and
browser recovery stop worker processes before changing their checkout or browser.
Admission never waits for a browser-wide lock; interrupted reads recover from history.
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


def deployment_recovery_priority(state_dir: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Read durable, opaque IDs of captures interrupted by prior deploys.

    The inventory contains no prompts. Invalid or absent inventories do not
    authorize any account reads; candidates must still pass store validation.
    """
    try:
        snapshot = json.loads((state_dir / "deployment-interrupted.json").read_text())
    except (OSError, ValueError):
        return (), ()
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("priority"), dict):
        return (), ()

    def ids(table: str) -> tuple[str, ...]:
        entries = snapshot["priority"].get(table)
        if not isinstance(entries, list):
            return ()
        return tuple(dict.fromkeys(
            value for value in entries[:512]
            if isinstance(value, str) and 0 < len(value) <= 200
        ))

    return ids("job_responses"), ids("manual_reply_turns")


class DeploymentGate:
    def __init__(self, state_path: Path) -> None:
        state_dir = state_path.expanduser().parent
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.pause_path = state_dir / "deployment.pause"

    def is_paused(self) -> bool:
        return self.pause_path.exists()

    @contextmanager
    def admission(self) -> Generator[bool, None, None]:
        """Check admission without blocking; deployments stop owners explicitly."""
        yield not self.is_paused()


def mark_worker_ready(state_path: Path, worker: str) -> None:
    """Publish readiness only after this generation has initialized its stores."""
    generation = os.environ.get("PROMPTA_WORKER_GENERATION")
    if generation:
        target = state_path.expanduser().parent / "releases" / generation / f"ready-{worker}"
        target.write_text(str(os.getpid()))
