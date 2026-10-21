from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from .browser_driver import BrowserDriver
from .browser_script_loader import load_browser_script
from .config import ConnectorApproval
from .playwright_driver import PlaywrightDriver, _normalise_composer_text
from .rate_limit import RateLimitError, is_rate_limited_text
from .scheduler_runtime import SchedulerRuntime
from .send_outcome import SendOutcomeUnknownError
from .strict_types import int_value

logger = logging.getLogger(__name__)
_T = TypeVar("_T")

_DEFAULT_SEND_TIMEOUT_SECONDS = 20.0
_DELIVERY_HARD_TIMEOUT_SECONDS = 120.0
_CONNECTOR_APPROVAL_SECONDS = 300.0
_SEND_CONFIRM_POLL_SECONDS = 0.2
_DELIVERY_WINDOW_PREFIX = "prompta-delivery:"
_EFFORT_PREFERENCE_RETRY_SECONDS = 5 * 60.0
_MODEL_SELECTION_TIMEOUT_SECONDS = 20.0
_EFFORT_SELECTION_TIMEOUT_SECONDS = 12.0
_SEND_DISPATCH_TIMEOUT_SECONDS = 25.0
_SEND_CONFIRM_STATE_TIMEOUT_SECONDS = 8.0


def _is_conversation_path(path: str) -> bool:
    """Detect a permanent ChatGPT conversation route without reading its identifier."""

    return "/c/" in path


async def _timed_stage(
    stage: str,
    operation: Awaitable[_T],
    *,
    timeout: float,
) -> _T:
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(operation, timeout=max(0.1, timeout))
    except BaseException as exc:
        logger.warning(
            "Prompta delivery stage finished stage=%s duration_ms=%d outcome=failed error_type=%s",
            stage,
            round((time.monotonic() - started) * 1000),
            type(exc).__name__,
        )
        raise
    logger.info(
        "Prompta delivery stage finished stage=%s duration_ms=%d outcome=ok",
        stage,
        round((time.monotonic() - started) * 1000),
    )
    return result


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
        auth_timeout_seconds: float = 30.0,
        driver_factory: Callable[[], BrowserDriver] | None = None,
        send_timeout_seconds: float = _DEFAULT_SEND_TIMEOUT_SECONDS,
        delivery_hard_timeout_seconds: float = _DELIVERY_HARD_TIMEOUT_SECONDS,
        connector_approval: bool | None = None,
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
        self.auth_timeout_seconds = max(0.1, float(auth_timeout_seconds))
        self.driver_factory = driver_factory
        self.send_timeout_seconds = max(1.0, float(send_timeout_seconds))
        self.delivery_hard_timeout_seconds = max(0.01, float(delivery_hard_timeout_seconds))
        self.connector_approval = (
            ConnectorApproval.load().enabled if connector_approval is None else connector_approval
        )
        self._dispatch_started = False
        self.runtime = SchedulerRuntime(self.state_path, self.state_path)
        self._next_effort_preference_retry_at = 0.0

    def _new_driver(self) -> BrowserDriver:
        if self.driver_factory is not None:
            return self.driver_factory()
        return PlaywrightDriver(
            profile=self.profile,
            chrome_path=self.chrome_path,
            headless=True,
            auth_timeout_seconds=self.auth_timeout_seconds,
            debugger_address=self.debugger_address,
            ownership_prefix=_DELIVERY_WINDOW_PREFIX,
        )

    def _global_cooldown_remaining(self) -> float:
        return self.runtime.global_backoff_remaining()

    def _record_send_attempt(self) -> None:
        self.runtime.update_scheduler_state({"last_attempt_at": time.time()})

    async def _ensure_high_effort(self, driver: BrowserDriver) -> None:
        await _timed_stage("chat_surface_ready", driver.ensure_chat_surface(), timeout=12.0)
        now = asyncio.get_running_loop().time()
        if now < self._next_effort_preference_retry_at:
            return
        stage = "effort_selection"
        try:
            power = await _timed_stage(
                stage,
                driver.set_effort_power_position(3),
                timeout=_EFFORT_SELECTION_TIMEOUT_SECONDS,
            )
            if str(power.get("text") or "").strip().casefold() != "high":
                raise RuntimeError("ChatGPT High effort verification failed")
            if "upgrade required" in str(power.get("description") or "").casefold():
                raise RuntimeError("ChatGPT High effort unexpectedly requires an upgrade")
            await _timed_stage(
                "effort_menu_dismiss", driver.dismiss_transient_controls(), timeout=4.0
            )
            stage = "model_selection"
            await _timed_stage(
                stage,
                driver.select_effort_model("GPT-6"),
                timeout=_MODEL_SELECTION_TIMEOUT_SECONDS,
            )
        except (RuntimeError, TimeoutError) as exc:
            if driver.needs_browser_restart:
                raise
            self._next_effort_preference_retry_at = now + _EFFORT_PREFERENCE_RETRY_SECONDS
            logger.warning(
                "Prompta preferred model/effort stage failed stage=%s error_type=%s; "
                "continuing with current Chat settings and retrying later",
                stage,
                type(exc).__name__,
            )
            await _timed_stage(
                "transient_controls_dismiss",
                driver.dismiss_transient_controls(),
                timeout=4.0,
            )
            return
        self._next_effort_preference_retry_at = 0.0
        await _timed_stage(
            "transient_controls_dismiss",
            driver.dismiss_transient_controls(),
            timeout=4.0,
        )
        logger.info("Prompta set and verified preferred model and High effort")

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

        self._dispatch_started = False
        try:
            if self.connector_approval:
                finished = threading.Event()
                errors: list[BaseException] = []

                def deliver() -> None:
                    try:
                        asyncio.run(self._send_browser(message, accepted=finished))
                    except BaseException as exc:
                        errors.append(exc)
                    finally:
                        finished.set()

                threading.Thread(target=deliver, name="prompta-connector-approval", daemon=True).start()
                finished.wait()
                if errors:
                    raise errors[0]
            else:
                asyncio.run(self._send_browser(message))
        except TimeoutError as exc:
            if self._dispatch_started:
                raise SendOutcomeUnknownError(
                    "Prompta delivery deadline expired during or after dispatch; send acceptance is unknown",
                    stage="delivery_timeout",
                ) from exc
            raise DeliveryBackendUnavailableError(
                "Prompta delivery deadline expired before dispatch"
            ) from exc
        except RateLimitError as exc:
            delay = self.runtime.record_global_rate_limit(exc)
            raise RateLimitError(
                str(exc),
                retry_after=max(1, math.ceil(delay)),
            ) from exc

    async def _handle_connector_approvals(self, driver: BrowserDriver) -> None:
        deadline = asyncio.get_running_loop().time() + _CONNECTOR_APPROVAL_SECONDS
        while (remaining := deadline - asyncio.get_running_loop().time()) > 0:
            try:
                approved = await asyncio.wait_for(
                    driver.eval(load_browser_script("approve_connector.js")),
                    timeout=min(5.0, remaining),
                )
                if approved is True:
                    logger.info("Prompta selected Always allow for a connector permission")
            except Exception as exc:
                logger.info("Connector permission check unavailable error_type=%s", type(exc).__name__)
            await asyncio.sleep(min(1.0, max(0.0, deadline - asyncio.get_running_loop().time())))

    async def _send_browser(
        self, message: str, *, accepted: threading.Event | None = None
    ) -> None:
        driver = self._new_driver()
        context = ""
        capture: dict[str, object] | None = None
        send_attempted = False

        async def dispatch() -> None:
            nonlocal context, capture, send_attempted
            try:
                if not driver.is_connected:
                    await _timed_stage("cdp_connect", driver.connect(), timeout=45.0)
                context = await _timed_stage(
                    "fresh_tab_navigation", driver.new_tab(), timeout=40.0
                )
                await _timed_stage(
                    "composer_readiness", driver.wait_for_composer(), timeout=25.0
                )
                initial_path = str(
                    await _timed_stage(
                        "fresh_chat_route_check",
                        driver.eval(load_browser_script("location_pathname.js")),
                        timeout=5.0,
                    )
                    or ""
                )
                if _is_conversation_path(initial_path):
                    raise RuntimeError(
                        "ChatGPT fresh-chat navigation landed on an existing conversation"
                    )

                await self._ensure_high_effort(driver)

                baseline = await _timed_stage(
                    "composer_baseline", driver.dom_state(), timeout=15.0
                )
                baseline_path = str(
                    await _timed_stage(
                        "baseline_route_check",
                        driver.eval(load_browser_script("location_pathname.js")),
                        timeout=5.0,
                    )
                    or ""
                )
                if _is_conversation_path(baseline_path):
                    raise RuntimeError(
                        "ChatGPT fresh-chat navigation changed to an existing conversation"
                    )
                stale_text = _normalise_composer_text(str(baseline.get("composer_text") or ""))
                if stale_text:
                    logger.warning("Prompta found stale text in a fresh-chat composer; clearing it")
                    await _timed_stage(
                        "stale_draft_clear", driver.clear_composer(), timeout=10.0
                    )
                    baseline = await _timed_stage(
                        "stale_draft_verify_clear", driver.dom_state(), timeout=10.0
                    )
                    if _normalise_composer_text(str(baseline.get("composer_text") or "")):
                        raise RuntimeError("ChatGPT stale new-chat composer could not be cleared")

                rate_limit_text = str(baseline.get("rate_limit_text") or "")
                if is_rate_limited_text(rate_limit_text):
                    raise RateLimitError.from_text(rate_limit_text)
                baseline_send_in_progress = bool(baseline.get("send_in_progress"))

                capture = driver.arm_send_capture()
                await _timed_stage("prompt_insertion", driver.type_message(message), timeout=30.0)

                typed = await _timed_stage(
                    "prompt_verification", driver.dom_state(), timeout=15.0
                )
                if _normalise_composer_text(str(typed.get("composer_text") or "")) != _normalise_composer_text(
                    message
                ):
                    raise RuntimeError("ChatGPT composer did not contain the configured prompt")

                predispatch_path = str(
                    await _timed_stage(
                        "predispatch_route_check",
                        driver.eval(load_browser_script("location_pathname.js")),
                        timeout=5.0,
                    )
                    or ""
                )
                if _is_conversation_path(predispatch_path):
                    raise RuntimeError(
                        "ChatGPT fresh-chat navigation changed to an existing conversation before dispatch"
                    )

                dispatch_error: SendOutcomeUnknownError | None = None
                try:
                    # A timeout during the send control itself is ambiguous.
                    # Never automatically retry unless dispatch was never entered.
                    self._dispatch_started = True
                    send_attempted = True
                    self._record_send_attempt()
                    await _timed_stage(
                        "send_dispatch",
                        driver.click_send(message),
                        timeout=_SEND_DISPATCH_TIMEOUT_SECONDS,
                    )
                except SendOutcomeUnknownError as exc:
                    dispatch_error = exc
                    logger.warning(
                        "Prompta send outcome became ambiguous during dispatch; "
                        "checking only whether the prompt was accepted"
                    )
                except TimeoutError as exc:
                    dispatch_error = SendOutcomeUnknownError(
                        "Prompta send dispatch exceeded its bound; acceptance is unknown",
                        stage="send_dispatch",
                    )
                    logger.warning(
                        "Prompta send dispatch timed out; automatic resend disabled"
                    )
                    if exc.__cause__ is not None:
                        logger.debug(
                            "Prompta send dispatch timeout cause type=%s",
                            type(exc.__cause__).__name__,
                        )

                last_state: dict[str, object] = {}
                last_path = baseline_path
                last_transport_confirmed = False
                deadline = asyncio.get_running_loop().time() + self.send_timeout_seconds

                while asyncio.get_running_loop().time() < deadline:
                    status = int_value((capture or {}).get("status"))
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
                            "prompta send transport failed after dispatch",
                            stage="send_transport",
                        )

                    transport_confirmed = (
                        capture is not None and driver.captured_send_response(capture) is not None
                    )
                    last_transport_confirmed = transport_confirmed
                    if transport_confirmed:
                        logger.info(
                            "Prompta dispatched fresh-chat prompt "
                            "transport_confirmed=true route_confirmed=false "
                            "generation_confirmed=false"
                        )
                        return

                    path = last_path
                    try:
                        # A transient CDP failure in one probe must not turn a
                        # still-running, one-shot confirmation window into an
                        # immediate unknown result. Check the independent UI
                        # signal and keep polling for transport/route recovery.
                        path = str(
                            await _timed_stage(
                                "send_confirmation_route",
                                driver.eval(load_browser_script("location_pathname.js")),
                                timeout=5.0,
                            )
                            or ""
                        )
                        if _is_conversation_path(path) and path != baseline_path:
                            logger.info(
                                "Prompta dispatched fresh-chat prompt "
                                "transport_confirmed=false route_confirmed=true "
                                "generation_confirmed=false"
                            )
                            return
                    except Exception as exc:
                        logger.info(
                            "Prompta send confirmation probe unavailable probe=route error_type=%s",
                            type(exc).__name__,
                        )

                    try:
                        state = await _timed_stage(
                            "send_confirmation_state",
                            driver.send_confirmation_state(),
                            timeout=_SEND_CONFIRM_STATE_TIMEOUT_SECONDS,
                        )
                    except Exception as exc:
                        # Transport callbacks remain live while browser probes
                        # time out; re-check on the next bounded poll instead of
                        # classifying one transient probe failure as terminal.
                        status = int_value((capture or {}).get("status"))
                        if status == 429:
                            raise RateLimitError("prompta send rate limited") from exc
                        if status >= 500:
                            raise SendOutcomeUnknownError(
                                f"prompta send returned HTTP {status} after dispatch",
                                stage="send_response",
                            ) from exc
                        if status >= 400:
                            raise SendNotAcceptedError(
                                f"prompta send failed with HTTP {status}"
                            ) from exc
                        transport_confirmed = (
                            capture is not None
                            and driver.captured_send_response(capture) is not None
                        )
                        if transport_confirmed:
                            logger.info(
                                "Prompta dispatched fresh-chat prompt "
                                "transport_confirmed=true route_confirmed=false "
                                "generation_confirmed=false after UI confirmation timeout"
                            )
                            return
                        logger.info(
                            "Prompta send confirmation probe unavailable probe=state error_type=%s",
                            type(exc).__name__,
                        )
                        await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)
                        continue

                    last_state = state
                    if path:
                        last_path = path

                    rate_limit_text = str(state.get("rate_limit_text") or "")
                    if is_rate_limited_text(rate_limit_text):
                        raise RateLimitError.from_text(rate_limit_text)

                    route_confirmed = _is_conversation_path(path) and path != baseline_path
                    composer_now = _normalise_composer_text(
                        str(state.get("composer_text") or "")
                    )
                    generation_confirmed = (
                        not baseline_send_in_progress
                        and bool(state.get("send_in_progress"))
                        and not composer_now
                    )

                    if route_confirmed or generation_confirmed:
                        logger.info(
                            "Prompta dispatched fresh-chat prompt transport_confirmed=false "
                            "route_confirmed=%s generation_confirmed=%s",
                            route_confirmed,
                            generation_confirmed,
                        )
                        return

                    await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)

                final_composer = _normalise_composer_text(str(last_state.get("composer_text") or ""))
                if (
                    dispatch_error is None
                    and final_composer == _normalise_composer_text(message)
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
                    + f"conversation_route={_is_conversation_path(last_path)})"
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
        try:
            await asyncio.wait_for(dispatch(), timeout=self.delivery_hard_timeout_seconds)
            if capture is not None:
                driver.clear_send_capture(capture)
                capture = None
            if accepted is not None:
                accepted.set()
            if self.connector_approval:
                await self._handle_connector_approvals(driver)
        finally:
            if capture is not None:
                driver.clear_send_capture(capture)
            if context:
                try:
                    await _timed_stage(
                        "owned_tab_cleanup", driver.close_context(context), timeout=5.0
                    )
                except Exception as exc:
                    logger.warning(
                        "Prompta owned-tab cleanup failed error_type=%s", type(exc).__name__
                    )
            try:
                await _timed_stage("browser_disconnect", driver.close(), timeout=5.0)
            except Exception as exc:
                logger.warning(
                    "Prompta browser disconnect failed error_type=%s", type(exc).__name__
                )
