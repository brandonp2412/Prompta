from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from websockets.exceptions import ConnectionClosed

from .cache import ActiveConversation
from .conversation_actions import SendNotAcceptedError, SendVerificationError
from .jobs import PromptJob, _next_daily_epoch, remove_job
from .rate_limit import RateLimitBackoff, RateLimitError
from .scheduler_runtime import SchedulerRuntime

logger = logging.getLogger(__name__)

_FAILURE_RETRY_SECONDS = 300.0
_MAX_ACTIVE_SCHEDULED_JOBS = 4
_MAX_ACTIVE_BROWSER_CONVERSATIONS = 24


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()


def scheduled_job_prompt(job: PromptJob) -> str:
    if not job.source_revision:
        return job.prompt
    return (
        f"{job.prompt}\n\n"
        "Prompta job context: the Prompta source revision when this job was created was "
        f"{job.source_revision}. Use this revision when checking whether a reported bug predates "
        "later code changes."
    )


class SchedulerExecution:
    def __init__(
        self,
        scheduler: SchedulerRuntime,
        active: dict[str, ActiveConversation],
        jobs_file: Path,
        send_once: Callable[..., Any],
        send_reply: Callable[..., Any],
        sync_conversation: Callable[..., Any],
        interrupt_active: Callable[[], None],
        current_driver: Callable[[], Any],
        set_driver: Callable[[Any], None],
        conversation_complete: Callable[[str], bool] | None = None,
        conversation_busy: Callable[[str], bool] | None = None,
        resource_admission: Callable[[], tuple[bool, str]] | None = None,
    ) -> None:
        self.scheduler = scheduler
        self.active = active
        self.jobs_file = jobs_file
        self.send_once_callback = send_once
        self.send_reply_callback = send_reply
        self.sync_conversation_callback = sync_conversation
        self.interrupt_active = interrupt_active
        self.current_driver = current_driver
        self.set_driver = set_driver
        self.conversation_complete = conversation_complete or (lambda _conversation_id: False)
        self.conversation_busy = conversation_busy
        self.resource_admission = resource_admission or (lambda: (True, ""))
        self._resource_pressure_reason = ""
        self._resource_pressure_logged_at = 0.0
        self.once_requests: asyncio.Queue[tuple[str, list[str], asyncio.Future[str]]] = (
            asyncio.Queue()
        )
        self.reply_requests: asyncio.Queue[tuple[str, str, list[str], asyncio.Future[str]]] = (
            asyncio.Queue()
        )
        self.sync_requests: asyncio.Queue[tuple[str, asyncio.Future[int]]] = asyncio.Queue()

    @property
    def driver(self) -> Any:
        return self.current_driver()

    @driver.setter
    def driver(self, value: Any) -> None:
        self.set_driver(value)

    def can_start_new_conversation(self) -> bool:
        if (
            not self.scheduler.unattended_mode()
            and len(self.active) >= _MAX_ACTIVE_BROWSER_CONVERSATIONS
        ):
            return False

        allowed, reason = self.resource_admission()
        now = time.monotonic()
        if allowed:
            if self._resource_pressure_reason:
                logger.info("Prompta host pressure cleared; queue admission resumed")
            self._resource_pressure_reason = ""
            self._resource_pressure_logged_at = 0.0
            return True

        if (
            self._resource_pressure_logged_at <= 0
            or now - self._resource_pressure_logged_at >= 60.0
        ):
            logger.warning(
                "Prompta deferred new queue work: %s", reason or "host resource pressure"
            )
            self._resource_pressure_logged_at = now
        self._resource_pressure_reason = reason
        return False

    def _delivery_idempotency_key(self, job: PromptJob) -> str:
        state = self.scheduler.job_state(job.name)
        marker = 0.0
        try:
            last_sent_at = float(state.get("last_sent_at") or 0.0)
            last_uncertain_send_at = float(state.get("last_uncertain_send_at") or 0.0)
        except (TypeError, ValueError):
            last_sent_at = 0.0
            last_uncertain_send_at = 0.0
        keys = (
            ("last_uncertain_send_at",)
            if last_uncertain_send_at > last_sent_at
            else ("next_due_at_epoch", "initial_due_at_epoch", "last_sent_at")
        )
        for key in keys:
            try:
                value = float(state.get(key) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                marker = value
                break
        if job.run_at_epoch is not None:
            marker = float(job.run_at_epoch)
        raw = f"{job.name}\0{prompt_hash(job.prompt)}\0{marker:.6f}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def run_job(self, job: PromptJob, *, now: float) -> bool:
        """Make the durable scheduling decision; browser delivery is a separate step."""
        if self.scheduler.job_state(job.name).get("paused") is True:
            return False
        if self.scheduler.due_in(job, now) > 0:
            return False
        if self.scheduler.has_queued_delivery(job.name):
            return False

        prompt = scheduled_job_prompt(job)
        intent_id, created = self.scheduler.enqueue_delivery_intent(
            job,
            prompt=prompt,
            job_prompt_sha256=prompt_hash(job.prompt),
            idempotency_key=self._delivery_idempotency_key(job),
            queued_at=now,
        )
        if not created:
            return False
        if job.run_at_epoch is not None:
            remove_job(self.jobs_file, job.name)
            logger.info(
                "Prompta one-time job=%s durably queued delivery_intent=%d and was removed",
                job.name,
                intent_id,
            )
        else:
            logger.info(
                "Prompta job=%s durably queued delivery_intent=%d",
                job.name,
                intent_id,
            )
        return True

    async def drain_scheduled_deliveries(self, *, now: float | None = None) -> bool:
        attempted_at = time.time() if now is None else now
        if not self.can_start_new_conversation():
            return False
        machine_gun_mode = self.scheduler.unattended_mode()
        active_scheduled_jobs = sum(
            1 for active in self.active.values() if active.job_name and active.job_name != "once"
        )
        if not machine_gun_mode and active_scheduled_jobs >= _MAX_ACTIVE_SCHEDULED_JOBS:
            return False
        if self.scheduler.global_backoff.remaining() > 0:
            return False
        if self.scheduler.send_gap_remaining(attempted_at) > 0:
            return False

        intent = next(
            (
                candidate
                for candidate in self.scheduler.pending_delivery_intents(attempted_at)
                if (
                    machine_gun_mode
                    or not any(
                        active.job_name == candidate["job_name"] for active in self.active.values()
                    )
                )
                and self.scheduler.backoffs.setdefault(
                    candidate["job_name"], RateLimitBackoff()
                ).remaining()
                <= 0
                and self.scheduler.failure_retry_remaining(candidate["job_name"], attempted_at) <= 0
            ),
            None,
        )
        if intent is None:
            return False

        job_name = intent["job_name"]
        backoff = self.scheduler.backoffs.setdefault(job_name, RateLimitBackoff())
        self.scheduler.update_scheduler_state({"last_attempt_at": attempted_at})
        self.scheduler.mark_delivery_attempt(intent["id"], attempted_at)
        try:
            try:
                conversation_id = await self.send_once_callback(
                    intent["prompt"],
                    job_name=job_name,
                )
            except SendNotAcceptedError:
                logger.warning(
                    "Prompta delivery intent=%d job=%s was not accepted; retrying once immediately",
                    intent["id"],
                    job_name,
                )
                conversation_id = await self.send_once_callback(
                    intent["prompt"],
                    job_name=job_name,
                )
        except RateLimitError as exc:
            delay = self.scheduler.record_global_rate_limit(exc)
            self.scheduler.mark_failure(job_name, str(exc))
            self.scheduler.defer_delivery(
                intent["id"],
                error=str(exc),
                available_at=attempted_at + delay,
            )
            logger.warning(
                "Prompta delivery intent=%d job=%s rate limited account-wide; retrying after %.1fs",
                intent["id"],
                job_name,
                delay,
            )
            return False
        except SendVerificationError as exc:
            uncertain_at = time.time() if now is None else attempted_at
            self.scheduler.mark_delivery_uncertain(
                intent["id"],
                job_name,
                attempted_at=uncertain_at,
                error=str(exc),
            )
            logger.warning(
                "Prompta delivery intent=%d job=%s outcome uncertain; not retrying this intent: %s",
                intent["id"],
                job_name,
                exc,
            )
            if self.driver is not None:
                self.interrupt_active()
                await self.driver.close()
                self.driver = None
            return False
        except (ConnectionClosed, OSError, RuntimeError) as exc:
            logger.exception(
                "Prompta delivery intent=%d job=%s send failed: %s",
                intent["id"],
                job_name,
                exc,
            )
            retry_until = attempted_at + _FAILURE_RETRY_SECONDS
            self.scheduler.mark_failure(job_name, str(exc), retry_until=retry_until)
            self.scheduler.defer_delivery(
                intent["id"],
                error=str(exc),
                available_at=retry_until,
            )
            browser_restart_required = bool(
                self.driver is not None and self.driver.needs_browser_restart is True
            )
            if self.driver is not None:
                self.interrupt_active()
                if not browser_restart_required:
                    await self.driver.close()
                    self.driver = None
            self.scheduler.failure_retry_until[job_name] = retry_until
            if browser_restart_required:
                raise RuntimeError(
                    "Browser session was lost; restarting Prompta to recycle browser"
                ) from exc
            return False

        sent_at = time.time() if now is None else attempted_at
        next_due_at = 0.0
        if not intent["one_time"]:
            if intent["daily_at"] is not None:
                next_due_at = _next_daily_epoch(intent["daily_at"], sent_at)
            else:
                delivery_job = PromptJob(
                    job_name,
                    "",
                    intent["interval_seconds"],
                    exact_interval=intent["exact_interval"],
                )
                next_due_at = sent_at + self.scheduler.next_delay(delivery_job)
        backoff.reset()
        self.scheduler.failure_retry_until.pop(job_name, None)
        self.scheduler.complete_delivery(
            intent["id"],
            job_name,
            conversation_id=conversation_id,
            sent_at=sent_at,
            job_updates={
                "prompt_sha256": intent["job_prompt_sha256"],
                "last_sent_at": sent_at,
                "last_uncertain_send_at": 0.0,
                "initial_due_at_epoch": 0.0,
                "next_due_at_epoch": next_due_at,
                "last_conversation_id": conversation_id,
                "rate_limit_backoff": backoff.snapshot(),
                "failure_retry_until_epoch": 0.0,
                "status": "healthy",
                "status_message": "",
                "status_at": sent_at,
            },
        )
        logger.info(
            "Prompta delivered intent=%d job=%s conversation=%s",
            intent["id"],
            job_name,
            conversation_id,
        )
        return True

    async def drain_once_requests(self) -> bool:
        did_work = False
        while True:
            if not self.can_start_new_conversation():
                return did_work
            remaining = self.scheduler.global_backoff.remaining()
            attempted_at = time.time()
            if remaining <= 0 and self.scheduler.send_gap_remaining(attempted_at) > 0:
                return did_work
            try:
                prompt, attachments, future = self.once_requests.get_nowait()
            except asyncio.QueueEmpty:
                return did_work
            try:
                if remaining > 0:
                    raise RateLimitError(
                        "ChatGPT account-wide rate limit backoff is active",
                        retry_after=max(1, int(remaining + 0.999)),
                    )
                self.scheduler.update_scheduler_state({"last_attempt_at": attempted_at})
                conversation_id = await self.send_once_callback(prompt, attachments=attachments)
            except RateLimitError as exc:
                self.scheduler.record_global_rate_limit(exc)
                if not future.done():
                    future.set_exception(exc)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            else:
                if not future.done():
                    future.set_result(conversation_id)
                did_work = True
            finally:
                self.once_requests.task_done()

    def reply_target_is_busy(self, conversation_id: str) -> bool:
        if self.scheduler.unattended_mode() or self.conversation_complete(conversation_id):
            return False
        if self.conversation_busy is not None:
            return self.conversation_busy(conversation_id)
        return any(
            active.conversation_id == conversation_id and active.settled_at <= 0
            for active in self.active.values()
        )

    async def drain_reply_requests(self) -> bool:
        did_work = False
        pending = self.reply_requests.qsize()
        for _ in range(pending):
            remaining = self.scheduler.global_backoff.remaining()
            attempted_at = time.time()
            if remaining <= 0 and self.scheduler.send_gap_remaining(attempted_at) > 0:
                return did_work
            try:
                item = self.reply_requests.get_nowait()
            except asyncio.QueueEmpty:
                return did_work
            conversation_id, prompt, attachments, future = item
            if self.reply_target_is_busy(conversation_id):
                self.reply_requests.task_done()
                await self.reply_requests.put(item)
                continue
            try:
                if remaining > 0:
                    raise RateLimitError(
                        "ChatGPT account-wide rate limit backoff is active",
                        retry_after=max(1, int(remaining + 0.999)),
                    )
                self.scheduler.update_scheduler_state({"last_attempt_at": attempted_at})
                result = await self.send_reply_callback(
                    conversation_id, prompt, attachments=attachments
                )
            except RateLimitError as exc:
                self.scheduler.record_global_rate_limit(exc)
                if not future.done():
                    future.set_exception(exc)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            else:
                if not future.done():
                    future.set_result(result)
                did_work = True
            finally:
                self.reply_requests.task_done()
        return did_work

    async def drain_sync_requests(self) -> bool:
        did_work = False
        while True:
            try:
                conversation_id, future = self.sync_requests.get_nowait()
            except asyncio.QueueEmpty:
                return did_work
            try:
                message_count = await self.sync_conversation_callback(conversation_id)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            else:
                if not future.done():
                    future.set_result(message_count)
                did_work = True
            finally:
                self.sync_requests.task_done()
