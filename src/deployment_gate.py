"""Cooperative deployment pause for all browser-owning worker operations.

A shared flock spans each browser operation. The pause marker prevents new
admissions during deployment. Deployment records current work and stops its
owners before updating the checkout; interrupted reads recover from history.
"""

from __future__ import annotations

import fcntl
import json
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
        self.lock_path = state_dir / "deployment.lock"

    def is_paused(self) -> bool:
        return self.pause_path.exists()

    @contextmanager
    def admission(self) -> Generator[bool, None, None]:
        """Keep the shared lock for the admitted browser operation's lifetime."""
        with self.lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            try:
                yield not self.is_paused()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
