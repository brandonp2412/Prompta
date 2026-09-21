from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from .cache import ActiveConversation, ChatCache
from .chromium import ChromiumToolEnricher, merge_tool_blocks

logger = logging.getLogger(__name__)

LIVE_SNAPSHOT_INTERVAL_SECONDS = 2.0
RESTART_RECOVERY_INTERRUPTED_SECONDS = 15 * 60.0
RESTART_RECOVERY_LOAD_ATTEMPTS = 2
RESTART_RECOVERY_RETRY_SECONDS = 60.0
ACTIVE_TAB_RETENTION_SECONDS = 15.0
FALLBACK_COMPLETION_POLLS = 10
DELIVERY_FAILURE_POLLS = 3
DELIVERY_RETRY_DISCOVERY_POLLS = 3
DELIVERY_RETRY_MAX_ATTEMPTS = 1
DELIVERY_RETRY_GRACE_SECONDS = 15.0
DELIVERY_RECOVERY_MAX_ATTEMPTS = 1
DELIVERY_RECOVERY_GRACE_SECONDS = 15.0
TRANSIENT_FAILURE_TIMEOUT_SECONDS = 15 * 60.0
TRANSIENT_RECOVERY_GRACE_SECONDS = 15.0


class ConversationTracker:
    def __init__(
        self,
        cache: ChatCache,
        ensure_driver: Callable[[], Any],
        ensure_route: Callable[..., Any],
        current_driver: Callable[[], Any],
        recovery_message_timeout_seconds: Callable[[], float],
    ) -> None:
        self.cache = cache
        self.tool_enricher = ChromiumToolEnricher()
        self.ensure_driver = ensure_driver
        self.ensure_route = ensure_route
        self.current_driver = current_driver
        self.recovery_message_timeout_seconds = recovery_message_timeout_seconds
        self.active: dict[str, ActiveConversation] = {}
        self.next_recovery_retry_at = time.monotonic() + RESTART_RECOVERY_RETRY_SECONDS

    async def recover_cached_conversations(self, *, limit: int = 50) -> int:

        attached_ids = {
            active.conversation_id for active in self.active.values()
        }
        recoverable = [
            row
            for row in self.cache.recoverable_conversations(
                interrupted_after=time.time() - RESTART_RECOVERY_INTERRUPTED_SECONDS,
                limit=max(1, limit) + len(attached_ids),
            )
            if str(row.get("id") or "") not in attached_ids
        ][: max(1, limit)]
        if not recoverable:
            self.next_recovery_retry_at = (
                time.monotonic() + RESTART_RECOVERY_RETRY_SECONDS
            )
            return 0

        driver = await self.ensure_driver()
        recovered = 0
        for row in recoverable:
            conversation_id = str(row.get("id") or "")
            target_url = str(
                row.get("url") or f"https://chatgpt.com/c/{conversation_id}"
            )
            context = ""
            try:
                context = await driver.new_tab(target_url)
                expected_path = urlsplit(target_url).path.rstrip("/")
                await self.ensure_route(driver, expected_path)
                snapshot: dict[str, Any] = {}
                messages: list[Any] = []
                for load_attempt in range(RESTART_RECOVERY_LOAD_ATTEMPTS):
                    deadline = (
                        asyncio.get_running_loop().time()
                        + self.recovery_message_timeout_seconds()
                    )
                    while asyncio.get_running_loop().time() < deadline:
                        snapshot = await driver.conversation_snapshot(context)
                        candidate_messages = snapshot.get("messages")
                        if isinstance(candidate_messages, list) and candidate_messages:
                            messages = candidate_messages
                            break
                        await asyncio.sleep(0.5)
                    if messages:
                        break
                    if load_attempt + 1 < RESTART_RECOVERY_LOAD_ATTEMPTS:
                        logger.warning(
                            "Prompta recovery conversation=%s did not expose messages; "
                            "reloading before retry",
                            conversation_id,
                        )
                        await driver.navigate(target_url)
                        await self.ensure_route(driver, expected_path)
                if not messages:
                    logger.warning(
                        "Prompta recovery conversation=%s still has no messages; "
                        "retrying through ChatGPT history",
                        conversation_id,
                    )
                    await driver.navigate("https://chatgpt.com/")
                    await self.ensure_route(driver, expected_path)
                    deadline = (
                        asyncio.get_running_loop().time()
                        + self.recovery_message_timeout_seconds()
                    )
                    while asyncio.get_running_loop().time() < deadline:
                        snapshot = await driver.conversation_snapshot(context)
                        candidate_messages = snapshot.get("messages")
                        if isinstance(candidate_messages, list) and candidate_messages:
                            messages = candidate_messages
                            break
                        await asyncio.sleep(0.5)
                if not messages:
                    raise RuntimeError(
                        "ChatGPT conversation did not expose any messages after "
                        "direct reload and history recovery"
                    )

                snapshot["streaming"] = True
                self.cache.resume(conversation_id, context_id=context)
                self.cache.write_snapshot(conversation_id, snapshot)
                self.active[context] = ActiveConversation(
                    conversation_id=conversation_id,
                    context_id=context,
                    job_name=str(row.get("job_name") or ""),
                    prompt=str(row.get("prompt") or ""),
                    last_digest=self.cache.digest(snapshot),
                    last_live_snapshot_at=time.monotonic(),
                    recovered_cache_updated_at=float(row.get("updated_at") or 0.0),
                )
                recovered += 1
                logger.info(
                    "Prompta reattached live conversation=%s after restart",
                    conversation_id,
                )
            except Exception:
                logger.exception(
                    "Prompta could not reattach conversation=%s after restart",
                    conversation_id,
                )
                if context:
                    try:
                        await driver.close_context(context)
                    except Exception:
                        logger.debug(
                            "Could not close failed Prompta recovery tab",
                            exc_info=True,
                        )
                if str(row.get("status") or "") == "active":
                    self.cache.mark_interrupted(conversation_id)
        self.next_recovery_retry_at = time.monotonic() + RESTART_RECOVERY_RETRY_SECONDS
        return recovered

    @staticmethod
    def apply_structured_tool_blocks(
        snapshot: dict[str, Any],
        blocks: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        if not blocks:
            return snapshot
        messages = snapshot.get("messages")
        if not isinstance(messages, list):
            return snapshot
        assistant_index = next(
            (
                index
                for index in range(len(messages) - 1, -1, -1)
                if isinstance(messages[index], dict)
                and str(messages[index].get("role") or "") == "assistant"
            ),
            None,
        )
        if assistant_index is None:
            return snapshot
        assistant = messages[assistant_index]
        content = str(assistant.get("content") or "")
        enriched_content = merge_tool_blocks(content, list(blocks))
        if enriched_content == content:
            return snapshot
        enriched = dict(snapshot)
        enriched_messages = [
            dict(message) if isinstance(message, dict) else message for message in messages
        ]
        enriched_messages[assistant_index]["content"] = enriched_content
        enriched["messages"] = enriched_messages
        return enriched

    async def enrich_completed_tool_calls(
        self,
        conversation_id: str,
        snapshot: dict[str, Any],
        *,
        active: ActiveConversation | None = None,
    ) -> dict[str, Any]:
        messages = snapshot.get("messages")
        if not isinstance(messages, list):
            return snapshot
        assistant = next(
            (
                message
                for message in reversed(messages)
                if isinstance(message, dict)
                and str(message.get("role") or "") == "assistant"
            ),
            None,
        )
        if assistant is None:
            return snapshot
        content = str(assistant.get("content") or "")
        if "tool:" not in content and "function:" not in content:
            return snapshot
        metadata = self.cache.metadata(conversation_id)
        url = str(metadata.get("url") or f"https://chatgpt.com/c/{conversation_id}")
        blocks, ordered_content = await self.tool_enricher.enrichment(url)
        if not blocks:
            return snapshot
        if active is not None:
            active.structured_tool_blocks = tuple(blocks)
        if ordered_content:
            enriched = dict(snapshot)
            enriched_messages = [
                dict(message) if isinstance(message, dict) else message for message in messages
            ]
            assistant_index = next(
                (
                    index
                    for index in range(len(enriched_messages) - 1, -1, -1)
                    if isinstance(enriched_messages[index], dict)
                    and str(enriched_messages[index].get("role") or "") == "assistant"
                ),
                None,
            )
            if assistant_index is not None:
                enriched_messages[assistant_index]["content"] = ordered_content
                enriched["messages"] = enriched_messages
            else:
                enriched = self.apply_structured_tool_blocks(snapshot, blocks)
        else:
            enriched = self.apply_structured_tool_blocks(snapshot, blocks)
        logger.info(
            "Prompta enriched conversation=%s with %d structured Chromium tool call(s)",
            conversation_id,
            len(blocks),
        )
        return enriched

    async def poll_active_conversations(self) -> None:
        if not self.active:
            return
        try:
            driver = await self.ensure_driver()
        except Exception:
            logger.exception("Prompta cache capture could not reconnect Firefox BiDi")
            return
        if driver is None:
            return
        for context, active in list(self.active.items()):
            try:
                activity = await driver.conversation_activity(context)
                streaming_hint = bool(activity.get("streaming"))
                completion_hint = bool(activity.get("complete", True))
                transient_hint = bool(activity.get("transient"))
                failure_hint = bool(activity.get("failed"))
                persistent_transient = transient_hint and not streaming_hint
                if persistent_transient:
                    now_epoch = time.time()
                    if active.transient_since_epoch <= 0:
                        recovered_at = active.recovered_cache_updated_at
                        active.transient_since_epoch = (
                            min(now_epoch, recovered_at) if recovered_at > 0 else now_epoch
                        )
                    transient_timeout = (
                        TRANSIENT_FAILURE_TIMEOUT_SECONDS
                        if active.transient_recovery_attempts <= 0
                        else TRANSIENT_RECOVERY_GRACE_SECONDS
                    )
                    if now_epoch - active.transient_since_epoch >= transient_timeout:
                        if active.transient_recovery_attempts <= 0:
                            target_url = str(
                                self.cache.metadata(active.conversation_id).get("url")
                                or f"https://chatgpt.com/c/{active.conversation_id}"
                            )
                            expected_path = urlsplit(target_url).path.rstrip("/")
                            active.transient_recovery_attempts = 1
                            active.transient_since_epoch = now_epoch
                            active.recovered_cache_updated_at = 0.0
                            try:
                                await driver.navigate(target_url, context=context)
                                await self.ensure_route(
                                    driver,
                                    expected_path,
                                    context=context,
                                )
                                await driver.wait_for_composer(
                                    timeout=10.0,
                                    context=context,
                                )
                                active.last_live_snapshot_at = 0.0
                                logger.warning(
                                    "Prompta reloaded persistently interrupted conversation=%s "
                                    "before giving up",
                                    active.conversation_id,
                                )
                                continue
                            except Exception:
                                logger.exception(
                                    "Prompta recovery reload failed conversation=%s",
                                    active.conversation_id,
                                )
                        self.cache.mark_interrupted(active.conversation_id)
                        try:
                            await driver.close_context(context)
                        except Exception:
                            logger.debug(
                                "Could not close persistently interrupted Prompta tab",
                                exc_info=True,
                            )
                        self.active.pop(context, None)
                        logger.warning(
                            "Prompta marked conversation=%s interrupted after persistent "
                            "ChatGPT connection interruption",
                            active.conversation_id,
                        )
                        continue
                else:
                    active.transient_since_epoch = 0.0
                    active.transient_recovery_attempts = 0
                    active.recovered_cache_updated_at = 0.0
                if streaming_hint or transient_hint:
                    active.idle_polls = 0
                    active.settled_at = 0.0
                    now = time.monotonic()
                    if now - active.last_live_snapshot_at < LIVE_SNAPSHOT_INTERVAL_SECONDS:
                        continue
                    active.last_live_snapshot_at = now
                snapshot = await driver.conversation_snapshot(context)
                if streaming_hint:
                    snapshot["streaming"] = True
            except Exception:
                logger.exception(
                    "Prompta cache capture failed conversation=%s", active.conversation_id
                )
                continue

            if active.structured_tool_blocks:
                snapshot = self.apply_structured_tool_blocks(
                    snapshot,
                    active.structured_tool_blocks,
                )

            digest = self.cache.digest(snapshot)
            changed = digest != active.last_digest
            messages = snapshot.get("messages")
            if not isinstance(messages, list):
                messages = []
            last_message = messages[-1] if messages else None
            has_assistant = (
                isinstance(last_message, dict)
                and str(last_message.get("role") or "") == "assistant"
                and bool(str(last_message.get("content") or "").strip())
            )
            streaming = bool(snapshot.get("streaming"))

            if changed:
                self.cache.write_snapshot(active.conversation_id, snapshot)
                active.last_digest = digest
                if not (
                    active.settled_at > 0
                    and completion_hint
                    and not streaming
                    and not failure_hint
                ):
                    active.idle_polls = 0
                    active.settled_at = 0.0

            if failure_hint:
                active.idle_polls += 1
                active.settled_at = 0.0
                now = time.monotonic()
                if (
                    active.delivery_recovery_at > 0
                    and now - active.delivery_recovery_at < DELIVERY_RECOVERY_GRACE_SECONDS
                ):
                    continue
                if (
                    active.delivery_retry_at > 0
                    and now - active.delivery_retry_at < DELIVERY_RETRY_GRACE_SECONDS
                ):
                    continue
                if active.idle_polls < DELIVERY_FAILURE_POLLS:
                    continue
                if active.delivery_retry_attempts < DELIVERY_RETRY_MAX_ATTEMPTS:
                    try:
                        retried = await driver.click_delivery_retry(context, timeout=3.0)
                    except Exception:
                        logger.exception(
                            "Prompta could not retry failed ChatGPT delivery conversation=%s",
                            active.conversation_id,
                        )
                        retried = False
                    if retried:
                        active.delivery_retry_attempts += 1
                        active.delivery_retry_at = time.monotonic()
                        active.idle_polls = 0
                        logger.warning(
                            "Prompta retried failed ChatGPT delivery conversation=%s attempt=%d",
                            active.conversation_id,
                            active.delivery_retry_attempts,
                        )
                        continue
                    discovery_deadline = (
                        DELIVERY_FAILURE_POLLS + DELIVERY_RETRY_DISCOVERY_POLLS
                    )
                    if active.idle_polls < discovery_deadline:
                        logger.warning(
                            "Prompta delivery retry control not available conversation=%s "
                            "poll=%d/%d; keeping tab alive",
                            active.conversation_id,
                            active.idle_polls,
                            discovery_deadline,
                        )
                        continue
                if active.delivery_recovery_attempts < DELIVERY_RECOVERY_MAX_ATTEMPTS:
                    target_url = str(
                        self.cache.metadata(active.conversation_id).get("url")
                        or f"https://chatgpt.com/c/{active.conversation_id}"
                    )
                    expected_path = urlsplit(target_url).path.rstrip("/")
                    try:
                        await driver.navigate(target_url, context=context)
                        await self.ensure_route(
                            driver,
                            expected_path,
                            context=context,
                        )
                        await driver.wait_for_composer(
                            timeout=10.0,
                            context=context,
                        )
                    except Exception:
                        logger.exception(
                            "Prompta delivery-failure recovery reload failed conversation=%s",
                            active.conversation_id,
                        )
                    else:
                        active.delivery_recovery_attempts += 1
                        active.delivery_recovery_at = time.monotonic()
                        active.delivery_retry_at = 0.0
                        active.idle_polls = 0
                        active.last_live_snapshot_at = 0.0
                        logger.warning(
                            "Prompta reloaded failed-delivery conversation=%s before giving up",
                            active.conversation_id,
                        )
                        continue
                self.cache.mark_interrupted(active.conversation_id)
                try:
                    await driver.close_context(context)
                except Exception:
                    logger.debug("Could not close failed Prompta tab", exc_info=True)
                self.active.pop(context, None)
                logger.warning(
                    "Prompta marked conversation=%s interrupted after persistent ChatGPT delivery failure",
                    active.conversation_id,
                )
                continue

            active.delivery_retry_at = 0.0
            if streaming_hint or transient_hint:
                continue

            if active.settled_at > 0 and completion_hint and not streaming:
                pass
            elif not changed and has_assistant and not streaming:
                active.idle_polls += 1
            else:
                active.idle_polls = 0
                active.settled_at = 0.0

            completion_polls = 3
            if (
                completion_hint
                and "turn_ended" in activity
                and activity.get("turn_ended") is None
            ):
                completion_polls = FALLBACK_COMPLETION_POLLS
            if active.idle_polls < completion_polls:
                continue
            if not completion_hint and active.idle_polls < 30:
                continue

            if active.settled_at <= 0:
                snapshot = await self.enrich_completed_tool_calls(
                    active.conversation_id,
                    snapshot,
                    active=active,
                )
                self.cache.write_snapshot(active.conversation_id, snapshot, complete=True)
                active.last_digest = self.cache.digest(snapshot)
                active.settled_at = time.monotonic()
                logger.info(
                    "Prompta cached completed conversation=%s messages=%d; retaining tab for %.0fs",
                    active.conversation_id,
                    len(messages),
                    ACTIVE_TAB_RETENTION_SECONDS,
                )
                continue

            if time.monotonic() - active.settled_at < ACTIVE_TAB_RETENTION_SECONDS:
                continue

            close_driver = self.current_driver()
            if close_driver is not None:
                try:
                    await close_driver.close_context(context)
                except Exception:
                    logger.debug("Could not close retained Prompta tab", exc_info=True)
            self.active.pop(context, None)
            logger.info(
                "Prompta closed retained conversation tab=%s after %.0fs",
                active.conversation_id,
                ACTIVE_TAB_RETENTION_SECONDS,
            )
