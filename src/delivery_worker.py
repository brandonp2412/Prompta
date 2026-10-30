from __future__ import annotations

import argparse
import logging
import math
import os
import socket
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from sqlalchemy.exc import OperationalError

from .config import WorkingHours
from .delivery_browser import (
    BrowserDeliverySender,
    DeliveryBackendUnavailableError,
    SendNotAcceptedError,
)
from .delivery_queue import DeliveryQueueStore
from .history_recovery import run_history_recovery
from .persistence import DEFAULT_RUNTIME_PATH
from .rate_limit import RateLimitError
from .resource_pressure import ResourceAdmission
from .scheduler_runtime import SchedulerRuntime
from .send_outcome import SendOutcomeUnknownError
from .service_health import ServiceHealthStore, notify_watchdog

logger = logging.getLogger(__name__)


def _sqlite_busy(exc: OperationalError) -> bool:
    return isinstance(exc.orig, sqlite3.OperationalError) and (
        "database is locked" in str(exc.orig).lower()
        or "database table is locked" in str(exc.orig).lower()
    )


DEFAULT_STATE_PATH = DEFAULT_RUNTIME_PATH
_LEASE_SECONDS = 300.0
_LEASE_RENEW_SECONDS = 30.0
_LEASE_RENEW_RETRY_SECONDS = 2.0
_MAX_REJECTED_ATTEMPTS = 5
_RETRY_BASE_SECONDS = 2.0
_RETRY_CAP_SECONDS = 300.0


def _retry_delay(attempt: int) -> float:
    exponent = max(0, min(12, int(attempt) - 1))
    return min(_RETRY_CAP_SECONDS, math.ldexp(_RETRY_BASE_SECONDS, exponent))


def _record_int(record: dict[str, object], key: str) -> int:
    value = record.get(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return 0


class DeliveryAdmission:
    def __init__(
        self,
        runtime: SchedulerRuntime,
        resource_admission: Callable[[], tuple[bool, str]] | None = None,
        working_hours: WorkingHours | None = None,
    ) -> None:
        self.runtime = runtime
        self.resource_admission = resource_admission or ResourceAdmission()
        self.working_hours = working_hours
        self._last_resource_state: tuple[bool, str] | None = None

    def __call__(self, *, manual: bool = False) -> tuple[bool, str, float]:
        current = time.time()
        if not manual:
            working_hours = self.working_hours or WorkingHours.load()
            allowed, reason, retry_after = working_hours.admission(now=current)
            if not allowed:
                return False, reason, retry_after

        allowed, reason = self.resource_admission()
        state = (allowed, reason)
        if state != self._last_resource_state:
            try:
                self.runtime.set_resource_admission(allowed, reason)
            except OperationalError as exc:
                if not _sqlite_busy(exc):
                    raise
                logger.warning("Resource admission persistence busy; delaying delivery")
                return False, "SQLite database busy; retrying admission", 1.0
            self._last_resource_state = state
        return allowed, reason, 0.0


class DeliveryLeaseRenewer(Protocol):
    def renew_lease(self, send_id: str, owner: str, *, lease_seconds: float) -> bool: ...


def _renew_lease_until_done(
    queue: DeliveryLeaseRenewer,
    send_id: str,
    owner: str,
    stop: threading.Event,
    lost: threading.Event,
) -> None:
    failures = 0
    wait_seconds = _LEASE_RENEW_SECONDS
    while not stop.wait(wait_seconds):
        try:
            renewed = queue.renew_lease(
                send_id,
                owner,
                lease_seconds=_LEASE_SECONDS,
            )
        except Exception as exc:
            # The renewer is a daemon thread. Never allow it to silently die
            # and leave the sender thinking its lease is still protected.
            failures += 1
            logger.warning(
                "Delivery lease renewal failed send_id=%s attempt=%d error_type=%s",
                send_id, failures, type(exc).__name__,
            )
            if failures >= 3:
                lost.set()
                return
            wait_seconds = _LEASE_RENEW_RETRY_SECONDS
            continue
        if not renewed:
            lost.set()
            return
        failures = 0
        wait_seconds = _LEASE_RENEW_SECONDS


def _retry(
    queue: DeliveryQueueStore,
    record: dict[str, object],
    owner: str,
    *,
    error: str,
    delay: float,
    status: str = "retrying",
) -> None:
    attempt = max(0, _record_int(record, "retry_attempt")) + 1
    retried = queue.retry_claim(
        str(record["send_id"]),
        owner,
        retry_at=time.time() + max(0.0, delay),
        retry_attempt=attempt,
        error=error,
        status=status,
    )
    if not retried:
        logger.warning(
            "Delivery retry receipt was not committed send_id=%s; "
            "the lease may have expired and automatic replay remains disabled",
            record["send_id"],
        )


def _scheduled_job_name(record: dict[str, object]) -> str:
    client_id = str(record.get("client_id") or "")
    prefix = "scheduled:"
    if not client_id.startswith(prefix):
        return ""
    _idempotency_key, separator, job_name = client_id[len(prefix) :].partition(":")
    return job_name if separator else ""


class DeliverySender(Protocol):
    def __call__(self, message: str, *, pin_chat: bool = False) -> None: ...


def _deliver_one(
    queue: DeliveryQueueStore,
    sender: DeliverySender,
    runtime: SchedulerRuntime,
    health: ServiceHealthStore,
    owner: str,
    record: dict[str, object],
) -> None:
    send_id = str(record["send_id"])
    message = str(record.get("message") or "")
    job_name = _scheduled_job_name(record)
    state = runtime.job_state(job_name) if job_name else {}
    once = (
        (
            bool(state.get("pending_delivery_one_time"))
            and state.get("last_delivery_send_id") == send_id
        )
        if job_name
        else str(record.get("client_id") or "").startswith("manual:once:")
    )
    pin_chat = bool(record.get("pin_chat")) or str(record.get("client_id") or "").startswith(
        "manual:once:"
    )
    if job_name and job_name not in runtime.read_jobs() and not once:
        error = f"scheduled job {job_name!r} was removed before delivery"
        if queue.fail_claim(send_id, owner, status="cancelled", error=error):
            logger.info(
                "Cancelled removed scheduled job before delivery send_id=%s job=%s",
                send_id,
                job_name,
            )
        else:
            logger.warning(
                "Could not cancel removed scheduled job send_id=%s job=%s", send_id, job_name
            )
        return

    activity = "dispatch:" + send_id
    health.begin_activity("delivery_worker", activity)
    lease_stop = threading.Event()
    lease_lost = threading.Event()
    renewer = threading.Thread(
        target=_renew_lease_until_done,
        args=(queue, send_id, owner, lease_stop, lease_lost),
        name="prompta-delivery-lease-" + send_id[:8],
        daemon=True,
    )
    renewer.start()

    try:
        try:
            if isinstance(sender, BrowserDeliverySender):
                sender(
                    message,
                    pin_chat=pin_chat,
                    send_id=send_id,
                    job_name=job_name,
                    images=record["images"],
                )
            else:
                sender(message, pin_chat=pin_chat)
        except RateLimitError as exc:
            # A rejected send is retried only as its own queued item. It must
            # never close admission for other independent, parallel deliveries.
            attempt = max(0, _record_int(record, "retry_attempt")) + 1
            # HTTP 429 proves this request was rejected, but does not imply
            # that the user's queued job should permanently fail. Keep its
            # original identity and retry after the server's backoff, even if
            # an extended rate limit spans more than five attempts.
            delay = max(_retry_delay(attempt), float(exc.retry_after))
            _retry(queue, record, owner, error=str(exc), delay=delay, status="rate_limited")
            logger.warning(
                "Rate limited send_id=%s attempt=%d retry_in=%.1fs",
                send_id,
                attempt,
                delay,
            )
            return
        except DeliveryBackendUnavailableError as exc:
            attempt = max(0, _record_int(record, "retry_attempt")) + 1
            delay = _retry_delay(attempt)
            _retry(queue, record, owner, error=str(exc), delay=delay)
            logger.warning(
                "Browser unavailable before dispatch send_id=%s attempt=%d retry_in=%.1fs: %s",
                send_id,
                attempt,
                delay,
                exc,
            )
            return
        except SendNotAcceptedError as exc:
            attempt = max(0, _record_int(record, "retry_attempt")) + 1
            if attempt >= _MAX_REJECTED_ATTEMPTS:
                queue.fail_claim(
                    send_id,
                    owner,
                    status="dead_lettered",
                    error=str(exc),
                )
                logger.error(
                    "ChatGPT rejected delivery send_id=%s after %d attempts: %s",
                    send_id,
                    attempt,
                    exc,
                )
            else:
                delay = _retry_delay(attempt)
                _retry(queue, record, owner, error=str(exc), delay=delay)
                logger.warning(
                    "ChatGPT did not accept delivery send_id=%s attempt=%d retry_in=%.1fs: %s",
                    send_id,
                    attempt,
                    delay,
                    exc,
                )
            return
        except SendOutcomeUnknownError as exc:
            quarantined = queue.fail_claim(
                send_id,
                owner,
                status="outcome_unknown",
                error=str(exc),
            )
            if not quarantined:
                logger.error(
                    "Could not commit uncertain delivery receipt send_id=%s; "
                    "lease expiry must quarantine the send",
                    send_id,
                )
            logger.error(
                "Fresh-chat send outcome is unknown; automatic resend disabled send_id=%s stage=%s: %s",
                send_id,
                exc.stage,
                exc,
            )
            return
        except Exception as exc:
            attempt = max(0, _record_int(record, "retry_attempt")) + 1
            if attempt >= _MAX_REJECTED_ATTEMPTS:
                queue.fail_claim(
                    send_id,
                    owner,
                    status="dead_lettered",
                    error=str(exc),
                )
                logger.exception(
                    "Unexpected delivery failure send_id=%s after %d attempts",
                    send_id,
                    attempt,
                )
            else:
                delay = _retry_delay(attempt)
                _retry(queue, record, owner, error=str(exc), delay=delay)
                logger.exception(
                    "Unexpected delivery failure send_id=%s attempt=%d retry_in=%.1fs",
                    send_id,
                    attempt,
                    delay,
                )
            return

        if lease_lost.is_set():
            logger.error(
                "Delivery lease was lost before completion send_id=%s; refusing stale completion",
                send_id,
            )
            return

        if not queue.complete_claim(send_id, owner):
            logger.error("Could not commit successful delivery receipt send_id=%s", send_id)
            return
        logger.info(
            "Prompta accepted fresh chat and handed off passive capture send_id=%s", send_id
        )
    finally:
        lease_stop.set()
        renewer.join(timeout=1.0)
        health.end_activity("delivery_worker", activity)


def run(
    state_path: Path = DEFAULT_STATE_PATH,
    *,
    chrome_profile: Path | None = None,
    chrome_path: str = "/usr/bin/chromium",
    chrome_debugger_address: str | None = None,
    chrome_auth_timeout_seconds: float = 30.0,
) -> None:
    state_path = state_path.expanduser()
    state_dir = state_path.parent
    queue = DeliveryQueueStore(state_dir / "ui-send-jobs.sqlite3")
    runtime = SchedulerRuntime(state_path, state_path)
    health = ServiceHealthStore(state_path)
    admission = DeliveryAdmission(runtime)
    sender = BrowserDeliverySender(
        state_path,
        profile=chrome_profile,
        chrome_path=chrome_path,
        debugger_address=chrome_debugger_address,
        auth_timeout_seconds=chrome_auth_timeout_seconds,
    )
    owner = socket.gethostname() + ":" + str(os.getpid()) + ":" + uuid.uuid4().hex[:8]

    logger.info("Prompta jobs delivery worker consuming %s", queue.path)
    if hasattr(sender, "results"):
        sender.results.recover_orphans()
    health.reset_activity("delivery_worker")
    notify_watchdog()
    recovery_stop = threading.Event()
    recovery_thread = threading.Thread(
        target=run_history_recovery,
        args=(sender.results, runtime, sender._new_driver),
        kwargs={"stop": recovery_stop},
        name="prompta-history-recovery",
        daemon=True,
    )
    recovery_thread.start()

    try:
        while True:
            try:
                health.beat("delivery_worker")
                notify_watchdog()

                hours_allowed, _reason, _retry_after = WorkingHours.load().admission()
                allowed, reason, retry_after = admission(manual=not hours_allowed)
                if not allowed:
                    if reason:
                        logger.debug("Delivery admission blocked: %s", reason)
                    time.sleep(min(1.0, max(0.1, retry_after)) if retry_after > 0 else 1.0)
                    continue

                record = queue.claim_next(
                    owner,
                    lease_seconds=_LEASE_SECONDS,
                    manual_only=not hours_allowed,
                )
                if record is None:
                    time.sleep(0.5)
                    continue

                _deliver_one(queue, sender, runtime, health, owner, record)
            except OperationalError as exc:
                if not _sqlite_busy(exc):
                    raise
                logger.warning(
                    "SQLite busy in delivery worker; will retry without dispatching", exc_info=True
                )
                time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        recovery_stop.set()
        recovery_thread.join(timeout=2.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Prompta jobs delivery worker")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument(
        "--chrome-profile",
        type=Path,
        default=(
            Path(os.environ["PROMPTA_CHROME_PROFILE"])
            if os.environ.get("PROMPTA_CHROME_PROFILE")
            else None
        ),
    )
    parser.add_argument(
        "--chrome-path",
        default=os.environ.get("PROMPTA_CHROME_PATH", "/usr/bin/chromium"),
    )
    parser.add_argument(
        "--chrome-debugger-address",
        default=os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9222"),
    )
    parser.add_argument(
        "--chrome-auth-timeout-seconds",
        type=float,
        default=float(os.environ.get("PROMPTA_CHROME_AUTH_TIMEOUT_SECONDS", "30")),
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(
        args.state,
        chrome_profile=args.chrome_profile,
        chrome_path=args.chrome_path,
        chrome_debugger_address=args.chrome_debugger_address,
        chrome_auth_timeout_seconds=args.chrome_auth_timeout_seconds,
    )


if __name__ == "__main__":
    main()
