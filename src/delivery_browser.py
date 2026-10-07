from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections.abc import Callable
from pathlib import Path

from .browser_script_loader import load_browser_script
from .browser_session import BrowserDriver, BrowserSession
from .playwright_driver import PlaywrightDriver
from .rate_limit import RateLimitError, is_rate_limited_text
from .scheduler_runtime import SchedulerRuntime
from .send_outcome import SendOutcomeUnknownError
from .strict_types import int_value

logger = logging.getLogger(__name__)

_DEFAULT_SEND_TIMEOUT_SECONDS = 20.0
_SEND_CONFIRM_POLL_SECONDS = 0.2
_DELIVERY_WINDOW_PREFIX = "prompta-delivery:"


class DeliveryBackendUnavailableError(RuntimeError):
    """A pre-dispatch browser failure that is safe to retry."""


class SendNotAcceptedError(RuntimeError):
    """ChatGPT demonstrably did not accept a submitted prompt."""


class BrowserDeliverySender:
    """Send one scheduled prompt in a fresh ChatGPT tab, then discard the tab."""

    def __init__(
        self,
        state_path: Path,
        *,
        profile: Path | None = None,
        chrome_path: str = "/usr/bin/chromium",
        debugger_address: str | None = None,
        flaresolverr_url: str | None = None,
        auth_timeout_seconds: float = 30.0,
        driver_factory: Callable[[], BrowserDriver] | None = None,
        send_timeout_seconds: float = _DEFAULT_SEND_TIMEOUT_SECONDS,
    ) -> None:
        self.state_path = state_path.expanduser()
        state_dir = self.state_path.parent
        self.profile = (
            profile
            or Path(
                os.environ.get(
                    "PROMPTA_CHROME_PROFILE",
                    str(state_dir / "chrome-profile"),
                )
            )
        ).expanduser()
        self.chrome_path = chrome_path
        self.debugger_address = debugger_address
        self.flaresolverr_url = flaresolverr_url
        self.auth_timeout_seconds = max(0.1, float(auth_timeout_seconds))
        self.driver_factory = driver_factory
        self.send_timeout_seconds = max(1.0, float(send_timeout_seconds))
        self.runtime = SchedulerRuntime(self.state_path, self.state_path)

    def _new_driver(self) -> BrowserDriver:
        if self.driver_factory is not None:
            return self.driver_factory()
        return PlaywrightDriver(
            profile=self.profile,
            chrome_path=self.chrome_path,
            headless=True,
            auth_timeout_seconds=self.auth_timeout_seconds,
            debugger_address=self.debugger_address,
            flaresolverr_url=self.flaresolverr_url,
            ownership_prefix=_DELIVERY_WINDOW_PREFIX,
        )

    def _global_cooldown_remaining(self) -> float:
        return self.runtime.global_backoff_remaining()

    def _record_send_attempt(self) -> None:
        self.runtime.update_scheduler_state({"last_attempt_at": time.time()})

    @staticmethod
    def _normalise(text: str) -> str:
        return " ".join(text.split()).strip()

    def __call__(self, message: str) -> None:
        if not message.strip():
            raise ValueError("prompta prompt is empty")

        remaining = self._global_cooldown_remaining()
        if remaining > 0:
            raise RateLimitError(
                "ChatGPT account-wide rate limit backoff is active",
                retry_after=max(1, math.ceil(remaining)),
            )

        gap = self.runtime.send_gap_remaining(time.time())
        if gap > 0:
            raise DeliveryBackendUnavailableError(
                "Prompta global send gap is active for another "
                + f"{max(1, math.ceil(gap))} seconds"
            )

        try:
            asyncio.run(self._send_browser(message))
        except RateLimitError as exc:
            delay = self.runtime.record_global_rate_limit(exc)
            raise RateLimitError(
                str(exc),
                retry_after=max(1, math.ceil(delay)),
            ) from exc

    async def _send_browser(self, message: str) -> None:
        browser = BrowserSession("https://chatgpt.com", self._new_driver)
        driver: BrowserDriver | None = None
        context = ""
        capture: dict[str, object] | None = None
        probe_armed = False
        send_attempted = False

        try:
            try:
                driver = await browser.ensure_driver()
                context = await driver.new_tab()
                await driver.wait_for_composer()
                await driver.ensure_chat_surface()
                await browser.ensure_high_effort(driver)

                baseline = await driver.dom_state()
                baseline_path = str(
                    await driver.eval(load_browser_script("location_pathname.js")) or ""
                )
                stale_text = self._normalise(str(baseline.get("composer_text") or ""))
                if stale_text:
                    logger.warning("Prompta found stale text in a fresh-chat composer; clearing it")
                    await driver.clear_composer()
                    baseline = await driver.dom_state()
                    if self._normalise(str(baseline.get("composer_text") or "")):
                        raise RuntimeError("ChatGPT stale new-chat composer could not be cleared")

                rate_limit_text = str(baseline.get("rate_limit_text") or "")
                if is_rate_limited_text(rate_limit_text):
                    raise RateLimitError.from_text(rate_limit_text)

                await driver.arm_page_send_probe()
                probe_armed = True
                capture = driver.arm_send_capture()
                await driver.type_message(message)

                typed = await driver.dom_state()
                if self._normalise(str(typed.get("composer_text") or "")) != self._normalise(
                    message
                ):
                    raise RuntimeError("ChatGPT composer did not contain the configured prompt")

                dispatch_error: SendOutcomeUnknownError | None = None
                try:
                    await driver.click_send()
                except SendOutcomeUnknownError as exc:
                    self._record_send_attempt()
                    send_attempted = True
                    dispatch_error = exc
                    logger.warning(
                        "Prompta send outcome became ambiguous during dispatch; "
                        "checking only whether the prompt was accepted"
                    )
                else:
                    self._record_send_attempt()
                    send_attempted = True

                last_state: dict[str, object] = {}
                last_probe: dict[str, object] = {}
                last_path = baseline_path
                last_transport_confirmed = False
                deadline = asyncio.get_running_loop().time() + self.send_timeout_seconds

                while asyncio.get_running_loop().time() < deadline:
                    try:
                        state = await driver.dom_state()
                        probe = await driver.page_send_probe()
                        path = str(
                            await driver.eval(load_browser_script("location_pathname.js")) or ""
                        )
                    except Exception as exc:
                        raise SendOutcomeUnknownError(
                            "Prompta lost send confirmation after dispatch",
                            stage="send_confirmation",
                        ) from exc

                    last_state = state
                    last_probe = probe
                    last_path = path

                    rate_limit_text = str(state.get("rate_limit_text") or "")
                    if is_rate_limited_text(rate_limit_text):
                        raise RateLimitError.from_text(rate_limit_text)

                    status = int_value(probe.get("response_status") or (capture or {}).get("status"))
                    transport_confirmed = bool(probe.get("committed")) or (
                        capture is not None and driver.captured_send_response(capture) is not None
                    )
                    last_transport_confirmed = transport_confirmed

                    if status == 429:
                        raise RateLimitError("prompta send rate limited")
                    if status >= 500:
                        raise SendOutcomeUnknownError(
                            f"prompta send returned HTTP {status} after dispatch",
                            stage="send_response",
                        )
                    if status >= 400:
                        raise SendNotAcceptedError(f"prompta send failed with HTTP {status}")
                    if capture is not None and capture.get("fetch_error"):
                        raise SendOutcomeUnknownError(
                            "prompta send transport failed after dispatch: "
                            + str(capture["fetch_error"]),
                            stage="send_transport",
                        )

                    route_confirmed = path.startswith("/c/") and path != baseline_path

                    if transport_confirmed or route_confirmed:
                        logger.info(
                            "Prompta dispatched fresh-chat prompt transport_confirmed=%s "
                            "route_confirmed=%s",
                            transport_confirmed,
                            route_confirmed,
                        )
                        return

                    await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)

                final_composer = self._normalise(str(last_state.get("composer_text") or ""))
                if (
                    final_composer == self._normalise(message)
                    and not last_transport_confirmed
                    and last_path == baseline_path
                ):
                    raise SendNotAcceptedError(
                        "ChatGPT did not accept the prompt; it remained in the composer"
                    )

                detail = (
                    "prompta could not prove the fresh-chat prompt was accepted "
                    + f"(composer_empty={not bool(final_composer)}, "
                    + f"transport_confirmed={last_transport_confirmed}, "
                    + f"probe_status={int_value(last_probe.get('response_status'))}, "
                    + f"path={last_path or '/'})"
                )
                if dispatch_error is not None:
                    raise SendOutcomeUnknownError(
                        detail,
                        stage=dispatch_error.stage,
                    ) from dispatch_error
                raise SendOutcomeUnknownError(detail, stage="send_confirmation")
            except (RateLimitError, SendNotAcceptedError, SendOutcomeUnknownError):
                raise
            except Exception as exc:
                if not send_attempted:
                    raise DeliveryBackendUnavailableError(str(exc)) from exc
                raise SendOutcomeUnknownError(
                    "Prompta failed after dispatch and cannot prove send acceptance",
                    stage="post_dispatch",
                ) from exc
        finally:
            if driver is not None:
                if capture is not None:
                    driver.clear_send_capture(capture)
                if probe_armed:
                    try:
                        await driver.clear_page_send_probe()
                    except Exception:
                        logger.debug("Could not clear page send probe", exc_info=True)
                if context:
                    try:
                        await driver.close_context(context)
                    except Exception:
                        logger.debug("Could not discard Prompta fresh-chat tab", exc_info=True)
                await driver.close()
