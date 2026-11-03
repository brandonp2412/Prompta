"""Explicit-only, exact-branch browser reply dispatch; no prepared-intent draining."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path

from patchright.async_api import Error as PatchrightError

from .browser_ownership import MAX_OWNED_TAB_AGE_SECONDS
from .browser_script_loader import load_browser_script
from .delivery_browser import BrowserDeliverySender
from .deployment_gate import DeploymentGate
from .patchright_driver import PatchrightDriver, _expected_composer_text, _normalise_composer_text
from .rate_limit import RateLimitError
from .reply_contracts import ManualReplyStore, ReplyConflict, ReplyIntent
from .response_capture import CaptureResult, has_new_capture_activity
from .response_store import HISTORY_READ_INTERVAL_SECONDS
from .scheduler_runtime import SchedulerRuntime
from .strict_types import int_value

logger = logging.getLogger(__name__)
_CONFIRM_SECONDS = 20.0
_RECOVER_PARENT_TIMEOUT_SECONDS = 20.0
_RECOVER_PARENT_POLL_SECONDS = 1.0
_MAX_QUEUED_REPLY_DISPATCHES = 2
_CAPTURE_SURFACE_GRACE_SECONDS = 90.0
_CAPTURE_SURFACE_RECHECK_SECONDS = 90.0


def _branch_probe(conversation_id: str, parent_id: str) -> str:
    """Read only the active route and last assistant identity after explicit navigation."""
    return (
        load_browser_script("verify_manual_reply_branch.js")
        .replace(
            "__CONVERSATION__",
            json.dumps(conversation_id),
        )
        .replace("__PARENT__", json.dumps(parent_id))
    )


def _recovery_probe(
    conversation_id: str, original_answer: str, *, original_prompt: str = "", allow_partial: bool = False,
) -> str:
    """Verify the one original turn on an explicitly reopened exact branch."""
    return (
        load_browser_script("recover_manual_reply_parent.js")
        .replace("__CONVERSATION__", json.dumps(conversation_id))
        .replace("__ORIGINAL_ANSWER__", json.dumps(original_answer))
        .replace("__ORIGINAL_PROMPT__", json.dumps(original_prompt))
        .replace("__ALLOW_PARTIAL__", json.dumps(allow_partial))
    )


def _tip_recovery_probe(
    conversation_id: str, parent_id: str, user_text: str,
    assistant_text: str, turn_count: int,
) -> str:
    """Verify the final manual reply and its preceding assistant, without sending."""
    return (
        load_browser_script("recover_manual_reply_tip.js")
        .replace("__CONVERSATION__", json.dumps(conversation_id))
        .replace("__PARENT__", json.dumps(parent_id))
        .replace("__USER_TEXT__", json.dumps(user_text))
        .replace("__ASSISTANT_TEXT__", json.dumps(assistant_text))
        .replace("__TURN_COUNT__", str(turn_count))
    )


def _branch_wait_probe(conversation_id: str, parent_id: str) -> str:
    """Wait on the exact tab's DOM mutations for conversation hydration."""
    return load_browser_script("wait_for_manual_reply_branch.js").replace(
        "__VERIFY__", _branch_probe(conversation_id, parent_id)
    )


def _reply_delivery_probe(conversation_id: str, parent_id: str, text: str) -> str:
    """Verify the exact new user turn in the explicitly owned conversation."""
    return (
        load_browser_script("verify_manual_reply_delivery.js")
        .replace("__CONVERSATION__", json.dumps(conversation_id))
        .replace("__PARENT__", json.dumps(parent_id))
        .replace("__REPLY__", json.dumps(text))
    )


def _capture_surface_failure_probe(conversation_id: str) -> str:
    """Detect an errored exact conversation surface without reading its content."""
    return f"""(() => {{
        if (location.pathname !== {json.dumps('/c/' + conversation_id)}) return 'route_lost';
        const main = document.querySelector('main');
        if (!main) return '';
        const turns = main.querySelectorAll(
            '[data-message-author-role], [data-chatgpt-search-unit-key], [data-content-search-unit-key]'
        );
        if (turns.length) return '';
        return /something went wrong|unable to load|an error occurred|failed to load|conversation not found/i
            .test(main.innerText || '') ? 'error_surface' : '';
    }})()"""


class ManualReplyDispatcher:
    def __init__(self, store: ManualReplyStore, state_path: Path) -> None:
        self.store = store
        self.state_path = state_path
        self._active: set[str] = set()
        self._recovering: set[str] = set()
        self._recovery_scheduled: set[str] = set()
        self.runtime = SchedulerRuntime(state_path, state_path)
        self._recovery_cursor = 0
        self._lock = threading.Lock()

    def submit(self, send_id: str, intent: ReplyIntent) -> dict[str, object]:
        """Called only by an explicit UI POST; never starts prepared rows on its own."""
        turn = self.store.prepare(send_id, intent)
        if turn["status"] not in ("prepared", "preflight_failed"):
            return turn
        with self._lock:
            if intent.reply_id in self._active:
                return turn
            if turn["status"] == "preflight_failed":
                turn = self.store.retry_preflight(intent.reply_id)
            if turn["status"] != "prepared":
                return turn
            self._active.add(intent.reply_id)
        try:
            threading.Thread(
                target=self._run,
                args=(turn,),
                name="prompta-explicit-reply",
                daemon=True,
            ).start()
        except RuntimeError:
            with self._lock:
                self._active.discard(intent.reply_id)
            self.store.mark_preflight_failed(intent.reply_id)
            raise ReplyConflict("Manual reply worker is unavailable") from None
        return turn

    def active_count(self) -> int:
        """Number of captured or preflighted replies still owned by this process."""
        with self._lock:
            return len(self._active)

    def inflight_count(self) -> int:
        """All sends and read-only recoveries that must drain at shutdown."""
        with self._lock:
            return len(self._active | self._recovering | self._recovery_scheduled)

    def pump_queued(self) -> None:
        """Dispatch only explicit user-clicked follow-ups whose parent is ready.

        The durable intent survives page closes and process restarts. A prepared
        intent that was never claimed can be resumed; failed preflights and
        ambiguous submissions are never automatically retried.
        """
        if (DeploymentGate(self.state_path).is_paused()
                or self.runtime.read_backoff_remaining() > 0):
            return
        selected: set[str] = set()
        for _ in range(_MAX_QUEUED_REPLY_DISPATCHES):
            if self.active_count() >= _MAX_QUEUED_REPLY_DISPATCHES:
                return
            ready = self.store.next_queued_intent(exclude=selected)
            if ready is None:
                break
            send_id, intent = ready
            selected.add(intent.reply_id)
            try:
                self.submit(send_id, intent)
            except ReplyConflict:
                # A concurrent explicit request may already own this turn.
                continue
        # Let verified replies use the next read slot before another missing
        # parent consumes it; otherwise one stuck parent can starve every send.
        if not selected:
            self._schedule_queued_parent_recovery()

    def _schedule_queued_parent_recovery(self) -> None:
        # A queued reply is explicit consent to reopen its exact branch.
        # Recovery runs off the 1s queue-pump path and never dispatches a send;
        # only next_queued_intent can authorize dispatch after verified lineage.
        # A scan is wasted while the previous background scan is still running.
        with self._lock:
            if self._recovery_scheduled:
                return
        if (self.store.responses.history_recovery_global_pace_remaining() > 0
                or self.store.responses.history_recovery_security_pause_remaining() > 0
                or self.runtime.read_backoff_remaining() > 0):
            return
        candidates = self.store.queued_recovery_candidates()
        if not candidates:
            return
        for offset in range(len(candidates)):
            index = (self._recovery_cursor + offset) % len(candidates)
            send_id = candidates[index]
            with self._lock:
                if (send_id in self._recovery_scheduled or send_id in self._recovering
                        or len(self._recovery_scheduled) >= 1):
                    continue
                self._recovery_scheduled.add(send_id)
                self._recovery_cursor = (index + 1) % len(candidates)
            try:
                threading.Thread(
                    target=self._recover_queued_parent,
                    args=(send_id,),
                    name="prompta-queued-reply-recovery",
                    daemon=True,
                ).start()
            except RuntimeError:
                with self._lock:
                    self._recovery_scheduled.discard(send_id)
                logger.warning("Queued reply recovery thread unavailable")
            return

    def _recover_queued_parent(self, send_id: str) -> None:
        try:
            self.recover(send_id)
        except (ReplyConflict, PatchrightError, RuntimeError, TimeoutError) as exc:
            logger.info("Queued reply parent recovery pending error_type=%s", type(exc).__name__)
        except Exception as exc:
            logger.warning("Queued reply parent recovery failed error_type=%s", type(exc).__name__)
        finally:
            with self._lock:
                self._recovery_scheduled.discard(send_id)

    def recover(self, send_id: str) -> dict[str, str]:
        """Inspect the exact branch after a direct click or a queued reply consent."""
        with self._lock:
            if send_id in self._recovering:
                raise ReplyConflict("This chat's reply identity is already being verified")
            self._recovering.add(send_id)
        try:
            with DeploymentGate(self.state_path).admission() as deploy_allowed:
                if not deploy_allowed:
                    raise ReplyConflict("Prompta is paused for deployment")
                return asyncio.run(self._recover_exact_parent(send_id))
        finally:
            with self._lock:
                self._recovering.discard(send_id)

    async def _recover_exact_parent(self, send_id: str) -> dict[str, str]:
        # Ignore later unsent follow-ups: their durable presence must not
        # prevent verifying the preceding assistant message.
        turns = [turn for turn in (self.store.turns(send_id) or []) if turn["status"] != "queued"]
        if not turns:
            raise ReplyConflict("A saved Prompta chat is required")
        latest = turns[-1]
        if latest["status"] not in ("completed", "interrupted", "unavailable", "outcome_unknown", "stopped"):
            raise ReplyConflict("A terminal Prompta turn is required")
        conversation_id = str(latest.get("conversation_id") or "")
        answer = str(latest["assistant_text"])
        if not conversation_id:
            raise ReplyConflict("The conversation ID is unavailable")
        if latest["message_id"]:
            return {"message_id": str(latest["message_id"])}
        previous_parent = str(turns[-2]["message_id"] or "") if len(turns) > 1 else ""
        if len(turns) > 1 and not previous_parent:
            raise ReplyConflict("The preceding assistant identity is unavailable")
        if self.store.responses.history_recovery_security_pause_remaining() > 0:
            raise ReplyConflict("ChatGPT account read security pause is active")
        remaining = self.runtime.read_backoff_remaining()
        if remaining > 0:
            raise ReplyConflict(
                f"ChatGPT account read cooldown is active; retry in {int(remaining + 0.999)} seconds"
            )
        if not self.store.responses.reserve_history_recovery_global_slot(
            now=time.time(), interval=HISTORY_READ_INTERVAL_SECONDS,
        ):
            raise ReplyConflict("ChatGPT account read pacing is active; retry later")
        sender = BrowserDeliverySender(
            self.state_path,
            debugger_address=os.environ.get(
                "PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9223"
            ),
        )
        driver = PatchrightDriver(
            profile=sender.profile,
            chrome_path=sender.chrome_path,
            debugger_address=sender.debugger_address,
            auth_timeout_seconds=sender.auth_timeout_seconds,
            ownership_prefix="prompta:reply:",
        )
        context = ""
        try:
            await driver.connect()
            try:
                context = await driver.new_tab("https://chatgpt.com/c/" + conversation_id)
                await driver.wait_for_composer()
            except Exception:
                if driver.history_rate_limited():
                    sender.runtime.record_read_rate_limit(
                        RateLimitError("ChatGPT exact conversation read returned HTTP 429")
                    )
                    raise ReplyConflict("ChatGPT account read cooldown is active; retry later") from None
                raise
            if len(turns) == 1:
                probe = _recovery_probe(
                    conversation_id, answer, original_prompt=str(latest["user_text"]),
                    allow_partial=latest["status"] != "completed"
                )
            else:
                probe = _tip_recovery_probe(
                    conversation_id, previous_parent, str(latest["user_text"]),
                    answer, len(turns),
                )
            deadline = asyncio.get_running_loop().time() + _RECOVER_PARENT_TIMEOUT_SECONDS
            while True:
                if driver.history_rate_limited():
                    sender.runtime.record_read_rate_limit(
                        RateLimitError("ChatGPT exact conversation read returned HTTP 429")
                    )
                    raise ReplyConflict("ChatGPT account read cooldown is active; retry later")
                try:
                    candidate = await asyncio.wait_for(driver.eval(probe), timeout=5.0)
                except (PatchrightError, TimeoutError):
                    candidate = None
                if isinstance(candidate, str) and candidate:
                    break
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise ReplyConflict("The latest assistant message could not be verified")
                await asyncio.sleep(min(_RECOVER_PARENT_POLL_SECONDS, remaining))
            if len(turns) == 1:
                recovered = self.store.recover_original_parent(
                    send_id, conversation_id, candidate, answer
                )
            else:
                recovered = self.store.recover_reply_parent(
                    send_id, str(latest["reply_id"]), conversation_id,
                    previous_parent, str(latest["user_text"]), answer, candidate,
                )
            if not recovered:
                raise ReplyConflict("The saved branch changed during recovery")
            return {"message_id": candidate}
        finally:
            if context:
                try:
                    await asyncio.wait_for(driver.close_context(context), timeout=5.0)
                except Exception as exc:
                    logger.warning("Exact recovery tab cleanup failed error_type=%s", type(exc).__name__)
            try:
                await asyncio.wait_for(driver.close(), timeout=5.0)
            except Exception as exc:
                logger.warning("Exact recovery browser disconnect failed error_type=%s", type(exc).__name__)

    def _run(self, turn: dict[str, object]) -> None:
        try:
            with DeploymentGate(self.state_path).admission() as deploy_allowed:
                if not deploy_allowed:
                    return  # Remains durably prepared for the worker after deploy.
                try:
                    asyncio.run(self._dispatch(turn))
                except Exception as exc:
                    # Never log submitted text, provider response or browser URL.
                    logger.warning(
                        "Explicit reply dispatch stopped error_type=%s", type(exc).__name__
                    )
                    self.store.mark_preflight_failed(str(turn["reply_id"]))
        finally:
            with self._lock:
                self._active.discard(str(turn["reply_id"]))

    async def _dispatch(self, turn: dict[str, object]) -> None:
        # Keep the explicit intent prepared until opening its branch is admitted.
        if self.runtime.read_backoff_remaining() > 0:
            return
        if self.runtime.account_state(strict=True).get("resource_blocked") is True:
            self.store.mark_preflight_failed(str(turn["reply_id"]))
            return
        # Opening a saved conversation reads history even with a known parent.
        # Defer before preflight so pacing preserves the explicit queued intent.
        if not self.store.responses.reserve_history_recovery_global_slot(
            now=time.time(), interval=HISTORY_READ_INTERVAL_SECONDS,
        ):
            return
        reply_id = str(turn["reply_id"])
        conversation_id = str(turn["conversation_id"])
        parent_id = str(turn["parent_id"])
        text = str(turn["user_text"])
        owner = f"{os.getpid()}:{uuid.uuid4().hex}"
        sender = BrowserDeliverySender(
            self.state_path,
            debugger_address=os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9223"),
        )
        driver = PatchrightDriver(
            profile=sender.profile,
            chrome_path=sender.chrome_path,
            debugger_address=sender.debugger_address,
            auth_timeout_seconds=sender.auth_timeout_seconds,
            ownership_prefix="prompta:reply:",
        )
        context = ""
        capture: dict[str, object] | None = None
        claimed = False
        completed = False
        preflight_stage = "connect"
        try:
            # Explicit replies honour the account resource block that also
            # gates the fresh-chat worker.
            preflight_stage = "account_resource_admission"
            if sender.runtime.account_state(strict=True).get("resource_blocked") is True:
                return
            # Only retry establishing the authenticated browser. No reply has
            # been claimed, typed or submitted at this point.
            for attempt in range(2):
                try:
                    await driver.connect()
                except (PatchrightError, RuntimeError) as exc:
                    if attempt == 1:
                        raise
                    logger.warning(
                        "Explicit reply connection retrying error_type=%s", type(exc).__name__
                    )
                    await asyncio.sleep(1.0)
                else:
                    break
            preflight_stage = "open_exact_tab"
            context = await driver.new_tab("https://chatgpt.com/c/" + conversation_id)
            await driver.wait_for_composer()
            preflight_stage = "await_exact_parent"
            wait_for_parent = _branch_wait_probe(conversation_id, parent_id)
            if await driver.eval(wait_for_parent) is not True:
                return
            preflight_stage = "check_existing_composer"
            baseline = await driver.dom_state()
            existing_text = _normalise_composer_text(str(baseline.get("composer_text") or ""))
            requested_text = _expected_composer_text(text)
            if (existing_text and existing_text != requested_text) or baseline.get("send_in_progress"):
                return
            preflight_stage = "arm_passive_observer"
            await driver.enable_passive_updates()
            await driver.eval(
                load_browser_script("passive_response_observer.js"), main_world=True
            )
            # A never-claimed reply may leave its exact text in the composer.
            # Reuse only that identical draft after another explicit user click.
            preflight_stage = "prepare_composer"
            if existing_text != requested_text:
                await driver.type_message(text)
            preflight_stage = "reverify_exact_parent"
            if await driver.eval(wait_for_parent) is not True:
                return
            preflight_stage = "check_typed_composer"
            before_send = await driver.dom_state()
            if _normalise_composer_text(
                str(before_send.get("composer_text") or "")
            ) != _expected_composer_text(text) or before_send.get("send_in_progress"):
                return
            preflight_stage = "account_resource_admission"
            if sender.runtime.account_state(strict=True).get("resource_blocked") is True:
                return
            preflight_stage = "irreversible_claim"
            claimed = self.store.claim(
                reply_id,
                owner,
                deadline=time.time() + MAX_OWNED_TAB_AGE_SECONDS,
            )
            if not claimed:
                return
            capture = driver.arm_send_capture()
            try:
                await asyncio.wait_for(driver.click_send(text), timeout=25.0)
            except Exception:
                self.store.finish(reply_id, owner, uncertain=True)
                return
            deadline = asyncio.get_running_loop().time() + MAX_OWNED_TAB_AGE_SECONDS
            confirm_end = asyncio.get_running_loop().time() + _CONFIRM_SECONDS
            confirmed = False
            while asyncio.get_running_loop().time() < confirm_end:
                status = int_value(capture.get("status"))
                if status == 429:
                    break
                if status >= 400 or capture.get("fetch_error") or capture.get("ambiguous_request"):
                    break
                if driver.captured_send_response(capture) is not None:
                    confirmed = True
                    break
                await asyncio.sleep(0.2)
            delivery_proof: dict[str, object] = {}
            if not confirmed:
                # ChatGPT may render an accepted reply even when CDP misses its
                # POST response. Only the exact new user turn on this owned
                # conversation, after the verified parent, can prove delivery.
                try:
                    probe = await driver.eval(
                        _reply_delivery_probe(conversation_id, parent_id, text)
                    )
                    if isinstance(probe, dict):
                        delivery_proof = {
                            key: value for key, value in probe.items()
                            if isinstance(key, str)
                        }
                except (PatchrightError, RuntimeError, TimeoutError):
                    pass
                confirmed = delivery_proof.get("verified") is True
            if not confirmed:
                logger.warning(
                    "Explicit reply send unconfirmed request_seen=%s "
                    "response_started=%s status=%s fetch_error=%s ambiguous=%s",
                    bool(capture.get("request_id")),
                    bool(capture.get("response_started")),
                    int_value(capture.get("status")),
                    bool(capture.get("fetch_error")),
                    bool(capture.get("ambiguous_request")),
                )
                self.store.finish(reply_id, owner, uncertain=True)
                return
            if not self.store.acknowledge_submission(
                reply_id, owner, conversation_id=conversation_id, parent_id=parent_id,
            ):
                return
            # Verified acceptance is durable before waiting for a final answer.
            driver.record_verified_activity()
            if delivery_proof.get("complete") is True:
                response_id = str(delivery_proof.get("message_id") or "")
                answer = str(delivery_proof.get("text") or "")
                if response_id and answer:
                    result = CaptureResult(
                        "dom", "complete", answer, conversation_id, response_id, None,
                    )
                    if self.store.accepted(
                        reply_id, owner, conversation_id=conversation_id,
                        parent_id=parent_id, message_id=response_id,
                        response_parent_id="",
                    ) and self.store.observe(reply_id, owner, result):
                        completed = True
                        return
            approval_task: asyncio.Task[None] | None = None
            if sender.connector_approval:
                approval_task = asyncio.create_task(
                    sender._handle_connector_approvals(driver, deadline=deadline),
                )
            last_verified_text = ""
            last_verified_tools: tuple[dict[str, object], ...] = ()
            last_verified_blocks: tuple[dict[str, str], ...] = ()
            observed_tool_calls: tuple[dict[str, object], ...] = ()
            surface_probe_at = (
                asyncio.get_running_loop().time() + _CAPTURE_SURFACE_GRACE_SECONDS
            )
            consecutive_missing_answers = 0
            try:
                while asyncio.get_running_loop().time() < deadline and driver.is_connected:
                    current = self.store.get(reply_id)
                    if current is not None and current["status"] == "stopped":
                        break
                    update = await driver.wait_capture_update(
                        timeout=min(
                            5.0,
                            deadline - asyncio.get_running_loop().time(),
                        )
                    )
                    # Ambiguous DOM observers are common during hydration.
                    # Stop only if the owned page actually left its exact
                    # saved branch; otherwise wait for identity-bound evidence.
                    if (
                        update is not None
                        and update.source == "dom"
                        and update.status == "unknown"
                        and not update.message_id
                        and await driver.eval("location.pathname")
                        != "/c/" + conversation_id
                    ):
                        break
                    if update is not None and update.stream_error:
                        logger.warning("ChatGPT explicit reply reported a stream error")
                        break
                    # An owned response update, not just final answer text, is progress.
                    changed = has_new_capture_activity(
                        update,
                        previous_text=last_verified_text,
                        previous_tools=last_verified_tools,
                        previous_blocks=last_verified_blocks,
                    )
                    if changed and (
                        update is not None
                        and (update.source == "sse" or (
                            update.message_id and update.message_id != parent_id
                            and await driver.eval("location.pathname") == "/c/" + conversation_id
                        ))
                        and driver.record_verified_activity()
                    ):
                        if update is not None:
                            if update.text:
                                last_verified_text = update.text
                            if update.tool_calls:
                                last_verified_tools = update.tool_calls
                            if update.display_blocks:
                                last_verified_blocks = update.display_blocks
                        refreshed = time.time() + MAX_OWNED_TAB_AGE_SECONDS
                        if self.store.renew(reply_id, owner, deadline=refreshed):
                            deadline = asyncio.get_running_loop().time() + MAX_OWNED_TAB_AGE_SECONDS
                    result = driver.captured_assistant_response(capture)
                    if (result is not None and result.tool_calls
                        and result.conversation_id in (None, conversation_id)
                        and not capture.get("ambiguous_request")):
                        observed_tool_calls = result.tool_calls
                        if await driver.eval("location.pathname") == "/c/" + conversation_id:
                            self.store.observe_tools(reply_id, owner, replace(
                                result, conversation_id=conversation_id,
                            ))
                    if (update is not None and (update.tool_calls or update.display_blocks)
                        and update.conversation_id == conversation_id
                        and (update.message_id or update.observer_id)
                        and await driver.eval("location.pathname") == "/c/" + conversation_id):
                        self.store.observe_tools(reply_id, owner, update)
                    if (
                        result is not None
                        and result.status == "complete"
                        and result.conversation_id not in (None, conversation_id)
                    ):
                        break
                    if (
                        result is not None
                        and result.status == "complete"
                        and result.parent_id
                        and result.message_id
                        and result.message_id != parent_id
                        and result.text
                    ):
                        response_id = result.message_id
                        if result.conversation_id is None:
                            # A POST stream may omit the conversation field.
                            # Bind only after the owned page proves its exact route.
                            if await driver.eval("location.pathname") != (
                                "/c/" + conversation_id
                            ):
                                break
                            result = CaptureResult(
                                result.source, result.status, result.text,
                                conversation_id, response_id, result.parent_id,
                                result.observer_id, result.tool_calls,
                            )
                        if not self.store.accepted(
                            reply_id,
                            owner,
                            conversation_id=conversation_id,
                            parent_id=parent_id,
                            message_id=response_id,
                            response_parent_id=result.parent_id,
                        ):
                            break
                        if self.store.observe(reply_id, owner, result):
                            completed = True
                            driver.record_verified_activity()
                        break
                    # Some accepted POSTs complete in the owned tab before their
                    # SSE body can be read. The pre-send parent, original POST
                    # acknowledgment, single fresh DOM node and exact route bind
                    # this answer without pretending to know its response parent.
                    if (
                        update is not None
                        and update.source == "dom"
                        and update.status == "complete"
                        and update.conversation_id == conversation_id
                        and update.message_id
                        and update.message_id != parent_id
                        and update.text
                        and await driver.eval("location.pathname")
                        == "/c/" + conversation_id
                    ):
                        if not self.store.accepted(
                            reply_id,
                            owner,
                            conversation_id=conversation_id,
                            parent_id=parent_id,
                            message_id=update.message_id,
                            response_parent_id="",
                        ):
                            break
                        if observed_tool_calls:
                            update = replace(update, tool_calls=observed_tool_calls)
                        if self.store.observe(reply_id, owner, update):
                            completed = True
                            driver.record_verified_activity()
                        break
                    # An accepted POST can outlive a broken ChatGPT conversation
                    # surface. Give hydration time, then release the owned lease
                    # for read-only reply recovery instead of waiting 45 minutes.
                    if asyncio.get_running_loop().time() >= surface_probe_at:
                        surface_probe_at = (
                            asyncio.get_running_loop().time()
                            + _CAPTURE_SURFACE_RECHECK_SECONDS
                        )
                        # A successful POST can finish while the passive DOM
                        # binding misses its final mutation. Reconcile only the
                        # exact persisted parent and new user turn; never resend.
                        try:
                            exact_reply = await driver.eval(
                                _reply_delivery_probe(conversation_id, parent_id, text)
                            )
                        except (PatchrightError, RuntimeError, TimeoutError):
                            exact_reply = None
                        if (isinstance(exact_reply, dict)
                            and exact_reply.get("verified") is True
                            and exact_reply.get("complete") is True):
                            response_id = str(exact_reply.get("message_id") or "")
                            answer = str(exact_reply.get("text") or "")
                            if response_id and answer:
                                final = CaptureResult(
                                    "dom", "complete", answer, conversation_id,
                                    response_id, None,
                                )
                                if self.store.accepted(
                                    reply_id, owner, conversation_id=conversation_id,
                                    parent_id=parent_id, message_id=response_id,
                                    response_parent_id="",
                                ) and self.store.observe(reply_id, owner, final):
                                    completed = True
                                    driver.record_verified_activity()
                                    break
                        # The user turn is confirmed, but ChatGPT may stop
                        # generating without an assistant turn. Only two
                        # spaced, exact-branch checks can release that capture.
                        if (isinstance(exact_reply, dict)
                            and exact_reply.get("verified") is True
                            and exact_reply.get("has_assistant") is False
                            and exact_reply.get("generating") is False
                            and not exact_reply.get("text")):
                            consecutive_missing_answers += 1
                            if (consecutive_missing_answers >= 2
                                or exact_reply.get("error_visible") is True):
                                logger.warning(
                                    "Explicit reply capture released for read-only recovery reason=missing_answer"
                                )
                                break
                        else:
                            consecutive_missing_answers = 0
                        try:
                            surface_failure = await driver.eval(
                                _capture_surface_failure_probe(conversation_id)
                            )
                        except (PatchrightError, RuntimeError, TimeoutError):
                            surface_failure = ""
                        if surface_failure in ("route_lost", "error_surface"):
                            logger.warning(
                                "Explicit reply capture released for read-only recovery reason=%s",
                                surface_failure,
                            )
                            break
            finally:
                if approval_task is not None:
                    approval_task.cancel()
                    try:
                        await approval_task
                    except asyncio.CancelledError:
                        pass
        except (PatchrightError, RuntimeError, TimeoutError):
            if claimed or not driver.history_rate_limited():
                raise
        finally:
            if not claimed:
                if driver.history_rate_limited():
                    sender.runtime.record_read_rate_limit(
                        RateLimitError("ChatGPT exact conversation read returned HTTP 429"),
                        extend_only=True,
                    )
                    logger.info("Explicit reply deferred for conversation read cooldown")
                else:
                    self.store.mark_preflight_failed(reply_id)
                    logger.warning("Explicit reply preflight left unsent stage=%s", preflight_stage)
            if claimed and not completed:
                self.store.finish(reply_id, owner, uncertain=True)
            if capture is not None:
                driver.clear_send_capture(capture)
            if context:
                try:
                    await driver.eval(
                        "(() => { window.__promptaPassiveResponseObserver?.stop?.(); return true; })()", main_world=True
                    )
                except Exception:
                    pass
                try:
                    await driver.close_context(context)
                except Exception:
                    pass
            await driver.close()
