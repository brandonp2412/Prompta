"""Cooperative deployment pause for all browser-owning worker operations.

A shared flock spans each browser operation. The pause marker prevents new
admissions during deployment. Deployment records current work and stops its
owners before updating the checkout; interrupted reads recover from history.
"""

from __future__ import annotations

import fcntl
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


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
