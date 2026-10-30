"""Shared permission-dialog supervision for Prompta-owned and account-wide ChatGPT tabs.

All callers evaluate the same scoped browser script. Live capture tabs poll faster;
the independent unread-chat watcher provides coverage when no capture owns a tab.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .browser_script_loader import load_browser_script

logger = logging.getLogger(__name__)
_APPROVAL_SCRIPT = load_browser_script("approve_connector.js")


async def supervise_connector_approvals(
    evaluate: Callable[[str], Awaitable[object]],
    *,
    deadline: float,
    source: str,
    poll_interval_seconds: float,
    active: Callable[[], bool] | None = None,
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
