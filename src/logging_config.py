"""Privacy-safe application logs with native journald severity levels."""

from __future__ import annotations

import logging
import os
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
    """Read the checked-out revision without invoking processes during service startup."""
    root = Path(__file__).resolve().parent.parent
    git_dir = root / ".git"
    try:
        if git_dir.is_file():
            pointer = git_dir.read_text(encoding="utf-8").strip()
            if not pointer.startswith("gitdir: "):
                return "unknown"
            git_dir = Path(pointer.removeprefix("gitdir: "))
            if not git_dir.is_absolute():
                git_dir = (root / git_dir).resolve()
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head[:12] if len(head) >= 12 else "unknown"
        ref = head.removeprefix("ref: ")
        common_dir = git_dir
        common_marker = git_dir / "commondir"
        if common_marker.is_file():
            common_dir = (git_dir / common_marker.read_text(encoding="utf-8").strip()).resolve()
        ref_file = common_dir / ref
        if ref_file.is_file():
            revision = ref_file.read_text(encoding="utf-8").strip()
            return revision[:12] if len(revision) >= 12 else "unknown"
        packed = common_dir / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                if line.endswith(" " + ref):
                    return line.split(" ", 1)[0][:12]
    except OSError:
        return "unknown"
    return "unknown"


def configure_logging(service: str) -> None:
    """Configure startup log routing once, without recording message bodies."""
    journal = bool(os.environ.get("JOURNAL_STREAM"))
    release = os.environ.get("PROMPTA_RELEASE_SHA") or (_release() if journal else "unknown")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        JournalSeverityFormatter(service=service, release=release, journal=journal)
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler])
