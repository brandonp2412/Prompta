from __future__ import annotations

import math
import random
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime

from .strict_types import float_value, int_value

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
    duration_pattern = r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b"
    first = re.search(r"(?<![\w.])" + duration_pattern, lowered)
    if first is None:
        return DEFAULT_RETRY_AFTER

    def seconds(value: re.Match[str]) -> float:
        quantity = float(value.group(1))
        unit = value.group(2)
        if unit.startswith(("hour", "hr")):
            return quantity * 60 * 60
        if unit.startswith(("min", "minute")):
            return quantity * 60
        return quantity

    delay = seconds(first)
    # ChatGPT may express one delay as "1 hour 30 minutes" or
    # "1 hour and 30 minutes"; do not retry after only its first part.
    following = re.match(
        r"\s*(?:,?\s*and\s+|,?\s+)" + duration_pattern,
        lowered[first.end():],
    )
    if following is not None:
        delay += seconds(following)
    return max(0, math.ceil(delay)) if math.isfinite(delay) else DEFAULT_RETRY_AFTER


def parse_retry_after_header(value: str | None, *, now: float | None = None) -> int:
    """Parse the RFC 9110 Retry-After delay-seconds or HTTP-date field."""
    if not value:
        return 0
    value = value.strip()
    if value.isdecimal():
        try:
            return int(value)
        except ValueError:
            return 0
    try:
        deadline = parsedate_to_datetime(value)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
    except (TypeError, ValueError, OverflowError):
        return 0
    now = time.time() if now is None else now
    return max(0, math.ceil(deadline.timestamp() - now))


def captured_retry_after(capture: Mapping[str, object]) -> int:
    seconds = parse_retry_after_header(str(capture.get("retry_after") or ""))
    milliseconds = float_value(capture.get("retry_after_ms"))
    return max(
        seconds,
        math.ceil(milliseconds / 1000) if math.isfinite(milliseconds) and milliseconds > 0 else 0,
    )


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


@dataclass(frozen=True)
class RateLimitState:
    attempts: int = 0
    blocked_until: float = 0.0
    last_limited_at: float = 0.0


def remaining_rate_limit_backoff(state: RateLimitState, *, now: float) -> float:
    return max(0.0, state.blocked_until - now)


def snapshot_rate_limit_backoff(
    state: RateLimitState,
    *,
    now: float,
    wall_time: float,
) -> dict[str, float | int]:
    remaining = remaining_rate_limit_backoff(state, now=now)
    limited_age = max(0.0, now - state.last_limited_at) if state.attempts else 0.0
    return {
        "attempts": state.attempts,
        "blocked_until_epoch": wall_time + remaining,
        "last_limited_at_epoch": wall_time - limited_age,
    }


def restore_rate_limit_backoff(
    snapshot: Mapping[str, object],
    *,
    now: float,
    wall_time: float,
) -> RateLimitState:
    attempts = max(0, int_value(snapshot.get("attempts")))
    blocked_until_epoch = float_value(snapshot.get("blocked_until_epoch"))
    last_limited_epoch = float_value(snapshot.get("last_limited_at_epoch"))
    remaining = max(0.0, blocked_until_epoch - wall_time)
    limited_age = max(0.0, wall_time - last_limited_epoch) if last_limited_epoch else 0.0
    if not attempts or (remaining <= 0 and limited_age >= _RATE_LIMIT_RESET_SECONDS):
        return RateLimitState()
    return RateLimitState(
        attempts=attempts,
        blocked_until=now + remaining,
        last_limited_at=now - limited_age,
    )


def transition_rate_limit_backoff(
    state: RateLimitState,
    retry_after: float,
    *,
    now: float,
    jitter_fraction: float,
) -> tuple[RateLimitState, float]:
    if (
        state.attempts
        and state.last_limited_at
        and now - state.last_limited_at >= _RATE_LIMIT_RESET_SECONDS
    ):
        state = RateLimitState()

    attempts = state.attempts + 1
    exponential = min(
        _RATE_LIMIT_BACKOFF_CAP_SECONDS,
        float(DEFAULT_RETRY_AFTER) * (2 ** min(attempts - 1, 20)),
    )
    explicit_retry_after = max(0.0, float(retry_after))
    floor = max(exponential, explicit_retry_after)
    jitter_cap = min(_RATE_LIMIT_JITTER_CAP_SECONDS, floor * _RATE_LIMIT_JITTER_FRACTION)
    jitter = max(0.0, min(1.0, float(jitter_fraction))) * jitter_cap
    blocked_until = max(state.blocked_until, now + floor + jitter)
    next_state = RateLimitState(
        attempts=attempts,
        blocked_until=blocked_until,
        last_limited_at=now,
    )
    return next_state, remaining_rate_limit_backoff(next_state, now=now)


class RateLimitBackoff:
    def __init__(self) -> None:
        self.attempts = 0
        self.blocked_until = 0.0
        self.last_limited_at = 0.0

    def _state(self) -> RateLimitState:
        return RateLimitState(
            attempts=self.attempts,
            blocked_until=self.blocked_until,
            last_limited_at=self.last_limited_at,
        )

    def _apply(self, state: RateLimitState) -> None:
        self.attempts = state.attempts
        self.blocked_until = state.blocked_until
        self.last_limited_at = state.last_limited_at

    def snapshot(
        self,
        *,
        now: float | None = None,
        wall_time: float | None = None,
    ) -> dict[str, float | int]:
        now = time.monotonic() if now is None else now
        wall_time = time.time() if wall_time is None else wall_time
        return snapshot_rate_limit_backoff(self._state(), now=now, wall_time=wall_time)

    def restore(
        self,
        snapshot: Mapping[str, object],
        *,
        now: float | None = None,
        wall_time: float | None = None,
    ) -> None:
        now = time.monotonic() if now is None else now
        wall_time = time.time() if wall_time is None else wall_time
        self._apply(restore_rate_limit_backoff(snapshot, now=now, wall_time=wall_time))

    def record(self, retry_after: float = 0.0, *, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        state, delay = transition_rate_limit_backoff(
            self._state(),
            retry_after,
            now=now,
            jitter_fraction=random.uniform(0.0, 1.0),
        )
        self._apply(state)
        return delay

    def remaining(self, *, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        return remaining_rate_limit_backoff(self._state(), now=now)

    def reset(self) -> None:
        self._apply(RateLimitState())
