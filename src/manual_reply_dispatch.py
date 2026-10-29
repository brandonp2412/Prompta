"""Explicit-only, exact-branch browser reply dispatch; no prepared-intent draining."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import threading
import time
import uuid
from pathlib import Path

from .browser_ownership import MAX_OWNED_TAB_AGE_SECONDS
from .browser_script_loader import load_browser_script
from .delivery_browser import BrowserDeliverySender
from .playwright_driver import PlaywrightDriver, _normalise_composer_text
from .rate_limit import RateLimitError
from .reply_contracts import ManualReplyStore, ReplyConflict, ReplyIntent
from .response_capture import CaptureResult
from .scheduler_runtime import SchedulerRuntime
from .strict_types import int_value

logger = logging.getLogger(__name__)
_CONFIRM_SECONDS = 20.0


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


def _recovery_probe(conversation_id: str, original_answer: str) -> str:
    """Verify the one original turn on an explicitly reopened exact branch."""
    return (
        load_browser_script("recover_manual_reply_parent.js")
        .replace("__CONVERSATION__", json.dumps(conversation_id))
        .replace("__ORIGINAL_ANSWER__", json.dumps(original_answer))
    )


def _branch_wait_probe(conversation_id: str, parent_id: str) -> str:
    """Wait on the exact tab's DOM mutations for conversation hydration."""
    return load_browser_script("wait_for_manual_reply_branch.js").replace(
        "__VERIFY__", _branch_probe(conversation_id, parent_id)
    )


class ManualReplyDispatcher:
    def __init__(self, store: ManualReplyStore, state_path: Path) -> None:
        self.store = store
        self.state_path = state_path
        self._active: set[str] = set()
        self._recovering: set[str] = set()
        self._lock = threading.Lock()

    def submit(self, send_id: str, intent: ReplyIntent) -> dict[str, object]:
        """Called only by an explicit UI POST; never starts prepared rows on its own."""
        existing = self.store.get(intent.reply_id)
        if existing is not None and existing["status"] != "prepared":
            return self.store.prepare(send_id, intent)
        runtime = SchedulerRuntime(self.state_path, self.state_path)
        backoff = runtime.global_backoff_remaining()
        if backoff > 0:
            raise ReplyConflict(
                f"Account-wide rate limit backoff ends in {math.ceil(backoff)} seconds"
            )
        turn = self.store.prepare(send_id, intent)
        if turn["status"] != "prepared":
            return turn
        with self._lock:
            if intent.reply_id in self._active:
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
            raise ReplyConflict("Manual reply worker is unavailable") from None
        return turn

    def recover(self, send_id: str) -> dict[str, str]:
        """Only an explicit UI POST can inspect the exact persisted branch."""
        with self._lock:
            if send_id in self._recovering:
                raise ReplyConflict("This chat's reply identity is already being verified")
            self._recovering.add(send_id)
        try:
            return asyncio.run(self._recover_exact_parent(send_id))
        finally:
            with self._lock:
                self._recovering.discard(send_id)

    async def _recover_exact_parent(self, send_id: str) -> dict[str, str]:
        original = self.store.responses.get(send_id)
        if original is None or original["status"] != "completed":
            raise ReplyConflict("A completed Prompta chat is required")
        conversation_id = str(original["conversation_id"])
        answer = str(original["assistant_text"])
        if not conversation_id or not answer:
            raise ReplyConflict("The original conversation cannot be verified")
        if original["message_id"]:
            return {"message_id": str(original["message_id"])}
        sender = BrowserDeliverySender(
            self.state_path,
            debugger_address=os.environ.get(
                "PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9223"
            ),
        )
        driver = PlaywrightDriver(
            profile=sender.profile,
            chrome_path=sender.chrome_path,
            debugger_address=sender.debugger_address,
            auth_timeout_seconds=sender.auth_timeout_seconds,
            ownership_prefix="prompta:reply:",
        )
        context = ""
        try:
            await driver.connect()
            context = await driver.new_tab("https://chatgpt.com/c/" + conversation_id)
            await driver.wait_for_composer()
            candidate = await driver.eval(_recovery_probe(conversation_id, answer))
            if not isinstance(candidate, str) or not candidate:
                raise ReplyConflict("The original assistant message could not be verified")
            if not self.store.recover_original_parent(
                send_id, conversation_id, candidate, answer
            ):
                raise ReplyConflict("The saved branch changed or already has a reply")
            return {"message_id": candidate}
        finally:
            if context:
                try:
                    await driver.close_context(context)
                except Exception:
                    pass
            await driver.close()

    def _run(self, turn: dict[str, object]) -> None:
        try:
            asyncio.run(self._dispatch(turn))
        except Exception as exc:
            # Never log the submitted text, provider response, or browser URL.
            logger.warning("Explicit reply dispatch stopped error_type=%s", type(exc).__name__)
        finally:
            with self._lock:
                self._active.discard(str(turn["reply_id"]))

    async def _dispatch(self, turn: dict[str, object]) -> None:
        reply_id = str(turn["reply_id"])
        conversation_id = str(turn["conversation_id"])
        parent_id = str(turn["parent_id"])
        text = str(turn["user_text"])
        owner = f"{os.getpid()}:{uuid.uuid4().hex}"
        runtime = SchedulerRuntime(self.state_path, self.state_path)
        sender = BrowserDeliverySender(
            self.state_path,
            debugger_address=os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9223"),
        )
        driver = PlaywrightDriver(
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
        try:
            await driver.connect()
            context = await driver.new_tab("https://chatgpt.com/c/" + conversation_id)
            await driver.wait_for_composer()
            wait_for_parent = _branch_wait_probe(conversation_id, parent_id)
            if await driver.eval(wait_for_parent) is not True:
                return
            baseline = await driver.dom_state()
            existing_text = _normalise_composer_text(str(baseline.get("composer_text") or ""))
            requested_text = _normalise_composer_text(text)
            if (existing_text and existing_text != requested_text) or baseline.get("send_in_progress"):
                return
            await driver.enable_passive_updates()
            await driver.eval(load_browser_script("passive_response_observer.js"))
            # A never-claimed reply may leave its exact text in the composer.
            # Reuse only that identical draft after another explicit user click.
            if existing_text != requested_text:
                await driver.type_message(text)
            if await driver.eval(wait_for_parent) is not True:
                return
            before_send = await driver.dom_state()
            if _normalise_composer_text(
                str(before_send.get("composer_text") or "")
            ) != _normalise_composer_text(text) or before_send.get("send_in_progress"):
                return
            if runtime.global_backoff_remaining() > 0:
                return
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
                    runtime.record_global_rate_limit(RateLimitError("ChatGPT rate limited"))
                    break
                if status >= 400 or capture.get("fetch_error") or capture.get("ambiguous_request"):
                    break
                if driver.captured_send_response(capture) is not None:
                    confirmed = True
                    break
                await asyncio.sleep(0.2)
            if not confirmed:
                self.store.finish(reply_id, owner, uncertain=True)
                return
            # A verified response to this tab's original POST is accepted activity.
            driver.record_verified_activity()
            approval_task: asyncio.Task[None] | None = None
            if sender.connector_approval:
                approval_task = asyncio.create_task(
                    sender._handle_connector_approvals(driver, deadline=deadline),
                )
            last_verified_text = ""
            try:
                while asyncio.get_running_loop().time() < deadline and driver.is_connected:
                    update = await driver.wait_capture_update(
                        timeout=min(
                            5.0,
                            deadline - asyncio.get_running_loop().time(),
                        )
                    )
                    if (
                        update is not None
                        and update.source == "dom"
                        and update.status == "unknown"
                        and not update.message_id
                    ):
                        break
                    if (
                        update is not None
                        and update.source == "dom"
                        and update.message_id
                        and update.message_id != parent_id
                        and update.text
                        and update.text != last_verified_text
                        and await driver.eval(load_browser_script("location_pathname.js"))
                        == "/c/" + conversation_id
                        and driver.record_verified_activity()
                    ):
                        last_verified_text = update.text
                        refreshed = time.time() + MAX_OWNED_TAB_AGE_SECONDS
                        if self.store.renew(reply_id, owner, deadline=refreshed):
                            deadline = asyncio.get_running_loop().time() + MAX_OWNED_TAB_AGE_SECONDS
                    result = driver.captured_assistant_response(capture)
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
                            if await driver.eval(load_browser_script("location_pathname.js")) != (
                                "/c/" + conversation_id
                            ):
                                break
                            result = CaptureResult(
                                result.source, result.status, result.text,
                                conversation_id, response_id, result.parent_id,
                                result.observer_id,
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
                        and await driver.eval(load_browser_script("location_pathname.js"))
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
                        if self.store.observe(reply_id, owner, update):
                            completed = True
                            driver.record_verified_activity()
                        break
            finally:
                if approval_task is not None:
                    approval_task.cancel()
                    try:
                        await approval_task
                    except asyncio.CancelledError:
                        pass
        finally:
            if claimed and not completed:
                self.store.finish(reply_id, owner, uncertain=True)
            if capture is not None:
                driver.clear_send_capture(capture)
            if context:
                try:
                    await driver.eval(load_browser_script("passive_response_stop.js"))
                except Exception:
                    pass
                try:
                    await driver.close_context(context)
                except Exception:
                    pass
            await driver.close()
