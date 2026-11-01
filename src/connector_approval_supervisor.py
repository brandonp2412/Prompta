"""Scoped connector permission supervision for actively captured Prompta-owned tabs.

Callers must provide a live owned-tab connection check; this supervisor never
inspects unrelated chats or runs outside a Prompta-managed capture.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from patchright.async_api import Error as PatchrightError
from patchright.async_api import Page
from patchright.async_api import TimeoutError as PatchrightTimeoutError

from .browser_script_loader import load_browser_script

logger = logging.getLogger(__name__)
_APPROVAL_SCRIPT = load_browser_script("approve_connector.js")


async def trusted_approval_retry(page: Page) -> object:
    """Use a real browser click if ChatGPT ignored the scoped DOM click.

    The selector is marked only by approve_connector.js after it verifies a
    recognizable permission group. No message text or other controls are read.
    """
    candidate = page.locator("[data-prompta-approval-candidate]")
    try:
        if await candidate.count() != 1 or not await candidate.is_visible():
            return "stuck"
        kind = await candidate.get_attribute("data-prompta-approval-candidate")
        if kind not in ("button", "checkbox"):
            return "stuck"
        await candidate.click(timeout=1800)
        if kind == "checkbox":
            return "progress" if await candidate.is_checked() else "stuck"
        try:
            await candidate.wait_for(state="hidden", timeout=1200)
        except PatchrightTimeoutError:
            return "stuck"
        return True
    except PatchrightError:
        return "stuck"


async def supervise_connector_approvals(
    evaluate: Callable[[str], Awaitable[object]],
    *,
    deadline: float,
    source: str,
    poll_interval_seconds: float,
    active: Callable[[], bool],
    trusted_retry: Callable[[], Awaitable[object]] | None = None,
    fresh_retry: Callable[[], Awaitable[object]] | None = None,
) -> int:
    """Keep scoped permissions moving even if the original CDP page handle goes stale.

    A fresh retry is allowed only through the caller's independently verified
    Prompta-owned target. Repeated failures are paced so they cannot flood logs
    or create a tight reconnect loop.
    """
    loop = asyncio.get_running_loop()
    grants = 0
    failures = 0
    next_fresh_retry_at = 0.0
    while (remaining := deadline - loop.time()) > 0:
        if not active():
            break
        result: object = False
        try:
            result = await asyncio.wait_for(evaluate(_APPROVAL_SCRIPT), timeout=min(5.0, remaining))
            if result == "stuck" and trusted_retry is not None:
                result = await asyncio.wait_for(
                    trusted_retry(), timeout=min(4.0, max(0.1, deadline - loop.time()))
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failures += 1
            if failures == 1:
                logger.warning(
                    "ChatGPT connector permission channel unavailable source=%s error_type=%s",
                    source, type(exc).__name__,
                )
            result = "stuck"
        else:
            failures = failures + 1 if result == "stuck" else 0

        if failures >= 3 and fresh_retry is not None and loop.time() >= next_fresh_retry_at:
            next_fresh_retry_at = loop.time() + 10.0
            try:
                result = await asyncio.wait_for(
                    fresh_retry(), timeout=min(12.0, max(0.1, deadline - loop.time()))
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "ChatGPT connector fresh owned-tab check failed source=%s error_type=%s",
                    source, type(exc).__name__,
                )
            else:
                if result in (True, "progress"):
                    failures = 0

        if result == "progress":
            continue
        if result is True:
            grants += 1
            logger.info("ChatGPT connector grant dismissed source=%s count=%d", source, grants)
            continue
        if result == "stuck" and failures == 1:
            logger.warning("ChatGPT connector grant did not dismiss source=%s", source)
        await asyncio.sleep(min(
            max(poll_interval_seconds, 0.5 if failures else 0.0),
            max(0.0, deadline - loop.time()),
        ))
    return grants
