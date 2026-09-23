from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prompta.cache import ActiveConversation, ChatCache
from prompta.chrome import ChromeDebuggerUnavailableError
from prompta.control_server import ControlDeferredError
from prompta.conversation_actions import SendNotAcceptedError
from prompta.conversation_tracker import RESTART_RECOVERY_RETRY_SECONDS, STALE_ACTIVE_TAB_SECONDS
from prompta.core import (
    Prompta,
    PromptaConfig,
    PromptJob,
    RateLimitBackoff,
    RateLimitError,
    SendVerificationError,
    _daemon_is_running,
    _open_control_connection,
    _parser,
    _run,
    _send_once_via_control,
    _send_reply_via_control,
    _start_control_server,
    _stop_via_control,
    _sync_via_control,
    add_job,
    clear_jobs,
    load_jobs,
    main,
    parse_retry_after,
    remove_job,
    set_job_paused,
)
from prompta.webdriver import BrowsingContextUnavailableError


class FakeDriver:
    def __init__(
        self,
        prompt: str,
        initial_composer: str = "",
        *,
        committed: bool = True,
        capture_status: int = 200,
        expose_user_message: bool = True,
        route_after_send: bool = True,
        enter_submits: bool = True,
    ) -> None:
        self.prompt = prompt
        self.committed = committed
        self.expose_user_message = expose_user_message
        self.route_after_send = route_after_send
        self.enter_submits = enter_submits
        self.is_connected = True
        self.context = "context-1"
        self.typed = initial_composer
        self.sent = False
        self.send_button_clicked = False
        self.attached_files: list[str] = []
        self.clear_composer_calls = 0
        self.capture: dict[str, Any] = {
            "request_id": "request-1" if capture_status else "",
            "status": capture_status,
            "response_started": bool(capture_status),
            "completed": False,
            "fetch_error": "",
        }
        self.navigated: list[str] = []
        self.navigation_contexts: list[str | None] = []

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        self.navigated.append(url)
        self.navigation_contexts.append(context)

    async def new_tab(self, url: str = "https://chatgpt.com/") -> str:
        self.context = "context-new"
        self.navigated.append(url)
        return self.context

    async def close_context(self, context: str) -> None:
        return None

    async def wait_for_composer(self) -> None:
        return None

    async def conversation_activity(self, context: str) -> dict[str, object]:
        return {"streaming": False}

    async def dom_state(self) -> dict[str, object]:
        if self.sent:
            return {
                "composer_text": "",
                "last_user_text": self.prompt if self.expose_user_message else "",
                "last_user_id": "message-1" if self.expose_user_message else "",
                "rate_limit_text": "",
            }
        return {
            "composer_text": self.typed,
            "last_user_text": "",
            "last_user_id": "",
            "rate_limit_text": "",
        }

    async def arm_page_send_probe(self) -> None:
        return None

    def arm_send_capture(self) -> dict[str, Any]:
        return self.capture

    async def type_message(self, text: str) -> None:
        self.typed = text

    async def clear_composer(self) -> None:
        self.clear_composer_calls += 1
        self.typed = ""

    async def attach_files(self, paths: list[str]) -> None:
        self.attached_files = list(paths)

    async def click_send(self) -> None:
        if not self.enter_submits:
            return
        self.sent = True
        self.typed = ""

    async def click_send_button(self, timeout: float = 10.0) -> None:
        del timeout
        self.send_button_clicked = True
        self.sent = True
        self.typed = ""

    async def page_send_probe(self) -> dict[str, object]:
        return {
            "message_id": "message-1",
            "response_status": int(self.capture["status"]),
            "committed": self.committed,
        }

    def captured_send_response(self, capture: dict[str, Any]) -> tuple[str, int] | None:
        status = int(capture["status"])
        if capture["request_id"] and capture["response_started"] and 200 <= status < 400:
            return str(capture["request_id"]), status
        return None

    async def eval(self, expression: str) -> str:
        assert expression == "location.pathname"
        if self.sent and self.route_after_send:
            return "/c/new-chat"
        return "/"

    def clear_send_capture(self, capture: dict[str, Any]) -> None:
        return None

    async def clear_page_send_probe(self) -> dict[str, object]:
        return {}

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_send_once_always_starts_from_new_chat(tmp_path: Path) -> None:
    prompt = "PROMPTA TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt)

    assert conversation_id == "new-chat"
    assert fake.navigated == ["https://chatgpt.com/"]
    assert fake.sent is True
    assert fake.clear_composer_calls == 0
    prompta.actions.ensure_high_effort.assert_awaited_once_with(fake)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_scheduled_send_requires_high_effort(tmp_path: Path) -> None:
    prompt = "PROMPTA SCHEDULED TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    assert await prompta.send_once(prompt, job_name="scheduled-job") == "new-chat"

    prompta.actions.ensure_high_effort.assert_awaited_once_with(fake)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_send_once_falls_back_to_send_button_when_enter_does_not_submit(
    tmp_path: Path,
) -> None:
    prompt = "PROMPTA TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt, enter_submits=False)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt)

    assert conversation_id == "new-chat"
    assert fake.send_button_clicked is True


@pytest.mark.asyncio
async def test_send_once_accepts_visible_user_message_without_transport_confirmation(
    tmp_path: Path,
) -> None:
    prompt = "PROMPTA TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt, committed=False, capture_status=0)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt)

    assert conversation_id == "new-chat"


@pytest.mark.asyncio
async def test_send_once_requires_dom_or_transport_confirmation(tmp_path: Path) -> None:
    prompt = "PROMPTA TEST"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            send_timeout_seconds=0.01,
        ),
        "ws://unused",
    )
    fake = FakeDriver(
        prompt,
        committed=False,
        capture_status=0,
        expose_user_message=False,
        route_after_send=False,
    )
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(SendVerificationError, match="could not prove"):
        await prompta.send_once(prompt)


@pytest.mark.asyncio
async def test_send_once_accepts_new_conversation_route_as_confirmation(tmp_path: Path) -> None:
    prompt = "PROMPTA TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt, committed=False, capture_status=0, expose_user_message=False)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt)

    assert conversation_id == "new-chat"


@pytest.mark.asyncio
async def test_send_once_ignores_provisional_web_route_until_durable_id(tmp_path: Path) -> None:
    prompt = "PROMPTA TEST"

    class ProvisionalRouteDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__(prompt, committed=False, capture_status=0)
            self.route_reads = 0

        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            if not self.sent:
                return "/"
            self.route_reads += 1
            if self.route_reads < 3:
                return "/c/WEB:temporary"
            return "/c/durable-chat"

    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
            send_timeout_seconds=1.0,
        ),
        "ws://unused",
    )
    fake = ProvisionalRouteDriver()
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt)

    assert conversation_id == "durable-chat"
    assert fake.route_reads >= 3
    assert prompta.cache.metadata(conversation_id)["url"] == "https://chatgpt.com/c/durable-chat"
    prompta.cache.close()


@pytest.mark.asyncio
async def test_send_once_with_attachment_clicks_send_button(tmp_path: Path) -> None:
    prompt = "PROMPTA ATTACHMENT TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt, attachments=["/tmp/sample.txt"])

    assert conversation_id == "new-chat"
    assert fake.attached_files == ["/tmp/sample.txt"]
    assert fake.send_button_clicked is True
    assert fake.sent is True


@pytest.mark.asyncio
async def test_send_once_allows_attachment_only_message(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver("")
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once("", attachments=["/tmp/sample.txt"])

    assert conversation_id == "new-chat"
    assert fake.attached_files == ["/tmp/sample.txt"]
    assert fake.typed == ""
    assert fake.send_button_clicked is True
    assert fake.sent is True


@pytest.mark.asyncio
async def test_send_once_clears_stale_dedicated_composer(tmp_path: Path) -> None:
    prompt = "PROMPTA TEST"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    fake = FakeDriver(prompt, initial_composer="stale draft from previous failed attempt")
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    conversation_id = await prompta.send_once(prompt)

    assert conversation_id == "new-chat"
    assert fake.clear_composer_calls == 1
    assert fake.sent is True


@pytest.mark.asyncio
async def test_send_reply_resumes_matching_queued_draft(tmp_path: Path) -> None:
    prompt = "Continue from the UI"
    conversation_id = "existing-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class ReplyFakeDriver(FakeDriver):
        def __init__(self, message: str) -> None:
            super().__init__(message, initial_composer=message)
            self.type_calls = 0

        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return f"/c/{conversation_id}"

        async def type_message(self, text: str) -> None:
            self.type_calls += 1
            await super().type_message(text)

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            return {
                "title": "Existing chat",
                "path": f"/c/{conversation_id}",
                "streaming": True,
                "messages": [{"id": "u1", "role": "user", "content": prompt}],
            }

    prompta.cache.start(
        conversation_id,
        context_id="context-existing",
        job_name="kite",
        prompt="Original prompt",
    )
    fake = ReplyFakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    result = await prompta.send_reply(conversation_id, prompt)

    assert result == conversation_id
    assert fake.type_calls == 0
    assert fake.sent is True
    await prompta.close()


@pytest.mark.asyncio
async def test_send_reply_preserves_unrelated_existing_draft(tmp_path: Path) -> None:
    prompt = "Continue from the UI"
    conversation_id = "existing-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class ReplyFakeDriver(FakeDriver):
        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return f"/c/{conversation_id}"

    prompta.cache.start(
        conversation_id,
        context_id="context-existing",
        job_name="kite",
        prompt="Original prompt",
    )
    fake = ReplyFakeDriver(prompt, initial_composer="My manual unsent draft")
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="already contains unsent text"):
        await prompta.send_reply(conversation_id, prompt)

    assert fake.typed == "My manual unsent draft"
    assert fake.sent is False
    await prompta.close()


@pytest.mark.asyncio
async def test_send_reply_refreshes_retained_conversation_tab(tmp_path: Path) -> None:
    prompt = "Continue from the UI"
    conversation_id = "existing-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class ReplyFakeDriver(FakeDriver):
        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return f"/c/{conversation_id}"

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            return {
                "title": "Existing chat",
                "path": f"/c/{conversation_id}",
                "streaming": True,
                "messages": [
                    {"id": "u1", "role": "user", "content": prompt},
                ],
            }

    fake = ReplyFakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]
    wait_for_cached_response = AsyncMock(return_value=True)
    prompta.actions.wait_for_cached_response_callback = wait_for_cached_response
    prompta.cache.start(
        conversation_id,
        context_id="context-1",
        job_name="kite",
        prompt="Original prompt",
    )
    prompta._active_conversations["context-1"] = ActiveConversation(
        conversation_id=conversation_id,
        context_id="context-1",
        job_name="kite",
        prompt="Original prompt",
        settled_at=0.0,
    )

    result = await prompta.send_reply(conversation_id, prompt)

    assert result == conversation_id
    wait_for_cached_response.assert_awaited_once_with(conversation_id)
    assert fake.navigated == [f"https://chatgpt.com/c/{conversation_id}"]
    assert fake.sent is True
    assert "context-1" not in prompta._active_conversations
    assert prompta._active_conversations["context-new"].settled_at == 0.0
    assert prompta.cache.recent_conversations()[0]["status"] == "active"
    await prompta.close()


@pytest.mark.asyncio
async def test_send_reply_allows_attachment_only_message(tmp_path: Path) -> None:
    conversation_id = "existing-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class ReplyAttachmentDriver(FakeDriver):
        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return f"/c/{conversation_id}"

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            return {
                "title": "Existing chat",
                "path": f"/c/{conversation_id}",
                "streaming": True,
                "messages": [
                    {"id": "u1", "role": "user", "content": ""},
                ],
            }

    fake = ReplyAttachmentDriver("")
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]
    prompta.cache.start(
        conversation_id,
        context_id="context-old",
        job_name="kite",
        prompt="Original prompt",
    )

    result = await prompta.send_reply(
        conversation_id,
        "",
        attachments=["/tmp/reply-attachment.png"],
    )

    assert result == conversation_id
    assert fake.attached_files == ["/tmp/reply-attachment.png"]
    assert fake.typed == ""
    assert fake.send_button_clicked is True
    assert fake.sent is True
    await prompta.close()


@pytest.mark.asyncio
async def test_send_reply_falls_back_to_send_button_when_enter_does_not_submit(
    tmp_path: Path,
) -> None:
    prompt = "Continue from the UI"
    conversation_id = "existing-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class ReplyFakeDriver(FakeDriver):
        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return f"/c/{conversation_id}"

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            return {
                "title": "Existing chat",
                "path": f"/c/{conversation_id}",
                "streaming": True,
                "messages": [
                    {"id": "u1", "role": "user", "content": prompt},
                ],
            }

    fake = ReplyFakeDriver(prompt, enter_submits=False)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]
    prompta.cache.start(
        conversation_id,
        context_id="context-old",
        job_name="kite",
        prompt="Original prompt",
    )

    result = await prompta.send_reply(conversation_id, prompt)

    assert result == conversation_id
    assert fake.send_button_clicked is True
    await prompta.close()


@pytest.mark.asyncio
async def test_send_reply_recovers_history_link_after_deep_link_redirect(
    tmp_path: Path,
) -> None:
    prompt = "Continue from the UI"
    conversation_id = "WEB:legacy-chat"
    current_path = "/c/permanent-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class LegacyReplyFakeDriver(FakeDriver):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.path = "/"
            self.history_activations: list[str] = []

        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return self.path

        async def activate_history_link(self, path: str) -> bool:
            self.history_activations.append(path)
            self.path = path
            return True

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            return {
                "title": "Legacy chat",
                "path": current_path,
                "streaming": True,
                "messages": [
                    {"id": "u2", "role": "user", "content": prompt},
                ],
            }

    fake = LegacyReplyFakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="",
        prompt="Original prompt",
    )
    with prompta.cache.connection:
        prompta.cache.connection.execute(
            "UPDATE conversations SET url = ? WHERE id = ?",
            (f"https://chatgpt.com{current_path}", conversation_id),
        )

    result = await prompta.send_reply(conversation_id, prompt)

    assert result == conversation_id
    assert fake.navigated == [f"https://chatgpt.com{current_path}"]
    assert fake.history_activations == [current_path]
    assert fake.sent is True
    await prompta.close()


@pytest.mark.asyncio
async def test_ensure_conversation_route_recovers_blank_page_by_direct_navigation(
    tmp_path: Path,
) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    expected_path = "/c/blank-route"

    class BlankRouteDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__("unused")
            self.path = ""
            self.history_activations: list[str] = []

        async def eval(self, expression: str, *, context: str | None = None) -> str:
            assert expression == "location.pathname"
            assert context == "context-blank"
            return self.path

        async def activate_history_link(self, path: str, *, context: str | None = None) -> bool:
            assert context == "context-blank"
            self.history_activations.append(path)
            return False

        async def navigate(self, url: str, *, context: str | None = None) -> None:
            await super().navigate(url, context=context)
            self.path = expected_path

    fake = BlankRouteDriver()

    await prompta.browser.ensure_conversation_route(
        cast(Any, fake),
        expected_path,
        context="context-blank",
    )

    assert fake.history_activations == [expected_path]
    assert fake.navigated == [f"https://chatgpt.com{expected_path}"]
    assert fake.navigation_contexts == ["context-blank"]
    await prompta.close()


@pytest.mark.asyncio
async def test_send_reply_recovers_when_deep_link_has_no_composer(tmp_path: Path) -> None:
    prompt = "Continue from the UI"
    conversation_id = "WEB:legacy-chat"
    current_path = "/c/permanent-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class MissingComposerReplyFakeDriver(FakeDriver):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.path = "/"
            self.wait_calls = 0
            self.history_activations: list[str] = []

        async def wait_for_composer(self) -> None:
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise RuntimeError("ChatGPT composer did not become ready")

        async def navigate(self, url: str, *, context: str | None = None) -> None:
            self.navigated.append(url)
            self.path = "/"

        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return self.path

        async def activate_history_link(self, path: str) -> bool:
            self.history_activations.append(path)
            self.path = path
            return True

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            return {
                "title": "Legacy chat",
                "path": current_path,
                "streaming": True,
                "messages": [
                    {"id": "u3", "role": "user", "content": prompt},
                ],
            }

    fake = MissingComposerReplyFakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="",
        prompt="Original prompt",
    )
    with prompta.cache.connection:
        prompta.cache.connection.execute(
            "UPDATE conversations SET url = ? WHERE id = ?",
            (f"https://chatgpt.com{current_path}", conversation_id),
        )

    result = await prompta.send_reply(conversation_id, prompt)

    assert result == conversation_id
    assert fake.navigated == [
        f"https://chatgpt.com{current_path}",
        "https://chatgpt.com/",
    ]
    assert fake.history_activations == [current_path]
    assert fake.wait_calls == 3
    assert fake.sent is True
    await prompta.close()


@pytest.mark.asyncio
async def test_send_reply_reloads_when_recovered_route_still_has_no_composer(
    tmp_path: Path,
) -> None:
    prompt = "Continue from the UI"
    conversation_id = "WEB:legacy-chat"
    current_path = "/c/permanent-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class DelayedComposerReplyFakeDriver(FakeDriver):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.path = "/"
            self.wait_calls = 0
            self.history_activations: list[str] = []

        async def wait_for_composer(self) -> None:
            self.wait_calls += 1
            if self.wait_calls in {1, 3}:
                raise RuntimeError("ChatGPT composer did not become ready")

        async def navigate(self, url: str, *, context: str | None = None) -> None:
            self.navigated.append(url)
            self.path = "/"

        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return self.path

        async def activate_history_link(self, path: str) -> bool:
            self.history_activations.append(path)
            self.path = path
            return True

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            return {
                "title": "Legacy chat",
                "path": current_path,
                "streaming": True,
                "messages": [
                    {"id": "u4", "role": "user", "content": prompt},
                ],
            }

    fake = DelayedComposerReplyFakeDriver(prompt)
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="",
        prompt="Original prompt",
    )
    with prompta.cache.connection:
        prompta.cache.connection.execute(
            "UPDATE conversations SET url = ? WHERE id = ?",
            (f"https://chatgpt.com{current_path}", conversation_id),
        )

    result = await prompta.send_reply(conversation_id, prompt)

    assert result == conversation_id
    assert fake.navigated == [
        f"https://chatgpt.com{current_path}",
        "https://chatgpt.com/",
        f"https://chatgpt.com{current_path}",
    ]
    assert fake.history_activations == [current_path, current_path]
    assert fake.wait_calls == 5
    assert fake.sent is True
    await prompta.close()


@pytest.mark.asyncio
async def test_high_effort_is_selected_and_verified(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    driver = MagicMock()
    driver.context = "context-1"
    driver.high_effort_slider_value = AsyncMock(return_value="2")
    page = MagicMock()
    page.keyboard.press = AsyncMock()
    driver._page.return_value = page
    driver.effort_trigger_info = AsyncMock(
        side_effect=[
            {"text": "Medium", "x": 10.0, "y": 20.0},
            {"text": "High", "x": 10.0, "y": 20.0},
        ]
    )
    driver.high_effort_slider_point = AsyncMock(return_value={"x": 30.0, "y": 40.0})
    driver._click_viewport_point = AsyncMock()

    await prompta.browser.ensure_high_effort(driver)

    assert driver._click_viewport_point.await_count == 2
    page.keyboard.press.assert_awaited_once_with("Escape")


@pytest.mark.asyncio
async def test_high_effort_rechecks_stale_viewport_coordinates(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    driver = MagicMock()
    driver.context = "context-1"
    driver.high_effort_slider_value = AsyncMock(return_value="2")
    page = MagicMock()
    page.keyboard.press = AsyncMock()
    driver._page.return_value = page
    driver.effort_trigger_info = AsyncMock(
        side_effect=[
            {"text": "Medium", "x": 10.0, "y": 700.0},
            {"text": "Medium", "x": 10.0, "y": 20.0},
            {"text": "High", "x": 10.0, "y": 20.0},
        ]
    )
    driver.high_effort_slider_point = AsyncMock(
        side_effect=[
            {"x": 30.0, "y": 700.0},
            {"x": 30.0, "y": 40.0},
        ]
    )
    driver._click_viewport_point = AsyncMock(
        side_effect=[
            RuntimeError("move target out of bounds"),
            None,
            RuntimeError("move target out of bounds"),
            None,
        ]
    )

    await prompta.browser.ensure_high_effort(driver)

    assert driver.effort_trigger_info.await_count == 3
    assert driver.high_effort_slider_point.await_count == 2
    assert driver._click_viewport_point.await_count == 4
    page.keyboard.press.assert_awaited_once_with("Escape")


def test_daemon_check_does_not_create_lock_file(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"

    assert _daemon_is_running(state_path) is False
    assert not (tmp_path / "daemon.lock").exists()


def test_named_jobs_round_trip(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    add_job(jobs_path, "flux", "Continue Flux", 1800)
    add_job(jobs_path, "tv", "Continue TV", 1800)
    add_job(jobs_path, "immediate", "Run immediately", 0)
    add_job(jobs_path, "exact", "Run exactly", 1800, exact_interval=True)
    add_job(jobs_path, "daily", "Daily check", daily_at="07:00")
    add_job(jobs_path, "default", "Default interval")
    jobs = load_jobs(jobs_path)
    assert set(jobs) == {"flux", "tv", "immediate", "exact", "daily", "default"}
    assert jobs["flux"].interval_seconds == 1800
    assert jobs["immediate"].interval_seconds == 0
    assert jobs["exact"].exact_interval is True
    assert jobs["daily"].daily_at == "07:00"
    assert jobs["default"].interval_seconds == 2400
    remove_job(jobs_path, "tv")
    assert set(load_jobs(jobs_path)) == {"flux", "immediate", "exact", "daily", "default"}
    clear_jobs(jobs_path)
    assert load_jobs(jobs_path) == {}


def test_one_time_job_round_trips_exact_epoch(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    add_job(
        jobs_path,
        "at-test",
        "Run once",
        0,
        exact_interval=True,
        run_at_epoch=1_800_000_000.0,
    )

    job = load_jobs(jobs_path)["at-test"]
    assert job.run_at_epoch == 1_800_000_000.0
    assert job.exact_interval is True


def test_one_time_job_due_in_uses_exact_epoch(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    job = PromptJob(
        "at-test",
        "Run once",
        0,
        exact_interval=True,
        run_at_epoch=2_000.0,
    )
    assert prompta.due_in(job, now=1_500.0) == 500.0
    assert prompta.due_in(job, now=2_100.0) == 0.0


def test_daily_job_rejects_invalid_time(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HH:MM"):
        add_job(tmp_path / "jobs.json", "daily", "Daily check", daily_at="7am")


def test_exact_interval_has_no_recurring_jitter() -> None:
    with patch("prompta.core.random.uniform", return_value=300.0):
        assert Prompta._next_delay(PromptJob("exact", "run", 1800, exact_interval=True)) == 1800


def test_daily_job_initial_schedule_uses_exact_local_time(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    job = PromptJob("daily", "Daily check", daily_at="07:00")
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    now = datetime(2026, 9, 12, 6, 30).timestamp()

    prompta._ensure_initial_schedules([job], now)

    assert prompta.due_in(job, now=now) == pytest.approx(30 * 60)


@pytest.mark.asyncio
async def test_daily_job_success_reschedules_for_next_local_day(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    job = PromptJob("daily", "Daily check", daily_at="07:00")
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]
    sent_at = datetime(2026, 9, 12, 7, 0).timestamp()
    next_day = datetime(2026, 9, 13, 7, 0).timestamp()

    with patch("prompta.core.time.time", return_value=sent_at):
        assert await prompta._run_job(job, now=sent_at) is True

    assert prompta.due_in(job, now=sent_at) == pytest.approx(next_day - sent_at)


def test_due_in_uses_persisted_last_send(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"jobs": {"flux": {"last_sent_at": 1000.0}}}))
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    assert prompta.due_in(PromptJob("flux", "same", 1800), now=1900.0) == 900.0
    assert prompta.due_in(PromptJob("flux", "changed", 1800), now=1900.0) == 900.0


def test_pause_state_round_trip(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    state_path = tmp_path / "state.json"
    add_job(jobs_path, "flux", "same")

    assert set_job_paused(jobs_path, state_path, "flux", True) is True
    assert json.loads(state_path.read_text())["jobs"]["flux"]["paused"] is True
    assert set_job_paused(jobs_path, state_path, "flux", False) is True
    assert json.loads(state_path.read_text())["jobs"]["flux"]["paused"] is False
    assert set_job_paused(jobs_path, state_path, "missing", True) is False


@pytest.mark.asyncio
async def test_paused_job_is_not_run(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"jobs": {"flux": {"paused": True}}}))
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]

    assert await prompta._run_job(PromptJob("flux", "same"), now=1000.0) is False
    assert prompta.send_once.await_count == 0


@pytest.mark.asyncio
async def test_active_scheduled_job_only_blocks_the_same_job(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
        ),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]
    prompta._active_conversations["context-flux"] = ActiveConversation(
        conversation_id="existing",
        context_id="context-flux",
        job_name="flux",
        prompt="still working",
    )

    assert await prompta._run_job(PromptJob("flux", "continue", 1800), now=1000.0) is False
    assert await prompta._run_job(PromptJob("other", "continue", 1800), now=1000.0) is True
    prompta.send_once.assert_awaited_once_with("continue", job_name="other")


@pytest.mark.asyncio
async def test_active_scheduled_jobs_remain_bounded(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
        ),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]
    for index in range(4):
        context_id = f"context-{index}"
        prompta._active_conversations[context_id] = ActiveConversation(
            conversation_id=f"conversation-{index}",
            context_id=context_id,
            job_name=f"job-{index}",
            prompt="still working",
        )

    assert await prompta._run_job(PromptJob("next", "continue", 1800), now=1000.0) is False
    assert prompta.send_once.await_count == 0


@pytest.mark.asyncio
async def test_active_one_shot_does_not_block_scheduled_job(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
        ),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]
    prompta._active_conversations["context-once"] = ActiveConversation(
        conversation_id="manual",
        context_id="context-once",
        job_name="once",
        prompt="manual work still running",
    )

    assert (
        await prompta._run_job(
            PromptJob("background", "scheduled work", 1800),
            now=1000.0,
        )
        is True
    )
    prompta.send_once.assert_awaited_once_with(
        "scheduled work",
        job_name="background",
    )


def test_due_in_uses_uncertain_send_to_prevent_duplicate_retry(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"jobs": {"flux": {"last_uncertain_send_at": 1000.0}}}))
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )

    assert prompta.due_in(PromptJob("flux", "same", 1800), now=1300.0) == 1500.0


@pytest.mark.asyncio
async def test_uncertain_send_is_persisted_instead_of_retried_rapidly(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(side_effect=SendVerificationError("uncertain"))  # type: ignore[method-assign]
    job = PromptJob("github", "bug hunt", 1800)

    with patch("prompta.core.time.time", return_value=1000.0):
        assert await prompta._run_job(job, now=1000.0) is False

    assert prompta.due_in(job, now=1001.0) == 1799.0


@pytest.mark.asyncio
async def test_scheduled_send_retries_once_when_chatgpt_does_not_accept_prompt(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
        ),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(  # type: ignore[method-assign]
        side_effect=[SendNotAcceptedError("not accepted"), "conversation"]
    )
    job = PromptJob("flux", "continue flux", 1800)

    with patch("prompta.core.time.time", return_value=1000.0):
        assert await prompta._run_job(job, now=1000.0) is True

    assert prompta.send_once.await_count == 2


@pytest.mark.asyncio
async def test_scheduled_send_not_accepted_retry_is_bounded(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
        ),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(  # type: ignore[method-assign]
        side_effect=SendNotAcceptedError("not accepted")
    )
    job = PromptJob("flux", "continue flux", 1800)

    with patch("prompta.core.time.time", return_value=1000.0):
        assert await prompta._run_job(job, now=1000.0) is False

    assert prompta.send_once.await_count == 2
    assert prompta.scheduler_execution.scheduler.failure_retry_remaining("flux", 1001.0) > 0


@pytest.mark.asyncio
async def test_rate_limit_backoff_is_account_wide_persisted_and_exponential(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(side_effect=RateLimitError("limited", retry_after=0))  # type: ignore[method-assign]
    first_job = PromptJob("flux", "continue flux", 1800)
    second_job = PromptJob("other", "continue other", 1800)

    with patch("prompta.core.random.uniform", return_value=0.0):
        await prompta._run_job(first_job, now=1000.0)
        first = prompta._global_backoff.remaining()
        assert first > 0

        await prompta._run_job(second_job, now=1000.0)
        assert prompta.send_once.await_count == 1

        restarted = Prompta(
            PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
            "ws://unused",
        )
        restarted.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]
        await restarted._run_job(second_job, now=1000.0)
        assert restarted.send_once.await_count == 0

        prompta._global_backoff.blocked_until = 0.0
        prompta._update_scheduler_state({"last_attempt_at": 0.0})
        await prompta._run_job(first_job, now=1061.0)
        second = prompta._global_backoff.remaining()

    assert second >= first * 2 - 1


@pytest.mark.asyncio
async def test_generic_failure_cooldown_survives_restart(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    job = PromptJob("flux", "continue flux", 1800)
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(side_effect=RuntimeError("browser broke"))  # type: ignore[method-assign]

    with patch("prompta.core.time.time", return_value=1000.0):
        await prompta._run_job(job, now=1000.0)

    restarted = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    restarted.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]
    await restarted._run_job(job, now=1100.0)
    assert restarted.send_once.await_count == 0

    await restarted._run_job(job, now=1301.0)
    assert restarted.send_once.await_count == 1


@pytest.mark.asyncio
async def test_send_attempts_are_spaced_across_jobs_and_restarts(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    first_job = PromptJob("one", "first", 1800)
    second_job = PromptJob("two", "second", 1800)
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]

    with patch("prompta.core.time.time", return_value=1000.0):
        assert await prompta._run_job(first_job, now=1000.0) is True

    restarted = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    restarted.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]
    assert await restarted._run_job(second_job, now=1030.0) is False
    assert restarted.send_once.await_count == 0

    assert await restarted._run_job(second_job, now=1059.0) is False
    with patch("prompta.core.time.time", return_value=1061.0):
        assert await restarted._run_job(second_job, now=1061.0) is True
    assert restarted.send_once.await_count == 1


def test_initial_schedules_are_randomised_and_persisted(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    jobs = [PromptJob("one", "first", 1800), PromptJob("two", "second", 1800)]
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )

    with patch("prompta.core.random.uniform", side_effect=[120.0, 900.0]):
        prompta._ensure_initial_schedules(jobs, 1000.0)

    assert prompta.due_in(jobs[0], now=1000.0) == 120.0
    assert prompta.due_in(jobs[1], now=1000.0) == 900.0

    restarted = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    with patch("prompta.core.random.uniform") as random_uniform:
        restarted._ensure_initial_schedules(jobs, 1100.0)
    random_uniform.assert_not_called()
    assert restarted.due_in(jobs[0], now=1100.0) == 20.0
    assert restarted.due_in(jobs[1], now=1100.0) == 800.0


@pytest.mark.asyncio
async def test_success_persists_recurring_jitter(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    job = PromptJob("flux", "continue", 1800)
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", state_path=state_path),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation")  # type: ignore[method-assign]

    with (
        patch("prompta.core.time.time", return_value=1000.0),
        patch("prompta.core.random.uniform", return_value=240.0),
    ):
        assert await prompta._run_job(job, now=1000.0) is True

    assert prompta.due_in(job, now=1001.0) == 2039.0


def test_backoff_round_trip() -> None:
    backoff = RateLimitBackoff()
    with patch("prompta.core.random.uniform", return_value=0.0):
        backoff.record(120, now=100.0)
    snapshot = backoff.snapshot(now=100.0, wall_time=1000.0)
    restored = RateLimitBackoff()
    restored.restore(snapshot, now=200.0, wall_time=1000.0)
    assert restored.attempts == 1
    assert restored.remaining(now=200.0) == 120.0


def test_backoff_honors_explicit_retry_after_without_escalating() -> None:
    backoff = RateLimitBackoff()
    with patch("prompta.core.random.uniform", return_value=0.0):
        assert backoff.record(300, now=100.0) == 300.0
        backoff.blocked_until = 0.0
        assert backoff.record(3, now=401.0) == 3.0
    assert backoff.attempts == 2


def test_backoff_resets_escalation_after_quiet_period() -> None:
    backoff = RateLimitBackoff()
    with patch("prompta.core.random.uniform", return_value=0.0):
        first = backoff.record(0, now=100.0)
        backoff.blocked_until = 0.0
        second = backoff.record(0, now=200.0)
        backoff.blocked_until = 0.0
        reset = backoff.record(0, now=2200.0)
    assert second == first * 2
    assert reset == first


def test_retry_after_parser() -> None:
    assert parse_retry_after("Try again in 30 seconds") == 30
    assert parse_retry_after("Please wait 2 minutes") == 120
    assert parse_retry_after("Try again in 1 hour") == 3600
    assert parse_retry_after("Wait a few minutes") == 300


def test_replace_alias_parses_as_add_command() -> None:
    args = _parser().parse_args(["replace", "flux", "Keep working"])

    assert args.command == "replace"
    assert args.name == "flux"
    assert args.prompt == "Keep working"


def test_pause_command_allows_omitted_name() -> None:
    args = _parser().parse_args(["pause"])

    assert args.command == "pause"
    assert args.name is None


def test_pause_without_name_pauses_all_jobs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    jobs_path = tmp_path / "jobs.json"
    state_path = tmp_path / "state.json"
    add_job(jobs_path, "flux", "Continue Flux")
    add_job(jobs_path, "kite", "Continue Kite")

    with patch(
        "sys.argv",
        [
            "prompta",
            "pause",
            "--jobs-file",
            str(jobs_path),
            "--state",
            str(state_path),
        ],
    ):
        main()

    state = json.loads(state_path.read_text())
    assert state["jobs"]["flux"]["paused"] is True
    assert state["jobs"]["kite"]["paused"] is True
    assert "Paused 2 jobs" in capsys.readouterr().out


def test_replace_command_overwrites_named_job(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    jobs_path = tmp_path / "jobs.json"
    add_job(jobs_path, "flux", "Old prompt", 1200)

    with patch(
        "sys.argv",
        [
            "prompta",
            "replace",
            "flux",
            "New prompt",
            "--interval-minutes",
            "30",
            "--jobs-file",
            str(jobs_path),
        ],
    ):
        main()

    job = load_jobs(jobs_path)["flux"]
    assert job.prompt == "New prompt"
    assert job.interval_seconds == 1800
    assert "Saved flux" in capsys.readouterr().out


def test_ls_alias_parses_as_list_command() -> None:
    args = _parser().parse_args(["ls"])

    assert args.command == "ls"
    assert hasattr(args, "jobs_file")
    assert hasattr(args, "state")


def test_once_command_parses_as_non_scheduled_prompt() -> None:
    args = _parser().parse_args(["once", "Do exactly one thing"])

    assert args.command == "once"
    assert args.prompt == "Do exactly one thing"
    assert args.browser == "chrome"
    assert not hasattr(args, "jobs_file")


@pytest.mark.asyncio
async def test_once_command_sends_exactly_once_without_scheduler(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _parser().parse_args(["once", "Do exactly one thing", "--direct-browser"])

    with (
        patch.object(Prompta, "send_once", AsyncMock(return_value="conversation-123")) as send_once,
        patch.object(
            Prompta,
            "wait_for_cached_response",
            AsyncMock(return_value=True),
        ) as wait_for_cached_response,
        patch.object(Prompta, "run", AsyncMock()) as run,
        patch.object(Prompta, "close", AsyncMock()),
    ):
        await _run(args)

    send_once.assert_awaited_once_with("Do exactly one thing")
    wait_for_cached_response.assert_awaited_once_with("conversation-123")
    run.assert_not_awaited()
    output = capsys.readouterr().out
    assert "One-shot" in output
    assert "conversation conversation-123" in output
    assert "assistant response complete" in output


@pytest.mark.asyncio
async def test_control_socket_routes_one_shot_through_scheduler(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=state_path,
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="conversation-via-daemon")  # type: ignore[method-assign]
    server, socket_path = await _start_control_server(prompta, state_path)
    try:
        client = asyncio.create_task(_send_once_via_control(state_path, "Do one thing"))
        for _ in range(100):
            if not prompta._once_requests.empty():
                break
            await asyncio.sleep(0.01)
        assert not prompta._once_requests.empty()
        await prompta._drain_once_requests()
        assert await client == "conversation-via-daemon"
        prompta.send_once.assert_awaited_once_with("Do one thing", attachments=[])  # type: ignore[attr-defined]
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)
        prompta.cache.close()


@pytest.mark.asyncio
async def test_control_socket_routes_attachment_only_one_shot(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=state_path,
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(return_value="attachment-only-chat")  # type: ignore[method-assign]
    server, socket_path = await _start_control_server(prompta, state_path)
    try:
        client = asyncio.create_task(
            _send_once_via_control(state_path, "", ["/tmp/attachment-only.png"])
        )
        for _ in range(100):
            if not prompta._once_requests.empty():
                break
            await asyncio.sleep(0.01)
        assert not prompta._once_requests.empty()
        await prompta._drain_once_requests()
        assert await client == "attachment-only-chat"
        prompta.send_once.assert_awaited_once_with(  # type: ignore[attr-defined]
            "",
            attachments=["/tmp/attachment-only.png"],
        )
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)
        prompta.cache.close()


@pytest.mark.asyncio
async def test_control_send_retries_after_poisoned_scheduler_restart(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    request = AsyncMock(
        side_effect=[
            RuntimeError("WebDriver session is poisoned; browser restart required"),
            {"ok": True, "conversation_id": "conversation-after-restart"},
        ]
    )
    restart = AsyncMock()

    with (
        patch("prompta.core._control_send_request", request),
        patch("prompta.core._wait_for_scheduler_restart", restart),
    ):
        result = await _send_once_via_control(state_path, "Do one thing")

    assert result == "conversation-after-restart"
    assert request.await_count == 2
    restart.assert_awaited_once_with(state_path)


@pytest.mark.asyncio
async def test_control_send_does_not_retry_unrelated_scheduler_error(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    request = AsyncMock(side_effect=RuntimeError("ChatGPT composer failed"))
    restart = AsyncMock()

    with (
        patch("prompta.core._control_send_request", request),
        patch("prompta.core._wait_for_scheduler_restart", restart),
    ):
        with pytest.raises(RuntimeError, match="composer failed"):
            await _send_once_via_control(state_path, "Do one thing")

    request.assert_awaited_once()
    restart.assert_not_awaited()


@pytest.mark.asyncio
async def test_busy_reply_does_not_block_other_scheduler_requests(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta._active_conversations["busy-context"] = ActiveConversation(
        conversation_id="busy-chat",
        context_id="busy-context",
        job_name="",
        prompt="Earlier prompt",
    )
    busy_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    await prompta._reply_requests.put(("busy-chat", "Follow up", [], busy_future))
    prompta.send_reply = AsyncMock(return_value="busy-chat")  # type: ignore[method-assign]

    did_work = await prompta._drain_reply_requests()

    assert did_work is False
    assert prompta._reply_requests.qsize() == 1
    assert not busy_future.done()
    prompta.send_reply.assert_not_awaited()  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_ui_control_reply_defers_busy_target_before_delivery(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=state_path,
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta._active_conversations["busy-context"] = ActiveConversation(
        conversation_id="busy-chat",
        context_id="busy-context",
        job_name="",
        prompt="Earlier prompt",
    )
    server, socket_path = await _start_control_server(prompta, state_path)
    try:
        with pytest.raises(ControlDeferredError, match="deferred before delivery"):
            await _send_reply_via_control(
                state_path,
                "busy-chat",
                "Follow up",
                defer_if_busy=True,
            )
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)
        prompta.cache.close()


def test_completed_cache_prevents_stale_active_reply_lock(tmp_path: Path) -> None:
    conversation_id = "completed-chat"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.cache.start(
        conversation_id,
        context_id="stale-context",
        job_name="",
        prompt="Earlier prompt",
    )
    prompta.cache.write_snapshot(
        conversation_id,
        {
            "title": "Completed",
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Earlier prompt"},
                {"id": "a1", "role": "assistant", "content": "Done"},
            ],
        },
        complete=True,
    )
    prompta._active_conversations["stale-context"] = ActiveConversation(
        conversation_id=conversation_id,
        context_id="stale-context",
        job_name="",
        prompt="Earlier prompt",
    )

    assert prompta._reply_target_is_busy(conversation_id) is False
    prompta.cache.close()


@pytest.mark.asyncio
async def test_scheduler_prioritises_ui_send_before_active_poll(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    order: list[str] = []

    async def drain_reply() -> bool:
        order.append("reply")
        return False

    async def drain_once() -> bool:
        order.append("once")
        return True

    async def drain_sync() -> bool:
        order.append("sync")
        return False

    async def retry_recovery() -> bool:
        order.append("recovery")
        return False

    async def poll_active() -> None:
        order.append("poll")

    test_prompta = cast(Any, prompta)
    test_prompta._drain_reply_requests = drain_reply
    test_prompta._drain_once_requests = drain_once
    test_prompta._drain_sync_requests = drain_sync
    test_prompta._retry_cached_recovery_if_due = retry_recovery
    test_prompta._poll_active_conversations = poll_active
    test_prompta.read_jobs = lambda: {}

    await prompta.run(once=True)

    assert order == ["reply", "once", "sync", "recovery", "poll"]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_control_one_shots_share_scheduler_send_pacing(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(side_effect=["first-chat", "second-chat"])  # type: ignore[method-assign]
    first: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    second: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    await prompta._once_requests.put(("First send", [], first))
    await prompta._once_requests.put(("Second send", [], second))
    prompta._update_scheduler_state({"last_attempt_at": time.time()})

    assert await prompta._drain_once_requests() is False
    assert prompta._once_requests.qsize() == 2
    assert prompta.send_once.await_count == 0
    assert not first.done()
    assert not second.done()

    prompta._update_scheduler_state({"last_attempt_at": 0.0})
    assert await prompta._drain_once_requests() is True
    assert await first == "first-chat"
    assert prompta._once_requests.qsize() == 1
    assert prompta.send_once.await_count == 1
    assert not second.done()
    assert prompta._send_gap_remaining(time.time()) > 0

    prompta._update_scheduler_state({"last_attempt_at": 0.0})
    assert await prompta._drain_once_requests() is True
    assert await second == "second-chat"
    assert prompta._once_requests.empty()
    assert prompta.send_once.await_count == 2
    prompta.cache.close()


@pytest.mark.asyncio
async def test_control_reply_and_scheduled_jobs_share_send_pacing(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.send_reply = AsyncMock(return_value="existing-chat")  # type: ignore[method-assign]
    prompta.send_once = AsyncMock(return_value="scheduled-chat")  # type: ignore[method-assign]
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    await prompta._reply_requests.put(("existing-chat", "Continue", [], future))
    prompta._update_scheduler_state({"last_attempt_at": 0.0})

    assert await prompta._drain_reply_requests() is True
    assert await future == "existing-chat"
    assert prompta._send_gap_remaining(time.time()) > 0

    scheduled = PromptJob("background", "Background send", 1800)
    assert await prompta._run_job(scheduled, now=time.time()) is False
    prompta.send_once.assert_not_awaited()
    prompta.cache.close()


@pytest.mark.asyncio
async def test_control_send_rate_limit_pauses_scheduler_jobs(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=state_path,
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.send_once = AsyncMock(side_effect=RateLimitError("Too many requests", retry_after=300))  # type: ignore[method-assign]
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    await prompta._once_requests.put(("User send", [], future))

    with patch("prompta.core.random.uniform", return_value=0.0):
        await prompta._drain_once_requests()

    with pytest.raises(RateLimitError):
        await future
    assert prompta._global_backoff.remaining() > 0

    scheduled = PromptJob("background", "Background send", 1800)
    await prompta._run_job(scheduled, now=time.time())
    assert prompta.send_once.await_count == 1
    prompta.cache.close()


@pytest.mark.asyncio
async def test_control_socket_routes_reply_through_scheduler(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=state_path,
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.send_reply = AsyncMock(return_value="existing-chat")  # type: ignore[method-assign]
    prompta.wait_for_cached_response = AsyncMock(return_value=True)  # type: ignore[method-assign]
    server, socket_path = await _start_control_server(prompta, state_path)
    try:
        client = asyncio.create_task(
            _send_reply_via_control(state_path, "existing-chat", "Continue here")
        )
        for _ in range(100):
            if not prompta._reply_requests.empty():
                break
            await asyncio.sleep(0.01)
        assert not prompta._reply_requests.empty()
        await prompta._drain_reply_requests()
        assert await client == "existing-chat"
        prompta.send_reply.assert_awaited_once_with(
            "existing-chat", "Continue here", attachments=[]
        )  # type: ignore[attr-defined]
        prompta.wait_for_cached_response.assert_not_awaited()  # type: ignore[attr-defined]
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)
        prompta.cache.close()


@pytest.mark.asyncio
async def test_stop_conversation_clicks_stop_and_settles_cache(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.cache.start(
        "chat-live",
        context_id="context-live",
        job_name="",
        prompt="Keep working",
    )
    active = ActiveConversation(
        conversation_id="chat-live",
        context_id="context-live",
        job_name="",
        prompt="Keep working",
    )
    prompta._active_conversations["context-live"] = active
    driver = MagicMock()
    driver.find_context_for_path = AsyncMock(return_value="context-live")
    driver.conversation_activity = AsyncMock(
        side_effect=[{"streaming": True}, {"streaming": False}]
    )
    driver.click_stop = AsyncMock(return_value=True)
    driver.conversation_snapshot = AsyncMock(
        return_value={
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep working"},
                {"id": "a1", "role": "assistant", "content": "Partial answer"},
            ],
        }
    )
    prompta.driver = driver

    result = await prompta.stop_conversation("chat-live")

    assert result == "chat-live"
    driver.click_stop.assert_awaited_once_with("context-live")
    assert active.settled_at > 0
    assert active.idle_polls >= 3
    prompta.cache.close()


@pytest.mark.asyncio
async def test_stop_conversation_tolerates_completion_race_when_button_disappears(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.cache.start(
        "chat-race",
        context_id="context-race",
        job_name="",
        prompt="Keep working",
    )
    active = ActiveConversation(
        conversation_id="chat-race",
        context_id="context-race",
        job_name="",
        prompt="Keep working",
    )
    prompta._active_conversations["context-race"] = active
    driver = MagicMock()
    driver.find_context_for_path = AsyncMock(return_value="context-race")
    driver.conversation_activity = AsyncMock(
        side_effect=[
            {"streaming": True},
            {"streaming": True},
            {"streaming": False},
        ]
    )
    driver.click_stop = AsyncMock(return_value=False)
    driver.conversation_snapshot = AsyncMock(
        return_value={
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep working"},
                {"id": "a1", "role": "assistant", "content": "Finished naturally"},
            ],
        }
    )
    prompta.driver = driver

    result = await prompta.stop_conversation("chat-race")

    assert result == "chat-race"
    assert driver.click_stop.await_count == 2
    assert active.settled_at > 0
    prompta.cache.close()


@pytest.mark.asyncio
async def test_stop_conversation_rebinds_stale_context_to_live_route(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.cache.start(
        "chat-live",
        context_id="context-stale",
        job_name="",
        prompt="Keep working",
    )
    active = ActiveConversation(
        conversation_id="chat-live",
        context_id="context-stale",
        job_name="",
        prompt="Keep working",
    )
    prompta._active_conversations["context-stale"] = active
    driver = MagicMock()
    driver.find_context_for_path = AsyncMock(return_value="context-live")
    driver.conversation_activity = AsyncMock(
        side_effect=[{"streaming": True}, {"streaming": False}]
    )
    driver.click_stop = AsyncMock(return_value=True)
    driver.conversation_snapshot = AsyncMock(
        return_value={
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep working"},
                {"id": "a1", "role": "assistant", "content": "Partial answer"},
            ],
        }
    )
    prompta.driver = driver

    result = await prompta.stop_conversation("chat-live")

    assert result == "chat-live"
    driver.find_context_for_path.assert_awaited_once_with("/c/chat-live")
    driver.click_stop.assert_awaited_once_with("context-live")
    assert "context-stale" not in prompta._active_conversations
    assert prompta._active_conversations["context-live"] is active
    assert active.context_id == "context-live"
    prompta.cache.close()


@pytest.mark.asyncio
async def test_control_socket_routes_stop_directly_to_scheduler(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=state_path,
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.stop_conversation = AsyncMock(return_value="existing-chat")  # type: ignore[method-assign]
    server, socket_path = await _start_control_server(prompta, state_path)
    try:
        result = await _stop_via_control(state_path, "existing-chat")
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)
        prompta.cache.close()

    assert result == "existing-chat"
    prompta.stop_conversation.assert_awaited_once_with("existing-chat")  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_control_socket_logs_unexpected_backend_exception(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=state_path,
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.stop_conversation = AsyncMock(side_effect=RuntimeError("backend exploded"))  # type: ignore[method-assign]

    with patch("prompta.control_server.logger.exception") as log_exception:
        server, socket_path = await _start_control_server(prompta, state_path)
        try:
            with pytest.raises(RuntimeError, match="backend exploded"):
                await _stop_via_control(state_path, "existing-chat")
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)
            prompta.cache.close()

    log_exception.assert_called_once_with("Prompta control request failed op=%s", "stop")


@pytest.mark.asyncio
async def test_control_socket_does_not_trace_expected_validation_error(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=state_path,
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )

    with patch("prompta.control_server.logger.exception") as log_exception:
        server, socket_path = await _start_control_server(prompta, state_path)
        try:
            with pytest.raises(RuntimeError, match="conversation id is empty"):
                await _stop_via_control(state_path, "")
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)
            prompta.cache.close()

    log_exception.assert_not_called()


@pytest.mark.asyncio
async def test_control_socket_routes_sync_through_scheduler(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=state_path,
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.sync_conversation = AsyncMock(return_value=4)  # type: ignore[method-assign]
    server, socket_path = await _start_control_server(prompta, state_path)
    try:
        client = asyncio.create_task(_sync_via_control(state_path, "existing-chat"))
        for _ in range(100):
            if not prompta._sync_requests.empty():
                break
            await asyncio.sleep(0.01)
        assert not prompta._sync_requests.empty()
        await prompta._drain_sync_requests()
        assert await client == 4
        prompta.sync_conversation.assert_awaited_once_with("existing-chat")  # type: ignore[attr-defined]
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)
        prompta.cache.close()


@pytest.mark.asyncio
async def test_sync_uses_running_scheduler_without_spawning_browser(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _parser().parse_args(["sync", "existing-chat"])
    with (
        patch("prompta.core._daemon_is_running", return_value=True),
        patch("prompta.core._sync_via_control", AsyncMock(return_value=4)) as sync_control,
    ):
        await _run(args)

    sync_control.assert_awaited_once_with(args.state, "existing-chat")
    output = capsys.readouterr().out
    assert "Synced" in output
    assert "4 messages" in output


@pytest.mark.asyncio
async def test_once_uses_running_scheduler_without_spawning_browser(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _parser().parse_args(["once", "Do exactly one thing"])
    with (
        patch("prompta.core._daemon_is_running", return_value=True),
        patch(
            "prompta.core._send_once_via_control",
            AsyncMock(return_value="conversation-queued"),
        ) as send_via_control,
        patch(
            "prompta.core._wait_for_cache_completion",
            AsyncMock(return_value=True),
        ) as wait_for_cache,
    ):
        await _run(args)

    send_via_control.assert_awaited_once_with(args.state, "Do exactly one thing")
    wait_for_cache.assert_awaited_once_with(args.cache, "conversation-queued")
    output = capsys.readouterr().out
    assert "conversation conversation-queued" in output
    assert "assistant response complete" in output


@pytest.mark.asyncio
async def test_poll_active_conversations_caches_streaming_updates_without_snapshot_spam(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.cache.start(
        "conversation-tool-run",
        context_id="context-tool-run",
        job_name="",
        prompt="Search the web",
    )
    active = ActiveConversation(
        conversation_id="conversation-tool-run",
        context_id="context-tool-run",
        job_name="",
        prompt="Search the web",
        idle_polls=2,
        settled_at=123.0,
    )
    prompta._active_conversations["context-tool-run"] = active

    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(return_value={"streaming": True})
    driver.conversation_snapshot = AsyncMock(
        return_value={
            "title": "Tool run",
            "path": "/c/conversation-tool-run",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Search the web"},
                {"id": "a1", "role": "assistant", "content": "Searching now"},
            ],
        }
    )
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()

    driver.conversation_activity.assert_awaited_once_with("context-tool-run")
    driver.conversation_snapshot.assert_awaited_once_with("context-tool-run")
    messages = prompta.cache.messages("conversation-tool-run")
    assert messages[-1]["content"] == "Searching now"
    assert messages[-1]["status"] == "streaming"
    assert active.idle_polls == 0
    assert active.settled_at == 0.0

    await prompta._poll_active_conversations()
    assert driver.conversation_snapshot.await_count == 1
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversation_keeps_brief_connection_interruption_live(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-transient"
    context_id = "context-transient"
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    active = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    prompta._active_conversations[context_id] = active

    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(
        return_value={
            "streaming": False,
            "complete": False,
            "transient": True,
            "failed": False,
        }
    )
    driver.conversation_snapshot = AsyncMock(
        return_value={
            "title": "Interrupted temporarily",
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": "Partial answer"},
            ],
            "streaming": False,
        }
    )
    driver.close_context = AsyncMock()
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()

    assert active.transient_since_epoch > 0
    assert prompta.cache.status(conversation_id) == "active"
    assert context_id in prompta._active_conversations
    driver.close_context.assert_not_awaited()
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversation_recovers_transient_with_stale_streaming_hint(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-transient-stale-streaming"
    context_id = "context-transient-stale-streaming"
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    active = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
        recovered_cache_updated_at=time.time() - 31,
    )
    prompta._active_conversations[context_id] = active

    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(
        return_value={
            "streaming": True,
            "complete": False,
            "transient": True,
            "failed": False,
            "turn_ended": False,
        }
    )
    driver.conversation_snapshot = AsyncMock()
    driver.navigate = AsyncMock()
    driver.eval = AsyncMock(return_value=f"/c/{conversation_id}")
    driver.wait_for_composer = AsyncMock()
    driver.close_context = AsyncMock()
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "active"
    assert context_id in prompta._active_conversations
    assert active.transient_recovery_attempts == 1
    driver.navigate.assert_awaited_once_with(
        f"https://chatgpt.com/c/{conversation_id}",
        context=context_id,
    )
    driver.wait_for_composer.assert_awaited_once_with(
        timeout=10.0,
        context=context_id,
    )
    driver.conversation_snapshot.assert_not_awaited()
    driver.close_context.assert_not_awaited()
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversation_reloads_stale_connection_failure_before_interrupting(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-stale-transient"
    context_id = "context-stale-transient"
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    active = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
        recovered_cache_updated_at=time.time() - 16 * 60,
    )
    prompta._active_conversations[context_id] = active

    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(
        return_value={
            "streaming": False,
            "complete": False,
            "transient": True,
            "failed": False,
        }
    )
    completed_snapshot = {
        "title": "Recovered after reload",
        "messages": [
            {"id": "u1", "role": "user", "content": "Do work"},
            {"id": "a1", "role": "assistant", "content": "Recovered answer"},
        ],
        "streaming": False,
    }
    driver.conversation_snapshot = AsyncMock(return_value=completed_snapshot)
    driver.navigate = AsyncMock()
    driver.eval = AsyncMock(return_value=f"/c/{conversation_id}")
    driver.wait_for_composer = AsyncMock()
    driver.close_context = AsyncMock()
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "active"
    assert context_id in prompta._active_conversations
    assert active.transient_recovery_attempts == 1
    driver.navigate.assert_awaited_once_with(
        f"https://chatgpt.com/c/{conversation_id}",
        context=context_id,
    )
    driver.wait_for_composer.assert_awaited_once_with(
        timeout=10.0,
        context=context_id,
    )
    driver.conversation_snapshot.assert_not_awaited()
    driver.close_context.assert_not_awaited()

    driver.conversation_activity.return_value = {
        "streaming": False,
        "complete": True,
        "transient": False,
        "failed": False,
    }
    for _ in range(4):
        await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "complete"
    assert active.transient_recovery_attempts == 0
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversation_interrupts_when_reloaded_connection_failure_persists(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-reloaded-transient"
    context_id = "context-reloaded-transient"
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    prompta._active_conversations[context_id] = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
        transient_since_epoch=time.time() - 16 * 60,
        transient_recovery_attempts=1,
    )

    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(
        return_value={
            "streaming": False,
            "complete": False,
            "transient": True,
            "failed": False,
        }
    )
    driver.conversation_snapshot = AsyncMock()
    driver.navigate = AsyncMock()
    driver.close_context = AsyncMock()
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "interrupted"
    assert context_id not in prompta._active_conversations
    driver.navigate.assert_not_awaited()
    driver.conversation_snapshot.assert_not_awaited()
    driver.close_context.assert_awaited_once_with(context_id)
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversations_fails_fast_when_webdriver_is_poisoned(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    for index in range(2):
        conversation_id = f"conversation-{index}"
        context_id = f"context-{index}"
        prompta.cache.start(
            conversation_id,
            context_id=context_id,
            job_name="",
            prompt="Do exactly one thing",
        )
        prompta._active_conversations[context_id] = ActiveConversation(
            conversation_id=conversation_id,
            context_id=context_id,
            job_name="",
            prompt="Do exactly one thing",
        )

    driver = MagicMock()
    driver.is_connected = True
    driver.needs_browser_restart = False

    async def poison_first_context(_context: str) -> dict[str, Any]:
        driver.needs_browser_restart = True
        raise RuntimeError("execute Chromium script: timed out; browser restart required")

    driver.conversation_activity = AsyncMock(side_effect=poison_first_context)
    prompta.driver = cast(Any, driver)

    with pytest.raises(RuntimeError, match="recycle browser"):
        await prompta._poll_active_conversations()

    assert driver.conversation_activity.await_count == 1
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversations_retires_closed_browser_tab(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-closed-tab"
    context_id = "context-closed-tab"
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    prompta._active_conversations[context_id] = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )

    driver = MagicMock()
    driver.is_connected = True
    driver.needs_browser_restart = False
    driver.conversation_activity = AsyncMock(
        side_effect=BrowsingContextUnavailableError(
            f"Chromium debugger target is unavailable: {context_id}"
        )
    )
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()

    assert context_id not in prompta._active_conversations
    assert prompta.cache.status(conversation_id) == "interrupted"
    assert driver.conversation_activity.await_count == 1
    assert driver.needs_browser_restart is False
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversations_reaps_tab_after_40_minutes_without_activity(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-stale-tab"
    context_id = "context-stale-tab"
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    prompta._active_conversations[context_id] = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    prompta.cache.last_message_activity_at = MagicMock(  # type: ignore[method-assign]
        return_value=time.time() - STALE_ACTIVE_TAB_SECONDS - 1
    )

    driver = MagicMock()
    driver.is_connected = True
    driver.needs_browser_restart = False
    driver.close_context = AsyncMock()
    driver.conversation_activity = AsyncMock()
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()

    assert context_id not in prompta._active_conversations
    assert prompta.cache.status(conversation_id) == "interrupted"
    driver.close_context.assert_awaited_once_with(context_id)
    driver.conversation_activity.assert_not_awaited()
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversations_reconnects_before_cache_capture(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.cache.start(
        "conversation-123",
        context_id="context-1",
        job_name="",
        prompt="Do exactly one thing",
    )
    prompta._active_conversations["context-1"] = ActiveConversation(
        conversation_id="conversation-123",
        context_id="context-1",
        job_name="",
        prompt="Do exactly one thing",
    )

    driver = MagicMock()
    driver.is_connected = False

    async def connect() -> None:
        driver.is_connected = True

    driver.connect = AsyncMock(side_effect=connect)
    driver.conversation_activity = AsyncMock(return_value={"streaming": False})
    driver.conversation_snapshot = AsyncMock(
        return_value={
            "title": "Recovered chat",
            "messages": [
                {
                    "id": "user-1",
                    "role": "user",
                    "content": "Do exactly one thing",
                    "status": "complete",
                },
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": "Done",
                    "status": "complete",
                },
            ],
            "streaming": False,
        }
    )
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()

    driver.connect.assert_awaited_once()
    driver.conversation_snapshot.assert_awaited_once_with("context-1")
    assert [message["content"] for message in prompta.cache.messages("conversation-123")] == [
        "Do exactly one thing",
        "Done",
    ]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversation_waits_for_assistant_after_latest_user(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-reply"
    context_id = "context-reply"
    waiting_snapshot = {
        "title": "Existing chat",
        "messages": [
            {"id": "user-1", "role": "user", "content": "First request", "status": "complete"},
            {
                "id": "assistant-1",
                "role": "assistant",
                "content": "First answer",
                "status": "complete",
            },
            {"id": "user-2", "role": "user", "content": "Follow-up", "status": "complete"},
        ],
        "streaming": False,
    }
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="First request",
    )
    active = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="First request",
        last_digest=prompta.cache.digest(waiting_snapshot),
        idle_polls=2,
    )
    prompta._active_conversations[context_id] = active

    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(return_value={"streaming": False})
    driver.conversation_snapshot = AsyncMock(return_value=waiting_snapshot)
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()

    assert active.idle_polls == 0
    assert active.settled_at == 0.0
    assert prompta.cache.recent_conversations()[0]["status"] == "active"

    completed_snapshot = {
        **waiting_snapshot,
        "messages": [
            *waiting_snapshot["messages"],
            {
                "id": "assistant-2",
                "role": "assistant",
                "content": "Follow-up answer",
                "status": "complete",
            },
        ],
    }
    driver.conversation_snapshot.return_value = completed_snapshot

    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()

    assert active.settled_at > 0.0
    assert prompta.cache.recent_conversations()[0]["status"] == "complete"

    # Completed tabs are only retained briefly for immediate replies; they must
    # not accumulate for tens of minutes and push headless Chromium into cgroup
    # memory reclaim while another send is starting.
    active.settled_at -= 16.0
    driver.close_context = AsyncMock()
    # Final-turn chrome/title metadata can still change after completion. That
    # must not restart the retention timer and keep the tab resident.
    driver.conversation_snapshot.return_value = {
        **completed_snapshot,
        "title": "Existing chat · final metadata",
    }
    await prompta._poll_active_conversations()

    driver.close_context.assert_awaited_once_with(context_id)
    assert context_id not in prompta._active_conversations
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversation_debounces_copy_action_when_react_end_turn_unknown(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-copy-gap"
    context_id = "context-copy-gap"
    snapshot = {
        "title": "Tool gap",
        "messages": [
            {"id": "user-1", "role": "user", "content": "Do several tool calls"},
            {"id": "assistant-1", "role": "assistant", "content": "Still working"},
        ],
        "streaming": False,
    }
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do several tool calls",
    )
    prompta.cache.write_snapshot(conversation_id, snapshot)
    active = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do several tool calls",
        last_digest=prompta.cache.digest(snapshot),
    )
    prompta._active_conversations[context_id] = active

    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(
        return_value={
            "streaming": False,
            "complete": True,
            "transient": False,
            "failed": False,
            "turn_ended": None,
        }
    )
    driver.conversation_snapshot = AsyncMock(return_value=snapshot)
    prompta.driver = cast(Any, driver)

    for _ in range(9):
        await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "active"
    assert active.settled_at == 0.0

    await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "complete"
    assert active.settled_at > 0.0
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_tool_turn_waits_for_authoritative_final_text(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-tool-missing-final"
    context_id = "context-tool-missing-final"
    source_events = [
        {
            "id": "progress-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Still working"],
            "text": "",
            "reasoning_title": "",
            "create_time": 100.0,
            "end_turn": False,
        },
        {
            "id": "call-1",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps(
                {
                    "path": "/Glass/link_123/execute_python",
                    "args": {"code": "print('done')"},
                }
            ),
            "connector_tool_payload": json.dumps({"code": "print('done')"}),
            "reasoning_title": "Checking",
            "create_time": 101.0,
            "end_turn": False,
        },
        {
            "id": "result-1",
            "role": "tool",
            "recipient": "assistant",
            "content_type": "code",
            "text": json.dumps({"text": "done"}),
            "invoked_resource": {
                "app_name": "Glass",
                "resource_uri": "/asdk_app_123/link_123/execute_python",
            },
            "create_time": 102.0,
            "end_turn": False,
        },
    ]
    snapshot = {
        "title": "Tool turn",
        "messages": [
            {"id": "user-1", "role": "user", "content": "Do work"},
            {"id": "assistant-1", "role": "assistant", "content": "Still working"},
        ],
        "source_events": source_events,
        "streaming": False,
    }
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    prompta.cache.write_snapshot(conversation_id, snapshot)
    active = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
        last_digest=prompta.cache.digest(snapshot),
    )
    prompta._active_conversations[context_id] = active

    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(
        return_value={
            "streaming": False,
            "complete": True,
            "transient": False,
            "failed": False,
            "turn_ended": None,
        }
    )
    driver.conversation_snapshot = AsyncMock(return_value=snapshot)
    driver.conversation_final_event = AsyncMock(return_value={})
    driver.navigate = AsyncMock()
    driver.eval = AsyncMock(return_value=f"/c/{conversation_id}")
    driver.wait_for_composer = AsyncMock()
    driver.close_context = AsyncMock()
    prompta.driver = cast(Any, driver)

    for _ in range(10):
        await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "active"
    assert active.settled_at == 0.0
    assert active.final_text_recovery_attempts == 1
    driver.navigate.assert_awaited_once_with(
        f"https://chatgpt.com/c/{conversation_id}",
        context=context_id,
    )
    driver.wait_for_composer.assert_awaited_once_with(
        timeout=10.0,
        context=context_id,
    )

    completed_snapshot = {
        **snapshot,
        "messages": [
            snapshot["messages"][0],
            {
                "id": "assistant-1",
                "role": "assistant",
                "content": "Still working\n\nFinished",
            },
        ],
        "source_events": [
            *source_events,
            {
                "id": "final-1",
                "role": "assistant",
                "recipient": "all",
                "content_type": "text",
                "parts": ["Finished"],
                "text": "",
                "reasoning_title": "",
                "create_time": 103.0,
                "end_turn": True,
            },
        ],
    }
    driver.conversation_snapshot.return_value = completed_snapshot
    for _ in range(11):
        await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "complete"
    parts = prompta.cache.connection.execute(
        """
        SELECT kind, content, end_turn
        FROM message_parts
        WHERE conversation_id = ?
        ORDER BY ordinal
        """,
        (conversation_id,),
    ).fetchall()
    assert ("final_text", "Finished", 1) in [tuple(part) for part in parts]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversation_marks_persistent_delivery_timeout_interrupted(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-timeout"
    context_id = "context-timeout"
    snapshot = {
        "title": "Timed out chat",
        "messages": [
            {"id": "user-1", "role": "user", "content": "Do work"},
            {"id": "assistant-1", "role": "assistant", "content": "Partial answer"},
        ],
        "streaming": False,
    }
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    prompta.cache.write_snapshot(conversation_id, snapshot)
    active = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
        last_digest=prompta.cache.digest(snapshot),
    )
    prompta._active_conversations[context_id] = active

    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(
        return_value={"streaming": False, "complete": False, "transient": False, "failed": True}
    )
    driver.conversation_snapshot = AsyncMock(return_value=snapshot)
    driver.click_delivery_retry = AsyncMock(return_value=False)
    driver.navigate = AsyncMock()
    driver.eval = AsyncMock(return_value=f"/c/{conversation_id}")
    driver.wait_for_composer = AsyncMock()
    driver.close_context = AsyncMock()
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()
    assert prompta.cache.status(conversation_id) == "active"
    assert context_id in prompta._active_conversations

    # The retry control can appear a few polls after ChatGPT first renders the
    # delivery-timeout text. Keep the tab alive while retry discovery catches up.
    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "active"
    assert context_id in prompta._active_conversations
    assert driver.click_delivery_retry.await_count == 3
    driver.close_context.assert_not_awaited()

    await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "active"
    assert context_id in prompta._active_conversations
    assert active.delivery_recovery_attempts == 1
    assert active.delivery_recovery_at > 0
    assert active.idle_polls == 0
    assert driver.click_delivery_retry.await_count == 4
    driver.click_delivery_retry.assert_awaited_with(context_id, timeout=3.0)
    driver.navigate.assert_awaited_once_with(
        f"https://chatgpt.com/c/{conversation_id}",
        context=context_id,
    )
    driver.wait_for_composer.assert_awaited_once_with(
        timeout=10.0,
        context=context_id,
    )
    driver.close_context.assert_not_awaited()

    # A reload is the last recovery step. If ChatGPT still shows the failed
    # delivery state after that grace period and retry discovery window, stop.
    active.delivery_recovery_at -= 16.0
    for _ in range(6):
        await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "interrupted"
    assert context_id not in prompta._active_conversations
    assert driver.navigate.await_count == 1
    driver.close_context.assert_awaited_once_with(context_id)
    prompta.cache.close()


@pytest.mark.asyncio
async def test_poll_active_conversation_retries_delivery_timeout_once_before_interrupting(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-timeout-retry"
    context_id = "context-timeout-retry"
    snapshot = {
        "title": "Timed out chat",
        "messages": [
            {"id": "user-1", "role": "user", "content": "Do work"},
            {"id": "assistant-1", "role": "assistant", "content": "Partial answer"},
        ],
        "streaming": False,
    }
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    prompta.cache.write_snapshot(conversation_id, snapshot)
    active = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
        last_digest=prompta.cache.digest(snapshot),
    )
    prompta._active_conversations[context_id] = active

    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(
        return_value={"streaming": False, "complete": False, "transient": False, "failed": True}
    )
    driver.conversation_snapshot = AsyncMock(return_value=snapshot)
    driver.click_delivery_retry = AsyncMock(return_value=True)
    driver.navigate = AsyncMock()
    driver.eval = AsyncMock(return_value=f"/c/{conversation_id}")
    driver.wait_for_composer = AsyncMock()
    driver.close_context = AsyncMock()
    prompta.driver = cast(Any, driver)

    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "active"
    assert context_id in prompta._active_conversations
    assert active.delivery_retry_attempts == 1
    assert active.delivery_retry_at > 0
    assert active.idle_polls == 0
    driver.click_delivery_retry.assert_awaited_once_with(context_id, timeout=3.0)
    driver.close_context.assert_not_awaited()

    # Give ChatGPT a grace period to replace the timeout UI after the trusted
    # retry click. If the same failure remains after that period, Prompta must
    # stop instead of endlessly clicking retry.
    active.delivery_retry_at -= 16.0
    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "active"
    assert context_id in prompta._active_conversations
    assert active.delivery_recovery_attempts == 1
    assert active.delivery_recovery_at > 0
    assert driver.click_delivery_retry.await_count == 1
    driver.navigate.assert_awaited_once_with(
        f"https://chatgpt.com/c/{conversation_id}",
        context=context_id,
    )
    driver.close_context.assert_not_awaited()

    active.delivery_recovery_at -= 16.0
    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()
    await prompta._poll_active_conversations()

    assert prompta.cache.status(conversation_id) == "interrupted"
    assert context_id not in prompta._active_conversations
    assert driver.click_delivery_retry.await_count == 1
    assert driver.navigate.await_count == 1
    driver.close_context.assert_awaited_once_with(context_id)
    prompta.cache.close()


@pytest.mark.asyncio
async def test_wait_for_cached_response_returns_false_after_interruption(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-interrupted"
    context_id = "context-interrupted"
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )
    prompta._active_conversations[context_id] = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Do work",
    )

    async def interrupt_on_poll() -> None:
        prompta.cache.mark_interrupted(conversation_id)
        prompta._active_conversations.clear()

    prompta._poll_active_conversations = AsyncMock(side_effect=interrupt_on_poll)  # type: ignore[method-assign]

    assert await prompta.wait_for_cached_response(conversation_id, timeout_seconds=1) is False
    prompta.cache.close()


@pytest.mark.asyncio
async def test_wait_for_cached_response_polls_until_conversation_completes(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta._active_conversations["context-1"] = ActiveConversation(
        conversation_id="conversation-123",
        context_id="context-1",
        job_name="",
        prompt="Do exactly one thing",
    )

    async def complete_on_poll() -> None:
        prompta._active_conversations.clear()

    prompta._poll_active_conversations = AsyncMock(side_effect=complete_on_poll)  # type: ignore[method-assign]

    assert await prompta.wait_for_cached_response("conversation-123", timeout_seconds=1) is True
    prompta._poll_active_conversations.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_run_does_not_abort_just_because_driver_disconnected(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    driver = MagicMock()
    driver.is_connected = False
    prompta.driver = cast(Any, driver)
    prompta._poll_active_conversations = AsyncMock()  # type: ignore[method-assign]
    prompta._drain_reply_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]
    prompta._drain_once_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]
    prompta.read_jobs = MagicMock(return_value={})  # type: ignore[method-assign]

    await prompta.run(once=True)

    prompta._poll_active_conversations.assert_awaited_once()  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_run_checks_deferred_recovery_before_scheduler_work(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta._retry_cached_recovery_if_due = AsyncMock(return_value=True)  # type: ignore[method-assign]
    prompta._poll_active_conversations = AsyncMock()  # type: ignore[method-assign]
    prompta._drain_sync_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]
    prompta._drain_reply_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]
    prompta._drain_once_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]
    prompta.read_jobs = MagicMock(return_value={})  # type: ignore[method-assign]

    await prompta.run(once=True)

    prompta._retry_cached_recovery_if_due.assert_awaited_once()  # type: ignore[attr-defined]
    prompta._poll_active_conversations.assert_awaited_once()  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_run_dispatches_due_job_before_active_poll_can_poison_browser(
    tmp_path: Path,
) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    job = PromptJob("due", "Do work", interval_seconds=0, exact_interval=True)
    driver = MagicMock()
    driver.needs_browser_restart = False
    prompta.driver = cast(Any, driver)
    order: list[str] = []

    async def run_job(*_args: Any, **_kwargs: Any) -> bool:
        order.append("job")
        return True

    async def poison_on_poll() -> None:
        order.append("poll")
        driver.needs_browser_restart = True

    prompta.read_jobs = MagicMock(return_value={"due": job})  # type: ignore[method-assign]
    prompta._ensure_initial_schedules = MagicMock()  # type: ignore[method-assign]
    prompta._run_job = AsyncMock(side_effect=run_job)  # type: ignore[method-assign]
    prompta._retry_cached_recovery_if_due = AsyncMock(return_value=False)  # type: ignore[method-assign]
    prompta._poll_active_conversations = AsyncMock(side_effect=poison_on_poll)  # type: ignore[method-assign]
    prompta._drain_reply_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]
    prompta._drain_once_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]
    prompta._drain_sync_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="recycle browser"):
        await prompta.run()

    assert order == ["job", "poll"]
    prompta._run_job.assert_awaited_once()  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_run_restarts_owned_browser_after_poisoned_bidi_session(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    driver = MagicMock()
    driver.is_connected = False
    driver.needs_browser_restart = True
    prompta.driver = cast(Any, driver)
    prompta._poll_active_conversations = AsyncMock()  # type: ignore[method-assign]
    prompta._drain_reply_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]
    prompta._drain_once_requests = AsyncMock(return_value=False)  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="recycle browser"):
        await prompta.run(once=True)

    prompta.cache.close()


@pytest.mark.asyncio
async def test_close_preserves_completed_retained_conversation(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.cache.start(
        "conversation-123",
        context_id="context-1",
        job_name="",
        prompt="Do work",
    )
    active = ActiveConversation(
        conversation_id="conversation-123",
        context_id="context-1",
        job_name="",
        prompt="Do work",
        settled_at=1.0,
    )
    prompta._active_conversations["context-1"] = active

    driver = MagicMock()
    driver.conversation_snapshot = AsyncMock(
        return_value={
            "title": "Completed",
            "messages": [
                {"id": "u1", "role": "user", "content": "Do work"},
                {"id": "a1", "role": "assistant", "content": "Done"},
            ],
            "streaming": False,
        }
    )
    driver.close = AsyncMock()
    prompta.driver = cast(Any, driver)

    await prompta.close()

    cache = ChatCache(tmp_path / "chats.sqlite3")
    conversation = cache.recent_conversations()[0]
    cache.close()
    assert conversation["status"] == "complete"


@pytest.mark.asyncio
async def test_close_skips_webdriver_flush_when_session_needs_restart(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    active = ActiveConversation(
        conversation_id="conversation-123",
        context_id="context-1",
        job_name="",
        prompt="Do work",
    )
    prompta._active_conversations["context-1"] = active

    driver = MagicMock()
    driver.needs_browser_restart = True
    driver.conversation_snapshot = AsyncMock(
        side_effect=AssertionError("poisoned WebDriver must not be queried during shutdown")
    )
    driver.close = AsyncMock()
    prompta.driver = cast(Any, driver)

    await prompta.close()

    driver.conversation_snapshot.assert_not_awaited()
    driver.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduler_once_waits_for_started_conversation_cache(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    job = PromptJob("e2e", "Do one thing", interval_seconds=0, exact_interval=True)
    prompta.read_jobs = MagicMock(return_value={"e2e": job})  # type: ignore[method-assign]
    prompta._ensure_initial_schedules = MagicMock()  # type: ignore[method-assign]

    async def start_conversation(*args: Any, **kwargs: Any) -> bool:
        prompta._active_conversations["context-1"] = ActiveConversation(
            conversation_id="conversation-123",
            context_id="context-1",
            job_name="e2e",
            prompt=job.prompt,
        )
        return True

    prompta._run_job = AsyncMock(side_effect=start_conversation)  # type: ignore[method-assign]
    prompta.wait_for_cached_response = AsyncMock(return_value=True)  # type: ignore[method-assign]

    await prompta.run(once=True)

    prompta.wait_for_cached_response.assert_awaited_once_with("conversation-123")  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_one_shot_waits_for_stream_and_persists_messages_end_to_end(tmp_path: Path) -> None:
    prompt = "Reply with exactly PROMPTA_CACHE_E2E_OK and nothing else."
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")

    class StreamingFakeDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__(prompt)
            self.snapshot_calls = 0

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            self.snapshot_calls += 1
            messages: list[dict[str, str]] = [{"id": "u1", "role": "user", "content": prompt}]
            streaming = self.snapshot_calls < 3
            if self.snapshot_calls >= 2:
                messages.append(
                    {
                        "id": "a1",
                        "role": "assistant",
                        "content": "PROMPTA_CACHE_E2E_OK",
                    }
                )
            return {
                "title": "Prompta cache E2E",
                "path": "/c/new-chat",
                "streaming": streaming,
                "messages": messages,
            }

    fake = StreamingFakeDriver()
    prompta.driver = cast(Any, fake)
    prompta.actions.ensure_high_effort = AsyncMock()  # type: ignore[method-assign]

    with patch("prompta.core.asyncio.sleep", AsyncMock()):
        conversation_id = await prompta.send_once(prompt)
        completed = await prompta.wait_for_cached_response(
            conversation_id,
            timeout_seconds=5,
        )

    assert completed is True
    rows = prompta.cache.recent_conversations()
    messages = prompta.cache.messages(conversation_id)
    assert rows[0]["status"] == "complete"
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "PROMPTA_CACHE_E2E_OK"
    assert messages[-1]["status"] == "complete"
    assert fake.snapshot_calls >= 6
    await prompta.close()


@pytest.mark.asyncio
async def test_sync_conversation_reuses_existing_active_context(tmp_path: Path) -> None:
    conversation_id = "already-live-sync-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta.cache.start(
        conversation_id,
        context_id="context-live",
        job_name="sloppatv",
        prompt="Long task",
    )
    prompta._active_conversations["context-live"] = ActiveConversation(
        conversation_id=conversation_id,
        context_id="context-live",
        job_name="sloppatv",
        prompt="Long task",
    )
    prompta.conversations.ensure_driver = AsyncMock()  # type: ignore[method-assign]

    assert await prompta.sync_conversation(conversation_id) == 1
    prompta.conversations.ensure_driver.assert_not_awaited()  # type: ignore[attr-defined]
    assert list(prompta._active_conversations) == ["context-live"]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_sync_conversation_retains_live_context_for_background_polling(
    tmp_path: Path,
) -> None:
    conversation_id = "live-sync-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="sloppatv",
        prompt="Long task",
    )

    class LiveSyncFakeDriver(FakeDriver):
        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return f"/c/{conversation_id}"

        async def activate_history_link(self, path: str) -> bool:
            return False

        async def conversation_activity(self, context: str) -> dict[str, object]:
            assert context == "context-new"
            return {"streaming": True}

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            return {
                "title": "Live sync",
                "path": f"/c/{conversation_id}",
                "streaming": False,
                "messages": [
                    {"id": "u1", "role": "user", "content": "Long task"},
                    {"id": "a1", "role": "assistant", "content": "Working"},
                ],
            }

    fake = LiveSyncFakeDriver("Long task")
    fake.close_context = AsyncMock()  # type: ignore[method-assign]
    fake.wait_for_composer = AsyncMock(
        side_effect=AssertionError("read-only sync must not wait for composer")
    )  # type: ignore[method-assign]
    prompta.driver = cast(Any, fake)

    assert await prompta.sync_conversation(conversation_id) == 2
    fake.wait_for_composer.assert_not_awaited()  # type: ignore[attr-defined]
    assert list(prompta._active_conversations) == ["context-new"]
    assert prompta.cache.recent_conversations()[0]["status"] == "active"
    fake.close_context.assert_not_awaited()  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_sync_conversation_preserves_persistent_delivery_failure(
    tmp_path: Path,
) -> None:
    conversation_id = "failed-sync-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="flux",
        prompt="Long task",
    )
    prompta.cache.mark_interrupted(conversation_id)

    class FailedSyncFakeDriver(FakeDriver):
        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return f"/c/{conversation_id}"

        async def activate_history_link(self, path: str) -> bool:
            return False

        async def conversation_activity(self, context: str) -> dict[str, object]:
            assert context == "context-new"
            return {
                "streaming": False,
                "complete": False,
                "transient": False,
                "failed": True,
            }

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            return {
                "title": "Failed sync",
                "path": f"/c/{conversation_id}",
                "streaming": False,
                "messages": [
                    {"id": "u1", "role": "user", "content": "Long task"},
                    {"id": "a1", "role": "assistant", "content": "Partial answer"},
                ],
            }

    fake = FailedSyncFakeDriver("Long task")
    fake.close_context = AsyncMock()  # type: ignore[method-assign]
    prompta.driver = cast(Any, fake)

    with (
        patch("prompta.core.asyncio.sleep", AsyncMock()),
        pytest.raises(RuntimeError, match="persistent delivery failure"),
    ):
        await prompta.sync_conversation(conversation_id)

    assert prompta.cache.status(conversation_id) == "interrupted"
    assert not prompta._active_conversations
    fake.close_context.assert_awaited_once_with("context-new")  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_status", ["active", "interrupted"])
async def test_sync_conversation_does_not_leave_phantom_active_when_probe_has_no_messages(
    tmp_path: Path,
    initial_status: str,
) -> None:
    conversation_id = "empty-sync-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="flux",
        prompt="Long task",
    )
    if initial_status == "interrupted":
        prompta.cache.mark_interrupted(conversation_id)

    class EmptySyncFakeDriver(FakeDriver):
        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return f"/c/{conversation_id}"

        async def activate_history_link(self, path: str) -> bool:
            return False

    fake = EmptySyncFakeDriver("Long task")
    fake.close_context = AsyncMock()  # type: ignore[method-assign]
    prompta.driver = cast(Any, fake)

    with (
        patch("prompta.conversation_actions._SYNC_OBSERVE_SECONDS", 0.0),
        pytest.raises(RuntimeError, match="did not expose any messages"),
    ):
        await prompta.sync_conversation(conversation_id)

    assert prompta.cache.status(conversation_id) == "interrupted"
    assert [message["content"] for message in prompta.cache.messages(conversation_id)] == [
        "Long task"
    ]
    assert not prompta._active_conversations
    fake.close_context.assert_awaited_once_with("context-new")  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_sync_conversation_waits_for_final_turn_evidence(
    tmp_path: Path,
) -> None:
    conversation_id = "unsettled-sync-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="flux",
        prompt="Long task",
    )

    class UnsettledSyncFakeDriver(FakeDriver):
        async def eval(self, expression: str) -> str:
            assert expression == "location.pathname"
            return f"/c/{conversation_id}"

        async def activate_history_link(self, path: str) -> bool:
            return False

        async def conversation_activity(self, context: str) -> dict[str, object]:
            assert context == "context-new"
            return {
                "streaming": False,
                "complete": False,
                "transient": False,
                "failed": False,
            }

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            return {
                "title": "Unsettled sync",
                "path": f"/c/{conversation_id}",
                "streaming": False,
                "messages": [
                    {"id": "u1", "role": "user", "content": "Long task"},
                    {"id": "a1", "role": "assistant", "content": "Still settling"},
                ],
            }

    fake = UnsettledSyncFakeDriver("Long task")
    fake.close_context = AsyncMock()  # type: ignore[method-assign]
    prompta.driver = cast(Any, fake)

    with patch("prompta.core.asyncio.sleep", AsyncMock()):
        assert await prompta.sync_conversation(conversation_id) == 2

    assert prompta.cache.status(conversation_id) == "active"
    assert list(prompta._active_conversations) == ["context-new"]
    fake.close_context.assert_not_awaited()  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_recover_cached_conversations_does_not_reopen_stale_active_chat(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "stale-restart-chat"
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="",
        prompt="Old work",
    )
    stale_at = time.time() - STALE_ACTIVE_TAB_SECONDS - 1
    with prompta.cache.connection:
        prompta.cache.connection.execute(
            "UPDATE conversations SET created_at = ?, updated_at = ? WHERE id = ?",
            (stale_at, stale_at, conversation_id),
        )
        prompta.cache.connection.execute(
            "UPDATE messages SET created_at = ?, updated_at = ?, activity_at = ? "
            "WHERE conversation_id = ?",
            (stale_at, stale_at, stale_at, conversation_id),
        )
    prompta.conversations.ensure_driver = AsyncMock(  # type: ignore[method-assign]
        side_effect=AssertionError("stale chats must not reopen browser tabs")
    )

    assert await prompta.recover_cached_conversations() == 0

    assert prompta.cache.status(conversation_id) == "interrupted"
    prompta.conversations.ensure_driver.assert_not_awaited()  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_recover_cached_conversations_defers_when_chrome_debugger_is_offline(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.conversations.recover_cached_conversations = AsyncMock(
        side_effect=ChromeDebuggerUnavailableError("offline")
    )
    before = time.monotonic()

    assert await prompta.recover_cached_conversations() == 0
    assert prompta._next_recovery_retry_at >= before + RESTART_RECOVERY_RETRY_SECONDS - 0.1

    prompta.cache.close()


@pytest.mark.asyncio
async def test_recover_cached_conversations_defers_transient_driver_failure(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    prompta.conversations.recover_cached_conversations = AsyncMock(
        side_effect=RuntimeError("create Playwright session: timed out; browser restart required")
    )
    before = time.monotonic()

    assert await prompta.recover_cached_conversations() == 0
    assert prompta._next_recovery_retry_at >= before + RESTART_RECOVERY_RETRY_SECONDS - 0.1

    prompta.cache.close()


@pytest.mark.asyncio
async def test_recover_cached_conversations_reattaches_streaming_chat_after_restart(
    tmp_path: Path,
) -> None:
    conversation_id = "recover-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="sloppatv",
        prompt="Keep working",
    )
    prompta.cache.write_snapshot(
        conversation_id,
        {
            "path": f"/c/{conversation_id}",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep working"},
                {"id": "a1", "role": "assistant", "content": "Still working"},
            ],
        },
    )
    prompta.cache.mark_interrupted(conversation_id)

    class RecoveryFakeDriver(FakeDriver):
        def __init__(self, prompt: str) -> None:
            super().__init__(prompt)
            self.snapshot_calls = 0

        async def eval(self, expression: str, *, context: str | None = None) -> str:
            assert expression == "location.pathname"
            assert context == "context-new"
            return f"/c/{conversation_id}"

        async def activate_history_link(self, path: str, *, context: str | None = None) -> bool:
            assert context == "context-new"
            return False

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            self.snapshot_calls += 1
            messages = []
            if self.snapshot_calls >= 3:
                messages = [
                    {"id": "u1", "role": "user", "content": "Keep working"},
                    {"id": "a1", "role": "assistant", "content": "Still working"},
                ]
            return {
                "title": "Recovered chat",
                "path": f"/c/{conversation_id}",
                "streaming": False,
                "messages": messages,
            }

    fake = RecoveryFakeDriver("Keep working")
    fake.wait_for_composer = AsyncMock(
        side_effect=AssertionError("recovery must not wait for composer")
    )  # type: ignore[method-assign]
    prompta.driver = cast(Any, fake)

    assert await prompta.recover_cached_conversations() == 1
    fake.wait_for_composer.assert_not_awaited()  # type: ignore[attr-defined]
    assert fake.snapshot_calls == 3
    assert list(prompta._active_conversations) == ["context-new"]
    assert prompta.cache.recent_conversations()[0]["status"] == "active"
    assert prompta.cache.messages(conversation_id)[-1]["status"] == "streaming"
    prompta.cache.close()


@pytest.mark.asyncio
async def test_recover_cached_conversations_reloads_slow_chat_before_interrupting(
    tmp_path: Path,
) -> None:
    conversation_id = "slow-recover-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="prompta-bugs",
        prompt="Keep checking Prompta",
    )
    prompta.cache.write_snapshot(
        conversation_id,
        {
            "path": f"/c/{conversation_id}",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep checking Prompta"},
                {"id": "a1", "role": "assistant", "content": "Still working"},
            ],
        },
    )

    class SlowRecoveryFakeDriver(FakeDriver):
        async def eval(self, expression: str, *, context: str | None = None) -> str:
            assert expression == "location.pathname"
            assert context == "context-new"
            return f"/c/{conversation_id}"

        async def activate_history_link(self, path: str, *, context: str | None = None) -> bool:
            assert context == "context-new"
            return False

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            messages: list[dict[str, str]] = []
            if len(self.navigated) >= 2:
                messages = [
                    {"id": "u1", "role": "user", "content": "Keep checking Prompta"},
                    {"id": "a1", "role": "assistant", "content": "Still working"},
                ]
            return {
                "title": "Slow recovered chat",
                "path": f"/c/{conversation_id}",
                "streaming": True,
                "messages": messages,
            }

    fake = SlowRecoveryFakeDriver("Keep checking Prompta")
    fake.close_context = AsyncMock()  # type: ignore[method-assign]
    prompta.driver = cast(Any, fake)
    original_sleep = asyncio.sleep

    async def fast_sleep(_: float) -> None:
        await original_sleep(0.002)

    with (
        patch("prompta.core._RESTART_RECOVERY_MESSAGE_TIMEOUT_SECONDS", 0.001),
        patch("prompta.core.asyncio.sleep", side_effect=fast_sleep),
    ):
        assert await prompta.recover_cached_conversations() == 1

    assert fake.navigated == [
        f"https://chatgpt.com/c/{conversation_id}",
        f"https://chatgpt.com/c/{conversation_id}",
    ]
    assert fake.navigation_contexts == ["context-new"]
    assert list(prompta._active_conversations) == ["context-new"]
    assert prompta.cache.status(conversation_id) == "active"
    fake.close_context.assert_not_awaited()  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_recover_cached_conversations_uses_history_after_direct_loads_stay_empty(
    tmp_path: Path,
) -> None:
    conversation_id = "history-recover-chat"
    target_url = f"https://chatgpt.com/c/{conversation_id}"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="quitter-translations",
        prompt="Keep translating",
    )
    prompta.cache.write_snapshot(
        conversation_id,
        {
            "path": f"/c/{conversation_id}",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep translating"},
                {"id": "a1", "role": "assistant", "content": "Still translating"},
            ],
        },
    )
    prompta.cache.mark_interrupted(conversation_id)

    class HistoryRecoveryFakeDriver(FakeDriver):
        def __init__(self, prompt: str) -> None:
            super().__init__(prompt)
            self.current_path = "/"
            self.history_activated = False
            self.history_activations: list[str] = []

        async def new_tab(self, url: str = "https://chatgpt.com/") -> str:
            self.context = "context-new"
            self.navigated.append(url)
            self.current_path = f"/c/{conversation_id}" if url == target_url else "/"
            return self.context

        async def navigate(self, url: str, *, context: str | None = None) -> None:
            assert context == "context-new"
            self.navigated.append(url)
            self.navigation_contexts.append(context)
            self.current_path = f"/c/{conversation_id}" if url == target_url else "/"

        async def eval(self, expression: str, *, context: str | None = None) -> str:
            assert expression == "location.pathname"
            assert context == "context-new"
            return self.current_path

        async def activate_history_link(self, path: str, *, context: str | None = None) -> bool:
            assert context == "context-new"
            self.history_activations.append(path)
            self.history_activated = True
            self.current_path = path
            return True

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            messages: list[dict[str, str]] = []
            if self.history_activated:
                messages = [
                    {"id": "u1", "role": "user", "content": "Keep translating"},
                    {"id": "a1", "role": "assistant", "content": "Still translating"},
                ]
            return {
                "title": "History recovered chat",
                "path": self.current_path,
                "streaming": True,
                "messages": messages,
            }

    fake = HistoryRecoveryFakeDriver("Keep translating")
    fake.close_context = AsyncMock()  # type: ignore[method-assign]
    prompta.driver = cast(Any, fake)
    original_sleep = asyncio.sleep

    async def fast_sleep(_: float) -> None:
        await original_sleep(0.002)

    with (
        patch("prompta.core._RESTART_RECOVERY_MESSAGE_TIMEOUT_SECONDS", 0.001),
        patch("prompta.core.asyncio.sleep", side_effect=fast_sleep),
    ):
        assert await prompta.recover_cached_conversations() == 1

    assert fake.navigated == [target_url, target_url, "https://chatgpt.com/"]
    assert fake.navigation_contexts == ["context-new", "context-new"]
    assert fake.history_activations == [f"/c/{conversation_id}"]
    assert list(prompta._active_conversations) == ["context-new"]
    assert prompta.cache.status(conversation_id) == "active"
    fake.close_context.assert_not_awaited()  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_recover_cached_conversation_uses_backend_final_when_dom_never_hydrates(
    tmp_path: Path,
) -> None:
    conversation_id = "backend-final-recover-chat"
    target_url = f"https://chatgpt.com/c/{conversation_id}"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    source_events = [
        {
            "id": "progress-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Still working"],
            "text": "",
            "reasoning_title": "",
            "create_time": 100.0,
            "end_turn": False,
        },
        {
            "id": "call-1",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps(
                {
                    "path": "/Glass/link_123/execute_python",
                    "args": {"code": "print('done')"},
                }
            ),
            "connector_tool_payload": json.dumps({"code": "print('done')"}),
            "reasoning_title": "Checking",
            "create_time": 101.0,
            "end_turn": False,
        },
        {
            "id": "result-1",
            "role": "tool",
            "recipient": "assistant",
            "content_type": "code",
            "text": json.dumps({"text": "done"}),
            "invoked_resource": {
                "app_name": "Glass",
                "resource_uri": "/asdk_app_123/link_123/execute_python",
            },
            "create_time": 102.0,
            "end_turn": False,
        },
    ]
    prompta.cache.start(
        conversation_id,
        context_id="old-context",
        job_name="prompta-bugs",
        prompt="Keep working",
    )
    prompta.cache.write_snapshot(
        conversation_id,
        {
            "path": f"/c/{conversation_id}",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep working"},
                {"id": "a1", "role": "assistant", "content": "Still working"},
            ],
            "source_events": source_events,
        },
    )
    prompta.cache.mark_interrupted(conversation_id)

    class BackendRecoveryFakeDriver(FakeDriver):
        def __init__(self, prompt: str) -> None:
            super().__init__(prompt)
            self.current_path = "/"

        async def new_tab(self, url: str = "https://chatgpt.com/") -> str:
            self.context = "context-new"
            self.navigated.append(url)
            self.current_path = f"/c/{conversation_id}" if url == target_url else "/"
            return self.context

        async def navigate(self, url: str, *, context: str | None = None) -> None:
            assert context == "context-new"
            self.navigated.append(url)
            self.navigation_contexts.append(context)
            self.current_path = f"/c/{conversation_id}" if url == target_url else "/"

        async def eval(self, expression: str, *, context: str | None = None) -> str:
            assert expression == "location.pathname"
            assert context == "context-new"
            return self.current_path

        async def activate_history_link(self, path: str, *, context: str | None = None) -> bool:
            assert context == "context-new"
            self.current_path = path
            return True

        async def conversation_snapshot(self, context: str) -> dict[str, Any]:
            assert context == "context-new"
            return {
                "title": "Backend recovered chat",
                "path": self.current_path,
                "streaming": False,
                "messages": [],
            }

        async def conversation_final_event(
            self,
            requested_conversation_id: str,
            *,
            context: str | None = None,
        ) -> dict[str, Any]:
            assert requested_conversation_id == conversation_id
            assert context == "context-new"
            return {
                "ok": True,
                "status": 200,
                "title": "Backend recovered chat",
                "final_event": {
                    "id": "final-1",
                    "parent_id": "result-1",
                    "role": "assistant",
                    "recipient": "all",
                    "content_type": "text",
                    "parts": ["Finished and verified."],
                    "text": "",
                    "create_time": 103.0,
                    "end_turn": True,
                },
            }

    fake = BackendRecoveryFakeDriver("Keep working")
    fake.close_context = AsyncMock()  # type: ignore[method-assign]
    prompta.driver = cast(Any, fake)
    original_sleep = asyncio.sleep

    async def fast_sleep(_: float) -> None:
        await original_sleep(0.002)

    with (
        patch("prompta.core._RESTART_RECOVERY_MESSAGE_TIMEOUT_SECONDS", 0.001),
        patch("prompta.core.asyncio.sleep", side_effect=fast_sleep),
    ):
        assert await prompta.recover_cached_conversations() == 1

    assert prompta.cache.status(conversation_id) == "complete"
    assert not prompta._active_conversations
    fake.close_context.assert_awaited_once_with("context-new")  # type: ignore[attr-defined]
    messages = prompta.cache.messages(conversation_id)
    assert "Finished and verified." in messages[-1]["content"]
    parts = prompta.cache.connection.execute(
        """
        SELECT kind, content, end_turn
        FROM message_parts
        WHERE conversation_id = ? AND message_key = ?
        ORDER BY ordinal
        """,
        (conversation_id, "a1"),
    ).fetchall()
    assert any(tuple(part) == ("final_text", "Finished and verified.", 1) for part in parts)
    assert any(str(part["kind"]) == "tool_call" for part in parts)
    prompta.cache.close()


@pytest.mark.asyncio
async def test_recover_cached_conversations_skips_already_attached_chat(tmp_path: Path) -> None:
    conversation_id = "already-attached-chat"
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta.cache.start(
        conversation_id,
        context_id="context-live",
        job_name="prompta-bugs",
        prompt="Keep working",
    )
    prompta.cache.write_snapshot(
        conversation_id,
        {
            "path": f"/c/{conversation_id}",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Keep working"},
                {"id": "a1", "role": "assistant", "content": "Still working"},
            ],
        },
    )
    prompta._active_conversations["context-live"] = ActiveConversation(
        conversation_id=conversation_id,
        context_id="context-live",
        job_name="prompta-bugs",
        prompt="Keep working",
    )
    prompta.conversations.ensure_driver = AsyncMock(  # type: ignore[method-assign]
        side_effect=AssertionError("already attached chats must not be reopened")
    )

    assert await prompta.recover_cached_conversations(limit=1) == 0
    prompta.conversations.ensure_driver.assert_not_awaited()  # type: ignore[attr-defined]
    prompta.cache.close()


@pytest.mark.asyncio
async def test_deferred_recovery_retries_one_cached_chat_when_due(tmp_path: Path) -> None:
    prompta = Prompta(PromptaConfig(jobs_file=tmp_path / "jobs.json"), "ws://unused")
    prompta._next_recovery_retry_at = 0.0
    prompta.recover_cached_conversations = AsyncMock(return_value=1)  # type: ignore[method-assign]

    assert await prompta._retry_cached_recovery_if_due() is True
    prompta.recover_cached_conversations.assert_awaited_once_with(limit=1)  # type: ignore[attr-defined]
    assert prompta._next_recovery_retry_at > 0.0
    prompta.cache.close()


@pytest.mark.asyncio
async def test_close_preserves_streaming_chat_for_restart_recovery(tmp_path: Path) -> None:
    conversation_id = "restart-chat"
    cache_path = tmp_path / "chats.sqlite3"
    prompta = Prompta(
        PromptaConfig(jobs_file=tmp_path / "jobs.json", cache_path=cache_path),
        "ws://unused",
    )
    prompta.cache.start(
        conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Long task",
    )
    prompta._active_conversations["context-1"] = ActiveConversation(
        conversation_id=conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Long task",
    )

    driver = MagicMock()
    driver.conversation_snapshot = AsyncMock(
        return_value={
            "path": f"/c/{conversation_id}",
            "streaming": True,
            "messages": [
                {"id": "u1", "role": "user", "content": "Long task"},
                {"id": "a1", "role": "assistant", "content": "Working"},
            ],
        }
    )
    driver.close = AsyncMock()
    prompta.driver = cast(Any, driver)

    await prompta.close()

    reopened = ChatCache(cache_path)
    assert reopened.recent_conversations()[0]["status"] == "active"
    reopened.close()


@pytest.mark.asyncio
async def test_open_control_connection_retries_transient_socket_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "state.json"
    socket_path = tmp_path / "control.sock"

    async def close_client(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(
        close_client,
        path=str(socket_path),
    )
    real_open = asyncio.open_unix_connection
    attempts = 0

    async def flaky_open(path: str):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise FileNotFoundError(path)
        return await real_open(path)

    monkeypatch.setattr("prompta.core.asyncio.open_unix_connection", flaky_open)
    try:
        _reader, writer = await _open_control_connection(state_path)
        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()

    assert attempts == 3


@pytest.mark.asyncio
async def test_completed_tool_enrichment_does_not_drop_fresh_final_text_from_stale_tab(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-stale-enrichment"
    prompta.cache.start(
        conversation_id,
        context_id="context-stale-enrichment",
        job_name="",
        prompt="Run a tool",
    )
    fence = chr(96) * 3
    nl = chr(10)
    generic_block = fence + "tool:tool" + nl + json.dumps({"status": "running"}) + nl + fence
    rich_block = (
        fence
        + "tool:Glass · execute_python"
        + nl
        + json.dumps({"status": "completed", "arguments": {"code": "print(1)"}})
        + nl
        + fence
    )
    final_text = "Fixed and deployed to Nox. Final verification passed."
    snapshot = {
        "title": "Tool chat",
        "path": f"/c/{conversation_id}",
        "messages": [
            {"id": "u1", "role": "user", "content": "Run a tool"},
            {
                "id": "a1",
                "role": "assistant",
                "content": generic_block + nl * 2 + final_text,
            },
        ],
        "streaming": False,
    }
    prompta.tool_enricher.enrichment = AsyncMock(return_value=([rich_block], rich_block))  # type: ignore[method-assign]

    enriched = await prompta._enrich_completed_tool_calls(conversation_id, snapshot)

    content = enriched["messages"][-1]["content"]
    assert final_text in content
    assert "Glass · execute_python" in content
    assert '"status": "running"' not in content
    prompta.cache.close()


@pytest.mark.asyncio
async def test_retained_completed_tool_enrichment_is_not_overwritten_by_browser_snapshot(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-rich-tool"
    context_id = "context-rich-tool"
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Run a tool",
    )
    fence = chr(96) * 3
    nl = chr(10)
    rich_block = (
        fence
        + "tool:Nox Python MCP · execute_python"
        + nl
        + json.dumps({"status": "completed", "arguments": {"code": "print(1)"}})
        + nl
        + fence
    )
    rich_snapshot = {
        "title": "Tool chat",
        "path": f"/c/{conversation_id}",
        "messages": [
            {"id": "u1", "role": "user", "content": "Run a tool"},
            {
                "id": "a1",
                "role": "assistant",
                "content": "Done" + nl * 2 + rich_block,
            },
        ],
        "streaming": False,
    }
    prompta.cache.write_snapshot(conversation_id, rich_snapshot, complete=True)
    active = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Run a tool",
        last_digest=prompta.cache.digest(rich_snapshot),
        settled_at=time.monotonic(),
        structured_tool_blocks=(rich_block,),
    )
    prompta._active_conversations[context_id] = active

    generic_snapshot = {
        **rich_snapshot,
        "messages": [
            rich_snapshot["messages"][0],
            {
                "id": "a1",
                "role": "assistant",
                "content": (
                    "Done"
                    + nl * 2
                    + fence
                    + "tool:tool"
                    + nl
                    + json.dumps({"status": "running"})
                    + nl
                    + fence
                ),
            },
        ],
    }
    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(
        return_value={
            "streaming": False,
            "complete": True,
            "transient": False,
            "failed": False,
        }
    )
    driver.conversation_snapshot = AsyncMock(return_value=generic_snapshot)
    driver.close_context = AsyncMock()
    prompta.driver = cast(Any, driver)
    prompta.tool_enricher.tool_blocks = AsyncMock()  # type: ignore[method-assign]

    await prompta._poll_active_conversations()

    cached = prompta.cache.messages(conversation_id)
    assert "Nox Python MCP · execute_python" in cached[-1]["content"]
    assert '"status": "running"' not in cached[-1]["content"]
    prompta.tool_enricher.tool_blocks.assert_not_awaited()  # type: ignore[attr-defined]
    driver.close_context.assert_not_awaited()
    prompta.cache.close()


@pytest.mark.asyncio
async def test_retained_completed_tool_enrichment_refreshes_late_final_text(
    tmp_path: Path,
) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    conversation_id = "conversation-late-final-text"
    context_id = "context-late-final-text"
    prompta.cache.start(
        conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Run a tool",
    )
    fence = chr(96) * 3
    nl = chr(10)
    rich_block = (
        fence
        + "tool:Nox Python MCP · execute_python"
        + nl
        + json.dumps({"status": "completed", "arguments": {"code": "print(1)"}})
        + nl
        + fence
    )
    initial_source = {
        "title": "Tool chat",
        "path": f"/c/{conversation_id}",
        "messages": [
            {"id": "u1", "role": "user", "content": "Run a tool"},
            {
                "id": "a1",
                "role": "assistant",
                "content": "Initial summary" + nl * 2 + rich_block,
            },
        ],
        "streaming": False,
    }
    cached_snapshot = {
        **initial_source,
        "messages": [
            initial_source["messages"][0],
            {
                "id": "a1",
                "role": "assistant",
                "content": rich_block + nl * 2 + "Initial summary",
            },
        ],
    }
    prompta.cache.write_snapshot(conversation_id, cached_snapshot, complete=True)
    active = ActiveConversation(
        conversation_id=conversation_id,
        context_id=context_id,
        job_name="",
        prompt="Run a tool",
        last_digest=prompta.cache.digest(initial_source),
        settled_at=time.monotonic(),
        structured_tool_blocks=(rich_block,),
    )
    prompta._active_conversations[context_id] = active

    generic_block = fence + "tool:tool" + nl + json.dumps({"status": "running"}) + nl + fence
    late_snapshot = {
        **initial_source,
        "messages": [
            initial_source["messages"][0],
            {
                "id": "a1",
                "role": "assistant",
                "content": "Late final summary" + nl * 2 + generic_block,
            },
        ],
    }
    ordered_late = rich_block + nl * 2 + "Late final summary"
    driver = MagicMock()
    driver.is_connected = True
    driver.conversation_activity = AsyncMock(
        return_value={
            "streaming": False,
            "complete": True,
            "transient": False,
            "failed": False,
        }
    )
    driver.conversation_snapshot = AsyncMock(return_value=late_snapshot)
    driver.close_context = AsyncMock()
    prompta.driver = cast(Any, driver)
    prompta.tool_enricher.enrichment = AsyncMock(return_value=([rich_block], ordered_late))  # type: ignore[method-assign]

    await prompta._poll_active_conversations()

    cached = prompta.cache.messages(conversation_id)
    assert cached[-1]["content"] == ordered_late
    assert cached[-1]["content"].endswith("Late final summary")
    assert cached[-1]["content"].index(rich_block) < cached[-1]["content"].index(
        "Late final summary"
    )
    assert prompta.tool_enricher.enrichment.await_count == 1  # type: ignore[attr-defined]

    await prompta._poll_active_conversations()

    assert prompta.tool_enricher.enrichment.await_count == 1  # type: ignore[attr-defined]
    driver.close_context.assert_not_awaited()
    prompta.cache.close()


def test_parser_accepts_pause_without_a_job_name() -> None:
    args = _parser().parse_args(["pause"])

    assert args.command == "pause"
    assert args.name is None


def test_parser_accepts_playwright_chromium_backend(tmp_path: Path) -> None:
    profile = tmp_path / "chrome-profile"
    args = _parser().parse_args(
        [
            "sync",
            "existing-chat",
            "--browser",
            "chrome",
            "--direct-browser",
            "--chrome-profile",
            str(profile),
            "--chrome-path",
            "/custom/chromium",
            "--flaresolverr-url",
            "http://127.0.0.1:8191",
        ]
    )

    assert args.browser == "chrome"
    assert args.direct_browser is True
    assert args.chrome_profile == profile
    assert args.chrome_path == "/custom/chromium"
    assert args.chrome_debugger_address is None
    assert args.flaresolverr_url == "http://127.0.0.1:8191"
    assert args.chrome_headed is False
    assert args.chrome_auth_timeout_seconds == 30.0


def test_parser_defaults_to_playwright_backend() -> None:
    args = _parser().parse_args(["sync", "existing-chat"])

    assert args.browser == "chrome"
    assert args.flaresolverr_url is None
