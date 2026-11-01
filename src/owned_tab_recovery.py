"""Recover interrupted Prompta chats from their surviving, owned Brave tabs.

Discovery reads only the local CDP target inventory and Prompta's ownership
ledger. The driver attaches to an exact pre-existing target: it never opens a
page, navigates ChatGPT, or sends an original message.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import UUID

from patchright.async_api import Browser, Page, Playwright, async_playwright
from sqlalchemy import func, select

from .browser_ownership import (
    MAX_OWNED_TAB_AGE_SECONDS,
    OWNED_TAB_LEDGER,
    owned_tab_records,
    owned_window_owner_alive,
    owned_window_owner_id,
    owned_window_started_at,
    touch_owned_tab,
)
from .connector_approval_supervisor import trusted_approval_retry
from .response_store import ResponseStore
from .response_tables import history_recovery_attempts, local_chat_pins, results

logger = logging.getLogger(__name__)
_DELIVERY_PREFIX = "prompta-delivery:"


@dataclass(frozen=True)
class SurvivingTab:
    target_id: str
    conversation_id: str


@dataclass(frozen=True)
class OwnedRecoveryCandidate:
    send_id: str
    tab: SurvivingTab


def _conversation_from_url(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "chatgpt.com"
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/c/")
    ):
        return None
    value = parsed.path.removeprefix("/c/")
    try:
        return value if str(UUID(value)) == value else None
    except (ValueError, AttributeError):
        return None


def surviving_owned_tabs(
    debugger_address: str,
    *,
    ledger_path: Path = OWNED_TAB_LEDGER,
    now: float | None = None,
) -> tuple[SurvivingTab, ...]:
    """Use only the loopback CDP metadata and unexpired Prompta target IDs."""
    host, separator, port = debugger_address.rpartition(":")
    if not separator or host not in ("127.0.0.1", "localhost", "[::1]"):
        return ()
    try:
        port_number = int(port)
        if not 1 <= port_number <= 65535:
            return ()
        with urlopen(f"http://{debugger_address}/json/list", timeout=2.0) as reply:
            payload = json.load(reply)
    except (OSError, ValueError, TypeError):
        return ()
    if not isinstance(payload, list):
        return ()
    stamp = time.time() if now is None else now
    ledger = owned_tab_records(ledger_path)
    matches: list[SurvivingTab] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("type") != "page":
            continue
        target = item.get("id")
        last_activity = ledger.get(target) if isinstance(target, str) else None
        if (
            last_activity is None
            or last_activity > stamp
            or stamp - last_activity >= MAX_OWNED_TAB_AGE_SECONDS
        ):
            continue
        conversation = _conversation_from_url(item.get("url"))
        if conversation is not None:
            matches.append(SurvivingTab(target, conversation))
    return tuple(matches)


def next_owned_recovery_candidate(
    store: ResponseStore,
    debugger_address: str,
    *,
    ledger_path: Path = OWNED_TAB_LEDGER,
    now: float | None = None,
) -> OwnedRecoveryCandidate | None:
    """Select a due incomplete capture whose exact URL has one surviving target."""
    stamp = time.time() if now is None else now
    tabs = surviving_owned_tabs(debugger_address, ledger_path=ledger_path, now=stamp)
    by_conversation: dict[str, list[SurvivingTab]] = {}
    for tab in tabs:
        by_conversation.setdefault(tab.conversation_id, []).append(tab)
    unique = {
        conversation: matches[0]
        for conversation, matches in by_conversation.items()
        if len(matches) == 1
    }
    if not unique:
        return None
    attempts = history_recovery_attempts
    joined = results.outerjoin(attempts, results.c.send_id == attempts.c.send_id).outerjoin(
        local_chat_pins, results.c.send_id == local_chat_pins.c.send_id
    )
    query = (
        select(
            results.c.send_id,
            results.c.conversation_id,
        )
        .select_from(joined)
        .where(
            results.c.status.in_(("interrupted", "unavailable")),
            results.c.capture_owner == "",
            results.c.conversation_id.in_(tuple(unique)),
            func.coalesce(attempts.c.next_attempt_at, 0) <= stamp,
        )
        .order_by(
            local_chat_pins.c.send_id.is_(None),
            # Give every due owned tab a first observation before revisiting
            # an empty tab; unobserved tabs may expire from Brave.
            func.coalesce(attempts.c.attempt_count, 0),
            func.coalesce(attempts.c.next_attempt_at, 0),
            results.c.created_at.desc(),
        )
    )
    with store.engine.connect() as connection:
        rows = connection.execute(query).mappings().all()
    # A conversation identity shared by multiple incomplete sends cannot prove
    # which saved run owns the visible answer; fail closed on that conversation.
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row["conversation_id"])
        counts[key] = counts.get(key, 0) + 1
    for row in rows:
        conversation = str(row["conversation_id"])
        if counts[conversation] == 1:
            return OwnedRecoveryCandidate(str(row["send_id"]), unique[conversation])
    return None


class ExistingOwnedTabDriver:
    """Read/continue one orphaned delivery tab without creating or closing tabs."""

    def __init__(
        self,
        debugger_address: str,
        tab: SurvivingTab,
        *,
        ledger_path: Path = OWNED_TAB_LEDGER,
    ) -> None:
        self.debugger_address = debugger_address
        self.tab = tab
        self.ledger_path = ledger_path
        self.context = "surviving-owned-tab"
        self._patchright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._marker = ""

    def _assert_fresh_ledger(self) -> None:
        stamp = time.time()
        last = owned_tab_records(self.ledger_path).get(self.tab.target_id)
        if last is None or last > stamp or stamp - last >= MAX_OWNED_TAB_AGE_SECONDS:
            raise RuntimeError("Surviving tab ownership expired")

    async def _verify_page(self) -> Page:
        page = self._page
        if page is None or page.is_closed():
            raise RuntimeError("Surviving tab is not attached")
        if _conversation_from_url(page.url) != self.tab.conversation_id:
            raise RuntimeError("Surviving tab changed conversation")
        marker = await page.evaluate("window.name", isolated_context=True)
        if marker != self._marker:
            raise RuntimeError("Surviving tab ownership marker changed")
        self._assert_fresh_ledger()
        return page

    async def connect(self) -> None:
        self._assert_fresh_ledger()
        self._patchright = await async_playwright().start()
        self._browser = await self._patchright.chromium.connect_over_cdp(
            f"http://{self.debugger_address}",
            timeout=7000,
        )
        for context in self._browser.contexts:
            for page in context.pages:
                if _conversation_from_url(page.url) != self.tab.conversation_id:
                    continue
                session = await context.new_cdp_session(page)
                try:
                    info = await session.send("Target.getTargetInfo")
                finally:
                    await session.detach()
                target_info = info.get("targetInfo")
                target_id = target_info.get("targetId") if isinstance(target_info, dict) else None
                if target_id != self.tab.target_id:
                    continue
                marker = await page.evaluate("window.name", isolated_context=True)
                owner = owned_window_owner_id(marker, prefix=_DELIVERY_PREFIX)
                started = owned_window_started_at(marker, prefix=_DELIVERY_PREFIX)
                if (
                    owner is None
                    or started is None
                    or started > time.time()
                    or owned_window_owner_alive(owner)
                ):
                    raise RuntimeError("Surviving tab is not an orphaned Prompta delivery")
                self._marker = marker
                self._page = page
                if not touch_owned_tab(self.tab.target_id, time.time(), self.ledger_path):
                    raise RuntimeError("Surviving tab lease could not be renewed")
                logger.info(
                    "Reattached orphaned Prompta delivery send conversation=%s",
                    self.tab.conversation_id,
                )
                return
        raise RuntimeError("Surviving Prompta-owned CDP target no longer exists")

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        if context != self.context or url != "https://chatgpt.com/c/" + self.tab.conversation_id:
            raise RuntimeError("Surviving tab recovery forbids navigation")
        await self._verify_page()  # A no-op: never call page.goto.

    async def dom_state(self) -> dict[str, object]:
        page = await self._verify_page()
        text = await page.evaluate(
            """() => [...document.querySelectorAll('[role="alert"],[role="status"]')]
                .slice(0, 5).map(node => (node.textContent || '').slice(0, 500)).join('\\n')""",
            isolated_context=True,
        )
        return {"rate_limit_text": text if isinstance(text, str) else ""}

    async def eval(self, expression: str) -> object:
        page = await self._verify_page()
        return await page.evaluate(expression, isolated_context=True)

    async def click_stuck_connector_approval(self) -> object:
        return await trusted_approval_retry(await self._verify_page())

    async def close(self) -> None:
        self._page = None
        if self._patchright is not None:
            # Stopping this CDP client leaves the user's persistent Brave tab open.
            await self._patchright.stop()
        self._patchright = None
        self._browser = None
