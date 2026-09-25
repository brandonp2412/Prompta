from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from .browser_script_loader import load_browser_script
from .cache import ActiveConversation, ChatCache
from .control_server import ControlDeferredError
from .rate_limit import RateLimitError, is_rate_limited_text
from .send_outcome import SendOutcomeUnknownError

logger = logging.getLogger(__name__)

_SEND_CONFIRM_POLL_SECONDS = 0.2
_SYNC_OBSERVE_SECONDS = 15.0


class SendVerificationError(SendOutcomeUnknownError):
    pass


class SendNotAcceptedError(RuntimeError):
    pass


class ConversationActions:
    def __init__(
        self,
        cache: ChatCache,
        active: dict[str, ActiveConversation],
        send_timeout_seconds: float,
        ensure_driver: Callable[[], Any],
        ensure_high_effort: Callable[[Any], Any],
        ensure_route: Callable[..., Any],
        enrich_completed_tool_calls: Callable[..., Any],
        wait_for_cached_response: Callable[..., Any],
        unattended_mode: Callable[[], bool],
        before_send_attempt: Callable[[], None] | None = None,
    ) -> None:
        self.cache = cache
        self.active = active
        self.send_timeout_seconds = send_timeout_seconds
        self.ensure_driver = ensure_driver
        self.ensure_high_effort = ensure_high_effort
        self.ensure_route = ensure_route
        self.enrich_completed_tool_calls = enrich_completed_tool_calls
        self.wait_for_cached_response_callback = wait_for_cached_response
        self.unattended_mode = unattended_mode
        self.before_send_attempt = before_send_attempt

    @staticmethod
    def normalise(text: str) -> str:
        normalized = " ".join(text.split()).strip()
        # ChatGPT's ProseMirror auto-links a URL immediately following "=" and
        # exposes one synthetic separating space in editor/transcript text.
        # Treat that browser-only presentation difference as equivalent while
        # keeping the configured prompt unchanged.
        return re.sub(r"(?<==)\s+(?=https?://)", "", normalized)

    @staticmethod
    async def _raise_if_history_rate_limited(driver: Any) -> None:
        dismiss = getattr(driver, "dismiss_history_rate_limit", None)
        if dismiss is not None:
            # Conversation-history throttling is independent of prompt delivery.
            # Dismiss the modal so it cannot obstruct the composer, but do not turn
            # it into an account-wide send backoff.
            await dismiss()

    async def send_once(
        self,
        prompt: str,
        *,
        job_name: str = "",
        attachments: list[str] | None = None,
        force_tracking: bool = False,
    ) -> str:
        if not prompt.strip() and not attachments:
            raise ValueError("prompta prompt is empty")
        driver = await self.ensure_driver()
        context = await driver.new_tab()
        capture: dict[str, Any] | None = None
        probe_armed = False
        succeeded = False
        try:
            await self._raise_if_history_rate_limited(driver)
            await driver.wait_for_composer()
            await self._raise_if_history_rate_limited(driver)
            await self.ensure_high_effort(driver)
            if attachments:
                await driver.attach_files(attachments)
                await driver.wait_for_composer()
            baseline = await driver.dom_state()
            baseline_path = str(
                await driver.eval(load_browser_script("location_pathname.js")) or ""
            )
            if self.normalise(str(baseline.get("composer_text") or "")):
                logger.warning(
                    "Prompta found stale text in the dedicated new-chat composer; clearing it"
                )
                await driver.clear_composer()
                baseline = await driver.dom_state()
                if self.normalise(str(baseline.get("composer_text") or "")):
                    raise RuntimeError("ChatGPT stale new-chat composer could not be cleared")

            await driver.arm_page_send_probe()
            probe_armed = True
            capture = driver.arm_send_capture()
            if prompt.strip():
                await driver.type_message(prompt)
            typed = await driver.dom_state()
            if self.normalise(str(typed.get("composer_text") or "")) != self.normalise(prompt):
                raise RuntimeError("ChatGPT composer did not contain the configured prompt")
            dispatch_error: SendOutcomeUnknownError | None = None
            try:
                if attachments:
                    await driver.click_send_button()
                else:
                    await driver.click_send()
            except SendOutcomeUnknownError as exc:
                if self.before_send_attempt is not None:
                    self.before_send_attempt()
                dispatch_error = exc
                logger.warning(
                    "Prompta send outcome became ambiguous during dispatch; reconciling read-only before any retry"
                )
            else:
                if self.before_send_attempt is not None:
                    self.before_send_attempt()

            post_submit: dict[str, Any] = {}
            try:
                post_submit = await driver.dom_state()
            except Exception:
                if dispatch_error is None:
                    dispatch_error = SendOutcomeUnknownError(
                        "Prompta could not inspect the composer after dispatch; send outcome is unknown",
                        stage="post_dispatch_confirmation",
                    )

            provisional_conversation_id = ""
            provisional_confirmed = False
            last_state: dict[str, Any] = post_submit if not attachments else {}
            last_probe: dict[str, Any] = {}
            last_path = baseline_path
            last_send_confirmed = False
            confirmation_timeout = max(1.0, self.send_timeout_seconds)
            if attachments:
                confirmation_timeout = max(confirmation_timeout, 120.0)
            deadline = asyncio.get_running_loop().time() + confirmation_timeout
            while asyncio.get_running_loop().time() < deadline:
                try:
                    state = await driver.dom_state()
                    probe = await driver.page_send_probe()
                    path = str(await driver.eval(load_browser_script("location_pathname.js")) or "")
                except Exception as exc:
                    raise SendOutcomeUnknownError(
                        "Prompta lost read-only confirmation after dispatch; send outcome is unknown",
                        stage="send_confirmation",
                    ) from exc
                rate_limit_text = str(state.get("rate_limit_text") or "")
                if is_rate_limited_text(rate_limit_text):
                    raise RateLimitError.from_text(rate_limit_text)
                last_state = state
                last_probe = probe
                last_path = path
                user_text = self.normalise(str(state.get("last_user_text") or ""))
                message_id = str(probe.get("message_id") or state.get("last_user_id") or "")
                status = int(probe.get("response_status") or capture.get("status") or 0)
                send_confirmed = (
                    bool(probe.get("committed"))
                    or driver.captured_send_response(capture) is not None
                )
                last_send_confirmed = send_confirmed
                if status == 429:
                    raise RateLimitError("prompta send rate limited")
                if status >= 500:
                    raise SendOutcomeUnknownError(
                        f"prompta send returned HTTP {status} after dispatch; outcome is unknown",
                        stage="send_response",
                    )
                if status >= 400:
                    raise SendNotAcceptedError(f"prompta send failed with HTTP {status}")
                if capture.get("fetch_error"):
                    raise SendOutcomeUnknownError(
                        f"prompta send transport failed after dispatch: {capture['fetch_error']}",
                        stage="send_transport",
                    )

                route_confirmed = path.startswith("/c/") and path != baseline_path
                dom_confirmed = user_text == self.normalise(prompt) and not self.normalise(
                    str(state.get("composer_text") or "")
                )
                route_conversation_id = (
                    path.removeprefix("/c/").split("/", 1)[0] if route_confirmed else ""
                )
                probe_conversation_id = str(probe.get("conversation_id") or "")
                durable_conversation_id = next(
                    (
                        candidate
                        for candidate in (probe_conversation_id, route_conversation_id)
                        if candidate
                        and not candidate.startswith("WEB:")
                        and not candidate.casefold().startswith("local-chatgpt%3a")
                        and not candidate.casefold().startswith("local-chatgpt:")
                    ),
                    "",
                )
                provisional = next(
                    (
                        candidate
                        for candidate in (probe_conversation_id, route_conversation_id)
                        if candidate.startswith("WEB:")
                    ),
                    "",
                )
                if provisional:
                    provisional_conversation_id = provisional
                    provisional_confirmed = (
                        provisional_confirmed or send_confirmed or dom_confirmed or route_confirmed
                    )

                if durable_conversation_id and (send_confirmed or dom_confirmed or route_confirmed):
                    conversation_id = durable_conversation_id
                    logger.info(
                        "Prompta sent prompt in new conversation=%s message_id=%s transport_confirmed=%s dom_confirmed=%s",
                        conversation_id,
                        message_id or "unknown",
                        send_confirmed,
                        dom_confirmed,
                    )
                    self.cache.start(
                        conversation_id,
                        context_id=context,
                        job_name=job_name,
                        prompt=prompt,
                        force_tracking=force_tracking,
                    )
                    if self.unattended_mode() and not force_tracking:
                        self.cache.mark_unattended(conversation_id)
                    else:
                        self.active[context] = ActiveConversation(
                            conversation_id=conversation_id,
                            context_id=context,
                            job_name=job_name,
                            prompt=prompt,
                        )
                    succeeded = True
                    return conversation_id
                await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)

            if provisional_conversation_id and provisional_confirmed:
                logger.warning(
                    "Prompta only observed provisional conversation=%s before send confirmation timeout; continuing cache capture until ChatGPT publishes the durable route",
                    provisional_conversation_id,
                )
                self.cache.start(
                    provisional_conversation_id,
                    context_id=context,
                    job_name=job_name,
                    prompt=prompt,
                    force_tracking=force_tracking,
                )
                if self.unattended_mode() and not force_tracking:
                    self.cache.mark_unattended(provisional_conversation_id)
                else:
                    self.active[context] = ActiveConversation(
                        conversation_id=provisional_conversation_id,
                        context_id=context,
                        job_name=job_name,
                        prompt=prompt,
                    )
                succeeded = True
                return provisional_conversation_id

            final_composer = self.normalise(str(last_state.get("composer_text") or ""))
            final_user_text = self.normalise(str(last_state.get("last_user_text") or ""))
            if (
                final_composer == self.normalise(prompt)
                and final_user_text != self.normalise(prompt)
                and not last_send_confirmed
                and not provisional_conversation_id
                and last_path == baseline_path
            ):
                raise SendNotAcceptedError(
                    "ChatGPT did not accept the prompt; it remained in the composer after submit"
                )
            detail = (
                "prompta could not prove the prompt was sent in a new conversation "
                f"(composer_empty={not bool(final_composer)}, "
                f"last_user_matches={final_user_text == self.normalise(prompt)}, "
                f"transport_confirmed={last_send_confirmed}, "
                f"probe_status={int(last_probe.get('response_status') or 0)}, "
                f"path={last_path or '/'})"
            )
            if dispatch_error is not None:
                raise SendOutcomeUnknownError(
                    detail, stage=dispatch_error.stage
                ) from dispatch_error
            raise SendVerificationError(detail, stage="send_confirmation")
        finally:
            if capture is not None:
                driver.clear_send_capture(capture)
            if probe_armed:
                try:
                    await driver.clear_page_send_probe()
                except Exception:
                    logger.debug("Could not clear page send probe", exc_info=True)
            if not succeeded or not any(
                active.context_id == context for active in self.active.values()
            ):
                try:
                    await driver.close_context(context)
                except Exception:
                    logger.debug("Could not close Prompta tab", exc_info=True)

    async def sync_conversation(self, conversation_id: str) -> int:

        if not conversation_id.strip():
            raise ValueError("conversation id is empty")

        metadata = self.cache.metadata(conversation_id)
        previous_status = str(metadata.get("status") or "")
        if previous_status == "active":
            live = next(
                (
                    active
                    for active in self.active.values()
                    if active.conversation_id == conversation_id
                ),
                None,
            )
            if live is not None:
                logger.info(
                    "Prompta sync reused active conversation=%s context=%s",
                    conversation_id,
                    live.context_id,
                )
                return len(self.cache.messages(conversation_id))

        target_url = str(metadata.get("url") or f"https://chatgpt.com/c/{conversation_id}")
        driver = await self.ensure_driver()
        context = await driver.new_tab(target_url)
        retain_context = False
        try:
            expected_path = urlsplit(target_url).path.rstrip("/")
            await self.ensure_route(driver, expected_path)

            deadline = asyncio.get_running_loop().time() + _SYNC_OBSERVE_SECONDS
            last_digest = ""
            stable_polls = 0
            failure_polls = 0
            latest: dict[str, Any] = {}
            while asyncio.get_running_loop().time() < deadline:
                activity = await driver.conversation_activity(context)
                streaming_hint = bool(activity.get("streaming"))
                transient_hint = bool(activity.get("transient"))
                failure_hint = bool(activity.get("failed"))
                completion_hint = bool(activity.get("complete", True))
                latest = await driver.conversation_snapshot(context)
                if streaming_hint:
                    latest["streaming"] = True
                messages = latest.get("messages")
                if not isinstance(messages, list):
                    messages = []
                digest = self.cache.digest(latest)
                streaming = bool(latest.get("streaming"))

                if failure_hint:
                    failure_polls += 1
                    stable_polls = 0
                    if failure_polls < 3:
                        await asyncio.sleep(0.5)
                        continue
                    if messages:
                        self.cache.write_snapshot(conversation_id, latest)
                    self.cache.mark_interrupted(conversation_id)
                    raise RuntimeError("ChatGPT conversation has a persistent delivery failure")
                failure_polls = 0

                if not messages:
                    stable_polls = 0
                    last_digest = digest
                    await asyncio.sleep(0.5)
                    continue

                if streaming or transient_hint:
                    self.cache.resume(conversation_id, context_id=context)
                    self.cache.write_snapshot(conversation_id, latest)
                    self.active[context] = ActiveConversation(
                        conversation_id=conversation_id,
                        context_id=context,
                        job_name=str(metadata.get("job_name") or ""),
                        prompt=str(metadata.get("prompt") or ""),
                        last_digest=digest,
                        last_live_snapshot_at=time.monotonic(),
                    )
                    retain_context = True
                    return len(messages)

                if messages and digest == last_digest:
                    stable_polls += 1
                else:
                    stable_polls = 0
                last_digest = digest

                if stable_polls >= 2 and completion_hint:
                    latest = await self.enrich_completed_tool_calls(
                        conversation_id,
                        latest,
                    )
                    self.cache.write_snapshot(conversation_id, latest, complete=True)
                    return len(messages)
                if stable_polls >= 2 and not completion_hint:
                    self.cache.resume(conversation_id, context_id=context)
                    self.cache.write_snapshot(conversation_id, latest)
                    self.active[context] = ActiveConversation(
                        conversation_id=conversation_id,
                        context_id=context,
                        job_name=str(metadata.get("job_name") or ""),
                        prompt=str(metadata.get("prompt") or ""),
                        last_digest=digest,
                        last_live_snapshot_at=time.monotonic(),
                    )
                    retain_context = True
                    return len(messages)
                await asyncio.sleep(0.5)

            messages = latest.get("messages")
            if not isinstance(messages, list) or not messages:
                if previous_status == "active":
                    self.cache.mark_interrupted(conversation_id)
                raise RuntimeError("ChatGPT conversation did not expose any messages")
            self.cache.resume(conversation_id, context_id=context)
            self.cache.write_snapshot(conversation_id, latest)
            self.active[context] = ActiveConversation(
                conversation_id=conversation_id,
                context_id=context,
                job_name=str(metadata.get("job_name") or ""),
                prompt=str(metadata.get("prompt") or ""),
                last_digest=last_digest,
                last_live_snapshot_at=time.monotonic(),
            )
            retain_context = True
            return len(messages)
        finally:
            if not retain_context:
                await driver.close_context(context)

    async def send_reply(
        self,
        conversation_id: str,
        prompt: str,
        *,
        attachments: list[str] | None = None,
        force_tracking: bool = False,
    ) -> str:

        if not conversation_id.strip():
            raise ValueError("conversation id is empty")
        if not prompt.strip() and not attachments:
            raise ValueError("prompta prompt is empty")

        driver = await self.ensure_driver()
        if force_tracking:
            self.cache.set_force_tracking(conversation_id)
        metadata = self.cache.metadata(conversation_id)
        force_tracking = force_tracking or bool(metadata.get("force_tracking"))
        target_url = str(metadata.get("url") or f"https://chatgpt.com/c/{conversation_id}")
        expected_path = urlsplit(target_url).path.rstrip("/")
        existing = next(
            (
                (context, active)
                for context, active in self.active.items()
                if active.conversation_id == conversation_id
            ),
            None,
        )
        if existing is not None:
            retained_context, retained_active = existing
            if retained_active.settled_at <= 0:
                if not await self.wait_for_cached_response_callback(conversation_id):
                    raise RuntimeError(
                        "Prompta cannot reply before the current assistant response is cached"
                    )
            self.active.pop(retained_context, None)
            try:
                await driver.close_context(retained_context)
            except Exception:
                logger.debug(
                    "Could not close retained Prompta tab before reply",
                    exc_info=True,
                )

        context = await driver.new_tab(target_url)
        active: ActiveConversation | None = None
        created_context = True

        capture: dict[str, Any] | None = None
        probe_armed = False
        try:

            async def prepare_conversation_route() -> None:
                await self._raise_if_history_rate_limited(driver)
                try:
                    await driver.wait_for_composer()
                except RuntimeError as exc:
                    if not created_context or "composer did not become ready" not in str(exc):
                        raise
                    logger.warning(
                        "Prompta deep-link composer unavailable for conversation=%s; retrying via ChatGPT home",
                        conversation_id,
                    )
                    await driver.navigate("https://chatgpt.com/")
                    await driver.wait_for_composer()
                await self.ensure_route(driver, expected_path)
                await driver.wait_for_composer()
                await self._raise_if_history_rate_limited(driver)

            try:
                await prepare_conversation_route()
            except RuntimeError as exc:
                if not created_context or "composer did not become ready" not in str(exc):
                    raise
                logger.warning(
                    "Prompta conversation composer still unavailable for conversation=%s; reloading target once",
                    conversation_id,
                )
                await driver.navigate(target_url)
                await prepare_conversation_route()

            await self.ensure_high_effort(driver)
            if attachments:
                await driver.attach_files(attachments)
                await driver.wait_for_composer()
            baseline = await driver.dom_state()
            prompt_text = self.normalise(prompt)
            composer_text = self.normalise(str(baseline.get("composer_text") or ""))
            resume_queued_draft = bool(
                prompt_text and not attachments and composer_text == prompt_text
            )
            if composer_text and not resume_queued_draft:
                raise ControlDeferredError(
                    "ChatGPT composer already contains unsent text; clear the draft to send the queued reply",
                    retry_after=60.0,
                )
            if resume_queued_draft:
                logger.warning(
                    "Prompta found the queued reply already in the composer; resuming its send"
                )
            baseline_user_id = str(baseline.get("last_user_id") or "")

            await driver.arm_page_send_probe()
            probe_armed = True
            capture = driver.arm_send_capture()
            if prompt.strip() and not resume_queued_draft:
                await driver.type_message(prompt)
            typed = await driver.dom_state()
            if self.normalise(str(typed.get("composer_text") or "")) != self.normalise(prompt):
                raise RuntimeError("ChatGPT composer did not contain the requested reply")
            dispatch_error: SendOutcomeUnknownError | None = None
            try:
                if attachments:
                    await driver.click_send_button()
                else:
                    await driver.click_send()
            except SendOutcomeUnknownError as exc:
                if self.before_send_attempt is not None:
                    self.before_send_attempt()
                dispatch_error = exc
                logger.warning(
                    "Prompta reply outcome became ambiguous during dispatch; reconciling read-only before any retry"
                )
            else:
                if self.before_send_attempt is not None:
                    self.before_send_attempt()

            confirmation_timeout = max(1.0, self.send_timeout_seconds)
            if attachments:
                confirmation_timeout = max(confirmation_timeout, 120.0)
            deadline = asyncio.get_running_loop().time() + confirmation_timeout
            while asyncio.get_running_loop().time() < deadline:
                try:
                    state = await driver.dom_state()
                    probe = await driver.page_send_probe()
                except Exception as exc:
                    raise SendOutcomeUnknownError(
                        "Prompta lost read-only reply confirmation after dispatch; send outcome is unknown",
                        stage="send_confirmation",
                    ) from exc
                rate_limit_text = str(state.get("rate_limit_text") or "")
                if is_rate_limited_text(rate_limit_text):
                    raise RateLimitError.from_text(rate_limit_text)
                status = int(probe.get("response_status") or capture.get("status") or 0)
                if status == 429:
                    raise RateLimitError("prompta send rate limited")
                if status >= 500:
                    raise SendOutcomeUnknownError(
                        f"prompta send returned HTTP {status} after dispatch; outcome is unknown",
                        stage="send_response",
                    )
                if status >= 400:
                    raise SendNotAcceptedError(f"prompta send failed with HTTP {status}")
                if capture.get("fetch_error"):
                    raise SendOutcomeUnknownError(
                        f"prompta send transport failed after dispatch: {capture['fetch_error']}",
                        stage="send_transport",
                    )

                send_confirmed = (
                    bool(probe.get("committed"))
                    or driver.captured_send_response(capture) is not None
                )
                user_text = self.normalise(str(state.get("last_user_text") or ""))
                user_id = str(state.get("last_user_id") or "")
                dom_confirmed = (
                    user_text == self.normalise(prompt)
                    and not self.normalise(str(state.get("composer_text") or ""))
                    and (bool(user_id and user_id != baseline_user_id) or send_confirmed)
                )
                if send_confirmed or dom_confirmed:
                    metadata = self.cache.resume(conversation_id, context_id=context)
                    if self.unattended_mode() and not force_tracking:
                        self.cache.mark_unattended(conversation_id)
                    else:
                        if active is None:
                            active = ActiveConversation(
                                conversation_id=conversation_id,
                                context_id=context,
                                job_name=str(metadata.get("job_name") or ""),
                                prompt=str(metadata.get("prompt") or ""),
                            )
                            self.active[context] = active
                        active.idle_polls = 0
                        active.settled_at = 0.0
                        snapshot = await driver.conversation_snapshot(context)
                        self.cache.write_snapshot(conversation_id, snapshot)
                        active.last_digest = self.cache.digest(snapshot)
                    logger.info(
                        "Prompta sent reply conversation=%s reused_tab=%s",
                        conversation_id,
                        not created_context,
                    )
                    return conversation_id
                await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)

            detail = "prompta could not prove the reply was sent to the selected conversation"
            if dispatch_error is not None:
                raise SendOutcomeUnknownError(
                    detail, stage=dispatch_error.stage
                ) from dispatch_error
            raise SendVerificationError(detail, stage="send_confirmation")
        finally:
            if capture is not None:
                driver.clear_send_capture(capture)
            if probe_armed:
                try:
                    await driver.clear_page_send_probe()
                except Exception:
                    logger.debug("Could not clear page send probe", exc_info=True)
            if created_context and not any(
                active.context_id == context for active in self.active.values()
            ):
                try:
                    await driver.close_context(context)
                except Exception:
                    logger.debug("Could not close failed reply tab", exc_info=True)

    async def stop_conversation(self, conversation_id: str) -> str:
        match = next(
            (
                (context, active)
                for context, active in self.active.items()
                if active.conversation_id == conversation_id
            ),
            None,
        )
        if match is None:
            raise RuntimeError(f"Prompta has no active tab for conversation {conversation_id}")
        context, active = match
        driver = await self.ensure_driver()
        if driver is None:
            raise RuntimeError("Prompta browser session is unavailable")

        metadata = self.cache.metadata(conversation_id)
        target_url = str(metadata.get("url") or f"https://chatgpt.com/c/{conversation_id}")
        expected_path = urlsplit(target_url).path.rstrip("/") or "/"
        resolved_context = await driver.find_context_for_path(expected_path)
        if resolved_context and resolved_context != context:
            displaced = self.active.get(resolved_context)
            if displaced is not None and displaced is not active:
                logger.warning(
                    "Prompta stop route displaced stale conversation=%s from context=%s",
                    displaced.conversation_id,
                    resolved_context,
                )
            self.active.pop(context, None)
            active.context_id = resolved_context
            self.active[resolved_context] = active
            context = resolved_context
            self.cache.resume(conversation_id, context_id=context)
            logger.warning(
                "Prompta rebound stop conversation=%s from stale context to context=%s",
                conversation_id,
                context,
            )

        activity = await driver.conversation_activity(context)
        if bool(activity.get("streaming")):
            stop_deadline = asyncio.get_running_loop().time() + 5.0
            button_deadline = asyncio.get_running_loop().time() + 2.0
            clicked = False
            while (
                bool(activity.get("streaming"))
                and asyncio.get_running_loop().time() < stop_deadline
            ):
                if not clicked and asyncio.get_running_loop().time() < button_deadline:
                    clicked = await driver.click_stop(context)
                await asyncio.sleep(0.1)
                activity = await driver.conversation_activity(context)
                if (
                    not clicked
                    and bool(activity.get("streaming"))
                    and asyncio.get_running_loop().time() >= button_deadline
                ):
                    raise RuntimeError("ChatGPT stop button was not available")
            if bool(activity.get("streaming")):
                raise RuntimeError(
                    "ChatGPT response did not stop"
                    if clicked
                    else "ChatGPT stop button was not available"
                )

        snapshot = await driver.conversation_snapshot(context)
        snapshot["streaming"] = False
        self.cache.write_snapshot(conversation_id, snapshot, complete=True)
        active.last_digest = self.cache.digest(snapshot)
        active.idle_polls = max(active.idle_polls, 3)
        active.settled_at = time.monotonic()
        logger.info("Prompta stopped conversation=%s", conversation_id)
        return conversation_id
