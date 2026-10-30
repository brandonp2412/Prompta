"""Watch rendered unread ChatGPT sidebar rows for connector approvals.

This opt-in service uses one background sidebar tab plus temporary background
conversation tabs. It also watches permission controls in already-open user
conversation tabs without navigating or closing them. It never requests history
APIs, reads message bodies, sends prompts, or modifies delivery-owned tabs.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Browser, BrowserContext, Page, Response, async_playwright

from .account_read_gate import AccountReadGate
from .browser_ownership import MAX_OWNED_TAB_AGE_SECONDS
from .browser_script_loader import load_browser_script
from .config import ConnectorApproval
from .connector_approval_supervisor import supervise_connector_approvals

logger = logging.getLogger(__name__)

_CHAT_PATH = re.compile(r"/c/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.IGNORECASE)
_SCAN_INTERVAL_SECONDS = 5.0
_SIDEBAR_REFRESH_SECONDS = 60.0
_MAX_WATCHED_CHATS = 8
_MAX_OPEN_CHAT_WATCHES = 16
_MAX_REMEMBERED_CHATS = 512
_FAILED_CHAT_RETRY_SECONDS = 90.0
_UNREAD_SCRIPT = load_browser_script("find_unread_chats.js")
_TAB_MARKER_SCRIPT = load_browser_script("get_window_name.js")
_CHAT_LOAD_SCRIPT = load_browser_script("connector_chat_load_state.js")


def unread_chat_paths(value: object) -> list[str]:
    """Accept only exact ChatGPT conversation routes from a rendered sidebar."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and _CHAT_PATH.fullmatch(item) and item not in result:
            result.append(item)
    return result[:_MAX_WATCHED_CHATS]


async def background_page(browser: Browser, context: BrowserContext) -> Page:
    """Open a CDP target without bringing it to the front of the user's browser."""
    session = await browser.new_browser_cdp_session()
    try:
        async with context.expect_page(timeout=10000) as event:
            await session.send("Target.createTarget", {"url": "about:blank", "background": True})
        return await event.value
    finally:
        await session.detach()


def chat_path_from_url(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != "chatgpt.com":
        return None
    return parts.path if _CHAT_PATH.fullmatch(parts.path) else None


def track_account_read_limits(page: Page, gate: AccountReadGate) -> None:
    """Observe response status/Retry-After only; never inspect network bodies."""

    def on_response(response: Response) -> None:
        url = urlsplit(response.url)
        if (
            response.status != 429
            or url.hostname != "chatgpt.com"
            or not (url.path.startswith("/backend-api/") or url.path.startswith("/c/"))
        ):
            return
        try:
            gate.note_http_429(response.headers.get("retry-after"))
        except Exception as exc:
            logger.warning("ChatGPT read backoff persistence failed type=%s", type(exc).__name__)

    page.on("response", on_response)


async def wait_for_account_read(gate: AccountReadGate) -> bool:
    """Stop all new ChatGPT network reads while the shared cooldown is active."""
    while ConnectorApproval.load().enabled:
        remaining = gate.remaining()
        if remaining <= 0:
            return True
        await asyncio.sleep(min(10.0, max(0.2, remaining)))
    return False


async def chat_loaded(page: Page, gate: AccountReadGate) -> bool:
    """A URL/title alone is not proof that ChatGPT hydrated its conversation."""
    for _ in range(24):
        if gate.remaining() > 0:
            return False
        state = await asyncio.wait_for(page.evaluate(_CHAT_LOAD_SCRIPT), timeout=3.0)
        if isinstance(state, dict):
            if state.get("limited") is True:
                gate.note_http_429()
                return False
            if state.get("failed") is True:
                logger.warning("ChatGPT approval tab failed to load conversation")
                return False
            if state.get("loaded") is True:
                return True
        await asyncio.sleep(0.5)
    logger.warning("ChatGPT approval tab never hydrated conversation")
    return False


async def open_chat_candidates(
    context: BrowserContext, excluded: set[Page]
) -> list[tuple[Page, str]]:
    """Identify open non-Prompta chats without reading their conversation content."""
    result: list[tuple[Page, str]] = []
    for page in context.pages:
        if page.is_closed() or page in excluded:
            continue
        path = chat_path_from_url(page.url)
        if path is None:
            continue
        try:
            marker = await asyncio.wait_for(page.evaluate(_TAB_MARKER_SCRIPT), timeout=0.75)
        except Exception:
            continue
        if not isinstance(marker, str) or marker.startswith(("prompta:", "prompta-delivery:")):
            continue  # The live capture/reply watcher owns this tab.
        result.append((page, path))
        if len(result) >= _MAX_OPEN_CHAT_WATCHES:
            break
    return result


async def watch_open_chat(page: Page, path: str) -> None:
    """Backup permission clicks in user-opened chats; never navigate or close them."""
    deadline = asyncio.get_running_loop().time() + MAX_OWNED_TAB_AGE_SECONDS

    def active() -> bool:
        return (
            not page.is_closed()
            and ConnectorApproval.load().enabled
            and chat_path_from_url(page.url) == path
        )

    await supervise_connector_approvals(
        page.evaluate,
        deadline=deadline,
        source="backup-open",
        poll_interval_seconds=1.0,
        active=active,
    )


async def watch_chat(
    browser: Browser,
    context: BrowserContext,
    path: str,
    owned_pages: set[Page] | None = None,
    gate: AccountReadGate | None = None,
) -> bool:
    page: Page | None = None
    try:
        if gate is not None and not await wait_for_account_read(gate):
            return False
        page = await background_page(browser, context)
        assert page is not None
        if owned_pages is not None:
            owned_pages.add(page)
        if gate is not None:
            track_account_read_limits(page, gate)
        await page.goto("https://chatgpt.com" + path, wait_until="domcontentloaded", timeout=30000)
        if gate is not None and not await chat_loaded(page, gate):
            return False
        watched_page = page
        deadline = asyncio.get_running_loop().time() + MAX_OWNED_TAB_AGE_SECONDS

        def active() -> bool:
            return (
                not watched_page.is_closed()
                and ConnectorApproval.load().enabled
                and watched_page.url.split("?", 1)[0].rstrip("/") == "https://chatgpt.com" + path
            )

        await supervise_connector_approvals(
            watched_page.evaluate,
            deadline=deadline,
            source="backup",
            poll_interval_seconds=1.0,
            active=active,
        )
        return True
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Background ChatGPT conversation watch failed type=%s", type(exc).__name__)
        return False
    finally:
        if page is not None:
            if owned_pages is not None:
                owned_pages.discard(page)
            if not page.is_closed():
                await page.close()


async def watch_sidebar(
    browser: Browser, context: BrowserContext, gate: AccountReadGate | None = None
) -> None:
    sidebar: Page | None = None
    watches: dict[str, asyncio.Task[bool]] = {}
    open_watches: dict[Page, asyncio.Task[None]] = {}
    owned_pages: set[Page] = set()
    remembered: OrderedDict[str, float] = OrderedDict()
    loop = asyncio.get_running_loop()
    try:
        if gate is not None and not await wait_for_account_read(gate):
            return
        sidebar = await background_page(browser, context)
        assert sidebar is not None
        owned_pages.add(sidebar)
        if gate is not None:
            track_account_read_limits(sidebar, gate)
        await sidebar.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=30000)
        last_refresh = loop.time()
        while not sidebar.is_closed():
            if not ConnectorApproval.load().enabled:
                return
            now = loop.time()
            allowed = gate is None or gate.remaining() <= 0
            if allowed and now - last_refresh >= _SIDEBAR_REFRESH_SECONDS:
                await sidebar.reload(wait_until="domcontentloaded", timeout=30000)
                last_refresh = loop.time()
                allowed = gate is None or gate.remaining() <= 0
            for path, task in list(watches.items()):
                if task.done():
                    succeeded = await task
                    if succeeded:
                        remembered[path] = now + MAX_OWNED_TAB_AGE_SECONDS
                    del watches[path]
            for page, task in list(open_watches.items()):
                if task.done():
                    await task
                    del open_watches[page]
            # Already-open user tabs only need local permission DOM checks.
            excluded = owned_pages | set(open_watches)
            for page, path in await open_chat_candidates(context, excluded):
                if len(open_watches) >= _MAX_OPEN_CHAT_WATCHES:
                    break
                open_watches[page] = asyncio.create_task(watch_open_chat(page, path))
            # Never navigate unread chats or refresh ChatGPT during account backoff.
            if allowed:
                raw = await asyncio.wait_for(sidebar.evaluate(_UNREAD_SCRIPT), timeout=5.0)
                for path in unread_chat_paths(raw):
                    if path in watches or remembered.get(path, 0.0) > now:
                        continue
                    if len(watches) >= _MAX_WATCHED_CHATS or (gate is not None and gate.remaining() > 0):
                        break
                    watches[path] = asyncio.create_task(
                        watch_chat(browser, context, path, owned_pages, gate)
                    )
                    remembered[path] = now + _FAILED_CHAT_RETRY_SECONDS
                    remembered.move_to_end(path)
                    if len(remembered) > _MAX_REMEMBERED_CHATS:
                        remembered.popitem(last=False)
                    logger.info("Background ChatGPT unread conversation watch started")
            await asyncio.sleep(_SCAN_INTERVAL_SECONDS)
    finally:
        for task in [*watches.values(), *open_watches.values()]:
            task.cancel()
        await asyncio.gather(*watches.values(), *open_watches.values(), return_exceptions=True)
        if sidebar is not None and not sidebar.is_closed():
            await sidebar.close()


async def run_forever(
    address: str = "127.0.0.1:9223", gate: AccountReadGate | None = None
) -> None:
    if gate is None:
        state_path = Path(
            os.environ.get(
                "PROMPTA_STATE_PATH",
                str(Path.home() / ".local/state/prompta/runtime.sqlite3"),
            )
        ).expanduser()
        gate = AccountReadGate(state_path)
    while True:
        if not ConnectorApproval.load().enabled:
            await asyncio.sleep(10.0)
            continue
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(
                    "http://" + address, timeout=10000
                )
                try:
                    contexts = browser.contexts
                    if not contexts:
                        raise RuntimeError("Configured ChatGPT Chromium session has no context")
                    await watch_sidebar(browser, contexts[0], gate)
                finally:
                    await browser.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Background ChatGPT approval watcher reconnecting type=%s", type(exc).__name__)
        await asyncio.sleep(5.0)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    address = os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9223")
    asyncio.run(run_forever(address))


if __name__ == "__main__":
    main()
