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

from .browser_ownership import (
    OWNED_WINDOW_PREFIX,
    new_owned_window_marker,
    new_page_owner_id,
    owned_window_owner_alive,
    owned_window_owner_id,
    owned_window_started_at,
)
from .browser_script_loader import load_browser_script
from .send_outcome import SendOutcomeUnknownError
from .webdriver import BrowserDriverBase, BrowsingContextUnavailableError

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_MS = 30_000


def _normalise_composer_text(text: str) -> str:
    normalized = " ".join(text.split()).strip()
    return re.sub(r"(?<==)\s+(?=https?://)", "", normalized)


_RATE_LIMIT_RE = re.compile(
    r"(?:too many requests|temporarily limited access|requests too quickly|rate limit|usage limit|limit (?:has been )?reached|reached (?:your|the) (?:usage )?limit)",
    re.IGNORECASE,
)
_LOGIN_RE = re.compile(r"^(?:log ?in|sign ?in)$", re.IGNORECASE)
_COMPOSER_NAME_RE = re.compile(
    r"^(?:chat with chatgpt|message(?: chatgpt)?|ask(?: chatgpt| anything)?|prompt|send a message)$",
    re.IGNORECASE,
)
_SEND_RE = re.compile(r"^(?:send|send prompt)$", re.IGNORECASE)
_EFFORT_RE = re.compile(r"\b(max|extra\s+high|instant|medium|high)\b", re.IGNORECASE)
_EFFORT_TRIGGER_RE = re.compile(
    r"\b(?:thinking\s+effort|select\s+(?:chatgpt\s+)?model|model\s+selector)\b",
    re.IGNORECASE,
)
_CLOUDFLARE_CHALLENGE_RE = re.compile(
    r"(?:verify you are human|checking your browser|performing security verification|"
    r"enable javascript and cookies to continue)",
    re.IGNORECASE,
)
_CLOUDFLARE_FRAME_RE = re.compile(r"(?:cloudflare|security verification|challenge)", re.IGNORECASE)


class ChromeDebuggerUnavailableError(RuntimeError):
    """Raised when Prompta cannot attach Playwright to the configured Chromium CDP endpoint."""


class PlaywrightDriver(BrowserDriverBase):
    """Playwright-backed ChatGPT browser driver.

    Interactions intentionally prefer accessibility semantics (role/name/label/
    placeholder) and stable browser/HTML capabilities. Private classes and test IDs
    are deliberately excluded from the active delivery path.
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
        ownership_prefix: str = OWNED_WINDOW_PREFIX,
        **_legacy: Any,
    ) -> None:
        super().__init__("")
        self.profile = profile.expanduser().resolve()
        self.chrome_path = chrome_path
        self.headless = headless
        self.auth_timeout_seconds = max(0.1, auth_timeout_seconds)
        self.debugger_address = debugger_address.strip() if debugger_address else None
        self.flaresolverr_url = flaresolverr_url.rstrip("/") if flaresolverr_url else None
        self.ownership_prefix = ownership_prefix
        self.page_owner_id = new_page_owner_id()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_context: BrowserContext | None = None
        self._pages: dict[str, Page] = {}
        self._page_contexts: dict[Page, str] = {}
        self._owned_contexts: set[str] = set()
        self._attached = bool(self.debugger_address)
        self._connected = False
        self._next_orphan_cleanup_at = 0.0
        self._history_rate_limit_seen = False

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

    async def _owned_page_started_at(self, page: Page) -> int | None:
        if page.is_closed():
            return None
        try:
            name = await page.evaluate(load_browser_script("get_window_name.js"))
        except PlaywrightError:
            return None
        return owned_window_started_at(name, prefix=self.ownership_prefix)

    async def _owned_page_owner_id(self, page: Page) -> str | None:
        if page.is_closed():
            return None
        try:
            name = await page.evaluate(load_browser_script("get_window_name.js"))
        except PlaywrightError:
            return None
        return owned_window_owner_id(name, prefix=self.ownership_prefix)

    async def _mark_owned(self, page: Page) -> None:
        await page.evaluate(
            load_browser_script("set_window_name.js"),
            new_owned_window_marker(
                prefix=self.ownership_prefix,
                owner_id=self.page_owner_id,
            ),
        )

    async def _is_owned_page(self, page: Page) -> bool:
        return await self._owned_page_owner_id(page) == self.page_owner_id

    async def _cleanup_stale_owned_pages(self, browser_context: BrowserContext) -> None:
        await self.cleanup_orphan_pages(
            minimum_age_seconds=60.0,
            interval_seconds=1.0,
        )

    async def cleanup_orphan_pages(
        self,
        *,
        minimum_age_seconds: float = 60.0,
        interval_seconds: float = 30.0,
    ) -> int:
        browser_context = self._browser_context
        if browser_context is None:
            return 0

        loop = asyncio.get_running_loop()
        now_monotonic = loop.time()
        if now_monotonic < self._next_orphan_cleanup_at:
            return 0
        self._next_orphan_cleanup_at = now_monotonic + max(1.0, interval_seconds)

        cutoff = time.time() - max(1.0, minimum_age_seconds)
        closed = 0
        for page in list(browser_context.pages):
            if page in self._page_contexts:
                continue
            started_at = await self._owned_page_started_at(page)
            if started_at is None or started_at > cutoff:
                continue
            owner_id = await self._owned_page_owner_id(page)
            if owner_id is None:
                # Legacy ownership markers cannot prove that another live process
                # does not still own the page, so fail safe and leave them alone.
                continue
            if owner_id != self.page_owner_id and owned_window_owner_alive(owner_id):
                continue
            try:
                await page.close()
            except PlaywrightError:
                continue
            closed += 1
        if closed:
            logger.warning("Prompta reaped %d orphaned browser tab(s)", closed)
        return closed

    def _on_request(self, request: Request) -> None:
        capture = self._send_capture
        if capture is None:
            return
        if request.method.upper() != "POST" or not self._is_send_endpoint(request.url):
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
                    if not await candidate.evaluate(
                        load_browser_script("is_active_composed_node.js")
                    ):
                        continue
                    if enabled and not await candidate.is_enabled():
                        continue
                    return candidate
                except PlaywrightError:
                    continue
        return None

    async def _hydrated_composer(self, page: Page) -> Locator | None:
        # ChatGPT hydrates its initial textarea into a contenteditable editor. The
        # empty editor can have no rendered box even though it is focusable, so
        # Playwright visibility is not a useful signal. Prefer semantic textbox
        # capability in the main landmark, then a unique contenteditable fallback.
        # Do not depend on ChatGPT-private data attributes or wrapper classes.
        main = page.get_by_role("main")
        candidates = (
            (
                main.locator('[contenteditable]:not([contenteditable="false"])[role="textbox"]'),
                False,
            ),
            (main.locator('[contenteditable]:not([contenteditable="false"])'), True),
            (
                page.locator('[contenteditable]:not([contenteditable="false"])[role="textbox"]'),
                True,
            ),
            (page.locator('[contenteditable]:not([contenteditable="false"])'), True),
        )
        for hydrated, require_unique in candidates:
            try:
                count = await hydrated.count()
            except PlaywrightError:
                continue
            if require_unique and count != 1:
                continue
            for index in range(min(count, 12)):
                candidate = hydrated.nth(index)
                try:
                    active = await candidate.evaluate(
                        load_browser_script("is_active_composed_node.js")
                    )
                    # Browser visibility is authoritative for the composer when our
                    # conservative composed-tree guard disagrees with Chromium.
                    # ChatGPT can transiently wrap its live editor in containers
                    # whose computed visibility makes the guard false-negative.
                    if not active and not await candidate.is_visible():
                        continue
                    if await candidate.is_enabled():
                        return candidate
                except PlaywrightError:
                    continue
        return None

    async def _composer(self, page: Page) -> Locator | None:
        main = page.get_by_role("main")

        # The chat composer is normally in the main landmark. Prefer its public
        # accessible name, then any textbox there, before looking at the
        # whole page (which can also contain search and dialog textboxes).
        def named(scope: Page | Locator) -> list[Locator]:
            return [
                scope.get_by_role("textbox", name=_COMPOSER_NAME_RE),
                scope.get_by_label(_COMPOSER_NAME_RE),
                scope.get_by_placeholder(_COMPOSER_NAME_RE),
            ]

        hydrated = await self._hydrated_composer(page)
        if hydrated is not None:
            return hydrated

        for candidates in (named(main), [main.get_by_role("textbox")], named(page)):
            found = await self._first_usable(candidates)
            if found is not None:
                return found
        # An unnamed page-wide textbox is only safe when it is unique.
        textboxes = page.get_by_role("textbox")
        if await textboxes.count() == 1:
            found = await self._first_usable([textboxes])
            if found is not None:
                return found
        return None

    async def _composer_submit_button(self, composer: Locator) -> Locator | None:
        # Prefer an actual form when present, but do not make the wrapper tag part
        # of the fallback contract. ChatGPT has changed composer wrappers before.
        owners = (
            composer.locator("xpath=ancestor::form[1]"),
            composer.locator('xpath=ancestor::*[.//button[@type="submit"]][1]'),
        )
        for owner in owners:
            try:
                if await owner.count() != 1:
                    continue
                tag_name = str(
                    await owner.evaluate(load_browser_script("element_tag_name.js")) or ""
                ).casefold()
                if tag_name in {"html", "body", "main"}:
                    continue
                submits = owner.locator('button[type="submit"]')
                if await submits.count() != 1:
                    continue

                # A generic, unlabeled submit is only safe when the structural
                # owner contains a single editor. This prevents a broad wrapper
                # (or the whole app shell) from donating an unrelated submit.
                editors = owner.locator(
                    'textarea,[contenteditable]:not([contenteditable="false"]),[role="textbox"]'
                )
                if await editors.count() != 1:
                    continue

                button = await self._first_usable([submits])
                if button is not None:
                    return button
            except PlaywrightError:
                continue
        return None

    async def _semantic_button(
        self,
        page: Page,
        name: re.Pattern[str],
    ) -> Locator | None:
        # Resolve controls by meaning rather than by one specific element/role.
        # ChatGPT has moved actions between native buttons, ARIA menu items, and
        # roleless focusable wrappers while keeping their accessible labels.
        # Prefer the chat landmark before the whole page so a toolbar action with
        # the same name cannot steal the click from the composer.
        scopes: tuple[Page | Locator, ...] = (page.get_by_role("main"), page)
        action_roles = ("button", "menuitem", "option", "link", "radio")

        for scope in scopes:
            semantic = await self._first_usable(
                [scope.get_by_role(role, name=name) for role in action_roles]
            )
            if semantic is not None:
                return semantic

            # If the ARIA role itself churned, inspect only elements that carry
            # some interaction/accessibility signal. Match public labels/text,
            # never CSS classes or private test IDs, and require an unambiguous
            # fallback within the current scope before clicking it.
            candidates = scope.locator(
                "button,a,input,select,[role],[tabindex],[aria-label],[aria-labelledby],[title]"
            )
            try:
                count = min(await candidates.count(), 80)
            except PlaywrightError:
                continue

            matched: list[Locator] = []
            for index in range(count):
                candidate = candidates.nth(index)
                try:
                    if not await candidate.is_visible() or not await candidate.is_enabled():
                        continue
                    if not await candidate.evaluate(
                        load_browser_script("is_active_composed_node.js")
                    ):
                        continue
                    labels = await candidate.evaluate(
                        load_browser_script("semantic_control_labels.js")
                    )
                    if not isinstance(labels, list):
                        continue
                    if any(name.search(str(label)) for label in labels):
                        matched.append(candidate)
                except PlaywrightError:
                    continue
            if len(matched) == 1:
                return matched[0]

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

            page = await browser_context.new_page()
            self.context = self._register_page(page, owned=True)
            self._network_subscribed = True
            self._connected = True

            await self.navigate("https://chatgpt.com/", context=self.context)

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
            context_id = self._page_contexts.get(page)
            if context_id in self._owned_contexts:
                await self._mark_owned(page)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Playwright navigation timed out for {url}") from exc

    async def new_tab(self, url: str = "https://chatgpt.com/") -> str:
        browser_context = self._browser_context
        if browser_context is None:
            raise RuntimeError("Playwright browser context is not connected")
        page = await browser_context.new_page()
        context_id = self._register_page(page, owned=True)
        self.context = context_id
        try:
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
        direct = await self._semantic_button(page, _LOGIN_RE)
        if direct is not None:
            return True
        fallback = await self._first_usable(
            [
                # Authentication URLs are a more durable structural contract than
                # ChatGPT's private test IDs or wrapper classes. Do not require an
                # anchor tag: client-side routers may expose link semantics on a
                # different element while preserving the destination.
                page.locator('[href*="/auth/login" i]'),
                page.locator('[href*="/login" i]'),
                page.locator('form[action*="/login" i] button'),
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

        # Prefer user-facing challenge semantics so DOM IDs/classes can change
        # without making Cloudflare detection disappear. Keep provider-specific
        # attributes below as compatibility fallbacks for challenge pages that
        # render little or no visible text.
        semantic = await self._first_usable(
            [
                page.get_by_text(_CLOUDFLARE_CHALLENGE_RE),
                page.get_by_title(_CLOUDFLARE_FRAME_RE),
            ],
            enabled=False,
        )
        if semantic is not None:
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
        user_agent = str(await page.evaluate(load_browser_script("get_user_agent.js")))
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
        page = self._page()

        # The first server-rendered textarea is short-lived. Give ChatGPT a
        # bounded grace period to replace it with the real ProseMirror editor
        # before starting a fill, otherwise Playwright can spend its full
        # action timeout writing to a node that is being detached.
        composer = await self._composer(page)
        fallback = composer
        hydration_deadline = asyncio.get_running_loop().time() + 1.5
        while asyncio.get_running_loop().time() < hydration_deadline:
            hydrated = await self._hydrated_composer(page)
            if hydrated is not None:
                composer = hydrated
                break
            current = await self._composer(page)
            if current is not None:
                fallback = current
            await asyncio.sleep(0.05)
        else:
            composer = fallback

        if composer is None:
            raise RuntimeError("ChatGPT composer could not be focused")
        await composer.focus()
        return composer

    async def _replace_composer_text(self, composer: Locator, text: str) -> None:
        try:
            if await composer.is_visible():
                await composer.fill(text)
                return
        except PlaywrightError:
            pass

        try:
            keyboard = self._page().keyboard
            await composer.focus()
            await keyboard.press("Control+A")
            await keyboard.press("Backspace")
            if text:
                await keyboard.insert_text(text)
        except PlaywrightError as exc:
            raise RuntimeError("ChatGPT composer could not accept text") from exc

    async def type_message(self, text: str) -> None:
        composer = await self._focus_composer()
        await self._replace_composer_text(composer, text)

        expected = _normalise_composer_text(text)
        deadline = asyncio.get_running_loop().time() + 3.0
        matched_since: float | None = None
        rewritten_after_hydration = False
        while asyncio.get_running_loop().time() < deadline:
            current = await self._composer(self._page())
            if current is not None:
                actual = _normalise_composer_text(await self._composer_text(current))
                now = asyncio.get_running_loop().time()
                if actual == expected:
                    if matched_since is None:
                        matched_since = now
                    if now - matched_since >= 0.75:
                        return
                else:
                    matched_since = None
                    if not rewritten_after_hydration:
                        await self._replace_composer_text(current, text)
                        rewritten_after_hydration = True
            await asyncio.sleep(0.05)

        raise RuntimeError("ChatGPT composer did not contain the requested prompt")

    async def clear_composer(self, timeout: float = 3.0) -> None:
        composer = await self._focus_composer()
        await self._replace_composer_text(composer, "")
        deadline = asyncio.get_running_loop().time() + timeout
        empty_since: float | None = None
        while asyncio.get_running_loop().time() < deadline:
            current = await self._composer(self._page())
            if current is not None and not (await self._composer_text(current)).strip():
                now = asyncio.get_running_loop().time()
                if empty_since is None:
                    empty_since = now
                if now - empty_since >= 0.75:
                    return
            else:
                empty_since = None
            await asyncio.sleep(0.05)
        raise RuntimeError("ChatGPT stale composer could not be cleared")

    async def _composer_text(self, composer: Locator) -> str:
        try:
            tag = (await composer.evaluate(load_browser_script("element_tag_name.js"))).casefold()
            if tag in {"textarea", "input"}:
                return await composer.input_value()
            return await composer.inner_text()
        except PlaywrightError:
            return ""

    async def click_send(self) -> None:
        await self._focus_composer()
        try:
            await self._page().keyboard.press("Enter")
        except Exception as exc:
            raise SendOutcomeUnknownError(
                "ChatGPT send mutation failed while pressing Enter; the prompt may have been submitted"
            ) from exc

    async def click_send_button(self, timeout: float = 120.0) -> None:
        page = self._page()
        deadline = asyncio.get_running_loop().time() + max(1.0, timeout)
        while asyncio.get_running_loop().time() < deadline:
            button = await self._semantic_button(page, _SEND_RE)
            if button is None:
                composer = await self._composer(page)
                if composer is not None:
                    button = await self._composer_submit_button(composer)
            if button is not None:
                try:
                    await button.click()
                except Exception as exc:
                    raise SendOutcomeUnknownError(
                        "ChatGPT send-button mutation failed; the prompt may have been submitted"
                    ) from exc
                return
            await asyncio.sleep(0.15)
        raise RuntimeError("ChatGPT send button did not become enabled")

    async def _rate_limit_texts(self, page: Page) -> list[str]:
        # Rate-limit UI has changed wrappers and private test IDs repeatedly.
        # Search durable accessibility surfaces first, then matching text inside
        # the current chat/dialog surface. The fresh-chat main landmark avoids
        # mistaking sidebar history for an active rate-limit notice.
        sources: tuple[Locator, ...] = (
            page.get_by_role("alert"),
            page.get_by_role("status"),
            page.locator('[aria-live]:not([aria-live="off"])'),
            page.get_by_role("dialog").get_by_text(_RATE_LIMIT_RE),
            page.get_by_role("main").get_by_text(_RATE_LIMIT_RE),
        )
        texts: list[str] = []
        for source in sources:
            try:
                count = min(await source.count(), 24)
            except PlaywrightError:
                continue
            for index in range(count):
                candidate = source.nth(index)
                try:
                    if not await candidate.is_visible():
                        continue
                    if not await candidate.evaluate(
                        load_browser_script("is_active_composed_node.js")
                    ):
                        continue
                    text = (await candidate.inner_text()).strip()
                except PlaywrightError:
                    continue
                if text and _RATE_LIMIT_RE.search(text) and text not in texts:
                    texts.append(text)
        return texts

    async def dom_state(self) -> dict[str, Any]:
        page = self._page()
        composer = await self._composer(page)
        composer_text = await self._composer_text(composer) if composer is not None else ""
        rate_limit_texts = await self._rate_limit_texts(page)

        return {
            "composer_text": composer_text,
            "rate_limit_text": "\n".join(rate_limit_texts),
        }

    async def ensure_chat_surface(self, timeout: float = 5.0) -> None:
        page = self._page()
        deadline = asyncio.get_running_loop().time() + timeout
        chat_name = re.compile(r"^\s*chat(?:\s+mode)?\s*$", re.IGNORECASE)

        async def chat_control() -> Locator | None:
            candidates = [
                page.get_by_role(role, name=chat_name)
                for role in ("radio", "tab", "button", "menuitemradio", "option")
            ]
            found = await self._first_usable(candidates, enabled=True)
            if found is not None:
                return found

            # Accessible roles and tags can churn independently of the public
            # label. Prefer the main landmark, then require a unique semantic match
            # page-wide so unrelated controls cannot steal the click.
            scopes: tuple[Page | Locator, ...] = (page.get_by_role("main"), page)
            for scope in scopes:
                interactive = scope.locator(
                    "button,input,summary,[role],[tabindex],[aria-label],"
                    "[aria-labelledby],[title],[aria-checked],[aria-selected],[data-state]"
                )
                try:
                    count = min(await interactive.count(), 40)
                except PlaywrightError:
                    continue
                matched: list[Locator] = []
                for index in range(count):
                    candidate = interactive.nth(index)
                    try:
                        if not await candidate.is_visible() or not await candidate.is_enabled():
                            continue
                        if not await candidate.evaluate(
                            load_browser_script("is_active_composed_node.js")
                        ):
                            continue
                        labels = await candidate.evaluate(
                            load_browser_script("semantic_control_labels.js")
                        )
                        if isinstance(labels, list) and any(
                            chat_name.search(str(label)) for label in labels
                        ):
                            matched.append(candidate)
                    except PlaywrightError:
                        continue
                if len(matched) == 1:
                    return matched[0]
            return None

        async def selected(control: Locator) -> bool:
            for attribute in ("aria-checked", "aria-selected"):
                value = (await control.get_attribute(attribute) or "").strip().casefold()
                if value == "true":
                    return True
                if value == "false":
                    return False
            state = (await control.get_attribute("data-state") or "").strip().casefold()
            if state in {"active", "checked", "selected", "on"}:
                return True
            if state in {"inactive", "unchecked", "unselected", "off"}:
                return False
            return False

        while asyncio.get_running_loop().time() < deadline:
            chat = await chat_control()
            if chat is None:
                # ChatGPT no longer always exposes explicit Chat/Work mode controls.
                # A usable composer is sufficient evidence that the page is on the
                # normal chat surface.
                if await self._composer(page) is not None:
                    return
                await asyncio.sleep(0.1)
                continue
            try:
                if await selected(chat):
                    return
                await chat.click()
                while asyncio.get_running_loop().time() < deadline:
                    if await selected(chat):
                        return
                    # Some implementations switch the surface without exposing a
                    # selected-state attribute. The composer is the semantic success
                    # signal in that case.
                    if await self._composer(page) is not None:
                        return
                    await asyncio.sleep(0.05)
            except PlaywrightError:
                await asyncio.sleep(0.1)
        raise RuntimeError("ChatGPT Chat surface did not become active")

    async def _effort_trigger_locator(self) -> Locator | None:
        page = self._page()
        trigger_roles = ("button", "combobox", "menuitem", "option", "radio")
        semantic_candidates = [
            page.get_by_role(role, name=name)
            for name in (_EFFORT_TRIGGER_RE, _EFFORT_RE)
            for role in trigger_roles
        ]
        for controls in semantic_candidates:
            try:
                count = min(await controls.count(), 12)
            except PlaywrightError:
                continue
            for index in range(count):
                control = controls.nth(index)
                try:
                    if not await control.is_visible() or not await control.is_enabled():
                        continue
                    popup = (await control.get_attribute("aria-haspopup") or "").casefold()
                    if popup not in {"true", "menu", "listbox", "dialog", "tree", "grid"}:
                        continue
                    return control
                except PlaywrightError:
                    continue

        # Accessible-role implementations can churn independently of the public
        # label. As a final semantic fallback, inspect popup owners directly and
        # accept one only when its accessible/visible text names the effort/model
        # control. This avoids coupling to styling classes or private test IDs.
        popup_controls = page.locator("[aria-haspopup]")
        try:
            count = min(await popup_controls.count(), 24)
        except PlaywrightError:
            count = 0
        for index in range(count):
            control = popup_controls.nth(index)
            try:
                if not await control.is_visible() or not await control.is_enabled():
                    continue
                popup = (await control.get_attribute("aria-haspopup") or "").casefold()
                if popup not in {"true", "menu", "listbox", "dialog", "tree", "grid"}:
                    continue
                labels = await control.evaluate(load_browser_script("semantic_control_labels.js"))
                if not isinstance(labels, list):
                    continue
                label = " ".join(str(value) for value in labels if value)
                if _EFFORT_TRIGGER_RE.search(label) or _EFFORT_RE.search(label):
                    return control
            except PlaywrightError:
                continue
        return None

    async def _power_control(self, page: Page) -> Locator | None:
        # The power row has changed accessible role before. The durable contract is
        # that it owns the reasoning slider, so discover that structure across
        # common selectable/container roles before falling back to its visible name.
        for role in ("menuitem", "menuitemradio", "radio", "option", "button", "group"):
            controls = page.get_by_role(role)
            try:
                count = min(await controls.count(), 40)
            except PlaywrightError:
                continue
            for index in range(count):
                item = controls.nth(index)
                try:
                    if not await item.is_visible():
                        continue
                    if (await item.get_attribute("aria-disabled") or "").casefold() == "true":
                        continue
                    if await item.locator(
                        '[role="slider"],[aria-valuenow][aria-valuemin][aria-valuemax]'
                    ).count():
                        return item
                except PlaywrightError:
                    continue

        # Some UI builds drop the wrapper role entirely but keep a focusable owner
        # around the slider. Use the nearest focusable ancestor only when it is a
        # unique structural owner, avoiding assumptions about classes or test IDs.
        sliders = page.locator('[role="slider"],[aria-valuenow][aria-valuemin][aria-valuemax]')
        try:
            slider_count = min(await sliders.count(), 12)
        except PlaywrightError:
            slider_count = 0
        owners: list[Locator] = []
        for index in range(slider_count):
            slider = sliders.nth(index)
            try:
                owner = slider.locator("xpath=ancestor::*[@tabindex][1]")
                if await owner.count() != 1:
                    continue
                candidate = owner.first
                if not await candidate.is_visible():
                    continue
                if (await candidate.get_attribute("aria-disabled") or "").casefold() == "true":
                    continue
                if (
                    await candidate.locator(
                        '[role="slider"],[aria-valuenow][aria-valuemin][aria-valuemax]'
                    ).count()
                    != 1
                ):
                    continue
                owners.append(candidate)
            except PlaywrightError:
                continue
        if len(owners) == 1:
            return owners[0]

        return await self._first_usable(
            [
                page.get_by_role(role, name=re.compile(r"\bpower\b", re.IGNORECASE))
                for role in ("menuitem", "option", "button", "group")
            ],
            enabled=True,
        )

    async def _open_effort_menu(self) -> None:
        page = self._page()
        power = await self._power_control(page)
        if power is not None:
            return

        for _ in range(2):
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.05)

        trigger = await self._effort_trigger_locator()
        if trigger is None:
            raise RuntimeError("ChatGPT thinking-effort control did not become available")
        try:
            await trigger.click()
        except PlaywrightError as exc:
            raise RuntimeError("ChatGPT thinking-effort menu could not be opened") from exc

        deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < deadline:
            power = await self._power_control(page)
            if power is not None:
                return
            await asyncio.sleep(0.05)
        raise RuntimeError("ChatGPT Power control did not become available")

    async def _model_selector_control(self, page: Page) -> Locator | None:
        model_menu_name = re.compile(
            r"\b(?:select|choose|change)\s+(?:model|engine)\b",
            re.IGNORECASE,
        )
        selectable_roles = ("menuitem", "button", "combobox", "option", "radio")
        named = await self._first_usable(
            [page.get_by_role(role, name=model_menu_name) for role in selectable_roles],
            enabled=True,
        )
        if named is not None:
            return named

        submenu_candidates: list[Locator] = []
        seen: set[str] = set()
        for role in selectable_roles:
            controls = page.get_by_role(role)
            try:
                count = min(await controls.count(), 40)
            except PlaywrightError:
                continue
            for index in range(count):
                item = controls.nth(index)
                try:
                    if not await item.is_visible() or not await item.is_enabled():
                        continue
                    popup = (await item.get_attribute("aria-haspopup") or "").casefold()
                    if popup not in {"true", "menu", "listbox", "dialog", "tree", "grid"}:
                        continue
                    key = (
                        await item.get_attribute("id")
                        or await item.get_attribute("aria-label")
                        or await item.text_content()
                        or ""
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    submenu_candidates.append(item)
                except PlaywrightError:
                    continue

        # If the owner has lost its ARIA role but still advertises popup semantics,
        # use it only when there is one unambiguous visible candidate on the page.
        if not submenu_candidates:
            popup_controls = page.locator("[aria-haspopup]")
            try:
                count = min(await popup_controls.count(), 24)
            except PlaywrightError:
                count = 0
            for index in range(count):
                item = popup_controls.nth(index)
                try:
                    if not await item.is_visible() or not await item.is_enabled():
                        continue
                    popup = (await item.get_attribute("aria-haspopup") or "").casefold()
                    if popup in {"true", "menu", "listbox", "dialog", "tree", "grid"}:
                        submenu_candidates.append(item)
                except PlaywrightError:
                    continue
        return submenu_candidates[0] if len(submenu_candidates) == 1 else None

    async def select_effort_model(self, model_name: str = "GPT-5.6 Sol") -> None:
        page = self._page()
        model_name_re = re.compile(rf"^\s*{re.escape(model_name)}(?:\s|$)", re.IGNORECASE)

        async def find_option() -> Locator | None:
            # Menus have changed role structure before. Prefer accessible role/name
            # semantics, but accept the equivalent selectable roles rather than
            # coupling model discovery to one private menu implementation.
            named_roles = [
                page.get_by_role(role, name=model_name_re)
                for role in ("menuitemradio", "radio", "option")
            ]
            text_roles = [
                page.get_by_role(role).filter(has_text=model_name_re)
                for role in ("menuitemradio", "radio", "option")
            ]
            return await self._first_usable(named_roles + text_roles, enabled=True)

        deadline = asyncio.get_running_loop().time() + 5.0
        while asyncio.get_running_loop().time() < deadline:
            option = await find_option()
            if option is not None:
                try:
                    if (await option.get_attribute("aria-checked") or "").casefold() == "true":
                        await page.keyboard.press("Escape")
                        return
                    await option.click()
                    return
                except PlaywrightError:
                    await asyncio.sleep(0.1)
                    continue

            selector = await self._model_selector_control(page)
            if selector is None:
                await self._open_effort_menu()
                selector = await self._model_selector_control(page)
            if selector is not None:
                try:
                    await selector.click()
                except PlaywrightError as exc:
                    raise RuntimeError("ChatGPT model selector could not be opened") from exc

            await asyncio.sleep(0.05)

        raise RuntimeError(f"ChatGPT model {model_name!r} is unavailable")

    async def effort_power_info(self) -> dict[str, Any]:
        page = self._page()
        power = await self._power_control(page)
        if power is None:
            return {}

        slider = power.get_by_role("slider", include_hidden=True)
        try:
            if await slider.count() < 1:
                slider = power.locator("[aria-valuenow][aria-valuemin][aria-valuemax]")
            if await slider.count() < 1:
                return {}
            current_value = int(await slider.first.get_attribute("aria-valuenow") or -1)
            min_value = int(await slider.first.get_attribute("aria-valuemin") or 0)
            max_value = int(await slider.first.get_attribute("aria-valuemax") or -1)
            described_by = str(await power.get_attribute("aria-describedby") or "").split()
            description_parts: list[str] = []
            id_nodes = page.locator("[id]")
            id_count = await id_nodes.count()
            for element_id in described_by:
                for index in range(id_count):
                    described = id_nodes.nth(index)
                    if await described.get_attribute("id") != element_id:
                        continue
                    text = (await described.inner_text()).strip()
                    if text:
                        description_parts.append(text)
                    break
        except (PlaywrightError, ValueError):
            return {}

        if current_value < min_value or max_value < min_value:
            return {}
        description = " ".join(description_parts)
        label = description.split(",", 1)[0].strip() if description else ""
        return {
            "text": label,
            "position": current_value - min_value + 1,
            "total": max_value - min_value + 1,
            "value": current_value,
            "description": description,
        }

    async def set_effort_power_position(self, position: int) -> dict[str, Any]:
        await self._open_effort_menu()
        page = self._page()
        power = await self._power_control(page)
        if power is None:
            raise RuntimeError("ChatGPT Power control did not become available")

        info = await self.effort_power_info()
        current = int(info.get("position") or 0)
        total = int(info.get("total") or 0)
        if current < 1 or total < 1 or position < 1 or position > total:
            raise RuntimeError(f"ChatGPT Power control has invalid state: {info!r}")

        try:
            await power.focus()
            key = "ArrowRight" if position > current else "ArrowLeft"
            for _ in range(abs(position - current)):
                await page.keyboard.press(key)
        except PlaywrightError as exc:
            raise RuntimeError("ChatGPT Power control could not be adjusted") from exc

        deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < deadline:
            info = await self.effort_power_info()
            if int(info.get("position") or 0) == position:
                return info
            await asyncio.sleep(0.05)
        raise RuntimeError(f"ChatGPT Power control did not reach position {position}")

    async def dismiss_transient_controls(self) -> None:
        page = self._page()
        try:
            await page.keyboard.press("Escape")
        except PlaywrightError:
            pass

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
