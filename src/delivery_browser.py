from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol, TypeVar, runtime_checkable

from .browser_driver import BrowserDriver
from .browser_ownership import MAX_OWNED_TAB_AGE_SECONDS
from .browser_script_loader import load_browser_script
from .config import ConnectorApproval
from .connector_approval_supervisor import supervise_connector_approvals
from .display_blocks_store import (
    deserialize_display_blocks,
    display_blocks_text,
    merge_display_blocks,
)
from .image_store import ImageStore, image_refs
from .patchright_driver import PatchrightDriver, _expected_composer_text, _normalise_composer_text
from .rate_limit import (
    DEFAULT_RETRY_AFTER,
    RateLimitError,
    captured_retry_after,
    is_rate_limited_text,
)
from .response_capture import CaptureResult, conversation_id_from_path, has_new_capture_activity
from .response_store import ResponseStore
from .scheduler_runtime import SchedulerRuntime
from .send_outcome import SendOutcomeUnknownError
from .strict_types import int_value

logger = logging.getLogger(__name__)
_T = TypeVar("_T")

_DEFAULT_SEND_TIMEOUT_SECONDS = 20.0
_DELIVERY_HARD_TIMEOUT_SECONDS = 120.0
_CONNECTOR_APPROVAL_SECONDS = float(MAX_OWNED_TAB_AGE_SECONDS)
_SEND_CONFIRM_POLL_SECONDS = 0.2
_DELIVERY_WINDOW_PREFIX = "prompta-delivery:"
_EFFORT_PREFERENCE_RETRY_SECONDS = 5 * 60.0
_MODEL_SELECTION_TIMEOUT_SECONDS = 20.0
_EFFORT_SELECTION_TIMEOUT_SECONDS = 12.0
_SEND_DISPATCH_TIMEOUT_SECONDS = 25.0
_SEND_CONFIRM_STATE_TIMEOUT_SECONDS = 8.0
_PASSIVE_RECOVERY_PROBE_SECONDS = 45.0
_EMPTY_REASONING_GRACE_SECONDS = 60.0
# Allow bounded pinning and receipt persistence after the dispatch deadline.
_HANDOFF_GRACE_SECONDS = 60.0


def _retain_dom_progress(saved: str, update: CaptureResult) -> tuple[str, CaptureResult]:
    """Keep visible commentary through DOM collapse, even between SQLite writes."""
    if update.source != "dom" or not update.display_blocks:
        return saved, update
    merged = merge_display_blocks(saved, update.display_blocks)
    text = max((update.text, display_blocks_text(merged)), key=len)
    return merged, replace(
        update, text=text, display_blocks=tuple(deserialize_display_blocks(merged)),
    )


def _is_conversation_path(path: str) -> bool:
    """Block dispatch into any chat-like route, including local optimistic drafts."""

    return "/c/" in path


def _is_provisional_conversation_path(path: str) -> bool:
    """A ChatGPT local-chatgpt route is not server acceptance."""
    route = path.lower()
    return "/c/local-chatgpt:" in route or "/c/local-chatgpt%3a" in route


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
    # The 200ms send-confirmation poll is expected to repeat. Keep failures
    # visible while avoiding dozens of duplicate INFO lines per accepted send.
    level = (logging.DEBUG if stage in ("send_confirmation_route", "send_confirmation_state")
             else logging.INFO)
    logger.log(
        level,
        "Prompta delivery stage finished stage=%s duration_ms=%d outcome=ok",
        stage,
        round((time.monotonic() - started) * 1000),
    )
    return result


class PassiveCaptureDriver(Protocol):
    @property
    def is_connected(self) -> bool: ...
    async def eval(self, expression: str, /) -> object: ...
    async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None: ...
    def captured_assistant_response(
        self, capture: dict[str, object], /
    ) -> CaptureResult | None: ...
    async def observed_assistant_response(self) -> CaptureResult: ...


@runtime_checkable
class TrustedApprovalDriver(Protocol):
    async def click_stuck_connector_approval(self) -> object: ...


@runtime_checkable
class FreshApprovalDriver(Protocol):
    async def retry_connector_approval_from_owned_tab(self) -> object: ...


@runtime_checkable
class VerifiedActivityDriver(Protocol):
    def record_verified_activity(self) -> bool: ...


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
        self.runtime = SchedulerRuntime(self.state_path, self.state_path)
        self._next_effort_preference_retry_at = 0.0
        self.results = ResponseStore(state_dir / "chat-results.sqlite3")
        self.images = ImageStore(state_dir)

    def _new_driver(self) -> BrowserDriver:
        if self.driver_factory is not None:
            return self.driver_factory()
        return PatchrightDriver(
            profile=self.profile,
            chrome_path=self.chrome_path,
            headless=True,
            auth_timeout_seconds=self.auth_timeout_seconds,
            debugger_address=self.debugger_address,
            ownership_prefix=_DELIVERY_WINDOW_PREFIX,
        )

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

    def __call__(
        self,
        message: str,
        *,
        pin_chat: bool = False,
        send_id: str = "",
        job_name: str = "",
        images: object = (),
    ) -> None:
        if not message.strip():
            raise ValueError("prompta prompt is empty")

        image_paths = tuple(self.images.path(ref) for ref in image_refs(images))
        dispatch_started = threading.Event()
        if send_id:
            self.results.ensure_queued(send_id, message, job_name)
            handshake = threading.Event()
            confirmed = threading.Event()
            errors: list[BaseException] = []

            def dispatch_and_capture() -> None:
                try:
                    asyncio.run(
                        self._send_browser(
                            message,
                            accepted=handshake,
                            confirmed=confirmed,
                            pin_chat=pin_chat,
                            send_id=send_id,
                            images=image_paths,
                            dispatch_started=dispatch_started,
                        )
                    )
                except BaseException as exc:
                    if not confirmed.is_set():
                        errors.append(exc)
                    else:
                        logger.warning(
                            "Background capture interrupted error_type=%s", type(exc).__name__
                        )
                finally:
                    handshake.set()

            try:
                threading.Thread(
                    target=dispatch_and_capture, name="prompta-passive-capture", daemon=True
                ).start()
            except RuntimeError as exc:
                raise DeliveryBackendUnavailableError("Passive capture thread unavailable") from exc
            received = handshake.wait(
                timeout=self.delivery_hard_timeout_seconds + _HANDOFF_GRACE_SECONDS
            )
            if confirmed.is_set():
                return
            if not received:
                # The background thread may still be inside a browser operation.
                # Never launch a second fresh chat while its outcome is unresolved.
                raise SendOutcomeUnknownError(
                    "Prompta background dispatch did not return a durable receipt in time",
                    stage="delivery_handoff",
                )
            if errors:
                exc = errors[0]
                if isinstance(exc, TimeoutError):
                    if dispatch_started.is_set():
                        raise SendOutcomeUnknownError(
                            "Prompta delivery deadline expired after dispatch",
                            stage="delivery_timeout",
                        ) from exc
                    raise DeliveryBackendUnavailableError(
                        "Prompta delivery deadline expired before dispatch"
                    ) from exc
                if dispatch_started.is_set() and not isinstance(
                    exc, (RateLimitError, SendNotAcceptedError, SendOutcomeUnknownError)
                ):
                    raise SendOutcomeUnknownError(
                        "Prompta background dispatch failed after send was attempted",
                        stage="post_dispatch",
                    ) from exc
                raise exc
            if dispatch_started.is_set():
                raise SendOutcomeUnknownError(
                    "Background delivery ended after dispatch without a receipt",
                    stage="delivery_handoff",
                )
            raise DeliveryBackendUnavailableError(
                "Background delivery ended before dispatch without a receipt"
            )
        try:
            if self.connector_approval:
                finished = threading.Event()
                errors: list[BaseException] = []

                def deliver() -> None:
                    try:
                        asyncio.run(
                            self._send_browser(
                                message,
                                accepted=finished,
                                pin_chat=pin_chat,
                                images=image_paths,
                                dispatch_started=dispatch_started,
                            )
                        )
                    except BaseException as exc:
                        errors.append(exc)
                    finally:
                        finished.set()

                threading.Thread(
                    target=deliver, name="prompta-connector-approval", daemon=True
                ).start()
                received = finished.wait(
                    timeout=self.delivery_hard_timeout_seconds + _HANDOFF_GRACE_SECONDS
                )
                if not received:
                    # A stuck browser operation must not hold a worker forever.
                    # Once the Send control was invoked its result is ambiguous.
                    if dispatch_started.is_set():
                        raise SendOutcomeUnknownError(
                            "Connector approval delivery did not return a receipt after dispatch",
                            stage="delivery_handoff",
                        )
                    raise DeliveryBackendUnavailableError(
                        "Connector approval delivery stalled before dispatch"
                    )
                if errors:
                    exc = errors[0]
                    if dispatch_started.is_set() and not isinstance(
                        exc, (RateLimitError, SendNotAcceptedError, SendOutcomeUnknownError)
                    ):
                        raise SendOutcomeUnknownError(
                            "Connector approval delivery failed after dispatch",
                            stage="post_dispatch",
                        ) from exc
                    raise exc
            else:
                asyncio.run(
                    self._send_browser(
                        message,
                        pin_chat=pin_chat,
                        images=image_paths,
                        dispatch_started=dispatch_started,
                    )
                )
        except TimeoutError as exc:
            if dispatch_started.is_set():
                raise SendOutcomeUnknownError(
                    "Prompta delivery deadline expired during or after dispatch; send acceptance is unknown",
                    stage="delivery_timeout",
                ) from exc
            raise DeliveryBackendUnavailableError(
                "Prompta delivery deadline expired before dispatch"
            ) from exc

    async def _pin_accepted_chat(self, driver: BrowserDriver) -> None:
        """Best-effort pin after a durable send receipt, never before it."""
        for attempt in range(2):
            try:
                await _timed_stage("once_chat_pin", driver.pin_current_chat(), timeout=25.0)
                return
            except Exception as exc:
                # Pinning is optional and must not downgrade an accepted send.
                logger.log(
                    logging.ERROR if attempt else logging.WARNING,
                    "Accepted Once job chat could not be pinned attempt=%d error_type=%s",
                    attempt + 1,
                    type(exc).__name__,
                )
                if attempt == 0:
                    await asyncio.sleep(0.5)

    async def _handle_connector_approvals(
        self, driver: PassiveCaptureDriver, *, deadline: float | None = None
    ) -> None:
        await supervise_connector_approvals(
            driver.eval,
            deadline=deadline or asyncio.get_running_loop().time() + _CONNECTOR_APPROVAL_SECONDS,
            source="live",
            poll_interval_seconds=0.2,
            active=lambda: driver.is_connected,
            trusted_retry=(
                driver.click_stuck_connector_approval
                if isinstance(driver, TrustedApprovalDriver) else None
            ),
            fresh_retry=(
                driver.retry_connector_approval_from_owned_tab
                if isinstance(driver, FreshApprovalDriver) else None
            ),
        )

    async def _capture_until_complete(
        self,
        driver: PassiveCaptureDriver,
        capture: dict[str, object],
        send_id: str,
        owner: str,
        *,
        deadline: float,
    ) -> None:
        """Use SSE completion and mutation notifications from this tab; never fetch."""
        approval_task: asyncio.Task[None] | None = None
        if self.connector_approval:
            approval_task = asyncio.create_task(
                self._handle_connector_approvals(driver, deadline=deadline)
            )
        last_saved_at = 0.0
        pending: CaptureResult | None = None
        seen_message = ""
        seen_observer = ""
        last_verified_text = ""
        last_verified_tools: tuple[dict[str, object], ...] = ()
        last_verified_blocks: tuple[dict[str, str], ...] = ()
        retained_blocks = "[]"
        final_status: str = "interrupted"
        next_recovery_probe = (
            asyncio.get_running_loop().time() + _PASSIVE_RECOVERY_PROBE_SECONDS
        )
        dom_completed_at: float | None = None
        empty_reasoning_since: float | None = None
        seen_tool_calls: tuple[dict[str, object], ...] = ()
        seen_sse_blocks: tuple[dict[str, str], ...] = ()
        if capture.get("sse_stream"):
            # The stream may start before the passive observer's first wait.
            self.results.mark_generating(send_id, owner)
        try:
            while (remaining := deadline - asyncio.get_running_loop().time()) > 0:
                current = self.results.get(send_id)
                if current is not None and current["status"] == "stopped":
                    break
                if not driver.is_connected:
                    break
                # Waiting is local: queue entries are emitted by the existing
                # POST or semantic MutationObserver, not by reading ChatGPT.
                try:
                    update = await driver.wait_capture_update(timeout=min(0.3 if dom_completed_at is not None else 5.0, remaining))
                except Exception as exc:
                    # A transient observer failure is not proof that the
                    # already-accepted response has disappeared.
                    logger.warning(
                        "Passive capture observer will retry error_type=%s",
                        type(exc).__name__,
                    )
                    await asyncio.sleep(
                        min(1.0, max(0.0, deadline - asyncio.get_running_loop().time()))
                    )
                    update = None
                now = asyncio.get_running_loop().time()
                if now >= next_recovery_probe and driver.is_connected:
                    next_recovery_probe = now + _PASSIVE_RECOVERY_PROBE_SECONDS
                    # A local owned-tab snapshot issues no account history read.
                    # It remains safe even while network history probes are 429-limited.
                    try:
                        snapshot = await asyncio.wait_for(
                            driver.observed_assistant_response(),
                            timeout=min(5.0, max(0.01, deadline - now)),
                        )
                        if snapshot.text and (
                            update is None
                            or snapshot.status == "complete"
                            or len(snapshot.text) > len(update.text)
                        ):
                            update = snapshot
                    except Exception as exc:
                        logger.info(
                            "Passive recovery snapshot unavailable error_type=%s",
                            type(exc).__name__,
                        )
                    # A conversation route can appear after the initial
                    # acceptance check. Bind only this live capture lease.
                    try:
                        path = await asyncio.wait_for(
                            driver.eval("location.pathname"),
                            timeout=min(
                                5.0,
                                max(0.01, deadline - asyncio.get_running_loop().time()),
                            ),
                        )
                        self.results.bind_conversation_route(send_id, owner, path)
                    except Exception as exc:
                        logger.info(
                            "Passive recovery route unavailable error_type=%s",
                            type(exc).__name__,
                        )
                if update is not None and update.stream_error:
                    logger.warning("ChatGPT owned response reported an explicit stream error")
                    break
                if (
                    update is not None
                    and update.source == "dom"
                    and update.status == "unknown"
                    and update.message_id is None
                ):
                    # A transient DOM re-render can hide the assistant node.
                    # Only a positively different branch identity (checked below)
                    # proves rollover; do not discard an accepted response here.
                    update = None
                # Multiple ChatGPT-owned continuation POSTs can follow connector
                # approvals. Do not splice their SSE data or close the tab;
                # keep observing the unique semantic DOM answer until finality/TTL.
                sse = (
                    None
                    if capture.get("ambiguous_request")
                    else driver.captured_assistant_response(capture)
                )
                if sse is not None and sse.stream_error:
                    logger.warning("ChatGPT owned SSE reported an explicit stream error")
                    break
                if (
                    sse is not None
                    and sse.ended_without_answer
                    and not sse.tool_calls
                    and not sse.display_blocks
                    and pending is None
                ):
                    if empty_reasoning_since is None:
                        empty_reasoning_since = now
                    elif now - empty_reasoning_since >= _EMPTY_REASONING_GRACE_SECONDS:
                        logger.warning(
                            "Prompta owned response stream ended with reasoning only; "
                            "no final answer after observation grace"
                        )
                        final_status = "unavailable"
                        break
                else:
                    empty_reasoning_since = None
                if int_value(capture.get("status")) == 429:
                    self.runtime.record_read_rate_limit(
                        RateLimitError(
                            "ChatGPT response rate limited",
                            retry_after=captured_retry_after(capture),
                        )
                    )
                    final_status = "unavailable"
                    break
                if capture.get("sse_stream"):
                    # An owned, successful event stream is live generation even
                    # when only thinking/tool activity is visible so far.
                    self.results.mark_generating(send_id, owner)
                if sse is not None and (
                    (sse.tool_calls and sse.tool_calls != seen_tool_calls)
                    or (sse.display_blocks and sse.display_blocks != seen_sse_blocks)
                ):
                    # The opening commentary can arrive before any tool or final
                    # assistant message. Persist ordered SSE blocks on each change.
                    if not self.results.write(send_id, owner, sse):
                        final_status = "unavailable"
                        break
                    seen_tool_calls = sse.tool_calls
                    seen_sse_blocks = sse.display_blocks
                if sse is not None and sse.status == "complete":
                    update = sse
                elif update is None and sse is not None and sse.text:
                    update = sse
                if update is not None and (update.text or update.tool_calls or update.display_blocks):
                    # Tools and final text can advance the backend message ID
                    # inside one modern assistant reply. The stable DOM reply
                    # unit and exact owned route prove it is not a new turn.
                    trusted_dom_continuation = bool(
                        update.source == "dom"
                        and update.observer_id
                        and (not seen_observer or seen_observer == update.observer_id)
                        and update.conversation_id
                        and current is not None
                        and current["conversation_id"] == update.conversation_id
                    )
                    if seen_message and update.message_id and seen_message != update.message_id:
                        if not trusted_dom_continuation:
                            logger.warning(
                                "Owned response branch changed without stable reply identity "
                                "send_id=%s", send_id,
                            )
                            final_status = "unavailable"
                            break
                        logger.info("Owned reply backend message advanced send_id=%s", send_id)
                    if seen_observer and update.observer_id and seen_observer != update.observer_id:
                        logger.warning("Owned response observer changed send_id=%s", send_id)
                        final_status = "unavailable"
                        break
                    if update.message_id:
                        seen_message = update.message_id
                    if update.observer_id:
                        seen_observer = update.observer_id
                    retained_blocks, update = _retain_dom_progress(retained_blocks, update)
                    if (
                        pending is None
                        or update.status == "complete"
                        or len(update.text) >= len(pending.text)
                    ):
                        pending = update
                if sse is not None and sse.tool_calls and pending is not None and not pending.tool_calls:
                    # A DOM answer may finish just before the observed POST stream.
                    pending = replace(pending, tool_calls=sse.tool_calls)
                # Only distinct, branch-bound ChatGPT updates extend the idle lease.
                # SSE progress includes reasoning/tool events without retaining their text.
                progress = has_new_capture_activity(
                    update,
                    previous_text=last_verified_text,
                    previous_tools=last_verified_tools,
                    previous_blocks=last_verified_blocks,
                )
                verified_branch = bool(update is not None and (
                    (update.source == "dom" and update.conversation_id
                     and update.message_id)
                    or (update.source == "sse" and capture.get("sse_stream")
                        and not capture.get("ambiguous_request"))
                ))
                if progress and verified_branch and isinstance(driver, VerifiedActivityDriver) and driver.record_verified_activity():
                    if update is not None:
                        if update.text:
                            last_verified_text = update.text
                        if update.tool_calls:
                            last_verified_tools = update.tool_calls
                        if update.display_blocks:
                            last_verified_blocks = update.display_blocks
                    refreshed = time.time() + MAX_OWNED_TAB_AGE_SECONDS
                    if self.results.renew_capture_deadline(send_id, owner, deadline=refreshed):
                        deadline = asyncio.get_running_loop().time() + MAX_OWNED_TAB_AGE_SECONDS
                now = asyncio.get_running_loop().time()
                if (pending is not None and pending.status == "complete"
                    and pending.source == "dom" and sse is None
                    and capture.get("response_started") and deadline - now > 2):
                    if dom_completed_at is None:
                        dom_completed_at = now
                    if now - dom_completed_at < 1.5:
                        continue
                if pending is not None and (
                    pending.status == "complete" or now - last_saved_at >= 5.0
                ):
                    # A changing backend parent is safe only within a
                    # conversation-bound DOM reply unit of this owned tab.
                    allow_dom_parent_update = bool(
                        pending.source == "dom"
                        and pending.observer_id
                        and pending.observer_id == seen_observer
                        and pending.conversation_id
                        and current is not None
                        and current["conversation_id"] == pending.conversation_id
                    )
                    if not self.results.write(
                        send_id, owner, pending,
                        allow_owned_dom_message_update=allow_dom_parent_update,
                    ):
                        final_status = "unavailable"
                        break
                    last_saved_at = now
                    if pending.status == "complete" and (pending.message_id or pending.observer_id):
                        # Same-tab completion is not proof that account history
                        # reads have recovered from ChatGPT's 429 cooldown.
                        return
                if 0 < deadline - now <= 2.0:
                    # At most one DOM fallback read, inside the hard tab TTL.
                    try:
                        snapshot = await asyncio.wait_for(
                            driver.observed_assistant_response(), timeout=deadline - now
                        )
                    except Exception as exc:
                        # The last permitted local observer read is best-effort.
                        # A timeout/disconnect must not discard unsaved partial text.
                        logger.info(
                            "Final passive capture probe unavailable error_type=%s",
                            type(exc).__name__,
                        )
                    else:
                        if snapshot.text and (
                            pending is None or len(snapshot.text) >= len(pending.text)
                        ):
                            pending = snapshot
                    break
            if pending is not None and pending.text:
                self.results.write(send_id, owner, pending)
        finally:
            self.results.finish(
                send_id, owner, "unavailable" if final_status == "unavailable" else "interrupted"
            )
            if approval_task is not None:
                approval_task.cancel()
                try:
                    await approval_task
                except asyncio.CancelledError:
                    pass

    async def _send_browser(
        self,
        message: str,
        *,
        accepted: threading.Event | None = None,
        confirmed: threading.Event | None = None,
        pin_chat: bool = False,
        send_id: str = "",
        images: tuple[Path, ...] = (),
        dispatch_started: threading.Event | None = None,
    ) -> None:
        driver = self._new_driver()
        context = ""
        capture: dict[str, object] | None = None
        send_attempted = False
        verified_observation: CaptureResult | None = None
        tab_opened_at = 0.0
        tab_deadline = 0.0
        capture_owner = f"{os.getpid()}:{threading.get_ident()}:{time.monotonic_ns()}"

        async def dispatch() -> None:
            nonlocal context, capture, send_attempted, tab_opened_at, tab_deadline, verified_observation
            try:
                if not driver.is_connected:
                    await _timed_stage("cdp_connect", driver.connect(), timeout=45.0)
                context = await _timed_stage("fresh_tab_navigation", driver.new_tab(), timeout=40.0)
                tab_opened_at = time.time()
                tab_deadline = asyncio.get_running_loop().time() + MAX_OWNED_TAB_AGE_SECONDS
                await _timed_stage("composer_readiness", driver.wait_for_composer(), timeout=25.0)
                initial_path = str(
                    await _timed_stage(
                        "fresh_chat_route_check",
                        driver.eval("location.pathname"),
                        timeout=5.0,
                    )
                    or ""
                )
                if _is_conversation_path(initial_path):
                    raise RuntimeError(
                        "ChatGPT fresh-chat navigation landed on an existing conversation"
                    )

                await self._ensure_high_effort(driver)

                baseline = await _timed_stage("composer_baseline", driver.dom_state(), timeout=15.0)
                baseline_path = str(
                    await _timed_stage(
                        "baseline_route_check",
                        driver.eval("location.pathname"),
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
                    await _timed_stage("stale_draft_clear", driver.clear_composer(), timeout=10.0)
                    baseline = await _timed_stage(
                        "stale_draft_verify_clear", driver.dom_state(), timeout=10.0
                    )
                    if _normalise_composer_text(str(baseline.get("composer_text") or "")):
                        raise RuntimeError("ChatGPT stale new-chat composer could not be cleared")

                rate_limit_text = str(baseline.get("rate_limit_text") or "")
                if is_rate_limited_text(rate_limit_text):
                    raise RateLimitError.from_text(rate_limit_text)
                baseline_send_in_progress = bool(baseline.get("send_in_progress"))

                if send_id:
                    try:
                        await _timed_stage(
                            "passive_capture_binding", driver.enable_passive_updates(), timeout=5.0
                        )
                    except Exception as exc:
                        logger.info(
                            "Passive capture binding unavailable error_type=%s", type(exc).__name__
                        )
                # Observe only this fresh owned tab, before submission. The
                # mutation observer reads the live DOM; it makes no requests.
                try:
                    await _timed_stage(
                        "passive_dom_observer_arm",
                        driver.eval(load_browser_script("passive_response_observer.js"), main_world=True),
                        timeout=5.0,
                    )
                except Exception as exc:
                    logger.info(
                        "Passive response observer unavailable error_type=%s",
                        type(exc).__name__,
                    )
                capture = driver.arm_send_capture()
                await _timed_stage("prompt_insertion", driver.type_message(message), timeout=30.0)
                if images:
                    await _timed_stage("image_upload", driver.attach_images(images), timeout=140.0)

                typed = await _timed_stage("prompt_verification", driver.dom_state(), timeout=15.0)
                if _normalise_composer_text(
                    str(typed.get("composer_text") or "")
                ) != _expected_composer_text(message):
                    raise RuntimeError("ChatGPT composer did not contain the configured prompt")

                predispatch_path = str(
                    await _timed_stage(
                        "predispatch_route_check",
                        driver.eval("location.pathname"),
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
                    if dispatch_started is not None:
                        dispatch_started.set()
                    send_attempted = True
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
                    logger.warning("Prompta send dispatch timed out; automatic resend disabled")
                    if exc.__cause__ is not None:
                        logger.debug(
                            "Prompta send dispatch timeout cause type=%s",
                            type(exc.__cause__).__name__,
                        )

                last_state: dict[str, object] = {}
                last_path = baseline_path
                last_transport_confirmed = False
                provisional_route_seen = False
                deadline = asyncio.get_running_loop().time() + self.send_timeout_seconds

                while asyncio.get_running_loop().time() < deadline:
                    status = int_value((capture or {}).get("status"))
                    if status == 429:
                        raise RateLimitError(
                            "prompta send rate limited",
                            retry_after=captured_retry_after(capture or {}) or DEFAULT_RETRY_AFTER,
                        )
                    # HTTP 5xx is ambiguous; observe only the original owned tab.
                    if 400 <= status < 500:
                        raise SendNotAcceptedError(f"prompta send failed with HTTP {status}")
                    if status < 500 and capture is not None and capture.get("fetch_error"):
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
                                driver.eval("location.pathname"),
                                timeout=5.0,
                            )
                            or ""
                        )
                        provisional_route_seen |= _is_provisional_conversation_path(path)
                        if _is_conversation_path(path) and path != baseline_path:
                            # The route can change before the conversation POST is
                            # acknowledged. Keep probing; navigation alone does not
                            # prove that ChatGPT accepted the prompt.
                            last_path = path
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
                            raise RateLimitError(
                                "prompta send rate limited",
                                retry_after=captured_retry_after(capture or {}) or DEFAULT_RETRY_AFTER,
                            ) from exc
                        if 400 <= status < 500:
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
                    if status < 500 and is_rate_limited_text(rate_limit_text):
                        raise RateLimitError.from_text(rate_limit_text)

                    # A local-chatgpt route is an optimistic draft, not a server ID.
                    route_confirmed = conversation_id_from_path(path) is not None
                    composer_now = _normalise_composer_text(str(state.get("composer_text") or ""))
                    if status >= 500 and capture is not None:
                        # An original-tab assistant mutation and exact route are
                        # positive evidence; a route or Stop button alone is not.
                        try:
                            observation = await driver.wait_capture_update(
                                timeout=min(1.0, max(0.01, deadline - asyncio.get_running_loop().time()))
                            )
                        except Exception as exc:
                            logger.info(
                                "Owned acceptance observation unavailable error_type=%s",
                                type(exc).__name__,
                            )
                            observation = None
                        if (
                            observation is not None and observation.source == "dom"
                            and observation.status in ("partial", "complete")
                            and observation.text and observation.observer_id and observation.message_id
                            and observation.conversation_id == conversation_id_from_path(path)
                            and not capture.get("ambiguous_request")
                        ):
                            verified_observation = observation
                            return
                    generation_confirmed = (
                        status < 500
                        and not baseline_send_in_progress
                        and bool(state.get("send_in_progress"))
                        and not composer_now
                        and (not provisional_route_seen or route_confirmed)
                    )

                    if generation_confirmed:
                        logger.info(
                            "Prompta dispatched fresh-chat prompt transport_confirmed=false "
                            "route_confirmed=%s generation_confirmed=true",
                            route_confirmed,
                        )
                        return

                    await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)

                # A POST acknowledgement may arrive during the last browser probe or
                # confirmation sleep. Re-read transport evidence before declaring a
                # retry-safe rejection; a late accepted POST must never be resent.
                final_status = int_value((capture or {}).get("status"))
                if final_status == 429:
                    raise RateLimitError(
                        "prompta send rate limited",
                        retry_after=captured_retry_after(capture or {}) or DEFAULT_RETRY_AFTER,
                    )
                if final_status >= 500:
                    # Keep non-sensitive evidence in the durable failure receipt.
                    # Neither a provisional route nor a 500 permits a blind resend.
                    persisted_route_seen = conversation_id_from_path(last_path) is not None
                    logger.warning(
                        "ChatGPT send confirmation failed status=%d "
                        "provisional_route_seen=%s persisted_route_seen=%s",
                        final_status, provisional_route_seen, persisted_route_seen,
                    )
                    raise SendOutcomeUnknownError(
                        f"prompta send returned HTTP {final_status} after dispatch "
                        f"(provisional_chat={provisional_route_seen}, "
                        f"persistent_chat={persisted_route_seen}); "
                        "acceptance unverified, no automatic resend",
                        stage="send_response",
                    )
                if final_status >= 400:
                    raise SendNotAcceptedError(f"prompta send failed with HTTP {final_status}")
                if capture is not None and capture.get("fetch_error"):
                    raise SendOutcomeUnknownError(
                        "prompta send transport failed after dispatch", stage="send_transport"
                    )
                if capture is not None and driver.captured_send_response(capture) is not None:
                    logger.info("Prompta dispatched fresh-chat prompt late_transport_confirmed=true")
                    return

                final_composer = _normalise_composer_text(
                    str(last_state.get("composer_text") or "")
                )
                if (
                    dispatch_error is None
                    and final_composer == _expected_composer_text(message)
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
            if not send_id and capture is not None:
                driver.clear_send_capture(capture)
                capture = None
            if not send_id and pin_chat:
                await self._pin_accepted_chat(driver)
            if send_id:
                # An accepted POST is verified tab activity; the idle clock
                # starts here, not at the earlier fresh-tab navigation.
                if isinstance(driver, VerifiedActivityDriver) and driver.record_verified_activity():
                    tab_opened_at = time.time()
                    tab_deadline = asyncio.get_running_loop().time() + MAX_OWNED_TAB_AGE_SECONDS
                receipt_ok = False
                try:
                    if verified_observation is not None:
                        receipt_ok = self.results.accept_observed(
                            send_id, capture_owner, verified_observation,
                            deadline=tab_opened_at + MAX_OWNED_TAB_AGE_SECONDS,
                        )
                    else:
                        receipt_ok = self.results.accept(
                            send_id, capture_owner,
                            deadline=tab_opened_at + MAX_OWNED_TAB_AGE_SECONDS,
                        )
                except Exception as exc:
                    logger.warning("Passive capture lease failed error_type=%s", type(exc).__name__)
                if verified_observation is not None and not receipt_ok:
                    raise SendOutcomeUnknownError(
                        "Accepted owned-tab evidence could not be persisted",
                        stage="receipt_persistence",
                    )
                if receipt_ok:
                    try:
                        path = await _timed_stage(
                            "capture_conversation_route",
                            driver.eval("location.pathname"),
                            timeout=5.0,
                        )
                        if self.results.bind_conversation_route(send_id, capture_owner, path):
                            logger.info(
                                "Prompta persisted verified fresh-chat conversation identity"
                            )
                    except Exception as exc:
                        logger.info(
                            "Fresh-chat route identity unavailable error_type=%s",
                            type(exc).__name__,
                        )
                # An accepted send is final even if local result persistence fails.
                if confirmed is not None:
                    confirmed.set()
                if accepted is not None:
                    accepted.set()
                # An optional sidebar pin may take tens of seconds. Receipt and
                # capture ownership must be durable before any such UI work.
                if pin_chat:
                    await self._pin_accepted_chat(driver)
                try:
                    if receipt_ok and capture is not None and (
                        verified_observation is None or verified_observation.status != "complete"
                    ):
                        await self._capture_until_complete(
                            driver, capture, send_id, capture_owner, deadline=tab_deadline
                        )
                    elif not receipt_ok:
                        self.results.unavailable(send_id)
                except Exception as exc:
                    logger.warning("Passive capture stopped error_type=%s", type(exc).__name__)
                    self.results.finish(send_id, capture_owner, "interrupted")
            else:
                if confirmed is not None:
                    confirmed.set()
                if accepted is not None:
                    accepted.set()
                if self.connector_approval:
                    await self._handle_connector_approvals(driver)
        finally:
            if capture is not None:
                driver.clear_send_capture(capture)
            if send_id and context:
                try:
                    await asyncio.wait_for(
                        driver.eval("(() => { window.__promptaPassiveResponseObserver?.stop?.(); return true; })()", main_world=True),
                        timeout=1.0,
                    )
                except Exception:
                    pass
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
