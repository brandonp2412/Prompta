"""Paced, exact-conversation recovery of Prompta-owned responses.

Normal recovery stays read-only. Deployment-interrupted captures may resume
configured connector approvals after exact branch verification in a new owned
tab. No recovery path resends prompts, lists account history, or reads other chats.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol, runtime_checkable
from uuid import UUID

from patchright.async_api import Error as PatchrightError

from .browser_script_loader import load_browser_script
from .config import ConnectorApproval
from .deployment_gate import DeploymentGate, deployment_recovery_priority
from .patchright_driver import BrowserSecurityChallengeError
from .rate_limit import RateLimitError, is_rate_limited_text
from .reply_contracts import ManualReplyStore
from .response_capture import CaptureResult, normalize_dom_snapshot
from .response_store import HISTORY_READ_INTERVAL_SECONDS, ResponseStore
from .scheduler_runtime import SchedulerRuntime
from .strict_types import int_value

logger = logging.getLogger(__name__)
_LOOKUP_TIMEOUT_SECONDS = 55.0
_READ_PROBE_SECONDS = 25.0
_RESUMED_COMPLETION_GRACE_SECONDS = 3.0
_HISTORY_CLOSE_TIMEOUT_SECONDS = 5.0
_SECURITY_PAUSE_BASE_SECONDS = 30 * 60.0
_SECURITY_PAUSE_CAP_SECONDS = 4 * 3600.0
_APPROVAL_SCRIPT = load_browser_script("approve_connector.js")


class HistoryDriver(Protocol):
    context: str

    async def connect(self) -> None: ...
    async def navigate(self, url: str, *, context: str | None = None) -> None: ...
    async def dom_state(self) -> dict[str, object]: ...
    async def eval(self, expression: str) -> object: ...
    async def close(self) -> None: ...


@runtime_checkable
class _HistoryRateLimitSignal(Protocol):
    def history_rate_limited(self) -> bool: ...


@runtime_checkable
class _ApprovalRetryDriver(Protocol):
    async def click_stuck_connector_approval(self) -> object: ...


@runtime_checkable
class _ReadLimitAPI(Protocol):
    def read_backoff_remaining(self) -> float: ...
    def record_read_rate_limit(self, exc: RateLimitError) -> float: ...


@runtime_checkable
class _LegacyLimitAPI(Protocol):
    def global_backoff_remaining(self) -> float: ...
    def record_global_rate_limit(self, exc: RateLimitError) -> float: ...


def _guarded_approval_script(probe: str, *, single_user_only: bool) -> str:
    """Recheck exact ownership inside the same page evaluation as the click.

    Historical probes remain read-only. This separate continuation operation
    can mutate only a recognized permission belonging to the verified final
    Prompta-owned turn; never an unrelated or later user turn.
    """
    single_user_guard = (
        "const main = document.querySelector('main');"
        "if (!main) return false;"
        "const selector = '[data-message-author-role=\"user\"],"
        "[data-chatgpt-search-unit-key$=\":user\"],"
        "[data-content-search-unit-key$=\":user\"]';"
        "const users = [...main.querySelectorAll(selector)].filter(node => "
        "node.isConnected && node.getClientRects().length > 0 && "
        "!node.parentElement?.closest(selector));"
        "if (users.length !== 1) return false;"
        if single_user_only else ""
    )
    return (
        "(async () => { const proof = " + probe + ";"
        "if (proof?.verified !== true || proof?.ambiguous === true || "
        "proof?.rate_limited === true) return false;"
        + single_user_guard +
        "return await " + _APPROVAL_SCRIPT + "; })()"
    )


def _guarded_approval_identity(probe: str, *, single_user_only: bool) -> str:
    """Re-verify ownership before a real Playwright retry of a stuck DOM click."""
    script = _guarded_approval_script(probe, single_user_only=single_user_only)
    # The permission action is replaced with a pure check, preserving all
    # guards in exactly the same page world as the fallback's preflight.
    return script.replace("return await " + _APPROVAL_SCRIPT + ";", "return true;")


def _read_backoff_remaining(runtime: object) -> float:
    # The account admission refactor gives read throttling its own persisted gate.
    if isinstance(runtime, _ReadLimitAPI):
        return runtime.read_backoff_remaining()
    if isinstance(runtime, _LegacyLimitAPI):
        return runtime.global_backoff_remaining()
    raise RuntimeError("Read rate-limit admission is unavailable")


def _record_read_rate_limit(runtime: object, exc: RateLimitError) -> float:
    if isinstance(runtime, _ReadLimitAPI):
        return runtime.record_read_rate_limit(exc)
    if isinstance(runtime, _LegacyLimitAPI):
        return runtime.record_global_rate_limit(exc)
    raise RuntimeError("Read rate-limit recording is unavailable")


class HistoryRecovery:
    def __init__(
        self,
        results: ResponseStore,
        runtime: SchedulerRuntime,
        driver_factory: Callable[[], HistoryDriver],
        *,
        approval_enabled: bool | None = None,
    ) -> None:
        self.approval_enabled = (
            ConnectorApproval.load().enabled if approval_enabled is None else approval_enabled
        )
        self.results = results
        self.replies = ManualReplyStore(results.path)
        self.runtime = runtime
        self.driver_factory = driver_factory

    async def _read_original_response(
        self, conversation_id: str, original_prompt: str,
        *, resume_approvals: bool = False,
    ) -> CaptureResult | None:
        script = (
            load_browser_script("historical_response_probe.js")
            .replace("__CONVERSATION__", json.dumps(conversation_id))
            .replace("__ORIGINAL_PROMPT__", json.dumps(original_prompt))
        )
        return await self._read_probe(
            conversation_id, script, resume_approvals=resume_approvals,
            single_user_only=True,
        )

    async def _read_reply_response(
        self, conversation_id: str, original_prompt: str, reply_text: str, parent_id: str,
        *, resume_approvals: bool = False,
    ) -> CaptureResult | None:
        script = (
            load_browser_script("historical_reply_probe.js")
            .replace("__CONVERSATION__", json.dumps(conversation_id))
            .replace("__ORIGINAL_PROMPT__", json.dumps(original_prompt))
            .replace("__REPLY_TEXT__", json.dumps(reply_text))
            .replace("__PARENT__", json.dumps(parent_id))
        )
        return await self._read_probe(
            conversation_id, script, resume_approvals=resume_approvals,
            single_user_only=False,
        )

    async def _read_probe(
        self, conversation_id: str, script: str, *,
        resume_approvals: bool = False, single_user_only: bool = False,
    ) -> CaptureResult | None:
        driver = self.driver_factory()
        last_partial: CaptureResult | None = None
        last_verified: CaptureResult | None = None
        complete_since: float | None = None
        approval_script = (
            _guarded_approval_script(script, single_user_only=single_user_only)
            if resume_approvals else ""
        )
        identity_script = (
            _guarded_approval_identity(script, single_user_only=single_user_only)
            if resume_approvals else ""
        )
        try:
            await driver.connect()
            await driver.navigate(
                "https://chatgpt.com/c/" + conversation_id, context=driver.context,
            )
            deadline = asyncio.get_running_loop().time() + _READ_PROBE_SECONDS
            while asyncio.get_running_loop().time() < deadline:
                try:
                    state = await driver.dom_state()
                except (TimeoutError, PatchrightError):
                    if (
                        isinstance(driver, _HistoryRateLimitSignal)
                        and driver.history_rate_limited()
                    ):
                        raise RateLimitError("ChatGPT conversation read returned HTTP 429") from None
                    # A single slow hydration/CDP read is not an account or
                    # branch failure. Stay on the same exact chat and retry
                    # without consuming another global navigation slot.
                    await asyncio.sleep(2.0)
                    continue
                if (
                    isinstance(driver, _HistoryRateLimitSignal)
                    and driver.history_rate_limited()
                ):
                    raise RateLimitError("ChatGPT conversation read returned HTTP 429")
                limit_text = str(state.get("rate_limit_text") or "")
                if is_rate_limited_text(limit_text):
                    raise RateLimitError.from_text(limit_text)
                try:
                    payload = await driver.eval(script)
                except (TimeoutError, PatchrightError):
                    if (
                        isinstance(driver, _HistoryRateLimitSignal)
                        and driver.history_rate_limited()
                    ):
                        raise RateLimitError("ChatGPT conversation read returned HTTP 429") from None
                    await asyncio.sleep(2.0)
                    continue
                if isinstance(payload, dict):
                    if payload.get("rate_limited") is True:
                        raise RateLimitError()
                    if payload.get("ambiguous") is True:
                        complete_since = None
                        # Hydration and streaming can transiently render two
                        # candidate nodes. Keep observing this same permitted
                        # tab until the deadline, without navigating again.
                        await asyncio.sleep(2.0)
                        continue
                    if payload.get("stream_error") is True:
                        logger.warning("Historical recovery found a response-stream error")
                        return None
                    if payload.get("verified") is not True:
                        complete_since = None
                    if (payload.get("verified") is True
                            and payload.get("pathname") == "/c/" + conversation_id):
                        result = normalize_dom_snapshot(payload)
                        if not result.conversation_id:
                            # The exact user turn and parent can be verified even
                            # before ChatGPT renders an assistant placeholder.
                            result = CaptureResult(
                                "dom", "unknown", "", conversation_id, None,
                                str(payload.get("verified_parent_id") or "") or None,
                                verified_loaded=True,
                            )
                        elif result.conversation_id == conversation_id:
                            result = replace(result, verified_loaded=True)
                        if result.conversation_id == conversation_id:
                            last_verified = result
                            grant: object = False
                            if approval_script:
                                # Unlike historical reads, this continuation may
                                # grant connector access only after its exact
                                # branch is reverified inside the click evaluation.
                                try:
                                    grant = await driver.eval(approval_script)
                                    if grant == "stuck" and isinstance(driver, _ApprovalRetryDriver):
                                        if await driver.eval(identity_script) is True:
                                            grant = await driver.click_stuck_connector_approval()
                                except (TimeoutError, PatchrightError) as exc:
                                    logger.info(
                                        "Recovered capture approval scan unavailable error_type=%s",
                                        type(exc).__name__,
                                    )
                                    grant = "pending"  # Never finalize on an uncertain permission check.
                                if grant is True or grant in ("progress", "pending", "stuck"):
                                    logger.info(
                                        "event=history_recovery_permission conversation_id=%s outcome=%s",
                                        conversation_id, grant,
                                    )
                            awaiting_permission = grant is True or grant in (
                                "progress", "pending", "stuck"
                            )
                            if result.text or result.tool_calls or result.verified_generating:
                                last_partial = (
                                    replace(result, status="partial")
                                    if awaiting_permission and result.status == "complete"
                                    else result
                                )
                            if awaiting_permission:
                                complete_since = None
                                await asyncio.sleep(0.2 if grant is True or grant == "progress" else 2.0)
                                continue  # Catch successive permissions or hydrate controls.
                            if result.status == "complete" and (result.text or result.tool_calls):
                                if approval_script:
                                    # A copy-ready response can be followed by another
                                    # tool permission after a delayed continuation.
                                    # Require stable finality while watching this
                                    # same exact tab, without another navigation.
                                    now = asyncio.get_running_loop().time()
                                    if complete_since is None:
                                        complete_since = now
                                    if now - complete_since < _RESUMED_COMPLETION_GRACE_SECONDS:
                                        last_partial = replace(result, status="partial")
                                        await asyncio.sleep(1.0)
                                        continue
                                return result
                            complete_since = None
                await asyncio.sleep(2.0)
            return last_partial or last_verified
        finally:
            try:
                # Cleanup is best effort. A failed CDP disconnect must not
                # discard a verified response that was already read.
                await asyncio.wait_for(driver.close(), timeout=_HISTORY_CLOSE_TIMEOUT_SECONDS)
            except Exception as exc:
                logger.warning(
                    "Historical recovery browser cleanup failed error_type=%s",
                    type(exc).__name__,
                )

    def _newest_pinned_due(self, *, now: float) -> dict[str, object] | None:
        """Sweep least-attempted pinned turns, newest activity first within a sweep."""
        originals = self.results.next_history_recovery(now=now, pinned_only=True)
        replies = self.replies.next_history_reply_recovery(now=now, pinned_only=True)
        choices = [row for row in (originals, replies) if row is not None]

        def priority(row: dict[str, object]) -> tuple[int, float]:
            activity = row.get("activity_at")
            recency = float(activity) if isinstance(activity, (int, float)) else float("-inf")
            return (-int_value(row.get("attempt_count")), recency)

        return max(choices, key=priority, default=None)

    def _next_automatic_candidate(
        self, *, now: float, priority_sends: tuple[str, ...],
        priority_replies: tuple[str, ...], deployment_only: bool = False,
    ) -> dict[str, object] | None:
        """Choose a deployment capture, or any incomplete chat for an explicit probe.

        Background network recovery is restricted to deployment inventory.
        Replies and original sends share the same persisted recovery budget.
        """
        options = (
            (True, self.replies.next_history_reply_recovery(
                now=now, priority_ids=priority_replies,
            ) if priority_replies else None),
            (True, self.results.next_history_recovery(
                now=now, priority_ids=priority_sends,
            ) if priority_sends else None),
            (False, self.replies.next_history_reply_recovery(now=now)
             if not deployment_only else None),
            (False, self.results.next_history_recovery(now=now)
             if not deployment_only else None),
        )

        def priority(item: tuple[bool, dict[str, object]]) -> tuple[int, float, bool]:
            in_deployment, candidate = item
            activity = candidate.get("activity_at")
            recency = float(activity) if isinstance(activity, (float, int)) else float("-inf")
            return (-int_value(candidate.get("attempt_count")), recency, in_deployment)

        available = [(deployed, row) for deployed, row in options if row is not None]
        return max(available, key=priority)[1] if available else None

    def _next_requested_candidate(
        self, requests: list[str], *, now: float,
    ) -> tuple[dict[str, object] | None, str]:
        """Try never-probed manual turns before repeatedly failing older requests."""
        best: dict[str, object] | None = None
        best_target = ""
        for target in requests:
            reply_id = target.removeprefix("reply:") if target.startswith("reply:") else ""
            candidate = (
                self.replies.next_history_reply_recovery(now=now, priority_ids=(reply_id,))
                if reply_id else self.results.next_history_recovery(
                    now=now, priority_ids=(target,),
                )
            )
            if candidate is not None:
                if (best is None or int_value(candidate.get("attempt_count"))
                        < int_value(best.get("attempt_count"))):
                    best, best_target = candidate, target
                continue
            # Keep active captures and temporarily unverifiable parents queued.
            # Only terminal or missing turns consume the durable recovery intent.
            row = self.replies.get(reply_id) if reply_id else self.results.get(target)
            if row is None or row["status"] in ("completed", "stopped", "cancelled"):
                self.results.clear_manual_recovery_request(target)
        return best, best_target

    def recover_once(
        self, *, now: float | None = None, preferred_send_id: str | None = None,
        owned_tab_recovery: bool = False, background: bool = False,
    ) -> bool:
        """Probe one chat; background network reads require demand or deploy inventory.

        Explicit calls and surviving owned-tab probes may inspect older chats.
        Pinning alone never authorizes background network recovery.
        """
        at = time.time() if now is None else now
        if (
            (not owned_tab_recovery and _read_backoff_remaining(self.runtime) > 0)
            or self.results.history_recovery_security_pause_remaining(now=at) > 0
            or self.results.history_recovery_global_pace_remaining(now=at) > 0
        ):
            return False
        # Newest eligible pinned chats take precedence. Deployment-interrupted
        # captures and explicit manual requests remain the fallbacks, all under
        # the same single verified recovery slot.
        priority_sends, priority_replies = deployment_recovery_priority(self.results.path.parent)
        manual_requests = (
            self.results.pending_manual_recovery_requests()
            if preferred_send_id is None else []
        )
        # Untried explicit requests get the next available non-pinned slot;
        # retries retain one in three slots so automatic recovery progresses.
        requested, requested_target = self._next_requested_candidate(manual_requests, now=at)
        slot_number = self.results.history_recovery_global_attempt_count() % 3
        manual_slot = requested is not None and (
            background or
            slot_number == 0 or (
                slot_number == 2 and int_value(requested.get("attempt_count")) == 0
            )
        )
        manual_target = requested_target if manual_slot else ""
        candidate = requested if manual_slot else None
        if candidate is None:
            candidate = (
                self.replies.next_history_reply_recovery(
                    now=at, priority_ids=(preferred_send_id.removeprefix("reply:"),),
                )
                if preferred_send_id is not None and preferred_send_id.startswith("reply:")
                else self.results.next_history_recovery(
                    now=at, priority_ids=(preferred_send_id,),
                ) if preferred_send_id is not None else (
                    None if background else self._newest_pinned_due(now=at)
                )
            )
        if candidate is None and preferred_send_id is None:
            candidate = self._next_automatic_candidate(
                now=at, priority_sends=priority_sends, priority_replies=priority_replies,
                deployment_only=background,
            )
        if candidate is None and preferred_send_id is None:
            candidate, manual_target = self._next_requested_candidate(manual_requests, now=at)
        if candidate is None:
            return False
        if not self.results.reserve_history_recovery_global_slot(
            now=at, interval=HISTORY_READ_INTERVAL_SECONDS,
        ):
            return False
        reply_id = str(candidate["reply_id"]) if "reply_id" in candidate else ""
        send_id = "reply:" + reply_id if reply_id else str(candidate["send_id"])
        # Automatic pinned/owned-tab probes must consume an explicit request
        # for the same turn, even if it was not chosen by the manual branch.
        if not manual_target and send_id in (
            manual_requests if preferred_send_id is None else
            self.results.pending_manual_recovery_requests()
        ):
            manual_target = send_id
        conversation_id = str(candidate["conversation_id"])
        prompt = str(candidate["user_text"])
        allow_resume = self.approval_enabled and bool(
            manual_target or owned_tab_recovery
            or (reply_id in priority_replies if reply_id else send_id in priority_sends)
        )
        logger.info(
            "event=history_recovery_started send_id=%s manual=%s owned_tab=%s resume_approvals=%s",
            send_id, bool(manual_target), owned_tab_recovery, allow_resume,
        )
        try:
            if str(UUID(conversation_id)) != conversation_id.lower():
                logger.warning("Historical recovery skipped invalid conversation identity send_id=%s", send_id)
            else:
                if reply_id:
                    probe = self._read_reply_response(
                        conversation_id, str(candidate["original_prompt"]),
                        prompt, str(candidate["parent_id"]),
                        **({"resume_approvals": True} if allow_resume else {}),
                    )
                else:
                    probe = self._read_original_response(
                        conversation_id, prompt,
                        **({"resume_approvals": True} if allow_resume else {}),
                    )
                result = asyncio.run(asyncio.wait_for(probe, timeout=_LOOKUP_TIMEOUT_SECONDS))
                if (result is not None and result.verified_loaded
                        and result.conversation_id == conversation_id):
                    observed = (
                        self.replies.observe_history_loaded(
                            reply_id, conversation_id, result.parent_id, now=at,
                        ) if reply_id else
                        self.results.observe_history_generating(send_id, conversation_id, now=at)
                    )
                    if observed:
                        logger.info("event=history_recovery_verified_page send_id=%s", send_id)
                elif (result is not None and result.verified_generating and not reply_id
                      and result.conversation_id == conversation_id):
                    self.results.observe_history_generating(send_id, conversation_id, now=at)
                recovered = result is not None and (
                    self.replies.recover_historical_reply(reply_id, result, now=at)
                    if reply_id else self.results.recover_historical_response(send_id, result, now=at)
                )
                stored = self.replies.get(reply_id) if reply_id else self.results.get(send_id)
                logger.info(
                    "event=history_recovery_observed send_id=%s result=%s text_chars=%s "
                    "stored_status=%s stored_text_chars=%s merged=%s message_id=%s "
                    "stored_message_id=%s turn_message_ids=%s",
                    send_id, result.status if result is not None else "unverified",
                    len(result.text) if result is not None else 0,
                    stored["status"] if stored is not None else "missing",
                    len(str(stored["assistant_text"])) if stored is not None else 0,
                    recovered,
                    result.message_id if result is not None else None,
                    stored["message_id"] if stored is not None else None,
                    result.turn_message_ids if result is not None else (),
                )
                if recovered and result is not None and result.status == "complete":
                    # A complete-looking DOM snapshot may only merge tool
                    # metadata while preserving a longer interrupted answer.
                    # Report success only after durable storage is terminal.
                    if stored is not None and stored["status"] == "completed":
                        # A local surviving-tab DOM check does not prove that
                        # account-wide HTTP history reads have recovered from 429.
                        if not owned_tab_recovery:
                            self.runtime.record_read_success()
                        logger.info("Historical response recovered send_id=%s", send_id)
                        if manual_target:
                            self.results.clear_manual_recovery_request(manual_target)
                        return True
        except RateLimitError as exc:
            # Only the account-wide read gate owns Retry-After. Never block
            # a single chat independently after this failed observation.
            _record_read_rate_limit(self.runtime, exc)
            logger.warning("Historical recovery paused for account rate limit")
        except BrowserSecurityChallengeError:
            # A challenge is not proof that the answer is unavailable.
            failures = self.results.history_recovery_security_failures(now=at)
            pause = min(
                _SECURITY_PAUSE_CAP_SECONDS,
                _SECURITY_PAUSE_BASE_SECONDS * 2 ** min(failures, 3),
            )
            self.results.pause_history_recovery_security(until=at + pause, now=at)
            logger.warning("Historical recovery paused for browser security challenge")
        except Exception as exc:
            logger.warning(
                "Historical recovery will retry send_id=%s error_type=%s",
                send_id, type(exc).__name__,
            )
        self.results.schedule_history_recovery(send_id, now=at)
        if manual_target:
            self.results.defer_manual_recovery_request(manual_target, now=at)
        return False


def _network_recovery_turn(
    *,
    network_read_allowed: bool,
    manual_slot: bool,
    pinned_target: str,
    owned_target: str,
    slot_number: int,
) -> bool:
    """Reserve network slots so an unresponsive old owned tab cannot starve history."""
    return network_read_allowed and (
        manual_slot
        or not owned_target
        or bool(pinned_target and pinned_target != owned_target)
        or (not pinned_target and slot_number != 1)
    )


def run_history_recovery(
    results: ResponseStore,
    runtime: SchedulerRuntime,
    driver_factory: Callable[[], HistoryDriver],
    *,
    stop: threading.Event | None = None,
    debugger_address: str | None = None,
) -> None:
    """Recover demanded/deployment chats with a shared five-minute budget."""
    shutdown = stop or threading.Event()
    recovery = HistoryRecovery(results, runtime, driver_factory)
    last_checked_at = 0.0
    while not shutdown.is_set():
        try:
            results.recover_orphans()
            recovery.replies.recover_orphans()
            current = time.monotonic()
            if current - last_checked_at >= HISTORY_READ_INTERVAL_SECONDS:
                if (
                    results.history_recovery_security_pause_remaining() <= 0
                    and results.history_recovery_global_pace_remaining() <= 0
                ):
                    # The global pacing clock advances for each attempted scan.
                    if (results.pending_manual_recovery_requests()
                            or results.next_history_recovery() is not None
                            or recovery.replies.next_history_reply_recovery() is not None):
                        with DeploymentGate(results.path).admission() as deploy_allowed:
                            if deploy_allowed:
                                last_checked_at = current
                                owned_candidate = None
                                if debugger_address:
                                    from .owned_tab_recovery import (
                                        ExistingOwnedTabDriver,
                                        best_owned_recovery_candidate,
                                    )
                                    owned_candidate = best_owned_recovery_candidate(
                                        results, debugger_address,
                                    )
                                owned_target = (
                                    ("reply:" + owned_candidate.reply_id)
                                    if owned_candidate is not None and owned_candidate.reply_id
                                    else owned_candidate.send_id if owned_candidate is not None else ""
                                )
                                priority_sends, priority_replies = deployment_recovery_priority(
                                    results.path.parent,
                                )
                                requested, _ = recovery._next_requested_candidate(
                                    results.pending_manual_recovery_requests(), now=time.time(),
                                )
                                deployed = recovery._next_automatic_candidate(
                                    now=time.time(), priority_sends=priority_sends,
                                    priority_replies=priority_replies, deployment_only=True,
                                )
                                network_read_allowed = _read_backoff_remaining(runtime) <= 0
                                if network_read_allowed and (requested is not None or deployed is not None):
                                    recovery.recover_once(background=True)
                                elif owned_candidate is not None:
                                    tab = owned_candidate.tab
                                    owned_recovery = HistoryRecovery(
                                        results, runtime,
                                        lambda: ExistingOwnedTabDriver(
                                            debugger_address or "", tab,
                                            reply=bool(owned_candidate.reply_id),
                                        ),
                                    )
                                    owned_recovery.recover_once(
                                        preferred_send_id=owned_target,
                                        owned_tab_recovery=True,
                                    )
        except Exception as exc:
            last_checked_at = time.monotonic()
            logger.warning("Historical recovery loop will retry error_type=%s", type(exc).__name__)
        shutdown.wait(5.0)
