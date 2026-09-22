"""Chromium/ChromeDriver transport for Prompta.

The high-level ChatGPT DOM/snapshot logic lives in :mod:`prompta.bidi`.  This
driver deliberately subclasses that implementation and replaces only the
browser-transport primitives that differ between Firefox WebDriver BiDi and
Chromium WebDriver.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.common.exceptions import (
    JavascriptException,
    NoSuchElementException,
    NoSuchWindowException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chromium.remote_connection import ChromiumRemoteConnection
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.remote.client_config import ClientConfig
from selenium.webdriver.remote.command import Command
from selenium.webdriver.remote.file_detector import UselessFileDetector
from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
from urllib3.exceptions import HTTPError as Urllib3HTTPError
from urllib3.util.retry import Retry

from .bidi import _BIDI_AUTH_TIMEOUT_SECONDS, FirefoxBiDiDriver

logger = logging.getLogger(__name__)


class ChromeDebuggerUnavailableError(RuntimeError):
    pass


_CHROMEDRIVER_COMMAND_TIMEOUT_SECONDS = 30
_FATAL_WEBDRIVER_MARKERS = (
    "tab crashed",
    "invalid session id",
    "session deleted",
    "disconnected",
    "not connected to devtools",
    "chrome not reachable",
    "unable to discover open pages",
    "no such window",
    "target window already closed",
    "web view not found",
)


class _PromptaChrome(webdriver.Chrome):
    def __init__(self, *, service: Service, options: Options) -> None:
        self.service = service
        self.options = options
        self.service.start()
        client_config = ClientConfig(
            remote_server_addr=self.service.service_url,
            keep_alive=True,
            timeout=_CHROMEDRIVER_COMMAND_TIMEOUT_SECONDS,
        )
        executor = ChromiumRemoteConnection(
            remote_server_addr=self.service.service_url,
            browser_name=DesiredCapabilities.CHROME["browserName"],
            vendor_prefix="goog",
            keep_alive=True,
            ignore_proxy=self.options._ignore_local_proxy,
            client_config=client_config,
        )
        try:
            RemoteWebDriver.__init__(self, command_executor=executor, options=self.options)
            self.file_detector = UselessFileDetector()
        except Exception:
            self.quit()
            raise


class ChromeDriverDriver(FirefoxBiDiDriver):
    """Prompta browser driver backed by Chromium through ChromeDriver."""

    def __init__(
        self,
        *,
        profile: Path,
        chrome_path: str = "/usr/bin/chromium",
        chromedriver_path: str = "/usr/bin/chromedriver",
        headless: bool = True,
        auth_timeout_seconds: float = _BIDI_AUTH_TIMEOUT_SECONDS,
        debugger_address: str | None = None,
        flaresolverr_url: str | None = None,
    ) -> None:
        # The inherited class owns all browser-independent helpers.  It expects
        # these bookkeeping fields to exist even though Chromium does not use
        # the Firefox BiDi websocket.
        super().__init__("")
        self.profile = profile.expanduser().resolve()
        self.chrome_path = chrome_path
        self.chromedriver_path = chromedriver_path
        self.headless = headless
        self.auth_timeout_seconds = max(0.1, auth_timeout_seconds)
        self.debugger_address = debugger_address.strip() if debugger_address else None
        self.flaresolverr_url = flaresolverr_url.rstrip("/") if flaresolverr_url else None
        self._driver: webdriver.Chrome | None = None
        self._owned_contexts: set[str] = set()
        self._bootstrap_url = ""
        self._owned_contexts_path = self.profile.with_name(
            f"{self.profile.name}.owned-contexts.json"
        )

    @property
    def is_connected(self) -> bool:
        return self._driver is not None and bool(self.context) and not self.needs_browser_restart

    def _load_persisted_owned_contexts(self) -> set[str]:
        if not self.debugger_address:
            return set()
        try:
            payload = json.loads(self._owned_contexts_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        if not isinstance(payload, list):
            return set()
        return {item for item in payload if isinstance(item, str) and item}

    def _persist_owned_contexts(self) -> None:
        if not self.debugger_address:
            return
        try:
            if not self._owned_contexts:
                self._owned_contexts_path.unlink(missing_ok=True)
                return
            self._owned_contexts_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._owned_contexts_path.with_name(f"{self._owned_contexts_path.name}.tmp")
            temporary.write_text(
                json.dumps(sorted(self._owned_contexts)),
                encoding="utf-8",
            )
            temporary.replace(self._owned_contexts_path)
        except OSError:
            pass

    def _remember_owned_context(self, context: str) -> None:
        if not self.debugger_address:
            return
        self._owned_contexts.add(context)
        self._persist_owned_contexts()

    def _forget_owned_context(self, context: str) -> None:
        self._owned_contexts.discard(context)
        self._persist_owned_contexts()

    async def _cleanup_stale_owned_contexts(self) -> None:
        stale_contexts = self._load_persisted_owned_contexts()
        if not stale_contexts:
            return
        unresolved = await asyncio.to_thread(
            self._close_debugger_targets,
            stale_contexts,
        )
        self._owned_contexts.update(unresolved)
        self._persist_owned_contexts()

    @staticmethod
    def _is_fatal_webdriver_error(exc: Exception) -> bool:
        if isinstance(exc, (Urllib3HTTPError, TimeoutError, OSError)):
            return True
        message = str(exc).casefold()
        return any(marker in message for marker in _FATAL_WEBDRIVER_MARKERS)

    def _driver_runtime_error(self, operation: str, exc: Exception) -> RuntimeError:
        fatal = self._is_fatal_webdriver_error(exc)
        if fatal:
            self.needs_browser_restart = True
        detail = str(getattr(exc, "msg", "") or exc).strip() or type(exc).__name__
        suffix = "; browser restart required" if fatal else ""
        return RuntimeError(f"{operation}: {detail}{suffix}")

    async def _run_webdriver_call(self, operation: str, callback: Callable[[], Any]) -> Any:
        async with self._call_lock:
            try:
                return await asyncio.to_thread(callback)
            except (WebDriverException, Urllib3HTTPError, TimeoutError, OSError) as exc:
                raise self._driver_runtime_error(operation, exc) from exc

    def _create_driver(self) -> webdriver.Chrome:
        options = Options()
        if self.debugger_address:
            options.add_experimental_option("debuggerAddress", self.debugger_address)
        else:
            self.profile.mkdir(parents=True, exist_ok=True)
            options.binary_location = self.chrome_path
            options.add_argument(f"--user-data-dir={self.profile}")
            options.add_argument("--profile-directory=Default")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--disable-background-networking")
            options.add_argument("--disable-breakpad")
            options.add_argument("--disable-component-update")
            options.add_argument("--password-store=basic")
            options.add_argument("--window-size=1280,1000")
            if self.headless:
                options.add_argument("--headless=new")
                options.add_argument("--disable-gpu")
        service = Service(executable_path=self.chromedriver_path)
        driver = _PromptaChrome(service=service, options=options)
        client_config = getattr(driver.command_executor, "_client_config", None)
        if client_config is not None:
            client_config.timeout = _CHROMEDRIVER_COMMAND_TIMEOUT_SECONDS
        connection_manager = getattr(driver.command_executor, "_conn", None)
        if connection_manager is not None and hasattr(connection_manager, "connection_pool_kw"):
            connection_manager.connection_pool_kw["retries"] = Retry(
                total=0, connect=0, read=0, redirect=0, status=0
            )
            connection_manager.clear()
        return driver

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

    async def _cloudflare_challenge_present(self, *, context: str | None = None) -> bool:
        expression = (
            "(()=>{const t=(document.title||'').toLowerCase();"
            "if(t.includes('just a moment')||t.includes('attention required'))return true;"
            "return Boolean(document.querySelector("
            "'#challenge-form,#cf-challenge-running,#cf-please-wait,#challenge-spinner,"
            '#turnstile-wrapper,input[name=\\"cf-turnstile-response\\"],'
            'iframe[src*=\\"challenges.cloudflare.com\\"]\''
            "));})()"
        )
        return bool(
            await self.eval(expression)
            if context is None
            else await self.eval(expression, context=context)
        )

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
        request = Request(
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
        url = str(
            await self.eval("location.href")
            if context is None
            else await self.eval("location.href", context=context)
        )
        user_agent = str(
            await self.eval("navigator.userAgent")
            if context is None
            else await self.eval("navigator.userAgent", context=context)
        )
        logger.warning("Cloudflare challenge detected; requesting clearance from FlareSolverr")
        cookies = await asyncio.to_thread(self._request_flaresolverr, url, user_agent)
        if not cookies:
            raise RuntimeError("FlareSolverr solved ChatGPT without returning Cloudflare cookies")

        def apply() -> None:
            driver = self._activate_context_sync(context)
            for raw_cookie in cookies:
                cookie: dict[str, Any] = {
                    "name": str(raw_cookie["name"]),
                    "value": str(raw_cookie.get("value") or ""),
                }
                domain = raw_cookie.get("domain")
                path = raw_cookie.get("path")
                if isinstance(domain, str) and domain:
                    cookie["domain"] = domain
                if isinstance(path, str) and path:
                    cookie["path"] = path
                if isinstance(raw_cookie.get("secure"), bool):
                    cookie["secure"] = raw_cookie["secure"]
                if isinstance(raw_cookie.get("httpOnly"), bool):
                    cookie["httpOnly"] = raw_cookie["httpOnly"]
                expiry = raw_cookie.get("expires")
                if isinstance(expiry, (int, float)) and expiry > 0:
                    cookie["expiry"] = int(expiry)
                same_site = raw_cookie.get("sameSite")
                if same_site in {"Lax", "Strict", "None"}:
                    cookie["sameSite"] = same_site
                driver.add_cookie(cookie)
            driver.refresh()

        await self._run_webdriver_call("apply FlareSolverr Cloudflare clearance", apply)
        logger.info(
            "Applied %d Cloudflare clearance cookie(s) from FlareSolverr",
            len(cookies),
        )

    async def wait_for_composer(
        self,
        timeout: float = 20.0,
        *,
        context: str | None = None,
    ) -> None:
        if not self.flaresolverr_url:
            await super().wait_for_composer(timeout=timeout, context=context)
            return

        recovered = False
        if await self._cloudflare_challenge_present(context=context):
            await self._recover_cloudflare(context=context)
            recovered = True
        try:
            await super().wait_for_composer(timeout=timeout, context=context)
        except RuntimeError as exc:
            if (
                recovered
                or "composer did not become ready" not in str(exc)
                or not await self._cloudflare_challenge_present(context=context)
            ):
                raise
            await self._recover_cloudflare(context=context)
            await super().wait_for_composer(timeout=timeout, context=context)

    async def _create_driver_session(self) -> webdriver.Chrome:
        attempts = 2 if self.debugger_address else 1
        last_error: Exception | None = None
        async with self._call_lock:
            for attempt in range(attempts):
                try:
                    return await asyncio.to_thread(self._create_driver)
                except (WebDriverException, Urllib3HTTPError, TimeoutError, OSError) as exc:
                    last_error = exc
                    if attempt + 1 < attempts:
                        await asyncio.sleep(0.5)
                        continue
                    raise self._driver_runtime_error("create ChromeDriver session", exc) from exc
        raise RuntimeError("ChromeDriver session creation failed") from last_error

    async def _find_debugger_bootstrap_url(self, handles: list[str]) -> str:
        if not self.debugger_address:
            return ""

        def find() -> str:
            driver = self._require_driver()
            try:
                original = str(driver.current_window_handle)
            except WebDriverException:
                original = ""
            try:
                for raw_handle in handles:
                    handle = str(raw_handle)
                    try:
                        driver.switch_to.window(handle)
                        url = str(driver.current_url or "")
                    except WebDriverException:
                        continue
                    if self._is_chatgpt_url(url) and "/c/" in url:
                        return url
                return ""
            finally:
                if original:
                    try:
                        driver.switch_to.window(original)
                    except WebDriverException:
                        pass

        return str(
            await self._run_webdriver_call(
                "find authenticated Chromium bootstrap tab",
                find,
            )
            or ""
        )

    async def _navigate_debugger_new_chat(self, context: str) -> bool:
        if not self._bootstrap_url:
            return False
        await self.navigate(self._bootstrap_url, context=context)
        await self.wait_for_composer(
            timeout=max(5.0, self.auth_timeout_seconds),
            context=context,
        )
        clicked = await self.eval(
            "(()=>{const links=[...document.querySelectorAll("
            '\'a[href="/"],a[href="https://chatgpt.com/"]\''
            ")];const a=links.find(e=>/new chat/i.test("
            "(e.textContent||'')+' '+(e.getAttribute('aria-label')||'')"
            "));if(!a)return false;a.click();return true})()",
            context=context,
        )
        if not clicked:
            return False
        deadline = asyncio.get_running_loop().time() + 10.0
        while asyncio.get_running_loop().time() < deadline:
            path = str(await self.eval("location.pathname", context=context) or "")
            if path == "/":
                await self.wait_for_composer(timeout=5.0, context=context)
                return True
            await asyncio.sleep(0.1)
        return False

    async def connect(self) -> None:
        if self.is_connected:
            return
        if self.needs_browser_restart:
            raise RuntimeError("Chromium WebDriver session is poisoned; browser restart required")
        try:
            if self.debugger_address:
                await asyncio.to_thread(self._assert_debugger_available)
            await self._cleanup_stale_owned_contexts()
            self._driver = await self._create_driver_session()
            handles = await self._run_webdriver_call(
                "read Chromium window handles",
                lambda: list(self._require_driver().window_handles),
            )
            if not handles:
                raise RuntimeError("ChromeDriver created no browser window")
            if self.debugger_address:
                self._bootstrap_url = await self._find_debugger_bootstrap_url(
                    [str(handle) for handle in handles]
                )

                def create_owned_tab() -> str:
                    driver = self._require_driver()
                    driver.switch_to.new_window("tab")
                    return str(driver.current_window_handle)

                self.context = await self._run_webdriver_call(
                    "create Prompta Chromium tab",
                    create_owned_tab,
                )
                self._remember_owned_context(self.context)
            else:
                self.context = str(handles[0])
            self._network_subscribed = True
            if self.debugger_address and self._bootstrap_url:
                if not await self._navigate_debugger_new_chat(self.context):
                    raise RuntimeError(
                        "Prompta could not open a fresh ChatGPT conversation "
                        "from the authenticated browser session"
                    )
            else:
                await self.navigate("https://chatgpt.com/")
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

    def _require_driver(self) -> webdriver.Chrome:
        if self._driver is None:
            raise RuntimeError("ChromeDriver is not connected")
        return self._driver

    def _activate_context_sync(self, context: str | None) -> webdriver.Chrome:
        driver = self._require_driver()
        target = context or self.context
        if not target:
            raise RuntimeError("ChromeDriver has no browsing context")
        if driver.current_window_handle != target:
            driver.switch_to.window(target)
        # Explicit-context operations are used by background conversation
        # watchers. They must not steal the driver's logical default context
        # from an in-flight send (attachment uploads are especially exposed
        # because they poll readiness for longer than plain-text sends).
        if context is None:
            self.context = target
        return driver

    async def eval(
        self,
        expression: str,
        *,
        await_promise: bool = False,
        context: str | None = None,
    ) -> Any:
        def execute() -> Any:
            driver = self._activate_context_sync(context)
            try:
                if await_promise:
                    script = (
                        "const done=arguments[arguments.length-1];"
                        "Promise.resolve((" + expression + ")).then(v=>done({ok:true,value:v}),"
                        "e=>done({ok:false,error:String(e&&e.stack||e)}));"
                    )
                    payload = driver.execute_async_script(script)
                    if not isinstance(payload, dict) or not payload.get("ok"):
                        error = payload.get("error") if isinstance(payload, dict) else payload
                        raise RuntimeError(f"ChromeDriver async script failed: {error}")
                    return payload.get("value")
                return driver.execute_script("return (" + expression + ");")
            except JavascriptException as exc:
                raise RuntimeError(f"ChromeDriver script failed: {exc.msg}") from exc

        return await self._run_webdriver_call("execute Chromium script", execute)

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        def navigate_sync() -> None:
            driver = self._activate_context_sync(context)
            driver.get(url)

        await self._run_webdriver_call("navigate Chromium tab", navigate_sync)

    async def find_context_for_path(self, expected_path: str) -> str | None:
        target_path = urlsplit(expected_path).path.rstrip("/") or "/"

        def find() -> str | None:
            driver = self._require_driver()
            try:
                original = str(driver.current_window_handle)
            except WebDriverException:
                original = ""
            try:
                handles = list(driver.window_handles)
                for handle in handles:
                    try:
                        driver.switch_to.window(handle)
                        current_path = (
                            urlsplit(str(driver.current_url or "")).path.rstrip("/") or "/"
                        )
                    except (NoSuchWindowException, WebDriverException):
                        continue
                    if current_path == target_path:
                        return str(handle)
                return None
            finally:
                if original:
                    try:
                        driver.switch_to.window(original)
                    except (NoSuchWindowException, WebDriverException):
                        pass

        return await self._run_webdriver_call("find Chromium tab by route", find)

    async def new_tab(self, url: str = "https://chatgpt.com/") -> str:
        def create() -> str:
            driver = self._require_driver()
            driver.switch_to.new_window("tab")
            return str(driver.current_window_handle)

        context = await self._run_webdriver_call("create Chromium tab", create)
        self.context = context
        self._remember_owned_context(context)
        try:
            is_new_chat = url.rstrip("/") == "https://chatgpt.com"
            if self.debugger_address and self._bootstrap_url and is_new_chat:
                if not await self._navigate_debugger_new_chat(context):
                    raise RuntimeError(
                        "Prompta could not open a fresh ChatGPT conversation "
                        "from the authenticated browser session"
                    )
            else:
                await self.navigate(url, context=context)
                if self.debugger_address and self._is_chatgpt_url(url) and "/c/" in url:
                    self._bootstrap_url = url
        except BaseException:
            try:
                await self.close_context(context)
            except Exception:
                logger.debug("Could not close Prompta tab after navigation failure", exc_info=True)
            raise
        return context

    async def close_context(self, context: str) -> None:
        def close_sync() -> None:
            driver = self._require_driver()
            default_context = self.context
            try:
                driver.switch_to.window(context)
                driver.close()
            except NoSuchWindowException:
                return
            handles = list(driver.window_handles)
            if not handles:
                self.context = ""
                return
            if default_context and default_context != context and default_context in handles:
                driver.switch_to.window(default_context)
                return
            next_context = str(handles[-1])
            driver.switch_to.window(next_context)
            self.context = next_context

        await self._run_webdriver_call("close Chromium tab", close_sync)
        self._forget_owned_context(context)

    async def _perform_actions(self, context: str, actions: list[dict[str, Any]]) -> None:
        def perform() -> None:
            driver = self._activate_context_sync(context)
            try:
                driver.execute(Command.W3C_ACTIONS, {"actions": actions})
            finally:
                try:
                    driver.execute(Command.W3C_CLEAR_ACTIONS, {})
                except WebDriverException:
                    pass

        await self._run_webdriver_call("perform Chromium input actions", perform)

    async def click_send_button(self, timeout: float = 120.0) -> None:
        """Click ChatGPT's actual send control through ChromeDriver.

        Selenium's element click lets ChromeDriver resolve scrolling and hit-testing
        against the live element instead of relying on coordinates captured just
        before the click. ChatGPT can reflow the composer while enabling Send,
        which made the inherited coordinate click occasionally hit a stale point.
        """

        composer_selector = (
            '#prompt-textarea,div[role="textbox"].ProseMirror,'
            "textarea#prompt-textarea,textarea#mobile-composer-prompt"
        )
        selectors = (
            '[data-testid="send-button"]',
            'button[aria-label="Send prompt"]',
            'button[type="submit"]',
        )
        deadline = asyncio.get_running_loop().time() + max(1.0, timeout)

        def click_sync() -> bool:
            driver = self._activate_context_sync(None)
            scope: Any | None = None
            for composer in driver.find_elements(By.CSS_SELECTOR, composer_selector):
                try:
                    if not composer.is_displayed():
                        continue
                    try:
                        scope = composer.find_element(By.XPATH, "./ancestor::form[1]")
                    except NoSuchElementException:
                        scope = None
                    break
                except WebDriverException as exc:
                    if self._is_fatal_webdriver_error(exc):
                        raise
                    continue

            for selector in selectors:
                # The generic submit fallback is only safe inside the active
                # composer form. ChatGPT has other visible submit controls, and
                # clicking one of those looks like a successful Selenium click
                # while leaving the prompt untouched in the composer.
                if scope is None and selector == 'button[type="submit"]':
                    continue
                root = scope if scope is not None else driver
                try:
                    elements = root.find_elements(By.CSS_SELECTOR, selector)
                except WebDriverException as exc:
                    if self._is_fatal_webdriver_error(exc):
                        raise
                    continue
                for element in elements:
                    try:
                        if not element.is_displayed() or not element.is_enabled():
                            continue
                        if element.get_attribute("aria-disabled") == "true":
                            continue
                        element.click()
                        return True
                    except WebDriverException as exc:
                        if self._is_fatal_webdriver_error(exc):
                            raise
                        continue
            return False

        while asyncio.get_running_loop().time() < deadline:
            if await self._run_webdriver_call("click ChatGPT send button", click_sync):
                return
            await asyncio.sleep(0.2)
        raise RuntimeError("ChatGPT send button did not become enabled")

    async def click_stop(self, context: str, timeout: float = 5.0) -> bool:
        selectors = (
            '[data-testid="stop-button"]',
            'button[aria-label="Stop answering"]',
            'button[aria-label="Stop generating"]',
        )
        deadline = asyncio.get_running_loop().time() + max(0.2, timeout)

        def click_sync() -> bool:
            driver = self._activate_context_sync(context)
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                except WebDriverException as exc:
                    if self._is_fatal_webdriver_error(exc):
                        raise
                    continue
                for element in elements:
                    try:
                        if not element.is_displayed() or not element.is_enabled():
                            continue
                        if element.get_attribute("aria-disabled") == "true":
                            continue
                        element.click()
                        return True
                    except WebDriverException as exc:
                        if self._is_fatal_webdriver_error(exc):
                            raise
                        continue
            return False

        while asyncio.get_running_loop().time() < deadline:
            if await self._run_webdriver_call("click ChatGPT stop button", click_sync):
                return True
            await asyncio.sleep(0.1)
        return False

    async def attach_files(self, files: list[str]) -> None:
        paths = [str(Path(path).expanduser().resolve()) for path in files]
        if not paths:
            return
        for path in paths:
            if not Path(path).is_file():
                raise RuntimeError(f"Prompta attachment does not exist: {path}")

        async def locate_and_upload() -> bool:
            def upload_sync() -> bool:
                driver = self._activate_context_sync(None)
                try:
                    element = driver.find_element(By.CSS_SELECTOR, "input[type=file]")
                except NoSuchElementException:
                    return False
                element.send_keys("\n".join(paths))
                return True

            return bool(await self._run_webdriver_call("upload ChatGPT attachment", upload_sync))

        if not await locate_and_upload():
            opened = await self.eval(
                """(()=>{const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};const buttons=[...document.querySelectorAll('button')].filter(visible);const b=buttons.find(e=>/attach|upload|add (?:file|photo)/i.test((e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'')));if(!b)return false;b.click();return true})()"""
            )
            if opened:
                await asyncio.sleep(0.25)
            if not await locate_and_upload():
                raise RuntimeError("ChatGPT attachment input could not be found")

        file_names = [Path(path).name for path in paths]
        encoded_names = json.dumps(file_names)
        deadline = asyncio.get_running_loop().time() + 120.0
        stable_ready_polls = 0
        while asyncio.get_running_loop().time() < deadline:
            raw_state = await self.eval(
                f"""JSON.stringify((()=>{{const visible=e=>{{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';}};const names={encoded_names};const pageText=document.body?.innerText||'';const selected=[...document.querySelectorAll('input[type=file]')].flatMap(input=>[...(input.files||[])]).map(file=>file.name);const attached=names.every(name=>pageText.includes(name)||selected.includes(name));const progressBusy=[...document.querySelectorAll('[aria-busy="true"],progress,[role="progressbar"]')].some(visible);const labelledBusy=[...document.querySelectorAll('[data-testid*="upload" i],[aria-label*="upload" i],[title*="upload" i]')].some(e=>visible(e)&&/(?:uploading|processing|attaching|cancel upload)/i.test((e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'')));return {{attached,busy:progressBusy||labelledBusy}};}})())"""
            )
            try:
                state = json.loads(raw_state or "{}")
            except json.JSONDecodeError:
                state = {}
            if bool(state.get("attached")) and not bool(state.get("busy")):
                stable_ready_polls += 1
                if stable_ready_polls >= 3:
                    return
            else:
                stable_ready_polls = 0
            await asyncio.sleep(0.2)
        raise RuntimeError("ChatGPT attachment upload did not finish within 120s")

    def _close_debugger_targets(self, contexts: set[str]) -> set[str]:
        if not self.debugger_address or not contexts:
            return set(contexts)
        base_url = f"http://{self.debugger_address}"
        try:
            with urlopen(f"{base_url}/json/list", timeout=1.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return set(contexts)
        target_ids = (
            {
                str(item.get("id") or "")
                for item in payload
                if isinstance(item, dict) and item.get("id")
            }
            if isinstance(payload, list)
            else set()
        )
        unresolved: set[str] = set()
        for context in contexts & target_ids:
            try:
                request = Request(
                    f"{base_url}/json/close/{quote(context, safe='')}",
                    method="PUT",
                )
                with urlopen(request, timeout=1.0):
                    pass
            except Exception:
                unresolved.add(context)
        return unresolved

    async def close(self) -> None:
        driver = self._driver
        self._driver = None
        self.context = ""
        self._network_subscribed = False
        self._send_capture = None
        owned_contexts = set(self._owned_contexts)
        self._owned_contexts.clear()
        if driver is None:
            return

        if self.debugger_address:

            def detach() -> None:
                fallback_contexts: set[str] = set()
                try:
                    handles = set(driver.window_handles)
                except WebDriverException:
                    handles = set()
                    fallback_contexts.update(owned_contexts)
                for context in owned_contexts & handles:
                    try:
                        driver.switch_to.window(context)
                        driver.close()
                    except (NoSuchWindowException, WebDriverException):
                        fallback_contexts.add(context)
                self._close_debugger_targets(fallback_contexts)
                try:
                    driver.service.stop()
                except Exception:
                    pass
                try:
                    command_executor = driver.command_executor
                    if not isinstance(command_executor, str):
                        command_executor.close()
                except Exception:
                    pass

            await asyncio.to_thread(detach)
            return

        try:
            await asyncio.to_thread(driver.quit)
        except WebDriverException:
            pass
