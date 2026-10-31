"""Paced exact-chat verification of visible tool headings, with optional metadata backfill.

Opens only one verified Prompta-owned conversation in a new background tab.
Never fetches history APIs, inspects other tabs, sends a prompt, or logs content.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import UUID

from patchright.async_api import async_playwright

from prompta.browser_script_loader import load_browser_script
from prompta.persistence import DEFAULT_RUNTIME_PATH
from prompta.rate_limit import RateLimitError
from prompta.response_capture import CaptureResult, normalize_dom_snapshot
from prompta.response_store import ResponseStore
from prompta.scheduler_runtime import SchedulerRuntime
from prompta.tool_recovery import recover_completed_tool_summaries

_READ_INTERVAL = 90.0


async def exact_visible_tools(
    conversation_id: str, original_prompt: str, *, cdp_url: str,
) -> CaptureResult | None:
    script = (
        load_browser_script("historical_response_probe.js")
        .replace("__CONVERSATION__", json.dumps(conversation_id))
        .replace("__ORIGINAL_PROMPT__", json.dumps(original_prompt))
    )
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]
        session = await browser.new_browser_cdp_session()
        target = ""
        try:
            # CDP background target does not focus or inspect existing tabs.
            async with context.expect_page(timeout=10_000) as event:
                created = await session.send("Target.createTarget", {
                    "url": "https://chatgpt.com/c/" + conversation_id,
                    "background": True,
                })
                target = str(created.get("targetId") or "")
            page = await event.value
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                payload: object = await page.evaluate(script)
                if isinstance(payload, dict):
                    if payload.get("rate_limited") is True:
                        raise RateLimitError()
                    if payload.get("verified") is True and payload.get("complete") is True:
                        observed = normalize_dom_snapshot(payload)
                        if observed.conversation_id == conversation_id and observed.tool_calls:
                            return observed
                await asyncio.sleep(2)
        finally:
            if target:
                await session.send("Target.closeTarget", {"targetId": target})
    return None


async def verify_exact(
    state_path: Path, send_id: str, *, cdp_url: str, max_wait_seconds: float,
    backfill: bool,
) -> bool:
    state = state_path.expanduser().resolve()
    results = ResponseStore(state.parent / "chat-results.sqlite3")
    runtime = SchedulerRuntime(state, state)
    row = results.get(send_id)
    if (
        row is None or row["status"] != "completed" or row["capture_owner"]
        or not isinstance(row["conversation_id"], str)
        or not isinstance(row["message_id"], str) or not row["message_id"]
        or not isinstance(row["user_text"], str)
    ):
        raise RuntimeError("Only completed, verified Prompta-owned runs are eligible")
    conversation_id = row["conversation_id"]
    if str(UUID(conversation_id)) != conversation_id.lower():
        raise RuntimeError("Stored conversation identity is invalid")
    until = time.monotonic() + max_wait_seconds
    while time.monotonic() < until:
        pause = max(
            runtime.read_backoff_remaining(),
            results.history_recovery_global_pace_remaining(),
            results.history_recovery_security_pause_remaining(),
        )
        if pause <= 0 and results.reserve_history_recovery_global_slot(
            now=time.time(), interval=_READ_INTERVAL,
        ):
            break
        await asyncio.sleep(min(30.0, max(1.0, pause)))
    else:
        print(f"DEFER: exact read admission unavailable within deadline {send_id}")
        return False

    try:
        capture = await exact_visible_tools(
            conversation_id, row["user_text"], cdp_url=cdp_url,
        )
    except RateLimitError as exc:
        runtime.record_read_rate_limit(exc)
        print(f"DEFER: exact read rate limited {send_id}")
        return False
    if capture is None or capture.message_id != row["message_id"]:
        print(f"GAP: no verified visible tool for exact final branch {send_id}")
        return False
    if backfill and not recover_completed_tool_summaries(results, send_id, capture):
        print(f"GAP: exact tool metadata backfill rejected {send_id}")
        return False
    print(f"PASS: verified visible tool headings={len(capture.tool_calls)} exact branch={send_id}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify exact owned ChatGPT tool headings")
    parser.add_argument("send_id")
    parser.add_argument("--state", type=Path, default=DEFAULT_RUNTIME_PATH)
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--max-wait-seconds", type=float, default=7200)
    parser.add_argument("--backfill", action="store_true")
    args = parser.parse_args()
    ok = asyncio.run(verify_exact(
        args.state, args.send_id, cdp_url=args.cdp_url,
        max_wait_seconds=args.max_wait_seconds, backfill=args.backfill,
    ))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
