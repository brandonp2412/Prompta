"""One-shot live tool canary: owned visible invocation -> SQLite -> local UI.

Only explicitly requested invocation. No retries, history navigation, or raw content logs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

from patchright.async_api import async_playwright

from prompta.browser_script_loader import load_browser_script
from prompta.delivery_queue import DeliveryQueueStore
from prompta.persistence import DEFAULT_RUNTIME_PATH
from prompta.response_store import ResponseStore
from prompta.tool_call_store import deserialize_tool_calls

_VISIBLE_COUNT = """() => {
  const selector = '[data-message-author-role="assistant"][data-message-id], [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids], [data-content-search-unit-key$=":assistant"]';
  const main = document.querySelector("main");
  if (!main) return 0;
  const visible = (node) => node.isConnected && node.getClientRects().length > 0 &&
    getComputedStyle(node).visibility !== "hidden";
  const replies = topLevelResponseNodes(main, selector).filter(visible);
  return toolCallsFromTurns(replies.map(responseTurnRoot), visible, ".markdown").length;
}"""


async def run_tool_canary(
    state_path: Path, *, timeout_seconds: float, ui_url: str, cdp_url: str,
) -> str:
    token = uuid.uuid4().hex[:12]
    send_id = "manual-tool-e2e-" + token
    state = state_path.expanduser().resolve()
    queue = DeliveryQueueStore(state.parent / "ui-send-jobs.sqlite3")
    results = ResponseStore(state.parent / "chat-results.sqlite3")
    prompt = (
        f"Prompta tool invocation verification {token}. Use the web search tool to "
        "find the official IETF RFC 9110 page and give only its publication year "
        f"followed by marker TOOLCANARY{token.upper()}. A tool invocation is required."
    )
    queue.enqueue_idempotent({
        "send_id": send_id, "client_id": "manual:prompta-tool-e2e:" + token,
        "message": prompt, "created_at": time.time(),
    })
    deadline = time.monotonic() + timeout_seconds
    visible = False
    helper = load_browser_script("markdown_from_dom.js")
    async with async_playwright() as playwright:
        # Observe only an already-launched Prompta-owned exact canary tab.
        # No tab creation, user messages, history reads, navigation, or clicks.
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        try:
            while time.monotonic() < deadline:
                queued = queue.get(send_id)
                record = results.get(send_id)
                conversation = str(record["conversation_id"]) if record else ""
                if conversation:
                    exact_url = "https://chatgpt.com/c/" + conversation
                    for context in browser.contexts:
                        for page in context.pages:
                            if page.url.split("?", 1)[0] != exact_url or page.is_closed():
                                continue
                            try:
                                count = await page.evaluate(
                                    "() => {" + helper + "return (" + _VISIBLE_COUNT + ")();}"
                                )
                                visible = visible or isinstance(count, int) and count > 0
                            except Exception:
                                pass
                if queued and str(queued["status"]) in {
                    "outcome_unknown", "dead_lettered", "cancelled",
                }:
                    raise RuntimeError(
                        f"Canary delivery ended {queued['status']} (no resend): {send_id}"
                    )
                if record and record["status"] == "completed":
                    calls = deserialize_tool_calls(record["tool_calls_json"])
                    if calls and visible:
                        break
                await asyncio.sleep(0.4)
        finally:
            await playwright.stop()

    record = results.get(send_id)
    if record is None or record["status"] != "completed" or not visible:
        raise RuntimeError(
            f"Canary did not prove visible invocation and completion: {send_id} "
            f"visible={visible} status={record['status'] if record else 'missing'}. No resend."
        )
    stored = deserialize_tool_calls(record["tool_calls_json"])
    if not stored or not record["conversation_id"] or not record["message_id"]:
        raise RuntimeError(f"Canary missing durable tool identity: {send_id}. No resend.")
    # API must expose the exact durable calls. Never print the surrounding transcript.
    with urlopen(ui_url.rstrip("/") + "/api/results/" + send_id + "/turns", timeout=10) as response:
        payload = json.load(response)
    turns = payload.get("turns", [])
    if not isinstance(turns, list) or not turns or turns[0].get("tool_calls") != stored:
        raise RuntimeError(f"Canary transcript API omitted tool events: {send_id}")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(ui_url.rstrip("/") + "/?view=chats&run=" + send_id)
            await page.locator(".tool-timeline-summary").wait_for(timeout=15_000)
            count = await page.locator(".assistant-group .tool-call").count()
            if count != len(stored):
                raise RuntimeError(f"Canary rendered {count} of {len(stored)} tool calls: {send_id}")
        finally:
            await browser.close()
    print(f"PASS: real visible tool -> {len(stored)} durable calls -> transcript API -> UI; {send_id}")
    return send_id


def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot real Prompta tool-call E2E")
    parser.add_argument("--state", type=Path, default=DEFAULT_RUNTIME_PATH)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--ui-url", default="http://127.0.0.1:8765")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args = parser.parse_args()
    asyncio.run(run_tool_canary(
        args.state, timeout_seconds=args.timeout_seconds,
        ui_url=args.ui_url, cdp_url=args.cdp_url,
    ))


if __name__ == "__main__":
    main()
