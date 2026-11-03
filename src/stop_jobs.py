"""User-requested cancellation of queued work and exact ChatGPT generations."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from patchright.async_api import async_playwright
from sqlalchemy import delete, select, update

from .browser_script_loader import load_browser_script
from .delivery_queue import DeliveryQueueStore
from .reply_contracts import ManualReplyStore, ReplyConflict
from .reply_tables import replies
from .response_capture import conversation_id_from_path
from .response_store import ResponseStore
from .response_tables import local_chat_pins, manual_recovery_requests, results

_STOP_LOOKUP_SECONDS = 20.0


async def click_chatgpt_stop(conversation_id: str, message_id: str) -> bool:
    """Use only an existing Prompta tab in the exact saved conversation."""
    address = os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9222")
    async with async_playwright() as runtime:
        browser = await runtime.chromium.connect_over_cdp(f"http://{address}", timeout=5000)
        for context in browser.contexts:
            for page in context.pages:
                url = urlparse(page.url)
                if url.scheme != "https" or url.hostname != "chatgpt.com":
                    continue
                if conversation_id_from_path(url.path) != conversation_id:
                    continue
                marker = await page.evaluate("window.name")
                if not isinstance(marker, str) or not marker.startswith(
                    ("prompta:", "prompta-delivery:", "prompta-reply:")
                ):
                    continue
                if message_id and not await page.evaluate(
                    r"""(expected) => {
                    const root = document.querySelector("main") || document;
                    const visible = (node) => node.isConnected &&
                        node.getClientRects().length > 0 && getComputedStyle(node).visibility !== "hidden";
                    const assistants = [...root.querySelectorAll(
                        '[data-message-author-role="assistant"][data-message-id], ' +
                        '[data-chatgpt-search-unit-key$=":assistant"], ' +
                        '[data-content-search-unit-key$=":assistant"]'
                    )].filter(visible);
                    const latest = assistants.at(-1);
                    if (!latest) return false;
                    const users = [...root.querySelectorAll(
                        '[data-message-author-role="user"], ' +
                        '[data-chatgpt-search-unit-key$=":user"], ' +
                        '[data-content-search-unit-key$=":user"]'
                    )].filter(visible);
                    const lastUser = users.at(-1);
                    if (lastUser && (latest.compareDocumentPosition(lastUser) & Node.DOCUMENT_POSITION_FOLLOWING))
                        return false;
                    const key = (node) => node.getAttribute("data-chatgpt-search-unit-key") ||
                        node.getAttribute("data-content-search-unit-key") || "";
                    // Modern ChatGPT splits a single assistant turn into multiple
                    // units (tools/thoughts/final). Check only the latest turn.
                    const group = key(latest).match(/^(fallback-turn-\d+):\d+:assistant$/)?.[1];
                    const candidates = group
                        ? assistants.filter((node) => key(node).startsWith(group + ":"))
                        : [latest];
                    return candidates.some((node) => {
                        if (node.getAttribute("data-message-id") === expected || key(node) === expected)
                            return true;
                        const raw = node.getAttribute("data-chatgpt-search-message-ids") ||
                            node.getAttribute("data-content-search-message-ids") || "";
                        let ids;
                        try {
                            ids = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
                        } catch { return false; }
                        return Array.isArray(ids) && ids.includes(expected);
                    });
                }""",
                    message_id,
                ):
                    continue
                stop = page.locator(
                    'button[data-testid="stop-button"], '
                    'button[aria-label="Stop generating"], button[aria-label="Stop streaming"]'
                ).first
                if await stop.is_visible():
                    await stop.click(timeout=3000)
                    return True
        # Disconnect this client without closing the browser, tabs, or profile.
        return False


async def stop_saved_turn(
    conversation_id: str, original_prompt: str, *, reply_text: str = "", parent_id: str = "",
    allow_missing_reply: bool = False,
) -> tuple[bool, bool]:
    """Reopen only the saved chat and verify its exact turn before stopping it."""
    try:
        if str(UUID(conversation_id)) != conversation_id.lower():
            return False, False
    except ValueError:
        return False, False
    script = load_browser_script(
        "historical_reply_probe.js" if reply_text else "historical_response_probe.js"
    ).replace("__CONVERSATION__", json.dumps(conversation_id)).replace(
        "__ORIGINAL_PROMPT__", json.dumps(original_prompt)
    ).replace("__REPLY_TEXT__", json.dumps(reply_text)).replace("__PARENT__", json.dumps(parent_id))
    original = load_browser_script("historical_response_probe.js").replace(
        "__CONVERSATION__", json.dumps(conversation_id)
    ).replace("__ORIGINAL_PROMPT__", json.dumps(original_prompt))
    address = os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9222")
    async with async_playwright() as runtime:
        browser = await runtime.chromium.connect_over_cdp(f"http://{address}", timeout=5000)
        page = await browser.contexts[0].new_page()
        try:
            await page.evaluate("window.name = 'prompta:stop'")
            await page.goto("https://chatgpt.com/c/" + conversation_id, wait_until="domcontentloaded")
            deadline = time.monotonic() + _STOP_LOOKUP_SECONDS
            while time.monotonic() < deadline:
                proof = await page.evaluate(script)
                if isinstance(proof, dict) and proof.get("verified") is True:
                    if proof.get("complete") is True:
                        return True, False
                    if proof.get("generating") is True:
                        stop = page.locator(
                            'button[data-testid="stop-button"], button[aria-label="Stop"], '
                            'button[aria-label="Stop generating"], button[aria-label="Stop streaming"]'
                        ).first
                        if await stop.is_visible():
                            await stop.click(timeout=3000)
                            return True, True
                if reply_text and allow_missing_reply:
                    # An accepted receipt can survive without the reply ever
                    # reaching ChatGPT. Only a completed, single original turn
                    # proves there is no remote reply generation to stop.
                    first = await page.evaluate(original)
                    if (isinstance(first, dict) and first.get("complete") is True
                            and first.get("branch_message_id") == parent_id
                            and await page.locator(
                                '[data-message-author-role="user"], '
                                '[data-content-search-unit-key$=":user"]'
                            ).evaluate_all("nodes => nodes.filter(n => "
                                           "!n.parentElement.closest('[data-message-author-role=\"user\"], "
                                           "[data-content-search-unit-key$=\":user\"]')).length") == 1):
                        return True, False
                await asyncio.sleep(0.5)
            return False, False
        finally:
            await page.close()


class StopJobService:
    def __init__(self, state_path: Path) -> None:
        root = state_path.expanduser().parent
        self.queue = DeliveryQueueStore(root / "ui-send-jobs.sqlite3")
        self.results = ResponseStore(root / "chat-results.sqlite3")
        self.replies = ManualReplyStore(root / "chat-results.sqlite3")

    def stop(self, send_id: str) -> dict[str, object]:
        record = self.results.get(send_id)
        queued = self.queue.get(send_id)
        if record is None and queued is None:
            raise ValueError("Run not found")
        cancelled = self.queue.cancel_pending(send_id, error="Stopped by user")
        with self.results.engine.connect() as connection:
            pending_replies = (
                connection.execute(
                    select(replies).where(
                        replies.c.send_id == send_id,
                        replies.c.status.in_(
                            ("queued", "prepared", "dispatching", "accepted", "generating", "interrupted", "outcome_unknown")
                        ),
                    ).order_by(replies.c.created_at, replies.c.reply_id)
                )
                .mappings()
                .all()
            )
        active = [
            row
            for row in pending_replies
            if row["status"] in ("dispatching", "accepted", "generating", "interrupted", "outcome_unknown")
        ]
        targets: dict[tuple[str, str], tuple[str, str, bool]] = {}
        if record is not None and (
            record["status"] in ("accepted", "generating")
            or (record["conversation_id"] and record["status"] in ("interrupted", "unavailable"))
        ):
            targets[(str(record["conversation_id"]), str(record["message_id"]))] = ("", "", False)
        # Only the latest reply can still generate remotely. Earlier turns
        # are settled by a subsequent user turn, even if their capture is stale.
        for row in active[-1:]:
            targets[(str(row["conversation_id"]), str(row["message_id"]))] = (
                str(row["user_text"]), str(row["parent_id"]), not row["lease_owner"],
            )
        if queued is not None and queued["status"] == "running" and not targets:
            raise ReplyConflict(
                "This job is still starting. Try Stop again once ChatGPT accepts it."
            )
        browser_stopped = False
        for (conversation, message), (reply_text, parent_id, ownerless) in targets.items():
            if not conversation:
                raise ReplyConflict(
                    "The ChatGPT conversation is not available yet. Try Stop again shortly."
                )
            try:
                clicked = asyncio.run(click_chatgpt_stop(conversation, message)) if message else False
                verified = clicked
                if not verified and record is not None:
                    verified, clicked = asyncio.run(stop_saved_turn(
                        conversation, str(record["user_text"]),
                        reply_text=reply_text, parent_id=parent_id, allow_missing_reply=ownerless,
                    ))
            except Exception as exc:
                raise ReplyConflict("Could not reach ChatGPT's Stop button. Try again.") from exc
            if not verified:
                raise ReplyConflict(
                    "ChatGPT's Stop button was not available in the matching tab. Refresh and try again."
                )
            browser_stopped = browser_stopped or clicked
        at = time.time()
        with self.results.engine.begin() as connection:
            # Stale capture owners cannot overwrite a deliberate stop.
            connection.execute(
                update(results)
                .where(
                    results.c.send_id == send_id,
                    results.c.status.in_(("queued", "accepted", "generating", "interrupted", "unavailable")),
                )
                .values(
                    status="stopped",
                    live_observed_at=0,
                    capture_owner="",
                    capture_deadline=0,
                    updated_at=at,
                    finished_at=at,
                )
            )
            connection.execute(
                update(replies)
                .where(
                    replies.c.send_id == send_id,
                    replies.c.status.in_(("queued", "prepared")),
                )
                .values(status="cancelled", lease_owner="", lease_deadline=0, updated_at=at)
            )
            connection.execute(
                update(replies)
                .where(
                    replies.c.send_id == send_id,
                    replies.c.status.in_(("dispatching", "accepted", "generating", "interrupted", "outcome_unknown")),
                )
                .values(
                    status="stopped", lease_owner="", lease_deadline=0,
                    live_observed_at=0, updated_at=at, finished_at=at,
                )
            )
            connection.execute(
                delete(manual_recovery_requests).where(
                    manual_recovery_requests.c.send_id == send_id
                )
            )
            # Stopping a chat removes only its Prompta sidebar pin. Keep this
            # in the same transaction as the stopped status so it persists.
            connection.execute(
                delete(local_chat_pins).where(local_chat_pins.c.send_id == send_id)
            )
        return {"ok": True, "cancelled_pending": cancelled, "browser_stopped": browser_stopped}
