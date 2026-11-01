from __future__ import annotations

import logging

from prompta.logging_config import JournalSeverityFormatter


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


def test_plain_formatter_has_no_journal_priority_prefix() -> None:
    formatter = JournalSeverityFormatter(service="ui", release="unknown", journal=False)
    record = logging.LogRecord("example", logging.ERROR, __file__, 1, "failure", (), None)
    assert formatter.format(record).startswith("20")
    assert "component=ui release=unknown failure" in formatter.format(record)
