"""Durable ChatGPT account read admission shared by background browser readers.

This adapter uses SchedulerRuntime's existing account-scoped SQLite backoff, not
an independent watcher timer. Local DOM inspection does not consume a network
read; navigation and refresh must pass the gate.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .rate_limit import DEFAULT_RETRY_AFTER, RateLimitError, parse_retry_after_header
from .scheduler_runtime import SchedulerRuntime

logger = logging.getLogger(__name__)


class AccountReadGate:
    def __init__(self, state_path: Path) -> None:
        self.runtime = SchedulerRuntime(state_path, state_path)

    def remaining(self) -> float:
        """Read the persisted account-wide deadline, including other workers' 429s."""
        return self.runtime.read_backoff_remaining()

    def note_http_429(self, retry_after_header: str | None = None) -> float:
        """Register one rate-limit event per account cooldown, not per failed XHR."""
        remaining = self.remaining()
        explicit_delay = parse_retry_after_header(retry_after_header)
        if remaining > 0:
            if explicit_delay <= remaining:
                return remaining
            return self.runtime.record_read_rate_limit(
                RateLimitError("ChatGPT account read HTTP 429", retry_after=explicit_delay),
                extend_only=True,
            )
        retry_after = max(DEFAULT_RETRY_AFTER, explicit_delay)
        remaining = self.runtime.record_read_rate_limit(
            RateLimitError("ChatGPT account read HTTP 429", retry_after=retry_after),
            extend_only=True,
        )
        logger.warning("ChatGPT account read paused after HTTP 429 seconds=%d", round(remaining))
        return remaining
