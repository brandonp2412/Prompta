"""Opt-in permission supervision inside currently watched Prompta-owned tabs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from patchright.async_api import Error as PlaywrightError
from patchright.async_api import Page
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from .browser_script_loader import load_browser_script

logger = logging.getLogger(__name__)
_APPROVAL_SCRIPT = load_browser_script("approve_connector.js")


@dataclass
class ApprovalCounters:
    detected: int = 0
    persistent_selected: int = 0
    allow_clicked: int = 0
    dismissed: int = 0
    timeout_failure: int = 0

    def record(self, result: object) -> str:
        if not isinstance(result, dict):
            return "invalid"
        status = result.get("status")
        if not isinstance(status, str) or status not in ("idle", "progress", "dismissed", "stuck"):
            return "invalid"
        for name in ("detected", "persistent_selected", "allow_clicked", "dismissed"):
            count = result.get(name, 0)
            if type(count) is int and 0 <= count <= 2:
                setattr(self, name, getattr(self, name) + count)
        return status


def _result(status: str, *, clicked: int = 0, selected: int = 0, dismissed: int = 0) -> dict[str, object]:
    return {
        "status": status,
        "allow_clicked": clicked,
        "persistent_selected": selected,
        "dismissed": dismissed,
    }


async def trusted_approval_retry(page: Page, *, active: Callable[[], bool]) -> object:
    """Use a real browser click if ChatGPT ignored the scoped DOM click.

    The selector is marked only by approve_connector.js after it verifies a
    recognizable permission group. No message text or other controls are read.
    """
    if not active():
        return _result("idle")
    candidate = page.locator("[data-prompta-approval-candidate]")
    try:
        if await candidate.count() != 1 or not await candidate.is_visible():
            return _result("stuck")
        kind = await candidate.get_attribute("data-prompta-approval-candidate")
        if kind not in ("button", "checkbox"):
            return _result("stuck")
        if not active():
            return _result("idle")
        await candidate.click(timeout=1800)
        if kind == "checkbox":
            return (
                _result("progress", selected=1)
                if await candidate.is_checked() else _result("stuck")
            )
        try:
            await candidate.wait_for(state="hidden", timeout=1200)
        except PlaywrightTimeoutError:
            return _result("stuck", clicked=1)
        return _result("dismissed", clicked=1, dismissed=1)
    except PlaywrightError:
        return _result("stuck")


async def supervise_connector_approvals(
    evaluate: Callable[[str], Awaitable[object]],
    *,
    deadline: float,
    source: str,
    poll_interval_seconds: float,
    active: Callable[[], bool],
    trusted_retry: Callable[[], Awaitable[object]] | None = None,
) -> ApprovalCounters:
    """Click scoped permissions until expiry or loss of ownership.

    A confirmed grant is followed by an immediate scan because another tool
    permission can appear without a new response/capture event.
    """
    loop = asyncio.get_running_loop()
    counts = ApprovalCounters()
    try:
        while (remaining := deadline - loop.time()) > 0:
            if not active():
                break
            try:
                before = tuple(vars(counts).values())
                status = counts.record(
                    await asyncio.wait_for(evaluate(_APPROVAL_SCRIPT), timeout=min(5.0, remaining))
                )
                if status == "stuck" and trusted_retry is not None and active():
                    status = counts.record(
                        await asyncio.wait_for(
                            trusted_retry(), timeout=min(4.0, max(0.1, deadline - loop.time()))
                        )
                    )
                if status in ("stuck", "invalid"):
                    counts.timeout_failure += 1
                if tuple(vars(counts).values()) != before:
                    logger.info(
                        "Connector approval counters source=%s detected=%d persistent_selected=%d "
                        "allow_clicked=%d dismissed=%d timeout_failure=%d",
                        source, counts.detected, counts.persistent_selected,
                        counts.allow_clicked, counts.dismissed, counts.timeout_failure,
                    )
                if status in ("dismissed", "progress"):
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                counts.timeout_failure += 1
                logger.warning(
                    "Connector approval check failed source=%s error_type=%s timeout_failure=%d",
                    source, type(exc).__name__, counts.timeout_failure,
                )
            await asyncio.sleep(min(poll_interval_seconds, max(0.0, deadline - loop.time())))
    finally:
        logger.info(
            "Connector approval final source=%s detected=%d persistent_selected=%d "
            "allow_clicked=%d dismissed=%d timeout_failure=%d",
            source, counts.detected, counts.persistent_selected,
            counts.allow_clicked, counts.dismissed, counts.timeout_failure,
        )
    return counts
