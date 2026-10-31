"""Read-only queue start estimates from local, completed scheduled captures."""

from __future__ import annotations

import heapq
import math
from statistics import median

from sqlalchemy import select

from .delivery_queue import DeliveryQueueStore
from .response_store import results
from .strict_types import float_value

_FALLBACK_RUN_SECONDS = 600
_MAX_RUN_SECONDS = 2700
_MIN_RUN_SECONDS = 30


class SlotProjection:
    """Project capacity as a set of next-free timestamps relative to now."""

    def __init__(self, limit: int, remaining: list[float], duration: int) -> None:
        self.limit = max(1, limit)
        self.duration = duration
        self._available = remaining[:]
        heapq.heapify(self._available)

    def enqueue(self) -> int:
        starts_in = 0.0
        # A cap can be lowered while more than 'limit' runs are still active.
        # Every excess occupant must finish before another job is admitted.
        while len(self._available) >= self.limit:
            starts_in = heapq.heappop(self._available)
        heapq.heappush(self._available, starts_in + self.duration)
        return max(0, math.ceil(starts_in))


class QueueEtaEstimator:
    """Uses only aggregate timings and IDs; never reads stored message bodies."""

    def __init__(self, queue: DeliveryQueueStore, *, now: float, active_ids: set[str]) -> None:
        self.queue = queue
        self.now = now
        self.active_ids = active_ids
        elapsed = results.c.finished_at - results.c.accepted_at
        with queue.results.engine.connect() as connection:
            durations = (
                connection.execute(
                    select(elapsed)
                    .where(
                        results.c.job_name != "",
                        results.c.status == "completed",
                        results.c.accepted_at > 0,
                        elapsed >= _MIN_RUN_SECONDS,
                        elapsed <= _MAX_RUN_SECONDS,
                    )
                    .order_by(results.c.finished_at.desc())
                    .limit(31)
                )
                .scalars()
                .all()
            )
            accepted = (
                connection.execute(
                    select(results.c.send_id, results.c.accepted_at).where(
                        results.c.send_id.in_(active_ids),
                        results.c.status.in_(("accepted", "generating")),
                        results.c.accepted_at > 0,
                    )
                ).all()
                if active_ids
                else []
            )
        self._durations = [float(value) for value in durations]
        self.samples = len(self._durations)
        self.duration_seconds = (
            round(median(self._durations)) if self.samples >= 3 else _FALLBACK_RUN_SECONDS
        )
        self._accepted = {str(send_id): float(started) for send_id, started in accepted}

    def remaining(self, send_ids: set[str]) -> list[float]:
        durations: list[float] = []
        for send_id in send_ids:
            started = self._accepted.get(send_id, 0.0)
            retry_at = 0.0
            if not started:
                receipt = self.queue.get(send_id)
                if receipt is not None:
                    if receipt.get("status") == "running":
                        started = float_value(receipt.get("lease_acquired_at"))
                    retry_at = float_value(receipt.get("retry_at"))
            remaining = float(self.duration_seconds)
            if started:
                elapsed = max(0.0, self.now - started)
                # A job that outlives the overall median must not display
                # "about one minute" indefinitely. Use the median remaining
                # time of historical runs that survived this long.
                survivors = [duration for duration in self._durations if duration > elapsed]
                if len(survivors) >= 3:
                    remaining = median(survivors) - elapsed
                elif elapsed < self.duration_seconds and self.samples < 3:
                    remaining = self.duration_seconds - elapsed
                remaining = max(_MIN_RUN_SECONDS, remaining)
            if retry_at > self.now:
                remaining = max(remaining, retry_at - self.now + self.duration_seconds)
            durations.append(remaining)
        return durations

    def projection(self, limit: int, send_ids: set[str]) -> SlotProjection:
        return SlotProjection(limit, self.remaining(send_ids), self.duration_seconds)
