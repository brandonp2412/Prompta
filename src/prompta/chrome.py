"""Chromium/ChromeDriver transport for Prompta.

The high-level ChatGPT DOM/snapshot logic lives in :mod:`prompta.bidi`.  This
driver deliberately subclasses that implementation and replaces only the
browser-transport primitives that differ between Firefox WebDriver BiDi and
Chromium WebDriver.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import (
    JavascriptException,
    NoSuchElementException,
    NoSuchWindowException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.command import Command

from .bidi import _BIDI_AUTH_TIMEOUT_SECONDS, FirefoxBiDiDriver


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
        self._driver: webdriver.Chrome | None = None
        self._owned_contexts: set[str] = set()

    @property
    def is_connected(self) -> bool:
        driver = self._driver
        if driver is None or not self.context:
            return False
        try:
            _ = driver.current_window_handle
        except WebDriverException:
            return False
        return True

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
        return webdriver.Chrome(service=service, options=options)

    async def connect(self) -> None:
        if self.is_connected:
            return
        if self.needs_browser_restart:
            raise RuntimeError("Chromium WebDriver session is poisoned; browser restart required")
        try:
            self._driver = await asyncio.to_thread(self._create_driver)
            handles = await asyncio.to_thread(lambda: list(self._require_driver().window_handles))
            if not handles:
                raise RuntimeError("ChromeDriver created no browser window")
            if self.debugger_address:
                def create_owned_tab() -> str:
                    driver = self._require_driver()
                    driver.switch_to.new_window("tab")
                    return str(driver.current_window_handle)

                self.context = await asyncio.to_thread(create_owned_tab)
                self._owned_contexts.add(self.context)
            else:
                self.context = str(handles[0])
            self._network_subscribed = True
            await self.navigate("https://chatgpt.com/")
            deadline = asyncio.get_running_loop().time() + self.auth_timeout_seconds
            last_error: Exception | None = None
            while asyncio.get_running_loop().time() < deadline:
                try:
                    if await self.login_required():
                        raise RuntimeError(
                            "Prompta Chromium profile is not logged into ChatGPT"
                        )
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
                        "Promise.resolve(("
                        + expression
                        + ")).then(v=>done({ok:true,value:v}),"
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

        return await asyncio.to_thread(execute)

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        def navigate_sync() -> None:
            driver = self._activate_context_sync(context)
            driver.get(url)

        await asyncio.to_thread(navigate_sync)

    async def new_tab(self, url: str = "https://chatgpt.com/") -> str:
        def create() -> str:
            driver = self._require_driver()
            driver.switch_to.new_window("tab")
            return str(driver.current_window_handle)

        context = await asyncio.to_thread(create)
        self.context = context
        if self.debugger_address:
            self._owned_contexts.add(context)
        await self.navigate(url, context=context)
        return context

    async def close_context(self, context: str) -> None:
        def close_sync() -> None:
            driver = self._require_driver()
            try:
                driver.switch_to.window(context)
                driver.close()
            except (NoSuchWindowException, WebDriverException):
                return
            handles = list(driver.window_handles)
            if handles:
                driver.switch_to.window(handles[-1])
                self.context = str(handles[-1])
            else:
                self.context = ""

        await asyncio.to_thread(close_sync)
        self._owned_contexts.discard(context)

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

        await asyncio.to_thread(perform)

    async def click_send_button(self, timeout: float = 120.0) -> None:
        """Click ChatGPT's actual send control through ChromeDriver.

        Selenium's element click lets ChromeDriver resolve scrolling and hit-testing
        against the live element instead of relying on coordinates captured just
        before the click. ChatGPT can reflow the composer while enabling Send,
        which made the inherited coordinate click occasionally hit a stale point.
        """

        selectors = (
            '[data-testid="send-button"]',
            'button[aria-label="Send prompt"]',
            'button[type="submit"]',
        )
        deadline = asyncio.get_running_loop().time() + max(1.0, timeout)

        def click_sync() -> bool:
            driver = self._activate_context_sync(None)
            for selector in selectors:
                for element in driver.find_elements(By.CSS_SELECTOR, selector):
                    try:
                        if not element.is_displayed() or not element.is_enabled():
                            continue
                        if element.get_attribute("aria-disabled") == "true":
                            continue
                        element.click()
                        return True
                    except WebDriverException:
                        # ChatGPT can replace the composer controls while React
                        # commits the editor state. Re-query on the next poll.
                        continue
            return False

        while asyncio.get_running_loop().time() < deadline:
            if await asyncio.to_thread(click_sync):
                return
            await asyncio.sleep(0.2)
        raise RuntimeError("ChatGPT send button did not become enabled")

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

            return await asyncio.to_thread(upload_sync)

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
                try:
                    handles = set(driver.window_handles)
                except WebDriverException:
                    handles = set()
                for context in owned_contexts & handles:
                    try:
                        driver.switch_to.window(context)
                        driver.close()
                    except (NoSuchWindowException, WebDriverException):
                        pass
                try:
                    driver.service.stop()
                except Exception:
                    pass
                try:
                    driver.command_executor.close()
                except Exception:
                    pass

            await asyncio.to_thread(detach)
            return

        try:
            await asyncio.to_thread(driver.quit)
        except WebDriverException:
            pass
