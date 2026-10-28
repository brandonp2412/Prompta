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
from .scheduler_runtime import SchedulerRuntime
from .strict_types import int_value

logger = logging.getLogger(__name__)
_CONFIRM_SECONDS = 20.0


def _branch_probe(conversation_id: str, parent_id: str) -> str:
    """Read only the active route and last assistant identity after explicit navigation."""
    return load_browser_script("verify_manual_reply_branch.js").replace(
        "__CONVERSATION__", json.dumps(conversation_id),
    ).replace("__PARENT__", json.dumps(parent_id))


class ManualReplyDispatcher:
    def __init__(self, store: ManualReplyStore, state_path: Path) -> None:
        self.store = store
        self.state_path = state_path
        self._active: set[str] = set()
        self._lock = threading.Lock()

    def submit(self, send_id: str, intent: ReplyIntent) -> dict[str, object]:
        """Called only by an explicit UI POST; never starts prepared rows on its own."""
        existing = self.store.get(intent.reply_id)
        if existing is not None and existing["status"] != "prepared":
            return self.store.prepare(send_id, intent)
        runtime = SchedulerRuntime(self.state_path, self.state_path)
        backoff = runtime.global_backoff_remaining()
        gap = runtime.delivery_claim_gap_remaining(time.time())
        if backoff > 0 or gap > 0:
            delay = max(backoff, gap)
            raise ReplyConflict(f"Account-wide send window opens in {math.ceil(delay)} seconds")
        turn = self.store.prepare(send_id, intent)
        if turn["status"] != "prepared":
            return turn
        with self._lock:
            if intent.reply_id in self._active:
                return turn
            self._active.add(intent.reply_id)
        try:
            threading.Thread(
                target=self._run, args=(turn,),
                name="prompta-explicit-reply", daemon=True,
            ).start()
        except RuntimeError:
            with self._lock:
                self._active.discard(intent.reply_id)
            raise ReplyConflict("Manual reply worker is unavailable") from None
        return turn

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
            verify = _branch_probe(conversation_id, parent_id)
            if await driver.eval(verify) is not True:
                return
            baseline = await driver.dom_state()
            if baseline.get("composer_text") or baseline.get("send_in_progress"):
                return
            await driver.enable_passive_updates()
            await driver.eval(load_browser_script("passive_response_observer.js"))
            await driver.type_message(text)
            if await driver.eval(verify) is not True:
                return
            before_send = await driver.dom_state()
            if (
                _normalise_composer_text(str(before_send.get("composer_text") or ""))
                != _normalise_composer_text(text)
                or before_send.get("send_in_progress")
            ):
                return
            if runtime.global_backoff_remaining() > 0:
                return
            remaining = runtime.reserve_send_attempt(time.time(), manual=True)
            if remaining > 0:
                return
            claimed = self.store.claim(
                reply_id, owner, deadline=time.time() + MAX_OWNED_TAB_AGE_SECONDS,
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
                    update = await driver.wait_capture_update(timeout=min(
                        5.0, deadline - asyncio.get_running_loop().time(),
                    ))
                    if (
                        update is not None and update.source == "dom"
                        and update.status == "unknown" and not update.message_id
                    ):
                        break
                    if (
                        update is not None and update.source == "dom"
                        and update.message_id and update.message_id != parent_id
                        and update.text and update.text != last_verified_text
                        and await driver.eval(load_browser_script("location_pathname.js"))
                        == "/c/" + conversation_id
                        and driver.record_verified_activity()
                    ):
                        last_verified_text = update.text
                        refreshed = time.time() + MAX_OWNED_TAB_AGE_SECONDS
                        if self.store.renew(reply_id, owner, deadline=refreshed):
                            deadline = asyncio.get_running_loop().time() + MAX_OWNED_TAB_AGE_SECONDS
                    result = driver.captured_assistant_response(capture)
                    if result is None or result.status != "complete":
                        continue
                    if (
                        result.conversation_id != conversation_id
                        or not result.parent_id or not result.message_id
                        or result.message_id == parent_id or not result.text
                    ):
                        break
                    if not self.store.accepted(
                        reply_id, owner, conversation_id=conversation_id,
                        parent_id=parent_id, message_id=result.message_id,
                        response_parent_id=result.parent_id,
                    ):
                        break
                    if self.store.observe(reply_id, owner, result):
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
