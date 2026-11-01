"""Privacy-safe application logs with native journald severity levels."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

_JOURNAL_PRIORITY = {
    logging.CRITICAL: 2,
    logging.ERROR: 3,
    logging.WARNING: 4,
    logging.INFO: 6,
    logging.DEBUG: 7,
}


class JournalSeverityFormatter(logging.Formatter):
    """Let systemd parse a record's priority instead of treating stderr as INFO."""

    def __init__(self, *, service: str, release: str, journal: bool) -> None:
        super().__init__(
            f"%(asctime)s %(levelname)s component={service} release={release} %(message)s"
        )
        self.journal = journal

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not self.journal:
            return message
        priority = next(
            (value for level, value in _JOURNAL_PRIORITY.items() if record.levelno >= level),
            7,
        )
        return f"<{priority}>{message}"


def _release() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            check=True,
            text=True,
            capture_output=True,
            timeout=2,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() or "unknown"


def configure_logging(service: str) -> None:
    """Configure startup log routing once, without recording message bodies."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        JournalSeverityFormatter(
            service=service,
            release=os.environ.get("PROMPTA_RELEASE_SHA") or _release(),
            journal=bool(os.environ.get("JOURNAL_STREAM")),
        )
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler])
