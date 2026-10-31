"""Shared permission-dialog supervision for Prompta-owned and account-wide ChatGPT tabs.

All callers evaluate the same scoped browser script. Live capture tabs poll faster;
the independent unread-chat watcher provides coverage when no capture owns a tab.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from patchright.async_api import Error as PlaywrightError
from patchright.async_api import Page
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

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
        except PlaywrightTimeoutError:
            return "stuck"
        return True
    except PlaywrightError:
        return "stuck"


async def supervise_connector_approvals(
    evaluate: Callable[[str], Awaitable[object]],
    *,
    deadline: float,
    source: str,
    poll_interval_seconds: float,
    active: Callable[[], bool] | None = None,
    trusted_retry: Callable[[], Awaitable[object]] | None = None,
) -> int:
    """Click scoped permissions until expiry or loss of ownership.

    A confirmed grant is followed by an immediate scan because another tool
    permission can appear without a new response/capture event.
    """
    loop = asyncio.get_running_loop()
    grants = 0
    while (remaining := deadline - loop.time()) > 0:
        if active is not None and not active():
            break
        try:
            result = await asyncio.wait_for(evaluate(_APPROVAL_SCRIPT), timeout=min(5.0, remaining))
            if result == "stuck" and trusted_retry is not None:
                result = await asyncio.wait_for(
                    trusted_retry(), timeout=min(4.0, max(0.1, deadline - loop.time()))
                )
            if result == "progress":
                continue  # A persistent-grant checkbox was selected; click Allow next.
            if result is True:
                grants += 1
                logger.info("ChatGPT connector grant dismissed source=%s count=%d", source, grants)
                continue
            if result == "stuck":
                logger.warning("ChatGPT connector grant did not dismiss source=%s", source)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.info(
                "ChatGPT connector permission check unavailable source=%s error_type=%s",
                source,
                type(exc).__name__,
            )
        await asyncio.sleep(min(poll_interval_seconds, max(0.0, deadline - loop.time())))
    return grants
