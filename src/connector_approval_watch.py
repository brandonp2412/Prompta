"""Watch rendered unread ChatGPT sidebar rows for connector approvals.

This opt-in service uses one background sidebar tab plus temporary background
conversation tabs. It never requests history APIs, reads message bodies, sends
prompts, or touches a tab belonging to the user or delivery worker.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import OrderedDict

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from .browser_ownership import MAX_OWNED_TAB_AGE_SECONDS
from .browser_script_loader import load_browser_script
from .config import ConnectorApproval

logger = logging.getLogger(__name__)

_CHAT_PATH = re.compile(r"/c/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.IGNORECASE)
_SCAN_INTERVAL_SECONDS = 5.0
_SIDEBAR_REFRESH_SECONDS = 60.0
_MAX_WATCHED_CHATS = 8
_MAX_REMEMBERED_CHATS = 512
_APPROVAL_SCRIPT = load_browser_script("approve_connector.js")
_UNREAD_SCRIPT = load_browser_script("find_unread_chats.js")


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


async def watch_chat(browser: Browser, context: BrowserContext, path: str) -> None:
    page: Page | None = None
    approved_count = 0
    try:
        page = await background_page(browser, context)
        await page.goto("https://chatgpt.com" + path, wait_until="domcontentloaded", timeout=30000)
        deadline = asyncio.get_running_loop().time() + MAX_OWNED_TAB_AGE_SECONDS
        while not page.is_closed() and asyncio.get_running_loop().time() < deadline:
            if not ConnectorApproval.load().enabled:
                return
            # A ChatGPT redirect/login is never a permission grant.
            if page.url.split("?", 1)[0].rstrip("/") != "https://chatgpt.com" + path:
                return
            try:
                approved = await asyncio.wait_for(page.evaluate(_APPROVAL_SCRIPT), timeout=5.0)
                if approved is True:
                    approved_count += 1
                    logger.info("Background ChatGPT connector grant confirmed count=%d", approved_count)
                    continue  # Successive permission dialogs can appear immediately.
                if approved == "stuck":
                    logger.warning("Background ChatGPT connector grant did not dismiss")
            except Exception as exc:
                logger.warning("Background ChatGPT permission check failed type=%s", type(exc).__name__)
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Background ChatGPT conversation watch failed type=%s", type(exc).__name__)
    finally:
        if page is not None and not page.is_closed():
            await page.close()


async def watch_sidebar(browser: Browser, context: BrowserContext) -> None:
    sidebar: Page | None = None
    watches: dict[str, asyncio.Task[None]] = {}
    remembered: OrderedDict[str, float] = OrderedDict()
    loop = asyncio.get_running_loop()
    try:
        sidebar = await background_page(browser, context)
        await sidebar.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=30000)
        last_refresh = loop.time()
        while not sidebar.is_closed():
            if not ConnectorApproval.load().enabled:
                return
            now = loop.time()
            if now - last_refresh >= _SIDEBAR_REFRESH_SECONDS:
                await sidebar.reload(wait_until="domcontentloaded", timeout=30000)
                last_refresh = loop.time()
            for path, task in list(watches.items()):
                if task.done():
                    await task
                    del watches[path]
            # Only rendered unread markers: no account-wide history endpoints.
            raw = await asyncio.wait_for(sidebar.evaluate(_UNREAD_SCRIPT), timeout=5.0)
            for path in unread_chat_paths(raw):
                if path in watches or remembered.get(path, 0.0) > now:
                    continue
                if len(watches) >= _MAX_WATCHED_CHATS:
                    break
                watches[path] = asyncio.create_task(watch_chat(browser, context, path))
                remembered[path] = now + MAX_OWNED_TAB_AGE_SECONDS
                remembered.move_to_end(path)
                if len(remembered) > _MAX_REMEMBERED_CHATS:
                    remembered.popitem(last=False)
                logger.info("Background ChatGPT unread conversation watch started")
            await asyncio.sleep(_SCAN_INTERVAL_SECONDS)
    finally:
        for task in watches.values():
            task.cancel()
        await asyncio.gather(*watches.values(), return_exceptions=True)
        if sidebar is not None and not sidebar.is_closed():
            await sidebar.close()


async def run_forever(address: str = "127.0.0.1:9223") -> None:
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
                    await watch_sidebar(browser, contexts[0])
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
