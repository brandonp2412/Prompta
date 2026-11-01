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


def _error_classes(exc: BaseException) -> str:
    """Identify exception causes without logging browser data or exception text."""
    classes: list[str] = []
    current: BaseException | None = exc
    for _ in range(3):
        if current is None:
            break
        kind = type(current)
        classes.append(f"{kind.__module__}.{kind.__name__}")
        current = current.__cause__ or current.__context__
    return ">".join(classes)


async def supervise_connector_approvals(
    evaluate: Callable[[str], Awaitable[object]],
    *,
    deadline: float,
    source: str,
    poll_interval_seconds: float,
    active: Callable[[], bool],
    trusted_retry: Callable[[], Awaitable[object]] | None = None,
) -> int:
    """Click scoped permissions until expiry or loss of ownership.

    Healthy checks remain fast. A failed browser pipe is given progressively
    longer recovery opportunities; repeatedly writing to it floods the journal.
    """
    loop = asyncio.get_running_loop()
    grants = 0
    failures = 0
    consecutive_failures = 0
    last_error_classes = ""
    stuck_reported = False
    while (remaining := deadline - loop.time()) > 0:
        if not active():
            break
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
            consecutive_failures += 1
            last_error_classes = _error_classes(exc)
            delay = min(
                30.0, max(1.0, poll_interval_seconds) * (2 ** min(consecutive_failures - 1, 5))
            )
            if consecutive_failures == 1:
                logger.warning(
                    "event=connector_approval_check_failed source=%s error_classes=%s retry_seconds=%.1f",
                    source,
                    last_error_classes,
                    delay,
                )
            await asyncio.sleep(min(delay, max(0.0, deadline - loop.time())))
            continue

        if consecutive_failures:
            logger.info(
                "event=connector_approval_check_recovered source=%s failed_checks=%d",
                source,
                consecutive_failures,
            )
            consecutive_failures = 0
        if result == "progress":
            continue  # A persistent-grant checkbox was selected; click Allow next.
        if result is True:
            grants += 1
            stuck_reported = False
            logger.info("ChatGPT connector grant dismissed source=%s count=%d", source, grants)
            continue
        if result == "stuck":
            if not stuck_reported:
                logger.warning("event=connector_approval_stuck source=%s", source)
                stuck_reported = True
        else:
            stuck_reported = False
        await asyncio.sleep(min(poll_interval_seconds, max(0.0, deadline - loop.time())))
    if consecutive_failures:
        logger.warning(
            "event=connector_approval_check_unavailable source=%s failed_checks=%d "
            "error_classes=%s",
            source,
            consecutive_failures,
            last_error_classes,
        )
    elif failures:
        logger.info(
            "event=connector_approval_check_summary source=%s failed_checks=%d", source, failures
        )
    return grants
