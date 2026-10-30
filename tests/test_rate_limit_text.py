from __future__ import annotations

import pytest

from prompta.rate_limit import DEFAULT_RETRY_AFTER, RateLimitError, parse_retry_after


@pytest.mark.parametrize(
    ("message", "seconds"),
    [
        ("Try again in 30 seconds", 30),
        ("Try again in 1.5 minutes", 90),
        ("Try again in 2 hours and 30 minutes", 9_000),
        ("Wait 0.1 seconds", 1),
        ("Please wait a few minutes", 300),
        ("Try again in 1-2 minutes", 120),
        ("Too many requests", DEFAULT_RETRY_AFTER),
        ("Try again in " + "9" * 5000 + " minutes", DEFAULT_RETRY_AFTER),
    ],
)
def test_human_readable_retry_backoff(message: str, seconds: int) -> None:
    assert parse_retry_after(message) == seconds
    assert RateLimitError.from_text(message).retry_after == seconds
