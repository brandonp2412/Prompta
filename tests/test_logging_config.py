from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from prompta.logging_config import JournalSeverityFormatter, _release, configure_logging


def test_journal_formatter_preserves_severity_and_release() -> None:
    formatter = JournalSeverityFormatter(service="delivery_worker", release="abc123", journal=True)
    for level, priority in (
        (logging.DEBUG, 7),
        (logging.INFO, 6),
        (logging.WARNING, 4),
        (logging.ERROR, 3),
        (logging.CRITICAL, 2),
    ):
        record = logging.LogRecord("example", level, __file__, 1, "safe log", (), None)
        message = formatter.format(record)
        assert message.startswith(f"<{priority}>")
        assert "component=delivery_worker release=abc123 safe log" in message


def test_release_label_matches_checked_out_commit() -> None:
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )
    assert _release() == result.stdout.strip()


def test_nonjournal_logging_does_not_spawn_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOURNAL_STREAM", raising=False)
    monkeypatch.delenv("PROMPTA_RELEASE_SHA", raising=False)

    def unexpected_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Git should not be needed outside journald")

    monkeypatch.setattr("subprocess.run", unexpected_run)
    configure_logging("test")


def test_plain_formatter_has_no_journal_priority_prefix() -> None:
    formatter = JournalSeverityFormatter(service="ui", release="unknown", journal=False)
    record = logging.LogRecord("example", logging.ERROR, __file__, 1, "failure", (), None)
    assert formatter.format(record).startswith("20")
    assert "component=ui release=unknown failure" in formatter.format(record)
