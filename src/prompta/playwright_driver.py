from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    Request,
    Response,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from .chatgpt_dom import (
    COMPOSER_SELECTORS,
    CONVERSATION_HISTORY_RATE_LIMIT_SELECTOR,
    FILE_INPUT_SELECTORS,
    MESSAGE_ROLE_SELECTOR,
    RATE_LIMIT_SELECTORS,
    SEND_BUTTON_SELECTORS,
    STOP_BUTTON_SELECTORS,
)
from .webdriver import BrowserDriverBase, BrowsingContextUnavailableError

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_MS = 30_000
_OWNED_WINDOW_PREFIX = "prompta:"
_SEND_ENDPOINTS = ("/backend-api/f/conversation", "/backend-api/conversation")
_RATE_LIMIT_RE = re.compile(
    r"(?:too many requests|temporarily limited access|requests too quickly|rate limit)",
    re.IGNORECASE,
)
_LOGIN_RE = re.compile(r"^(?:log ?in|sign ?in)$", re.IGNORECASE)
_COMPOSER_NAME_RE = re.compile(
    r"(?:message|ask|chatgpt|prompt|send a message)",
    re.IGNORECASE,
)
_SEND_RE = re.compile(r"^(?:send|send prompt)$", re.IGNORECASE)
_STOP_RE = re.compile(r"^(?:stop|stop answering|stop generating)$", re.IGNORECASE)
_ATTACH_RE = re.compile(
    r"(?:add files? and more|attach|upload|add (?:file|photo))",
    re.IGNORECASE,
)
_RETRY_RE = re.compile(r"^(?:try again|retry|regenerate(?: response)?)$", re.IGNORECASE)
_DISMISS_RE = re.compile(r"^(?:got it|ok|okay|dismiss|close)$", re.IGNORECASE)
_EFFORT_RE = re.compile(r"\b(extra\s+high|instant|medium|high)\b", re.IGNORECASE)


class ChromeDebuggerUnavailableError(RuntimeError):
    """Raised when Prompta cannot attach Playwright to the configured Chromium CDP endpoint."""


class PlaywrightDriver(BrowserDriverBase):
    """Playwright-backed ChatGPT browser driver.

    Interactions intentionally prefer accessibility semantics (role/name/label/
    placeholder) and only fall back to stable test IDs or CSS when ChatGPT does
    not expose a useful semantic contract.
    """

    def __init__(
        self,
        *,
        profile: Path,
        chrome_path: str = "/usr/bin/chromium",
        headless: bool = True,
        auth_timeout_seconds: float = 30.0,
        debugger_address: str | None = None,
        flaresolverr_url: str | None = None,
        **_legacy: Any,
    ) -> None:
        super().__init__("")
        self.profile = profile.expanduser().resolve()
        self.chrome_path = chrome_path
        self.headless = headless
        self.auth_timeout_seconds = max(0.1, auth_timeout_seconds)
        self.debugger_address = debugger_address.strip() if debugger_address else None
        self.flaresolverr_url = flaresolverr_url.rstrip("/") if flaresolverr_url else None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_context: BrowserContext | None = None
        self._pages: dict[str, Page] = {}
        self._page_contexts: dict[Page, str] = {}
        self._owned_contexts: set[str] = set()
        self._attached = bool(self.debugger_address)
        self._bootstrap_url = ""
        self._connected = False

    @property
    def is_connected(self) -> bool:
        if not self._connected or not self.context:
            return False
        page = self._pages.get(self.context)
        if page is None or page.is_closed():
            return False
        if self._browser is not None and not self._browser.is_connected():
            return False
        return True

    @staticmethod
    def _is_chatgpt_url(url: str) -> bool:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        return parsed.scheme in {"http", "https"} and (
            host == "chatgpt.com" or host.endswith(".chatgpt.com")
        )

    def _assert_debugger_available(self) -> None:
        if not self.debugger_address:
            return
        endpoint = f"http://{self.debugger_address}/json/version"
        try:
            with urlopen(endpoint, timeout=1.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ChromeDebuggerUnavailableError(
                f"Chromium debugger at {self.debugger_address} is unavailable"
            ) from exc
        if not isinstance(payload, dict) or not payload.get("webSocketDebuggerUrl"):
            raise ChromeDebuggerUnavailableError(
                f"Chromium debugger at {self.debugger_address} is unavailable"
            )

    def _register_page(self, page: Page, *, owned: bool) -> str:
        existing = self._page_contexts.get(page)
        if existing:
            if owned:
                self._owned_contexts.add(existing)
            return existing
        context_id = uuid.uuid4().hex
        self._pages[context_id] = page
        self._page_contexts[page] = context_id
        if owned:
            self._owned_contexts.add(context_id)
        page.set_default_timeout(_DEFAULT_TIMEOUT_MS)
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("requestfinished", self._on_request_finished)
        page.on("requestfailed", self._on_request_failed)
        page.on("close", lambda closed_page: self._forget_page(closed_page))
        return context_id

    def _forget_page(self, page: Page) -> None:
        context_id = self._page_contexts.pop(page, "")
        if not context_id:
            return
        self._pages.pop(context_id, None)
        self._owned_contexts.discard(context_id)
        if self.context == context_id:
            self.context = next(
                (
                    candidate
                    for candidate in self._owned_contexts
                    if candidate in self._pages and not self._pages[candidate].is_closed()
                ),
                "",
            )

    async def _mark_owned(self, page: Page) -> None:
        stamp = int(time.time())
        marker = f"{_OWNED_WINDOW_PREFIX}{stamp}:{uuid.uuid4().hex}"
        await page.evaluate("(value) => { window.name = value; }", marker)

    async def _is_owned_page(self, page: Page) -> bool:
        if page.is_closed():
            return False
        try:
            name = await page.evaluate("window.name")
        except PlaywrightError:
            return False
        return isinstance(name, str) and name.startswith(_OWNED_WINDOW_PREFIX)

    async def _cleanup_stale_owned_pages(self, browser_context: BrowserContext) -> None:
        for page in list(browser_context.pages):
            if await self._is_owned_page(page):
                try:
                    await page.close()
                except PlaywrightError:
                    pass

    def _on_request(self, request: Request) -> None:
        capture = self._send_capture
        if capture is None:
            return
        if (
            request.method.upper() != "POST"
            or urlsplit(request.url).path.rstrip("/") not in _SEND_ENDPOINTS
        ):
            return
        capture["request_obj"] = request
        capture["request_id"] = str(id(request))

    def _on_response(self, response: Response) -> None:
        capture = self._send_capture
        if capture is None or capture.get("request_obj") is not response.request:
            return
        capture["status"] = int(response.status)
        capture["response_started"] = True

    def _on_request_finished(self, request: Request) -> None:
        capture = self._send_capture
        if capture is not None and capture.get("request_obj") is request:
            capture["completed"] = True

    def _on_request_failed(self, request: Request) -> None:
        capture = self._send_capture
        if capture is not None and capture.get("request_obj") is request:
            capture["fetch_error"] = str(request.failure or "request failed")

    def arm_send_capture(self) -> dict[str, Any]:
        if not self.is_connected:
            raise RuntimeError("Playwright browser is not connected")
        capture: dict[str, Any] = {
            "request_id": "",
            "request_obj": None,
            "status": 0,
            "response_started": False,
            "completed": False,
            "fetch_error": "",
        }
        self._send_capture = capture
        return capture

    def clear_send_capture(self, capture: dict[str, Any]) -> None:
        if self._send_capture is capture:
            self._send_capture = None
        capture.pop("request_obj", None)

    async def _first_usable(
        self,
        locators: list[Locator],
        *,
        enabled: bool = True,
        limit: int = 12,
    ) -> Locator | None:
        for locator in locators:
            try:
                count = min(await locator.count(), limit)
            except PlaywrightError:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if not await candidate.is_visible():
                        continue
                    if enabled and not await candidate.is_enabled():
                        continue
                    return candidate
                except PlaywrightError:
                    continue
        return None

    async def _composer(self, page: Page) -> Locator | None:
        semantic = [
            page.get_by_role("textbox", name=_COMPOSER_NAME_RE),
            page.get_by_label(_COMPOSER_NAME_RE),
            page.get_by_placeholder(_COMPOSER_NAME_RE),
            page.get_by_role("textbox"),
        ]
        found = await self._first_usable(semantic)
        if found is not None:
            return found
        return await self._first_usable([page.locator(selector) for selector in COMPOSER_SELECTORS])

    async def _semantic_button(
        self,
        page: Page,
        name: re.Pattern[str],
        *,
        fallback_test_ids: tuple[str, ...] = (),
        fallback_selectors: tuple[str, ...] = (),
    ) -> Locator | None:
        semantic = await self._first_usable([page.get_by_role("button", name=name)])
        if semantic is not None:
            return semantic
        for test_id in fallback_test_ids:
            candidate = await self._first_usable([page.get_by_test_id(test_id)])
            if candidate is not None:
                return candidate
        if fallback_selectors:
            return await self._first_usable(
                [page.locator(selector) for selector in fallback_selectors]
            )
        return None

    def _page(self, context: str | None = None) -> Page:
        target = context or self.context
        page = self._pages.get(target)
        if page is None or page.is_closed():
            if target:
                self._owned_contexts.discard(target)
                self._pages.pop(target, None)
            raise BrowsingContextUnavailableError(
                f"Playwright browsing context {target or '<default>'} is unavailable"
            )
        return page

    async def connect(self) -> None:
        if self.is_connected:
            return
        if self.needs_browser_restart:
            raise RuntimeError("Playwright browser session is poisoned; browser restart required")
        await self.close()
        self._playwright = await async_playwright().start()
        try:
            if self.debugger_address:
                await asyncio.to_thread(self._assert_debugger_available)
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    f"http://{self.debugger_address}"
                )
                contexts = list(self._browser.contexts)
                if not contexts:
                    raise RuntimeError("Attached Chromium browser has no browser context")
                browser_context = next(
                    (
                        candidate
                        for candidate in contexts
                        if any(self._is_chatgpt_url(page.url) for page in candidate.pages)
                    ),
                    contexts[0],
                )
                self._browser_context = browser_context
                chatgpt_pages = [
                    page
                    for page in browser_context.pages
                    if not page.is_closed() and self._is_chatgpt_url(page.url)
                ]
                conversation_page = next(
                    (
                        page
                        for page in chatgpt_pages
                        if (urlsplit(page.url).path.rstrip("/") or "/").startswith("/c/")
                    ),
                    None,
                )
                bootstrap = conversation_page or (chatgpt_pages[0] if chatgpt_pages else None)
                self._bootstrap_url = bootstrap.url if bootstrap is not None else ""
                await self._cleanup_stale_owned_pages(browser_context)
            else:
                self.profile.mkdir(parents=True, exist_ok=True)
                self._browser_context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile.resolve()),
                    executable_path=self.chrome_path,
                    headless=self.headless,
                    args=[
                        "--profile-directory=Default",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-background-networking",
                        "--disable-breakpad",
                        "--disable-component-update",
                        "--password-store=basic",
                        "--window-size=1280,1000",
                    ],
                )
                browser_context = self._browser_context
                existing = [
                    page
                    for page in browser_context.pages
                    if not page.is_closed() and self._is_chatgpt_url(page.url)
                ]
                self._bootstrap_url = existing[0].url if existing else ""

            page = await browser_context.new_page()
            await self._mark_owned(page)
            self.context = self._register_page(page, owned=True)
            self._network_subscribed = True
            self._connected = True

            if self.debugger_address and self._bootstrap_url:
                await page.goto(self._bootstrap_url, wait_until="domcontentloaded")
                await self.wait_for_composer(
                    timeout=max(5.0, self.auth_timeout_seconds),
                    context=self.context,
                )
                new_chat = await self._first_usable(
                    [
                        page.get_by_role("link", name=re.compile(r"^new chat$", re.IGNORECASE)),
                        page.get_by_role("button", name=re.compile(r"^new chat$", re.IGNORECASE)),
                    ]
                )
                if new_chat is not None:
                    await new_chat.click()
                    try:
                        await page.wait_for_url(
                            re.compile(r"https://chatgpt\.com/?(?:\?.*)?$"),
                            timeout=10_000,
                        )
                    except PlaywrightTimeoutError:
                        pass
            else:
                await page.goto("https://chatgpt.com/", wait_until="domcontentloaded")

            deadline = asyncio.get_running_loop().time() + self.auth_timeout_seconds
            last_error: Exception | None = None
            while asyncio.get_running_loop().time() < deadline:
                try:
                    if await self.login_required():
                        raise RuntimeError("Prompta Chromium profile is not logged into ChatGPT")
                    if await self.ensure_token():
                        return
                except Exception as exc:
                    last_error = exc
                await asyncio.sleep(0.5)
        except BaseException:
            await self.close()
            raise

        await self.close()
        raise RuntimeError(
            "Prompta Chromium profile did not produce an authenticated ChatGPT "
            f"session within {self.auth_timeout_seconds:.0f}s"
        ) from last_error

    async def eval(
        self,
        expression: str,
        *,
        await_promise: bool = False,
        context: str | None = None,
    ) -> Any:
        del await_promise  # Playwright awaits returned promises automatically.
        page = self._page(context)
        try:
            return await asyncio.wait_for(page.evaluate(expression), timeout=30.0)
        except TimeoutError as exc:
            self.needs_browser_restart = True
            raise RuntimeError("Playwright page evaluation timed out after 30s") from exc
        except PlaywrightError as exc:
            message = str(exc).casefold()
            if any(
                text in message
                for text in (
                    "target page, context or browser has been closed",
                    "page has been closed",
                    "browser has been closed",
                )
            ):
                self._forget_page(page)
                raise BrowsingContextUnavailableError(
                    "Playwright browsing context is unavailable"
                ) from exc
            raise

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        page = self._page(context)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=_DEFAULT_TIMEOUT_MS)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Playwright navigation timed out for {url}") from exc

    async def activate_history_link(self, path: str, *, context: str | None = None) -> bool:
        page = self._page(context)
        target = path.rstrip("/") or "/"
        links = page.get_by_role("link")
        try:
            count = min(await links.count(), 250)
        except PlaywrightError:
            return False
        for index in range(count):
            link = links.nth(index)
            try:
                if not await link.is_visible():
                    continue
                href = await link.get_attribute("href")
                if not href:
                    continue
                if (urlsplit(href).path.rstrip("/") or "/") != target:
                    continue
                await link.click()
                return True
            except PlaywrightError:
                continue
        return False

    async def find_context_for_path(self, expected_path: str) -> str | None:
        browser_context = self._browser_context
        if browser_context is None:
            return None
        target_path = urlsplit(expected_path).path.rstrip("/") or "/"
        for page in list(browser_context.pages):
            if page.is_closed():
                continue
            if (urlsplit(page.url).path.rstrip("/") or "/") != target_path:
                continue
            context_id = self._page_contexts.get(page)
            if context_id:
                return context_id
            if not await self._is_owned_page(page):
                continue
            return self._register_page(page, owned=True)
        return None

    async def new_tab(self, url: str = "https://chatgpt.com/") -> str:
        browser_context = self._browser_context
        if browser_context is None:
            raise RuntimeError("Playwright browser context is not connected")
        page = await browser_context.new_page()
        await self._mark_owned(page)
        context_id = self._register_page(page, owned=True)
        self.context = context_id
        try:
            if (
                self.debugger_address
                and self._bootstrap_url
                and url.rstrip("/") == "https://chatgpt.com"
            ):
                await page.goto(self._bootstrap_url, wait_until="domcontentloaded")
                await self.wait_for_composer(
                    timeout=max(5.0, self.auth_timeout_seconds),
                    context=context_id,
                )
                new_chat = await self._first_usable(
                    [
                        page.get_by_role("link", name=re.compile(r"^new chat$", re.IGNORECASE)),
                        page.get_by_role("button", name=re.compile(r"^new chat$", re.IGNORECASE)),
                    ]
                )
                if new_chat is not None:
                    await new_chat.click()
                    return context_id
            await self.navigate(url, context=context_id)
            return context_id
        except BaseException:
            await self.close_context(context_id)
            raise

    async def close_context(self, context: str) -> None:
        page = self._pages.get(context)
        if page is None:
            self._owned_contexts.discard(context)
            return
        owned = context in self._owned_contexts
        if owned and not page.is_closed():
            try:
                await page.close()
            except PlaywrightError:
                pass
        self._forget_page(page)

    async def login_required(self) -> bool:
        page = self._page()
        direct = await self._first_usable(
            [
                page.get_by_role("button", name=_LOGIN_RE),
                page.get_by_role("link", name=_LOGIN_RE),
            ],
            enabled=False,
        )
        if direct is not None:
            return True
        fallback = await self._first_usable(
            [
                page.locator('button[data-testid="login-button"]'),
                page.locator('a[href*="/auth/login"]'),
                page.locator('a[href*="/login"]'),
            ],
            enabled=False,
        )
        return fallback is not None

    async def _cloudflare_challenge_present(self, *, context: str | None = None) -> bool:
        page = self._page(context)
        try:
            title = (await page.title()).casefold()
        except PlaywrightError:
            title = ""
        if "just a moment" in title or "attention required" in title:
            return True
        challenge = page.locator(
            "#challenge-form,#cf-challenge-running,#cf-please-wait,#challenge-spinner,"
            '#turnstile-wrapper,input[name="cf-turnstile-response"],'
            'iframe[src*="challenges.cloudflare.com"]'
        )
        return await self._first_usable([challenge], enabled=False) is not None

    def _request_flaresolverr(
        self,
        url: str,
        browser_user_agent: str,
    ) -> list[dict[str, Any]]:
        if not self.flaresolverr_url:
            return []
        body = json.dumps(
            {
                "cmd": "request.get",
                "url": url,
                "maxTimeout": 60_000,
            }
        ).encode("utf-8")
        request = UrlRequest(
            f"{self.flaresolverr_url}/v1",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=65.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            message = payload.get("message") if isinstance(payload, dict) else None
            raise RuntimeError(
                f"FlareSolverr failed to solve ChatGPT: {message or 'invalid response'}"
            )
        solution = payload.get("solution")
        if not isinstance(solution, dict):
            raise RuntimeError("FlareSolverr returned no solution for ChatGPT")
        solver_user_agent = str(solution.get("userAgent") or "")
        if browser_user_agent and solver_user_agent and solver_user_agent != browser_user_agent:
            raise RuntimeError(
                "FlareSolverr browser fingerprint does not match Prompta's attached browser"
            )
        raw_cookies = solution.get("cookies")
        if not isinstance(raw_cookies, list):
            return []
        return [
            cookie
            for cookie in raw_cookies
            if isinstance(cookie, dict)
            and str(cookie.get("name") or "").casefold().startswith(("cf_", "__cf", "_cf"))
        ]

    async def _recover_cloudflare(self, *, context: str | None = None) -> None:
        if not self.flaresolverr_url:
            raise RuntimeError("FlareSolverr is not configured")
        page = self._page(context)
        url = page.url
        user_agent = str(await page.evaluate("navigator.userAgent"))
        logger.warning("Cloudflare challenge detected; requesting clearance from FlareSolverr")
        cookies = await asyncio.to_thread(self._request_flaresolverr, url, user_agent)
        if not cookies:
            raise RuntimeError("FlareSolverr solved ChatGPT without returning Cloudflare cookies")
        browser_context = self._browser_context
        if browser_context is None:
            raise RuntimeError("Playwright browser context is not connected")
        converted: list[dict[str, Any]] = []
        for raw_cookie in cookies:
            cookie: dict[str, Any] = {
                "name": str(raw_cookie["name"]),
                "value": str(raw_cookie.get("value") or ""),
            }
            domain = raw_cookie.get("domain")
            path = raw_cookie.get("path")
            if isinstance(domain, str) and domain:
                cookie["domain"] = domain
                cookie["path"] = str(path or "/")
            else:
                cookie["url"] = url
            if isinstance(raw_cookie.get("secure"), bool):
                cookie["secure"] = raw_cookie["secure"]
            if isinstance(raw_cookie.get("httpOnly"), bool):
                cookie["httpOnly"] = raw_cookie["httpOnly"]
            expiry = raw_cookie.get("expires")
            if isinstance(expiry, (int, float)) and expiry > 0:
                cookie["expires"] = float(expiry)
            same_site = raw_cookie.get("sameSite")
            if same_site in {"Lax", "Strict", "None"}:
                cookie["sameSite"] = same_site
            converted.append(cookie)
        await browser_context.add_cookies(cast(Any, converted))
        await page.reload(wait_until="domcontentloaded")
        logger.info("Applied %d Cloudflare clearance cookie(s) from FlareSolverr", len(converted))

    async def wait_for_composer(
        self,
        timeout: float = 20.0,
        *,
        context: str | None = None,
    ) -> None:
        if self.flaresolverr_url and await self._cloudflare_challenge_present(context=context):
            await self._recover_cloudflare(context=context)
        page = self._page(context)
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if await self._composer(page) is not None:
                return
            await asyncio.sleep(0.15)
        if self.flaresolverr_url and await self._cloudflare_challenge_present(context=context):
            await self._recover_cloudflare(context=context)
            deadline = asyncio.get_running_loop().time() + timeout
            while asyncio.get_running_loop().time() < deadline:
                if await self._composer(page) is not None:
                    return
                await asyncio.sleep(0.15)
        raise RuntimeError("ChatGPT composer did not become ready")

    async def _focus_composer(self) -> Locator:
        await self.wait_for_composer()
        composer = await self._composer(self._page())
        if composer is None:
            raise RuntimeError("ChatGPT composer could not be focused")
        await composer.focus()
        return composer

    async def type_message(self, text: str) -> None:
        composer = await self._focus_composer()
        try:
            await composer.fill(text)
        except PlaywrightError:
            await composer.click()
            await self._page().keyboard.insert_text(text)
        actual = await self._composer_text(composer)
        expected = " ".join(text.split()).strip()
        if " ".join(actual.split()).strip() != expected:
            raise RuntimeError("ChatGPT composer did not contain the requested prompt")

    async def clear_composer(self, timeout: float = 3.0) -> None:
        composer = await self._focus_composer()
        try:
            await composer.fill("")
        except PlaywrightError:
            await composer.click()
            await self._page().keyboard.press("Control+A")
            await self._page().keyboard.press("Backspace")
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if not (await self._composer_text(composer)).strip():
                return
            await asyncio.sleep(0.1)
        raise RuntimeError("ChatGPT stale composer could not be cleared")

    async def _composer_text(self, composer: Locator) -> str:
        try:
            tag = (await composer.evaluate("el => el.tagName")).casefold()
            if tag in {"textarea", "input"}:
                return await composer.input_value()
            return await composer.inner_text()
        except PlaywrightError:
            return ""

    async def click_send(self) -> None:
        composer = await self._focus_composer()
        await composer.press("Enter")

    async def click_send_button(self, timeout: float = 120.0) -> None:
        page = self._page()
        deadline = asyncio.get_running_loop().time() + max(1.0, timeout)
        while asyncio.get_running_loop().time() < deadline:
            button = await self._semantic_button(
                page,
                _SEND_RE,
                fallback_test_ids=("send-button",),
                fallback_selectors=SEND_BUTTON_SELECTORS,
            )
            if button is not None:
                await button.click()
                return
            await asyncio.sleep(0.15)
        raise RuntimeError("ChatGPT send button did not become enabled")

    async def click_stop(self, context: str, timeout: float = 5.0) -> bool:
        page = self._page(context)
        deadline = asyncio.get_running_loop().time() + max(0.2, timeout)
        while asyncio.get_running_loop().time() < deadline:
            button = await self._semantic_button(
                page,
                _STOP_RE,
                fallback_test_ids=("stop-button",),
                fallback_selectors=STOP_BUTTON_SELECTORS,
            )
            if button is not None:
                await button.click()
                return True
            await asyncio.sleep(0.1)
        return False

    async def click_delivery_retry(self, context: str, timeout: float = 3.0) -> bool:
        page = self._page(context)
        deadline = asyncio.get_running_loop().time() + max(0.1, timeout)
        while asyncio.get_running_loop().time() < deadline:
            failure = page.get_by_text(
                re.compile(r"Message delivery timed out\.?\s*Please try again", re.IGNORECASE)
            )
            if await self._first_usable([failure], enabled=False) is None:
                await asyncio.sleep(0.15)
                continue
            retry = await self._semantic_button(page, _RETRY_RE)
            if retry is not None:
                await retry.click()
                return True
            await asyncio.sleep(0.15)
        return False

    async def attach_files(self, files: list[str]) -> None:
        paths = [str(Path(path).expanduser().resolve()) for path in files]
        if not paths:
            return
        for path in paths:
            if not Path(path).is_file():
                raise RuntimeError(f"Prompta attachment does not exist: {path}")
        page = self._page()

        file_input = await self._first_usable(
            [page.locator(selector) for selector in FILE_INPUT_SELECTORS],
            enabled=True,
        )
        if file_input is None:
            attach = await self._semantic_button(
                page,
                _ATTACH_RE,
                fallback_test_ids=("composer-plus-btn",),
            )
            if attach is not None:
                await attach.click()
                deadline = asyncio.get_running_loop().time() + 3.0
                while asyncio.get_running_loop().time() < deadline:
                    file_input = await self._first_usable(
                        [page.locator(selector) for selector in FILE_INPUT_SELECTORS],
                        enabled=True,
                    )
                    if file_input is not None:
                        break
                    await asyncio.sleep(0.1)
        if file_input is None:
            # Hidden file inputs are intentionally allowed here: file inputs have no
            # useful semantic role when ChatGPT keeps them visually hidden.
            fallback = page.locator('input[type="file"]')
            if await fallback.count():
                file_input = fallback.first
        if file_input is None:
            raise RuntimeError("ChatGPT attachment input could not be found")

        await file_input.set_input_files(paths)
        names = [Path(path).name for path in paths]
        deadline = asyncio.get_running_loop().time() + 120.0
        stable = 0
        while asyncio.get_running_loop().time() < deadline:
            selected = await file_input.evaluate(
                "input => Array.from(input.files || []).map(file => file.name)"
            )
            selected_names = set(selected or [])
            visible_names = True
            for name in names:
                if name in selected_names:
                    continue
                if (
                    await self._first_usable([page.get_by_text(name, exact=False)], enabled=False)
                    is None
                ):
                    visible_names = False
                    break
            busy = await self._first_usable(
                [
                    page.get_by_role("progressbar"),
                    page.locator('[aria-busy="true"]'),
                    page.locator('[data-testid*="upload" i]'),
                ],
                enabled=False,
            )
            if visible_names and busy is None:
                stable += 1
                if stable >= 3:
                    return
            else:
                stable = 0
            await asyncio.sleep(0.2)
        raise RuntimeError("ChatGPT attachment upload did not finish within 120s")

    async def dom_state(self) -> dict[str, Any]:
        page = self._page()
        composer = await self._composer(page)
        composer_text = await self._composer_text(composer) if composer is not None else ""

        users = page.locator(f'{MESSAGE_ROLE_SELECTOR}[data-message-author-role="user"]')
        last_user_id = ""
        last_user_text = ""
        try:
            count = await users.count()
            if count:
                last_user = users.nth(count - 1)
                last_user_id = (
                    await last_user.get_attribute("data-message-id")
                    or await last_user.get_attribute("data-message-uuid")
                    or ""
                )
                last_user_text = str(
                    await last_user.evaluate(
                        """root => {
                          const clone=root.cloneNode(true);
                          clone.querySelectorAll('button,[role="button"]').forEach(node=>node.remove());
                          const text=(clone.textContent||'').trim();
                          const suffix=['Show moreShow less','Show lessShow more'].find(v=>text.endsWith(v));
                          return (suffix?text.slice(0,-suffix.length):text).trim();
                        }"""
                    )
                    or ""
                )
        except PlaywrightError:
            pass

        rate_limit_texts: list[str] = []
        rate_limit_dialog: Locator | None = None

        async def is_history_rate_limit(candidate: Locator) -> bool:
            try:
                return bool(
                    await candidate.evaluate(
                        "(el, selector) => el.matches(selector) || Boolean(el.closest(selector))",
                        CONVERSATION_HISTORY_RATE_LIMIT_SELECTOR,
                    )
                )
            except PlaywrightError:
                return False

        # Conversation-history throttling is unrelated to sending prompts. Dismiss
        # it for hygiene, but never surface it as a send-rate-limit signal.
        history_rate_limit = await self._first_usable(
            [page.locator(CONVERSATION_HISTORY_RATE_LIMIT_SELECTOR)],
            enabled=False,
        )
        if history_rate_limit is not None:
            dismiss = await self._first_usable(
                [history_rate_limit.get_by_role("button", name=_DISMISS_RE)]
            )
            if dismiss is not None:
                try:
                    await dismiss.click()
                except PlaywrightError:
                    pass

        # A dedicated rate-limit dialog is a useful semantic signal. Generic
        # role=alert elements are intentionally ignored because ChatGPT uses them
        # for unrelated transient notifications.
        semantic_dialogs = page.get_by_role("dialog").filter(has_text=_RATE_LIMIT_RE)
        try:
            dialog_count = min(await semantic_dialogs.count(), 12)
        except PlaywrightError:
            dialog_count = 0
        for index in range(dialog_count):
            candidate = semantic_dialogs.nth(index)
            try:
                if not await candidate.is_visible() or await is_history_rate_limit(candidate):
                    continue
                text = (await candidate.inner_text()).strip()
            except PlaywrightError:
                continue
            if text and text not in rate_limit_texts:
                rate_limit_texts.append(text)
            if rate_limit_dialog is None:
                rate_limit_dialog = candidate

        # Fall back only to stable rate-limit test IDs. The history-throttling
        # test ID also contains "rate-limit", so explicitly exclude it.
        for selector in RATE_LIMIT_SELECTORS:
            matches = page.locator(selector).filter(has_text=_RATE_LIMIT_RE)
            try:
                match_count = min(await matches.count(), 12)
            except PlaywrightError:
                match_count = 0
            for index in range(match_count):
                candidate = matches.nth(index)
                try:
                    if not await candidate.is_visible() or await is_history_rate_limit(candidate):
                        continue
                    text = (await candidate.inner_text()).strip()
                except PlaywrightError:
                    continue
                if text and text not in rate_limit_texts:
                    rate_limit_texts.append(text)

        if rate_limit_dialog is not None:
            dismiss = await self._first_usable(
                [rate_limit_dialog.get_by_role("button", name=_DISMISS_RE)]
            )
            if dismiss is not None:
                try:
                    await dismiss.click()
                except PlaywrightError:
                    pass

        return {
            "composer_text": composer_text,
            "last_user_id": last_user_id,
            "last_user_text": last_user_text,
            "rate_limit_text": "\n".join(rate_limit_texts),
        }

    async def effort_trigger_info(self, timeout: float = 20.0) -> dict[str, Any]:
        page = self._page()
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            buttons = page.get_by_role("button")
            try:
                count = min(await buttons.count(), 100)
            except PlaywrightError:
                count = 0
            for index in range(count):
                button = buttons.nth(index)
                try:
                    if not await button.is_visible() or not await button.is_enabled():
                        continue
                    if not await button.get_attribute("aria-haspopup"):
                        continue
                    label = " ".join(
                        filter(
                            None,
                            (
                                await button.get_attribute("aria-label"),
                                await button.get_attribute("title"),
                                await button.inner_text(),
                            ),
                        )
                    )
                    match = _EFFORT_RE.search(label)
                    if not match:
                        continue
                    box = await button.bounding_box()
                    if box is None:
                        continue
                    selected = re.sub(r"\s+", " ", match.group(1)).strip().title()
                    return {
                        "text": selected,
                        "x": box["x"] + box["width"] / 2,
                        "y": box["y"] + box["height"] / 2,
                    }
                except PlaywrightError:
                    continue
            await asyncio.sleep(0.15)
        raise RuntimeError("ChatGPT thinking-effort control did not become available")

    async def high_effort_slider_point(self) -> dict[str, float]:
        page = self._page()
        deadline = asyncio.get_running_loop().time() + 3.0
        while asyncio.get_running_loop().time() < deadline:
            slider = await self._first_usable([page.get_by_role("slider")], enabled=True)
            if slider is None:
                await asyncio.sleep(0.1)
                continue
            try:
                min_value = float(await slider.get_attribute("aria-valuemin") or 0)
                max_value = float(await slider.get_attribute("aria-valuemax") or 3)
                target = 2.0
                if max_value <= min_value:
                    raise RuntimeError("ChatGPT High effort is unavailable: invalid-range")
                if target < min_value or target > max_value:
                    raise RuntimeError("ChatGPT High effort is unavailable: high-out-of-range")
                box = await slider.bounding_box()
                if box is None:
                    await asyncio.sleep(0.1)
                    continue
                padding = min(13.0, box["width"] / 4)
                usable = max(1.0, box["width"] - padding * 2)
                x = box["x"] + padding + usable * (target - min_value) / (max_value - min_value)
                y = box["y"] + box["height"] / 2
                return {"x": float(x), "y": float(y)}
            except (PlaywrightError, ValueError):
                await asyncio.sleep(0.1)
        raise RuntimeError("ChatGPT thinking-effort slider did not open")

    async def high_effort_slider_value(self) -> str:
        slider = await self._first_usable([self._page().get_by_role("slider")], enabled=True)
        if slider is None:
            return ""
        try:
            return str(await slider.get_attribute("aria-valuenow") or "")
        except PlaywrightError:
            return ""

    async def _click_viewport_point(self, context: str, x: float, y: float) -> None:
        page = self._page(context)
        viewport = await page.evaluate(
            "() => ({width: document.documentElement.clientWidth || innerWidth, "
            "height: document.documentElement.clientHeight || innerHeight})"
        )
        width = float((viewport or {}).get("width") or 0)
        height = float((viewport or {}).get("height") or 0)
        if x < 0 or y < 0 or x >= width or y >= height:
            raise RuntimeError("Playwright pointer target is out of bounds")
        await page.mouse.click(x, y)

    async def close(self) -> None:
        pages = [
            self._pages[context] for context in list(self._owned_contexts) if context in self._pages
        ]
        if self._attached:
            for page in pages:
                if not page.is_closed():
                    try:
                        await page.close()
                    except PlaywrightError:
                        pass
        elif self._browser_context is not None:
            try:
                await self._browser_context.close()
            except PlaywrightError:
                pass

        self._pages.clear()
        self._page_contexts.clear()
        self._owned_contexts.clear()
        self.context = ""
        self._network_subscribed = False
        self._send_capture = None
        self._connected = False

        # For an attached browser, stopping Playwright disconnects the automation
        # client without quitting the user's Chromium process.
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except PlaywrightError:
                pass
        self._playwright = None
        self._browser = None
        self._browser_context = None
        self._bootstrap_url = ""
