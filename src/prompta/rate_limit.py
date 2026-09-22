from __future__ import annotations

import random
import re
import time
from typing import Any

DEFAULT_RETRY_AFTER = 5 * 60
_RATE_LIMIT_BACKOFF_CAP_SECONDS = 30 * 60.0
_RATE_LIMIT_RESET_SECONDS = 30 * 60.0
_RATE_LIMIT_JITTER_FRACTION = 0.10
_RATE_LIMIT_JITTER_CAP_SECONDS = 60.0


class RateLimitError(RuntimeError):
    def __init__(
        self, message: str = "ChatGPT rate limit reached", retry_after: int = DEFAULT_RETRY_AFTER
    ) -> None:
        super().__init__(message)
        self.retry_after = max(0, int(retry_after))

    @classmethod
    def from_text(cls, text: str) -> RateLimitError:
        message = text.strip() or "ChatGPT rate limit reached"
        return cls(message, retry_after=parse_retry_after(message))


def parse_retry_after(text: str) -> int:
    lowered = text.casefold()
    if re.search(r"\b(?:a\s+)?few\s+(?:minutes?|mins?)\b", lowered):
        return 5 * 60
    match = re.search(r"\b(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b", lowered)
    if match is None:
        return DEFAULT_RETRY_AFTER
    value = int(match.group(1))
    unit = match.group(2)
    if unit.startswith(("hour", "hr")):
        return value * 60 * 60
    return value * 60 if unit.startswith(("min", "minute")) else value


def is_rate_limited_text(text: str) -> bool:
    lowered = " ".join(text.casefold().split())
    return any(
        phrase in lowered
        for phrase in (
            "too many requests",
            "rate limit",
            "try again in",
            "wait a few minutes",
            "you've reached the current usage cap",
            "you have reached the current usage cap",
        )
    )


class RateLimitBackoff:
    def __init__(self) -> None:
        self.attempts = 0
        self.blocked_until = 0.0
        self.last_limited_at = 0.0

    def snapshot(
        self,
        *,
        now: float | None = None,
        wall_time: float | None = None,
    ) -> dict[str, float | int]:
        now = time.monotonic() if now is None else now
        wall_time = time.time() if wall_time is None else wall_time
        remaining = self.remaining(now=now)
        limited_age = max(0.0, now - self.last_limited_at) if self.attempts else 0.0
        return {
            "attempts": self.attempts,
            "blocked_until_epoch": wall_time + remaining,
            "last_limited_at_epoch": wall_time - limited_age,
        }

    def restore(
        self,
        snapshot: dict[str, Any],
        *,
        now: float | None = None,
        wall_time: float | None = None,
    ) -> None:
        now = time.monotonic() if now is None else now
        wall_time = time.time() if wall_time is None else wall_time
        attempts = max(0, int(snapshot.get("attempts") or 0))
        blocked_until_epoch = float(snapshot.get("blocked_until_epoch") or 0.0)
        last_limited_epoch = float(snapshot.get("last_limited_at_epoch") or 0.0)
        remaining = max(0.0, blocked_until_epoch - wall_time)
        limited_age = max(0.0, wall_time - last_limited_epoch) if last_limited_epoch else 0.0
        if not attempts or (remaining <= 0 and limited_age >= _RATE_LIMIT_RESET_SECONDS):
            self.reset()
            return
        self.attempts = attempts
        self.blocked_until = now + remaining
        self.last_limited_at = now - limited_age

    def record(self, retry_after: float = 0.0, *, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        if (
            self.attempts
            and self.last_limited_at
            and now - self.last_limited_at >= _RATE_LIMIT_RESET_SECONDS
        ):
            self.reset()
        self.attempts += 1
        exponential = min(
            _RATE_LIMIT_BACKOFF_CAP_SECONDS,
            float(DEFAULT_RETRY_AFTER) * (2 ** min(self.attempts - 1, 20)),
        )
        explicit_retry_after = max(0.0, float(retry_after))
        floor = explicit_retry_after if explicit_retry_after > 0 else exponential
        jitter_cap = min(_RATE_LIMIT_JITTER_CAP_SECONDS, floor * _RATE_LIMIT_JITTER_FRACTION)
        delay = floor + random.uniform(0.0, jitter_cap)
        self.last_limited_at = now
        self.blocked_until = max(self.blocked_until, now + delay)
        return max(0.0, self.blocked_until - now)

    def remaining(self, *, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        return max(0.0, self.blocked_until - now)

    def reset(self) -> None:
        self.attempts = 0
        self.blocked_until = 0.0
        self.last_limited_at = 0.0
