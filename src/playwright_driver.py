from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from collections.abc import Awaitable, Sequence
from pathlib import Path
from typing import Literal, Protocol, TypeVar
from urllib.parse import urlsplit
from urllib.request import urlopen

from patchright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    Request,
    Response,
    async_playwright,
)
from patchright.async_api import (
    Error as PlaywrightError,
)
from patchright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from .browser_ownership import (
    OWNED_WINDOW_PREFIX,
    new_owned_window_marker,
    new_page_owner_id,
    owned_window_owner_alive,
    owned_window_owner_id,
    owned_window_started_at,
    record_owned_tab,
    touch_owned_tab,
)
from .browser_script_loader import load_browser_script
from .connector_approval_supervisor import trusted_approval_retry
from .flaresolverr_client import solve_cloudflare
from .response_capture import CaptureResult, normalize_dom_snapshot, parse_sse_body
from .send_outcome import SendOutcomeUnknownError
from .strict_types import int_value, json_object


class BrowsingContextUnavailableError(RuntimeError):
    """Raised when a Prompta-owned Playwright page is no longer available."""


logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_MS = 30_000
_MODEL_SELECTION_VERIFY_ATTEMPTS = 40
_MODEL_SELECTION_VERIFY_INTERVAL_SECONDS = 0.05
_MODEL_PICKER_STEP_TIMEOUT_SECONDS = 3.0


_PickerResult = TypeVar("_PickerResult")


async def _timed_model_picker_step(
    stage: str,
    operation: Awaitable[_PickerResult],
    *,
    timeout: float,
) -> _PickerResult:
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(operation, timeout=max(0.1, timeout))
    except BaseException as exc:
        logger.warning(
            "ChatGPT model picker stage finished stage=%s duration_ms=%d "
            "outcome=failed error_type=%s",
            stage,
            round((time.monotonic() - started) * 1000),
            type(exc).__name__,
        )
        raise
    logger.debug(
        "ChatGPT model picker stage finished stage=%s duration_ms=%d outcome=ok",
        stage,
        round((time.monotonic() - started) * 1000),
    )
    return result


class BrowserSecurityChallengeError(RuntimeError):
    """ChatGPT security challenge blocked an attempted navigation or UI action."""


def _normalise_composer_text(text: str) -> str:
    normalized = " ".join(text.split()).strip()
    return re.sub(r"(?<=[=(])\s+(?=https?://)", "", normalized)


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
_STOP_GENERATING_RE = re.compile(r"^stop generating$", re.IGNORECASE)
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
_FLARESOLVERR_LOCK = threading.Lock()
_FLARESOLVERR_NEXT_ATTEMPT_AT = 0.0


def _claim_flaresolverr_attempt() -> bool:
    global _FLARESOLVERR_NEXT_ATTEMPT_AT
    with _FLARESOLVERR_LOCK:
        now = time.monotonic()
        if now < _FLARESOLVERR_NEXT_ATTEMPT_AT:
            return False
        _FLARESOLVERR_NEXT_ATTEMPT_AT = now + 600.0
        return True


class _UsableCandidate(Protocol):
    async def is_visible(self) -> bool: ...
    async def is_enabled(self) -> bool: ...
    async def evaluate(self, expression: str, /) -> object: ...


_UsableT = TypeVar("_UsableT", bound=_UsableCandidate)
_UsableT_co = TypeVar("_UsableT_co", bound=_UsableCandidate, covariant=True)


class _UsableCollection(Protocol[_UsableT_co]):
    async def count(self) -> int: ...
    def nth(self, index: int, /) -> _UsableT_co: ...


class _LocatorPage(Protocol[_UsableT_co]):
    def locator(self, selector: str, /) -> _UsableCollection[_UsableT_co]: ...


class _AttributeControl(Protocol):
    async def get_attribute(self, name: str, /) -> str | None: ...


class _RateLimitCandidate(Protocol):
    async def is_visible(self) -> bool: ...
    async def evaluate(self, expression: str, /) -> object: ...
    async def inner_text(self) -> str: ...


_RateT = TypeVar("_RateT", bound=_RateLimitCandidate)
_RateT_co = TypeVar("_RateT_co", bound=_RateLimitCandidate, covariant=True)
_RateRole = Literal["alert", "status", "dialog", "main"]


class _RateLimitCollection(Protocol[_RateT_co]):
    async def count(self) -> int: ...
    def nth(self, index: int, /) -> _RateT_co: ...
    def get_by_text(self, pattern: re.Pattern[str], /) -> _RateLimitCollection[_RateT_co]: ...


class _RateLimitPage(Protocol[_RateT_co]):
    def get_by_role(self, role: _RateRole, /) -> _RateLimitCollection[_RateT_co]: ...
    def locator(self, selector: str, /) -> _RateLimitCollection[_RateT_co]: ...


_ModelRole = Literal[
    "menuitem",
    "menuitemradio",
    "option",
    "radio",
    "tab",
    "combobox",
    "button",
    "main",
]


class _LocatorScope(Protocol[_UsableT_co]):
    def locator(self, selector: str, /) -> _UsableCollection[_UsableT_co]: ...


class _ModelCollection(
    _UsableCollection[_UsableT_co],
    _LocatorScope[_UsableT_co],
    Protocol[_UsableT_co],
):
    pass


class _ModelPage(_LocatorScope[_UsableT_co], Protocol[_UsableT_co]):
    def get_by_role(
        self,
        role: _ModelRole,
        /,
        *,
        name: re.Pattern[str] | None = None,
    ) -> _ModelCollection[_UsableT_co]: ...


class ChromeDebuggerUnavailableError(RuntimeError):
    """Raised when Prompta cannot attach Playwright to the configured Chromium CDP endpoint."""


class PlaywrightDriver:
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
        ownership_prefix: str = OWNED_WINDOW_PREFIX,
    ) -> None:
        self.context = ""
        self._network_subscribed = False
        self._send_capture: dict[str, object] | None = None
        self._response_tasks: set[asyncio.Task[None]] = set()
        self._response_events: asyncio.Queue[CaptureResult | None] = asyncio.Queue(maxsize=4)
        self.needs_browser_restart = False
        self.profile = profile.expanduser().resolve()
        self.chrome_path = chrome_path
        self.headless = headless
        self.auth_timeout_seconds = max(0.1, auth_timeout_seconds)
        self.debugger_address = debugger_address.strip() if debugger_address else None
        self.ownership_prefix = ownership_prefix
        self.page_owner_id = new_page_owner_id()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_context: BrowserContext | None = None
        self._pages: dict[str, Page] = {}
        self._page_contexts: dict[Page, str] = {}
        self._owned_contexts: set[str] = set()
        self._owned_target_ids: dict[str, str] = {}
        self._attached = bool(self.debugger_address)
        self._connected = False
        self._next_orphan_cleanup_at = 0.0
        self._history_rate_limit_seen = False
        self._flaresolverr_attempted = False

    @staticmethod
    def _is_send_endpoint(url: str) -> bool:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and (parsed.hostname or "").casefold() in {"chatgpt.com", "chat.openai.com"}
            and parsed.path.rstrip("/") in {
                "/backend-api/f/conversation",
                "/backend-api/conversation",
            }
        )

    @staticmethod
    def _is_history_read_rate_limit(status: int, method: str, url: str) -> bool:
        if status != 429 or method.upper() != "GET":
            return False
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and (parsed.hostname or "").casefold() == "chatgpt.com"
            and re.fullmatch(
                r"/backend-api/conversations/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
                parsed.path,
            )
            is not None
        )

    def _observe_history_read_response(self, status: int, method: str, url: str) -> None:
        if self._is_history_read_rate_limit(status, method, url):
            self._history_rate_limit_seen = True

    def history_rate_limited(self) -> bool:
        """Whether this owned page observed a conversation-read HTTP 429."""
        return self._history_rate_limit_seen

    @staticmethod
    def captured_send_response(capture: dict[str, object]) -> tuple[str, int] | None:
        request_id = str(capture.get("request_id") or "")
        status = int_value(capture.get("status"))
        if request_id and bool(capture.get("response_started")) and 200 <= status < 400:
            return request_id, status
        return None

    async def ensure_token(self) -> str:
        payload = json_object(
            await self.eval(load_browser_script("ensure_token.js"), await_promise=True),
            label="token probe",
        )
        if payload.get("challenge") is True:
            raise BrowserSecurityChallengeError("ChatGPT authentication endpoint is challenged")
        token = str(payload.get("token") or "")
        if not payload.get("ok") or not token:
            raise RuntimeError("Prompta browser profile is not logged into ChatGPT")
        return token

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
        self._signal_response(None)
        self._owned_contexts.discard(context_id)
        self._owned_target_ids.pop(context_id, None)
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

    async def _lease_owned_page(self, page: Page) -> None:
        try:
            session = await asyncio.wait_for(page.context.new_cdp_session(page), timeout=3.0)
            try:
                info = await asyncio.wait_for(session.send("Target.getTargetInfo"), timeout=3.0)
                target_info = info.get("targetInfo")
                target_id = target_info.get("targetId") if isinstance(target_info, dict) else None
                if isinstance(target_id, str) and target_id:
                    record_owned_tab(target_id, time.time())
                    context_id = self._page_contexts.get(page)
                    if context_id is not None and context_id in self._owned_contexts:
                        self._owned_target_ids[context_id] = target_id
                else:
                    logger.warning("Prompta CDP target lacked an ID for expiry registration")
            finally:
                try:
                    await asyncio.wait_for(session.detach(), timeout=2.0)
                except Exception as exc:
                    logger.debug("Prompta CDP lease session detach failed type=%s", type(exc).__name__)
        except Exception as exc:
            logger.warning("Prompta tab lease registration failed error_type=%s", type(exc).__name__)

    def record_verified_activity(self) -> bool:
        """Only a currently owned, live page can refresh its ledger's idle clock."""
        if not self.is_connected or self.context not in self._owned_contexts:
            return False
        target_id = self._owned_target_ids.get(self.context)
        return bool(target_id and touch_owned_tab(target_id, time.time()))

    async def _mark_owned(self, page: Page) -> None:
        # Retry a failed lease before setting the marker, which can require page JavaScript.
        await self._lease_owned_page(page)
        marker = new_owned_window_marker(
            prefix=self.ownership_prefix,
            owner_id=self.page_owner_id,
        )
        await page.evaluate(load_browser_script("set_window_name.js"), marker)

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

        now = time.time()
        cutoff = now - max(1.0, minimum_age_seconds)
        closed = 0
        for page in list(browser_context.pages):
            if page in self._page_contexts:
                continue
            started_at = await self._owned_page_started_at(page)
            if started_at is None or started_at > cutoff:
                continue
            owner_id = await self._owned_page_owner_id(page)
            if owner_id is None:
                # Ownerless markers cannot prove that another live process still
                # owns the page, so fail safe and leave them alone.
                continue
            # A live owner may have renewed verified activity. The independent
            # watchdog, not an unrelated driver, applies the 45-minute idle TTL.
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
        if capture.get("request_obj") is not None:
            capture["ambiguous_request"] = True
            self._signal_response(None)
            return
        capture["request_obj"] = request
        capture["request_id"] = str(id(request))

    def _on_response(self, response: Response) -> None:
        # A failed conversation GET can show only a generic load-error banner.
        # Preserve the HTTP status so read-only recovery applies durable backoff.
        self._observe_history_read_response(
            response.status, response.request.method, response.url
        )
        capture = self._send_capture
        if capture is None or capture.get("request_obj") is not response.request:
            return
        capture["status"] = int(response.status)
        capture["retry_after"] = response.headers.get("retry-after", "")
        capture["retry_after_ms"] = response.headers.get("retry-after-ms", "")
        capture["response_started"] = True
        if (
            not capture.get("ambiguous_request")
            and 200 <= response.status < 300
            and "text/event-stream" in response.headers.get("content-type", "").casefold()
        ):
            # This is the existing POST's response. No fetch, routing, or history GET.
            # The stream itself is proof of generation, even before final text exists.
            capture["sse_stream"] = True
            task = asyncio.create_task(self._read_completed_sse_response(response, capture))
            self._response_tasks.add(task)
            task.add_done_callback(self._response_tasks.discard)

    async def _read_completed_sse_response(
        self, response: Response, capture: dict[str, object]
    ) -> None:
        try:
            await response.finished()
            # Playwright can read the body after the SSE stream terminates.
            # Its tab may close first; that is an interrupted capture, never a retry.
            body = await response.text()
            if not capture.get("ambiguous_request"):
                capture["assistant_result"] = parse_sse_body(body)
                self._signal_response(capture["assistant_result"])
        except asyncio.CancelledError:
            capture["assistant_capture_stop"] = "interrupted"
            self._signal_response(None)
            raise
        except (PlaywrightError, RuntimeError):
            capture["assistant_capture_stop"] = "interrupted"
            self._signal_response(None)

    def _signal_response(self, result: CaptureResult | None) -> None:
        if self._response_events.full():
            self._response_events.get_nowait()
        self._response_events.put_nowait(result)

    async def enable_passive_updates(self) -> None:
        page = self._pages.get(self.context)
        if page is None or page.is_closed():
            raise RuntimeError("The owned capture tab is unavailable")

        def on_change(payload: object) -> None:
            result = normalize_dom_snapshot(payload)
            if isinstance(payload, dict) and payload.get("ambiguous") is True:
                self._signal_response(CaptureResult("dom", "unknown", "", None, None, None))
            elif result.observer_id or result.message_id:
                self._signal_response(result)

        # Page-scoped CDP binding, not an HTTP request, refresh, or DOM scrape.
        await page.expose_function("__promptaPassiveUpdate", on_change)

    async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
        try:
            return await asyncio.wait_for(self._response_events.get(), timeout=max(0.01, timeout))
        except TimeoutError:
            return None

    @staticmethod
    def captured_assistant_response(capture: dict[str, object]) -> CaptureResult | None:
        result = capture.get("assistant_result")
        if isinstance(result, CaptureResult):
            return result
        if capture.get("assistant_capture_stop") == "interrupted":
            return CaptureResult("sse", "interrupted", "", None, None, None)
        return None

    async def observed_assistant_response(self) -> CaptureResult:
        try:
            payload = await self.eval(load_browser_script("passive_response_read.js"))
        except (PlaywrightError, RuntimeError, TimeoutError):
            return normalize_dom_snapshot(None)
        return normalize_dom_snapshot(payload)

    def _on_request_finished(self, request: Request) -> None:
        capture = self._send_capture
        if capture is not None and capture.get("request_obj") is request:
            capture["completed"] = True

    def _on_request_failed(self, request: Request) -> None:
        capture = self._send_capture
        if capture is not None and capture.get("request_obj") is request:
            capture["fetch_error"] = str(request.failure or "request failed")

    def arm_send_capture(self) -> dict[str, object]:
        if not self.is_connected:
            raise RuntimeError("Playwright browser is not connected")
        capture: dict[str, object] = {
            "request_id": "",
            "request_obj": None,
            "status": 0,
            "response_started": False,
            "sse_stream": False,
            "completed": False,
            "fetch_error": "",
            "ambiguous_request": False,
        }
        self._send_capture = capture
        return capture

    def clear_send_capture(self, capture: dict[str, object]) -> None:
        if self._send_capture is capture:
            self._send_capture = None
        capture.pop("request_obj", None)

    async def _first_usable(
        self,
        locators: Sequence[_UsableCollection[_UsableT]],
        *,
        enabled: bool = True,
        limit: int = 12,
    ) -> _UsableT | None:
        # Prefer the conservative composed-tree signal, but do not make it a
        # single point of failure. ChatGPT popovers can be visibly interactive
        # while a wrapper's transient CSS makes that guard report false. For a
        # semantic locator with exactly one browser-visible candidate, Chromium's
        # visibility/enabled state is a safe fallback.
        for locator in locators:
            try:
                count = await locator.count()
                if count > limit:
                    # A truncated scan cannot establish a unique active control.
                    continue
            except PlaywrightError:
                continue

            browser_usable: list[_UsableT] = []
            composed_active: list[_UsableT] = []
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if not await candidate.is_visible():
                        continue
                    if enabled and not await candidate.is_enabled():
                        continue
                    browser_usable.append(candidate)
                    if await candidate.evaluate(load_browser_script("is_active_composed_node.js")):
                        composed_active.append(candidate)
                except PlaywrightError:
                    continue

            if len(composed_active) == 1:
                return composed_active[0]
            if not composed_active and len(browser_usable) == 1:
                return browser_usable[0]
        return None

    async def _unique_usable(
        self,
        locator: _UsableCollection[_UsableT],
        *,
        enabled: bool = True,
        limit: int = 24,
    ) -> _UsableT | None:
        """Return one usable match, refusing to guess when several are active."""

        try:
            count = await locator.count()
            if count > limit:
                # Refuse a guessed control when matching nodes exceed the scan cap.
                return None
        except PlaywrightError:
            return None

        browser_usable: list[_UsableT] = []
        composed_active: list[_UsableT] = []
        for index in range(count):
            candidate = locator.nth(index)
            try:
                if not await candidate.is_visible():
                    continue
                if enabled and not await candidate.is_enabled():
                    continue
                browser_usable.append(candidate)
                if await candidate.evaluate(load_browser_script("is_active_composed_node.js")):
                    composed_active.append(candidate)
            except PlaywrightError:
                continue

        if len(composed_active) == 1:
            return composed_active[0]
        if not composed_active and len(browser_usable) == 1:
            return browser_usable[0]
        return None

    async def _hydrated_composer(self, page: _LocatorPage[_UsableT]) -> _UsableT | None:
        # ChatGPT hydrates its initial textarea into a contenteditable editor. The
        # editor can briefly have no rendered box, so accessibility/visibility APIs
        # alone are not sufficient. Discover by editable capability, then prefer a
        # unique public accessible name and finally a single active editor.
        editables = page.locator('[contenteditable]:not([contenteditable="false"])')
        try:
            count = await editables.count()
            if count > 24:
                # Scanning a prefix cannot rule out another active editor.
                return None
        except PlaywrightError:
            return None

        named: list[_UsableT] = []
        active: list[_UsableT] = []
        inspection_failed = False
        for index in range(count):
            candidate = editables.nth(index)
            try:
                composed_active = await candidate.evaluate(
                    load_browser_script("is_active_composed_node.js")
                )
                # Preserve the newer main behavior: Chromium visibility is
                # authoritative when the conservative composed-tree guard has a
                # transient false negative around the live ChatGPT editor.
                if not composed_active and not await candidate.is_visible():
                    continue
                if not await candidate.is_enabled():
                    continue
                active.append(candidate)
                labels = await candidate.evaluate(load_browser_script("semantic_control_labels.js"))
                if isinstance(labels, list) and any(
                    _COMPOSER_NAME_RE.search(str(label)) for label in labels
                ):
                    named.append(candidate)
            except PlaywrightError:
                # A failed inspection may conceal a second matching editor.
                # Never infer uniqueness from a partially inspected set.
                inspection_failed = True
        if inspection_failed:
            return None

        if len(named) == 1:
            return named[0]
        if len(active) == 1:
            return active[0]
        return None

    async def _composer(self, page: Page) -> Locator | None:
        main = page.get_by_role("main")

        # Prefer the public accessible name. Structural fallbacks are deliberately
        # conservative: when more than one active textbox exists, do not guess which
        # one is the prompt composer.
        def named(scope: Page | Locator) -> list[Locator]:
            return [
                scope.get_by_role("textbox", name=_COMPOSER_NAME_RE),
                scope.get_by_label(_COMPOSER_NAME_RE),
                scope.get_by_placeholder(_COMPOSER_NAME_RE),
            ]

        hydrated = await self._hydrated_composer(page)
        if hydrated is not None:
            return hydrated

        for candidates in (named(main), named(page)):
            found = await self._first_usable(candidates)
            if found is not None:
                return found

        return await self._unique_usable(page.get_by_role("textbox"))

    async def _composer_submit_button(
        self,
        composer: Locator,
        *,
        enabled: bool = True,
    ) -> Locator | None:
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

                button = await self._first_usable([submits], enabled=enabled)
                if button is not None:
                    return button
            except PlaywrightError:
                continue
        return None

    async def _image_input(self, page: Page) -> Locator | None:
        # ChatGPT now exposes multiple hidden camera, photos, video and file
        # pickers at once. Select its semantically named photo picker first.
        photos = page.locator('input[type="file"][aria-label="Attach photos"]:not([capture])')
        if await photos.count() == 1 and await photos.first.is_enabled():
            return photos.first
        images = page.locator('input[type="file"][multiple][accept*="image/"]:not([accept*="video/"]):not([capture])')
        if await images.count() == 1 and await images.first.is_enabled():
            return images.first
        composer = await self._composer(page)
        if composer is not None:
            owner = composer.locator('xpath=ancestor::*[.//input[@type="file"]][1]')
            inputs = owner.locator('input[type="file"]:not([capture])')
            count = await inputs.count()
            if count == 1 and await inputs.first.is_enabled():
                return inputs.first
            if count > 1:
                multi = owner.locator('input[type="file"][multiple]:not([capture])')
                if await multi.count() == 1 and await multi.first.is_enabled():
                    return multi.first
        inputs = page.locator('input[type="file"]:not([capture])')
        if await inputs.count() == 1 and await inputs.first.is_enabled():
            return inputs.first
        return None

    async def attach_images(self, paths: tuple[Path, ...]) -> None:
        if not paths:
            return
        for path in paths:
            if not path.is_file():
                raise RuntimeError("Prompta image attachment missing")
        page = self._page()
        field = await self._image_input(page)
        if field is None:
            attach = await self._semantic_button(
                page, re.compile(r"add files? and more|attach|upload|add (?:file|photo)", re.I)
            )
            if attach is not None:
                await attach.click()
                for _ in range(30):
                    field = await self._image_input(page)
                    if field is not None:
                        break
                    await asyncio.sleep(0.1)
        if field is None:
            raise RuntimeError("ChatGPT image attachment input unavailable")
        previews = page.locator(".composer-attachment-surface img")
        baseline = await previews.count()
        await field.set_input_files([str(path) for path in paths])
        stable = 0
        deadline = asyncio.get_running_loop().time() + 120.0
        while asyncio.get_running_loop().time() < deadline:
            count = await previews.count()
            ready = count >= baseline + len(paths)
            if ready:
                for index in range(baseline, baseline + len(paths)):
                    if not await previews.nth(index).evaluate(
                        load_browser_script("image_preview_ready.js")
                    ):
                        ready = False
                        break
            if ready:
                stable += 1
                if stable >= 5:
                    return
            else:
                stable = 0
            await asyncio.sleep(0.25)
        raise RuntimeError("ChatGPT image previews did not become ready within 120s")

    async def _semantic_button(
        self,
        page: Page,
        name: re.Pattern[str],
        *,
        enabled: bool = True,
    ) -> Locator | None:
        # Resolve controls by meaning rather than by one specific element/role.
        # ChatGPT has moved actions between native buttons, ARIA menu items, tabs,
        # switches, and roleless focusable wrappers while keeping public labels.
        # Prefer the chat landmark before the whole page so similarly named sidebar
        # actions cannot steal the click.
        scopes: tuple[Page | Locator, ...] = (page.get_by_role("main"), page)
        action_roles = (
            "button",
            "menuitem",
            "menuitemradio",
            "option",
            "link",
            "radio",
            "tab",
            "switch",
            "combobox",
        )

        for scope in scopes:
            semantic = await self._first_usable(
                [scope.get_by_role(role, name=name) for role in action_roles],
                enabled=enabled,
            )
            if semantic is not None:
                return semantic

            # If the ARIA role itself churned, inspect only elements that carry
            # interaction/accessibility signals. Match public labels/text, never
            # styling classes or private test IDs, and require an unambiguous
            # fallback within the current scope before clicking it.
            candidates = scope.locator(
                "button,a,input,select,summary,[role],[tabindex],[aria-label],"
                "[aria-labelledby],[aria-pressed],[aria-selected],[aria-checked],"
                "[data-state],[title]"
            )
            try:
                count = await candidates.count()
            except PlaywrightError:
                continue

            # A truncated scan cannot establish uniqueness. Do not match a
            # control ahead of unseen candidates when the role lookup failed.
            if count > 80:
                continue

            matched: list[Locator] = []
            for index in range(count):
                candidate = candidates.nth(index)
                try:
                    if not await candidate.is_visible():
                        continue
                    if enabled and not await candidate.is_enabled():
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

    async def _selection_state(self, control: _AttributeControl) -> bool | None:
        """Return semantic selected state without depending on one widget role."""

        saw_false = False
        for attribute in ("aria-checked", "aria-selected", "aria-pressed"):
            try:
                value = (await control.get_attribute(attribute) or "").strip().casefold()
            except PlaywrightError:
                continue
            if value == "true":
                return True
            if value == "false":
                saw_false = True

        try:
            current = (await control.get_attribute("aria-current") or "").strip().casefold()
        except PlaywrightError:
            current = ""
        if current and current != "false":
            return True
        if current == "false":
            saw_false = True

        try:
            state = (await control.get_attribute("data-state") or "").strip().casefold()
        except PlaywrightError:
            state = ""
        if state in {"active", "checked", "selected", "on", "open"}:
            return True
        if state in {"inactive", "unchecked", "unselected", "off", "closed"}:
            saw_false = True

        return False if saw_false else None

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
            self.context = await self._prepare_owned_page(page)
            self._network_subscribed = True
            self._connected = True

            await self.navigate("https://chatgpt.com/", context=self.context)
            if await self._cloudflare_challenge_present():
                if not await self._recover_security_challenge(page):
                    raise BrowserSecurityChallengeError("ChatGPT security challenge blocked authentication")
                await self.navigate("https://chatgpt.com/", context=self.context)
                if await self._cloudflare_challenge_present():
                    raise BrowserSecurityChallengeError("ChatGPT security challenge blocked authentication")

            deadline = asyncio.get_running_loop().time() + self.auth_timeout_seconds
            last_error: Exception | None = None
            while asyncio.get_running_loop().time() < deadline:
                try:
                    if await self.login_required():
                        raise RuntimeError("Prompta Chromium profile is not logged into ChatGPT")
                    if await self.ensure_token():
                        return
                except BrowserSecurityChallengeError:
                    if not await self._recover_security_challenge(page):
                        raise
                    await self.navigate("https://chatgpt.com/", context=self.context)
                    await self.ensure_token()
                    return
                except Exception as exc:
                    last_error = exc
                await asyncio.sleep(min(5.0, max(0.0, deadline - asyncio.get_running_loop().time())))
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
    ) -> object:
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

    async def click_stuck_connector_approval(self) -> object:
        return await trusted_approval_retry(self._page())

    @staticmethod
    def _navigation_response_is_security_challenge(response: Response | None) -> bool:
        if response is None:
            return False
        try:
            verdict = response.headers.get("cf-mitigated", "")
        except PlaywrightError:
            return False
        return verdict.casefold() == "challenge"

    async def _recover_security_challenge(self, page: Page) -> bool:
        """Try one local solver clearance before any prompt has been dispatched."""
        endpoint = os.environ.get("PROMPTA_FLARESOLVERR_URL", "").strip()
        if not endpoint or self._flaresolverr_attempted or not _claim_flaresolverr_attempt():
            return False
        self._flaresolverr_attempted = True
        started = time.monotonic()
        try:
            clearance = await asyncio.wait_for(
                asyncio.to_thread(solve_cloudflare, endpoint), timeout=70.0
            )
            if clearance is None:
                logger.warning("FlareSolverr clearance unavailable")
                return False
            cookie_value, user_agent = clearance
            current_agent = await page.evaluate(load_browser_script("navigator_user_agent.js"))
            if current_agent != user_agent:
                session = await page.context.new_cdp_session(page)
                await session.send("Network.setUserAgentOverride", {"userAgent": user_agent})
            await page.context.add_cookies(
                [{"name": "cf_clearance", "value": cookie_value, "url": "https://chatgpt.com/"}]
            )
            logger.info(
                "FlareSolverr clearance applied duration_ms=%d",
                round((time.monotonic() - started) * 1000),
            )
            return True
        except (Exception, TimeoutError) as exc:
            logger.warning("FlareSolverr recovery failed error_type=%s", type(exc).__name__)
            return False

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        page = self._page(context)
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=_DEFAULT_TIMEOUT_MS)
            if self._navigation_response_is_security_challenge(response):
                if not await self._recover_security_challenge(page):
                    raise BrowserSecurityChallengeError("ChatGPT security challenge blocked navigation")
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=_DEFAULT_TIMEOUT_MS
                )
                if self._navigation_response_is_security_challenge(response):
                    raise BrowserSecurityChallengeError("ChatGPT security challenge blocked navigation")
            context_id = self._page_contexts.get(page)
            if context_id in self._owned_contexts:
                await self._mark_owned(page)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Playwright navigation timed out for {url}") from exc

    async def _prepare_owned_page(self, page: Page) -> str:
        """Register a new Prompta tab before any setup that can fail."""
        try:
            context_id = self._register_page(page, owned=True)
            # Register the target before viewport or page JavaScript can hang or fail.
            await self._lease_owned_page(page)
            # CDP-attached Brave may start with a 0x0 browser viewport.
            # Give each owned tab an actionable viewport before navigation.
            await page.set_viewport_size({"width": 1280, "height": 960})
            return context_id
        except BaseException:
            context_id = self._page_contexts.get(page)
            if context_id is not None:
                await self.close_context(context_id)
            else:
                try:
                    await page.close()
                except PlaywrightError:
                    pass
            raise

    async def new_tab(self, url: str = "https://chatgpt.com/") -> str:
        browser_context = self._browser_context
        if browser_context is None:
            raise RuntimeError("Playwright browser context is not connected")
        page = await browser_context.new_page()
        context_id = await self._prepare_owned_page(page)
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

    @staticmethod
    def _authentication_route(url: str) -> bool:
        """Recognise explicit authentication redirects without inspecting account data."""
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        if host == "auth.openai.com":
            return True
        if host not in {"chatgpt.com", "www.chatgpt.com"}:
            return False
        path = parsed.path.casefold().rstrip("/")
        return path in {"/login", "/auth/login", "/auth/signin", "/auth/sign-in"}

    @staticmethod
    def _mfa_authentication_route(url: str) -> bool:
        """Recognise OpenAI MFA routes without reading authentication form contents."""
        parsed = urlsplit(url)
        if (parsed.hostname or "").casefold() != "auth.openai.com":
            return False
        path = parsed.path.casefold()
        return re.search(r"/mfa(?:-challenge)?(?:/|$)", path) is not None

    async def login_required(self) -> bool:
        page = self._page()
        if self._authentication_route(page.url):
            return True
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
        # attributes below as structural fallbacks for challenge pages that
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

    async def wait_for_composer(
        self,
        timeout: float = 20.0,
        *,
        context: str | None = None,
    ) -> None:
        if await self._cloudflare_challenge_present(context=context):
            if not os.environ.get("PROMPTA_FLARESOLVERR_URL"):
                raise BrowserSecurityChallengeError("ChatGPT security challenge is blocking composer readiness")
            if not await self._recover_security_challenge(self._page(context)):
                raise BrowserSecurityChallengeError("ChatGPT security challenge is blocking composer readiness")
            await self.navigate("https://chatgpt.com/", context=context)
            if await self._cloudflare_challenge_present(context=context):
                raise BrowserSecurityChallengeError("ChatGPT security challenge is blocking composer readiness")

        page = self._page(context)
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if await self._composer(page) is not None:
                # stufently/gpt-web-gateway documents that ChatGPT can render a
                # usable anonymous composer alongside Log in / Sign up controls.
                # A composer is therefore readiness evidence, not authentication
                # evidence: fail closed if public login semantics are also present.
                if await self.login_required():
                    raise RuntimeError("ChatGPT login required; composer unavailable")
                return
            # A challenge can replace the editor while hydration is in flight.
            # Fail closed before another wait rather than mistaking it for a stall.
            if await self._cloudflare_challenge_present(context=context):
                raise BrowserSecurityChallengeError("ChatGPT security challenge is blocking composer readiness")
            await asyncio.sleep(0.15)

        if await self._cloudflare_challenge_present(context=context):
            raise BrowserSecurityChallengeError("ChatGPT security challenge is blocking composer readiness")
        # FirstWari/chatgpt-web classifies authentication redirects separately
        # from hydration failures. Check only after exhausting the normal wait,
        # retaining Prompta's existing browser and authentication ownership.
        if self._mfa_authentication_route(page.url):
            raise RuntimeError("ChatGPT multi-factor authentication required; composer unavailable")
        if await self.login_required():
            raise RuntimeError("ChatGPT login required; composer unavailable")
        raise RuntimeError("ChatGPT composer did not become ready")

    async def _dismiss_known_composer_promo(self, page: Page) -> bool:
        """Dismiss only a recognised, nonessential ChatGPT composer promotion."""
        dialogs = page.get_by_role("dialog")
        try:
            count = await dialogs.count()
        except PlaywrightError:
            return False
        # Never scan an unbounded number of dialogs or click generic OK/CTA buttons.
        if count > 4:
            return False
        for index in range(count):
            dialog = dialogs.nth(index)
            try:
                if not await dialog.is_visible():
                    continue
                description = (await dialog.inner_text())[:1200]
                if not re.search(r"try thinking effort|introducing thinking effort", description, re.I):
                    continue
                close = await self._first_usable(
                    [
                        dialog.get_by_role(
                            "button", name=re.compile(r"^(close|dismiss|not now)$", re.I)
                        )
                    ]
                )
                if close is None:
                    continue
                await close.click(timeout=1500)
                return True
            except PlaywrightError:
                continue
        return False

    async def _focus_composer(self) -> Locator:
        await self.wait_for_composer()
        await self._dismiss_known_composer_promo(self._page())
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
            # Target selection and clearing at the composer, not whichever
            # element happens to own page-wide keyboard focus.
            await composer.press("ControlOrMeta+A")
            await composer.press("Backspace")
            if text:
                await composer.focus()
                # The keyboard is page-wide. Fail closed if hydration or a
                # popup stole focus before insertion; never type into it.
                focused = await composer.evaluate(load_browser_script("composer_has_focus.js"))
                if focused is not True:
                    raise RuntimeError("ChatGPT composer lost focus before text insertion")
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

    async def _send_control(
        self,
        page: Page,
        *,
        enabled: bool = True,
    ) -> Locator | None:
        button = await self._semantic_button(page, _SEND_RE, enabled=enabled)
        if button is not None:
            return button
        composer = await self._composer(page)
        if composer is None:
            return None
        return await self._composer_submit_button(composer, enabled=enabled)

    async def wait_for_send_ready(self, timeout: float = 3.0) -> Locator | None:
        # KudoAI/chatgpt.js 79d9a0f waits for the send control to become enabled
        # before dispatch. Preserve that useful behavior without importing its
        # private test-id selector: Prompta only uses public semantics or a
        # composer-scoped native submit control.
        page = self._page()
        control = await self._send_control(page, enabled=False)
        if control is None:
            # The keyboard fallback is valid only on an ordinary composer.
            # A challenge/login replacement must never receive the prompt.
            if await self._cloudflare_challenge_present():
                raise BrowserSecurityChallengeError("ChatGPT security challenge is blocking send readiness")
            if self._mfa_authentication_route(page.url):
                raise RuntimeError("ChatGPT multi-factor authentication required; send control unavailable")
            if await self.login_required():
                raise RuntimeError("ChatGPT login required; send control unavailable")
            return None

        deadline = asyncio.get_running_loop().time() + max(0.1, timeout)
        while asyncio.get_running_loop().time() < deadline:
            try:
                if await control.is_enabled():
                    return control
            except PlaywrightError:
                pass

            await asyncio.sleep(0.05)
            current = await self._send_control(page, enabled=False)
            if current is not None:
                control = current

        await self._raise_send_readiness_unavailable()

    async def _raise_send_readiness_unavailable(self) -> None:
        # This is pre-dispatch only: never retry after a possible send mutation.
        if await self._cloudflare_challenge_present():
            raise BrowserSecurityChallengeError("ChatGPT security challenge is blocking send readiness")
        page = self._page()
        if self._mfa_authentication_route(page.url):
            raise RuntimeError("ChatGPT multi-factor authentication required; send control unavailable")
        if await self.login_required():
            raise RuntimeError("ChatGPT login required; send control unavailable")
        raise RuntimeError("ChatGPT send control remained disabled")

    async def click_send(self, expected_message: str, /) -> None:
        await self._focus_composer()
        control = await self.wait_for_send_ready()

        # stufently/gpt-web-gateway 82e7858 re-focuses and re-reads the
        # composer before its keyboard fallback. Adapt that fail-closed guard
        # without importing private selectors or any response/history logic.
        composer = await self._focus_composer()
        actual = _normalise_composer_text(await self._composer_text(composer))
        expected = _normalise_composer_text(expected_message)
        if actual != expected:
            raise RuntimeError("ChatGPT composer changed before submit")

        try:
            if control is not None:
                await control.click()
            else:
                await self._page().keyboard.press("Enter")
        except Exception as exc:
            mutation = "clicking the send control" if control is not None else "pressing Enter"
            raise SendOutcomeUnknownError(
                f"ChatGPT send mutation failed while {mutation}; the prompt may have been submitted"
            ) from exc

    async def pin_current_chat(self) -> None:
        """Pin only the newly submitted chat, without reading or storing chat data."""
        page = self._page()
        await page.wait_for_url(re.compile(r"^https://chatgpt\.com/c/[^/?#]+"), timeout=15_000)
        path = urlsplit(page.url).path
        if not re.fullmatch(r"/c/[^/]+", path):
            raise RuntimeError("Fresh chat has no pin-capable conversation route")

        show_sidebar = page.get_by_role("button", name=re.compile(r"^(show|open) sidebar$", re.I))
        if await show_sidebar.count() == 1 and await show_sidebar.is_visible():
            await show_sidebar.click()

        link = page.locator(f'nav[aria-label="Chat history"] a[href$={json.dumps(path)}]')
        await link.wait_for(state="visible", timeout=12_000)

        async def open_options() -> None:
            await link.hover()
            for ancestor in range(1, 7):
                row = link.locator(f"xpath=ancestor::div[{ancestor}]")
                options = row.get_by_role(
                    "button", name=re.compile(r"^(?:Chat actions|(?:conversation|chat)? ?(?:more |other )?options)$", re.I)
                )
                if await options.count() == 1:
                    await options.click()
                    return
                buttons = row.locator("button")
                if await buttons.count() == 1:
                    await buttons.click()
                    return
            raise RuntimeError("Chat history row has no options button")

        async def menu_action(action: str) -> Locator:
            label = re.compile(rf"^{action}(?: chat)?$", re.I)
            item = page.get_by_role("menuitem", name=label)
            if await item.count() == 1:
                return item
            return page.get_by_text(label)

        try:
            await open_options()
            if await (await menu_action("Unpin")).count() == 1:
                return
            pin = await menu_action("Pin")
            if await pin.count() != 1:
                raise RuntimeError("Chat history menu has no Pin chat action")
            await pin.click()
            await open_options()
            if await (await menu_action("Unpin")).count() != 1:
                raise RuntimeError("ChatGPT did not verify the pinned chat")
        finally:
            await page.keyboard.press("Escape")

    async def click_send_button(self, timeout: float = 120.0) -> None:
        page = self._page()
        deadline = asyncio.get_running_loop().time() + max(1.0, timeout)
        while asyncio.get_running_loop().time() < deadline:
            button = await self._send_control(page)
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

    async def _rate_limit_texts(self, page: _RateLimitPage[_RateT]) -> list[str]:
        # Rate-limit UI has changed wrappers and private test IDs repeatedly.
        # Search durable accessibility surfaces first, then matching text inside
        # the current chat/dialog surface. The fresh-chat main landmark avoids
        # mistaking sidebar history for an active rate-limit notice.
        sources: tuple[_RateLimitCollection[_RateT], ...] = (
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

    async def dom_state(self) -> dict[str, object]:
        page = self._page()
        composer = await self._composer(page)
        composer_text = await self._composer_text(composer) if composer is not None else ""
        rate_limit_texts = await self._rate_limit_texts(page)
        send_in_progress = (
            await self._semantic_button(page, _STOP_GENERATING_RE, enabled=False)
            is not None
        )

        return {
            "composer_text": composer_text,
            "rate_limit_text": "\n".join(rate_limit_texts),
            "send_in_progress": send_in_progress,
        }

    async def send_confirmation_state(self) -> dict[str, object]:
        """Read only the active user composer and Stop generating control after dispatch."""
        page = self._page()
        # A single, bounded page evaluation avoids an expensive Playwright
        # accessibility/role scan while the fresh-chat UI is rehydrating. Read
        # only the user's textbox and explicit control labels, never messages.
        try:
            quick = await page.evaluate(load_browser_script("send_confirmation_state.js"))
            if (
                isinstance(quick, dict)
                and isinstance(quick.get("composer_text"), str)
                and isinstance(quick.get("send_in_progress"), bool)
            ):
                return {
                    "composer_text": str(quick["composer_text"]),
                    "send_in_progress": bool(quick["send_in_progress"]),
                }
        except (PlaywrightError, AttributeError):
            pass
        # Preserve semantic fallback for ChatGPT UI variants with no unique
        # visible composer, including shadow DOM/accessibility changes.
        composer = await self._composer(page)
        composer_text = await self._composer_text(composer) if composer is not None else ""
        send_in_progress = (
            await self._semantic_button(page, _STOP_GENERATING_RE, enabled=False)
            is not None
        )
        return {"composer_text": composer_text, "send_in_progress": send_in_progress}

    async def ensure_chat_surface(self, timeout: float = 5.0) -> None:
        page = self._page()
        deadline = asyncio.get_running_loop().time() + timeout
        chat_name = re.compile(r"^\s*chat(?:\s+mode)?\s*$", re.IGNORECASE)

        async def chat_control() -> Locator | None:
            candidates = [
                page.get_by_role(role, name=chat_name)
                for role in (
                    "radio",
                    "tab",
                    "button",
                    "menuitemradio",
                    "menuitem",
                    "option",
                    "switch",
                )
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
                    "[aria-labelledby],[title],[aria-checked],[aria-selected],"
                    "[aria-pressed],[aria-current],[data-state]"
                )
                try:
                    count = await interactive.count()
                except PlaywrightError:
                    continue
                # A prefix cannot establish uniqueness: a second Chat control
                # after index 39 would make the first match ambiguous.
                if count > 40:
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

        while asyncio.get_running_loop().time() < deadline:
            # Do not interact with Chat/Work controls if a security challenge
            # replaces the chat surface during initial navigation.
            if await self._cloudflare_challenge_present():
                raise BrowserSecurityChallengeError("ChatGPT security challenge is blocking Chat surface readiness")
            # A usable composer is sufficient evidence that the page is already on
            # the normal chat surface. Do not interact with a redundant Chat/Work
            # mode control merely because ChatGPT happens to render one.
            if await self._composer(page) is not None:
                return
            chat = await chat_control()
            if chat is None:
                # ChatGPT no longer always exposes explicit Chat/Work mode controls.
                # Keep waiting for the semantic success signal above.
                await asyncio.sleep(0.1)
                continue
            try:
                if await self._selection_state(chat) is True:
                    return
                await chat.click()
                while asyncio.get_running_loop().time() < deadline:
                    if await self._selection_state(chat) is True:
                        return
                    # Some implementations switch the surface without exposing a
                    # selected-state attribute. The composer is the semantic success
                    # signal in that case.
                    if await self._composer(page) is not None:
                        return
                    await asyncio.sleep(0.05)
            except PlaywrightError:
                await asyncio.sleep(0.1)
        if await self._cloudflare_challenge_present():
            raise BrowserSecurityChallengeError("ChatGPT security challenge is blocking Chat surface readiness")
        raise RuntimeError("ChatGPT Chat surface did not become active")

    async def _effort_trigger_locator(self) -> Locator | None:
        page = self._page()

        # A durable public label is sufficient for an explicit model/effort trigger.
        # Do not require aria-haspopup: popup metadata has changed independently of
        # the control label and _open_effort_menu verifies success structurally.
        direct = await self._semantic_button(page, _EFFORT_TRIGGER_RE)
        if direct is not None:
            return direct

        # Short state labels such as "High" are less specific, so retain popup
        # semantics for those to avoid matching unrelated controls.
        trigger_roles = (
            "button",
            "combobox",
            "menuitem",
            "menuitemradio",
            "option",
            "radio",
            "tab",
        )
        semantic_candidates = [page.get_by_role(role, name=_EFFORT_RE) for role in trigger_roles]
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
                count = await controls.count()
            except PlaywrightError:
                continue
            # A partial scan cannot prove which control owns the effort slider.
            if count > 40:
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
            slider_count = await sliders.count()
        except PlaywrightError:
            slider_count = 0
        if slider_count > 12:
            slider_count = 0  # Fall back to the explicitly named Power control.
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

    async def _model_selector_control(self, page: _ModelPage[_UsableT]) -> _UsableT | None:
        # Require model meaning, not merely popup ownership. A lone unrelated popup
        # (for example Plugins) must never become the model selector just because
        # ChatGPT has not hydrated the real control yet.
        model_menu_name = re.compile(
            r" *(?:(?:select|choose|change) +)?(?:chatgpt +)?(?:model|engine) *",
            re.IGNORECASE,
        )
        selectable_roles = (
            "menuitem",
            "menuitemradio",
            "option",
            "radio",
            "tab",
            "combobox",
            "button",
        )
        named = await self._first_usable(
            [page.get_by_role(role, name=model_menu_name) for role in selectable_roles],
            enabled=True,
        )
        if named is not None:
            return named

        # Tolerate role/tag churn only when one interactive control has a public
        # semantic label that still means model selection. Do not fall back to
        # arbitrary aria-haspopup elements.
        scopes: tuple[_LocatorScope[_UsableT], ...] = (page.get_by_role("main"), page)
        for scope in scopes:
            controls = scope.locator(
                "button,input,select,summary,[role],[tabindex],[aria-label],"
                "[aria-labelledby],[title]"
            )
            try:
                count = await controls.count()
                if count > 60:
                    # Prefix scans cannot establish uniqueness across all controls.
                    continue
            except PlaywrightError:
                continue

            matched: list[_UsableT] = []
            for index in range(count):
                item = controls.nth(index)
                try:
                    if not await item.is_visible() or not await item.is_enabled():
                        continue
                    labels = await item.evaluate(load_browser_script("semantic_control_labels.js"))
                    if not isinstance(labels, list):
                        continue
                    if any(
                        model_menu_name.fullmatch(str(label).strip())
                        for label in labels
                        if str(label).strip()
                    ):
                        matched.append(item)
                except PlaywrightError:
                    continue
            if len(matched) == 1:
                return matched[0]

        return None

    async def _model_selection_verified(
        self,
        page: Page,
        option: Locator,
        model_name_re: re.Pattern[str],
    ) -> bool:
        # After a model click the menu option can disappear immediately.
        # Reading attributes from a missing Playwright locator waits for its
        # default timeout, starving the bounded post-click verification.
        if await option.is_visible():
            if await self._selection_state(option) is True:
                return True
        else:
            # Radix hides its submenu after a selection but retains the
            # checked option in the DOM. get_by_role() excludes hidden options;
            # a role/checked-state CSS query still sees the committed choice.
            # count() is immediate, unlike waiting on the hidden role locator.
            selected_options = page.locator(
                '[role="menuitemradio"][aria-checked="true"], '
                '[role="radio"][aria-checked="true"], '
                '[role="option"][aria-selected="true"], '
                '[role="tab"][aria-selected="true"]'
            ).filter(has_text=model_name_re)
            try:
                if await selected_options.count() == 1:
                    return True
            except PlaywrightError:
                pass

        selector = await self._model_selector_control(page)
        if selector is None:
            return False
        try:
            labels = await selector.evaluate(load_browser_script("semantic_control_labels.js"))
        except PlaywrightError:
            return False
        if not isinstance(labels, list):
            return False
        return any(
            model_name_re.search(label)
            for value in labels
            if (label := str(value).strip())
        )

    async def _verify_model_selection_after_click(
        self,
        page: Page,
        option: Locator,
        model_name_re: re.Pattern[str],
    ) -> bool:
        for _ in range(_MODEL_SELECTION_VERIFY_ATTEMPTS):
            if await self._model_selection_verified(page, option, model_name_re):
                return True
            await asyncio.sleep(_MODEL_SELECTION_VERIFY_INTERVAL_SECONDS)
        return False

    async def select_effort_model(self, model_name: str = "GPT-6") -> None:
        page = self._page()
        model_name_re = re.compile(
            rf"^ *{re.escape(model_name)}(?: |$)",
            re.IGNORECASE,
        )

        # The current High menu has a direct, stable three-control path.
        # Avoid the broad fallback discovery when its exact controls exist.
        if model_name.casefold() == "gpt-6":
            trigger = page.get_by_role("button", name=re.compile(r"^select chatgpt model$", re.I))
            try:
                if (
                    await trigger.count() == 1
                    and await trigger.first.get_attribute("data-selected-reasoning-effort") == "high"
                ):
                    await trigger.first.dispatch_event("click")
                    row = page.get_by_role("menuitem", name=re.compile(r"^select model$", re.I))
                    if await row.count() == 1 and (await row.first.inner_text()).strip() == "High":
                        # This Radix view toggle requires keyboard activation;
                        # a synthetic click can dismiss the entire menu.
                        await row.first.focus()
                        await page.keyboard.press("Enter")
                        option = page.get_by_role("menuitemradio", name=model_name_re)
                        for _ in range(10):
                            if await option.count() == 1 and await option.first.is_visible():
                                if await option.first.get_attribute("aria-checked") != "true":
                                    await option.first.dispatch_event("click")
                                if await self._verify_model_selection_after_click(
                                    page, option.first, model_name_re
                                ):
                                    await page.keyboard.press("Escape")
                                    return
                            await asyncio.sleep(0.1)
            except PlaywrightError:
                pass

        async def find_option() -> Locator | None:
            # Menus have changed role structure before. Prefer accessible role/name
            # semantics across common selectable roles, then an unambiguous semantic
            # control fallback if the role disappears entirely.
            option_roles = (
                "menuitemradio",
                "radio",
                "option",
                "menuitem",
                "button",
                "tab",
            )
            named_roles = [page.get_by_role(role, name=model_name_re) for role in option_roles]
            text_roles = [
                page.get_by_role(role).filter(has_text=model_name_re) for role in option_roles
            ]
            found = await self._first_usable(named_roles + text_roles, enabled=True)
            if found is not None:
                return found
            return await self._semantic_button(page, model_name_re)

        async def expanded(control: Locator) -> bool:
            try:
                return (
                    await control.get_attribute("aria-expanded") or ""
                ).strip().casefold() == "true"
            except PlaywrightError:
                return False

        # Drive the menu as a semantic state machine. Never guess at unrelated popup
        # controls and never re-click an already-expanded trigger while waiting for
        # the next submenu to hydrate.
        deadline = asyncio.get_running_loop().time() + 15.0

        def step_timeout() -> float:
            remaining = deadline - asyncio.get_running_loop().time()
            return max(0.1, min(_MODEL_PICKER_STEP_TIMEOUT_SECONDS, remaining))

        option_seen = False
        selector_seen = False
        trigger_seen = False
        model_row_opened = False
        while asyncio.get_running_loop().time() < deadline:
            option = await _timed_model_picker_step(
                "option_discovery", find_option(), timeout=step_timeout()
            )
            option_seen = option_seen or option is not None
            if option is not None:
                # ChatGPT's High picker exposes a second High row labelled
                # "Select model" before its GPT model choices.
                if model_name.casefold() == "gpt-6" and not model_row_opened:
                    row = page.get_by_role("menuitem", name=re.compile(r"^select model$", re.I))
                    if await row.count() == 1:
                        item = row.first
                        if await item.is_visible() and (await item.inner_text()).strip() == "High":
                            await _timed_model_picker_step(
                                "high_model_row_open",
                                item.click(),
                                timeout=step_timeout(),
                            )
                            model_row_opened = True
                            continue
                try:
                    if await _timed_model_picker_step(
                        "selection_state_check",
                        self._model_selection_verified(page, option, model_name_re),
                        timeout=step_timeout(),
                    ):
                        await page.keyboard.press("Escape")
                        return

                    async def click_model_option() -> None:
                        try:
                            # ChatGPT's effort slider can overlap the centre of
                            # a model menu item and intercept pointer clicks.
                            await asyncio.wait_for(option.click(), timeout=1.25)
                        except (TimeoutError, PlaywrightError):
                            # Never send a second click if the first one took.
                            if await self._model_selection_verified(
                                page, option, model_name_re
                            ):
                                return
                            logger.info(
                                "ChatGPT model menu pointer click blocked; "
                                "trying the same semantic control's click event"
                            )
                            await option.dispatch_event("click")

                    await _timed_model_picker_step(
                        "model_option_click", click_model_option(), timeout=step_timeout()
                    )
                    if await _timed_model_picker_step(
                        "selection_verification",
                        self._verify_model_selection_after_click(page, option, model_name_re),
                        timeout=step_timeout(),
                    ):
                        await page.keyboard.press("Escape")
                        return
                    await self._raise_model_selection_unavailable(model_name)
                except PlaywrightError:
                    await asyncio.sleep(0.1)
                    continue

            selector = await _timed_model_picker_step(
                "selector_discovery",
                self._model_selector_control(page),
                timeout=step_timeout(),
            )
            selector_seen = selector_seen or selector is not None
            if selector is not None:
                try:
                    if await _timed_model_picker_step(
                        "selector_expansion_state", expanded(selector), timeout=step_timeout()
                    ):
                        await asyncio.sleep(0.05)
                        continue
                    await _timed_model_picker_step(
                        "selector_open", selector.click(), timeout=step_timeout()
                    )
                    await asyncio.sleep(0.08)
                    continue
                except PlaywrightError:
                    await asyncio.sleep(0.1)
                    continue

            trigger = await _timed_model_picker_step(
                "effort_trigger_discovery",
                self._effort_trigger_locator(),
                timeout=step_timeout(),
            )
            trigger_seen = trigger_seen or trigger is not None
            if trigger is not None:
                try:
                    if await _timed_model_picker_step(
                        "effort_trigger_expansion_state",
                        expanded(trigger),
                        timeout=step_timeout(),
                    ):
                        await asyncio.sleep(0.05)
                        continue
                    await _timed_model_picker_step(
                        "effort_trigger_open", trigger.click(), timeout=step_timeout()
                    )
                    await asyncio.sleep(0.08)
                    continue
                except PlaywrightError:
                    await asyncio.sleep(0.1)
                    continue

            await asyncio.sleep(0.1)

        logger.warning(
            "ChatGPT model picker exhausted semantic search model_option_seen=%s "
            "selector_control_seen=%s effort_trigger_seen=%s",
            option_seen,
            selector_seen,
            trigger_seen,
        )
        await self._raise_model_selection_unavailable(model_name)

    async def _raise_model_selection_unavailable(self, model_name: str) -> None:
        # A session can expire or encounter a security challenge while the picker
        # is hydrating. Do not change selection or authentication ownership.
        if await self._cloudflare_challenge_present():
            raise BrowserSecurityChallengeError("ChatGPT security challenge is blocking model selection")
        page = self._page()
        if self._mfa_authentication_route(page.url):
            raise RuntimeError("ChatGPT multi-factor authentication required; model selection unavailable")
        if await self.login_required():
            raise RuntimeError("ChatGPT login required; model selection unavailable")
        raise RuntimeError(f"ChatGPT model {model_name!r} is unavailable")

    async def effort_power_info(self) -> dict[str, object]:
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

    async def set_effort_power_position(self, position: int) -> dict[str, object]:
        await self._open_effort_menu()
        page = self._page()
        power = await self._power_control(page)
        if power is None:
            raise RuntimeError("ChatGPT Power control did not become available")

        info = await self.effort_power_info()
        current = int_value(info.get("position"))
        total = int_value(info.get("total"))
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
            if int_value(info.get("position")) == position:
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
        for task in tuple(self._response_tasks):
            task.cancel()
        if self._response_tasks:
            await asyncio.gather(*self._response_tasks, return_exceptions=True)
        self._response_tasks.clear()
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
