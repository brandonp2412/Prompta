"""Browser-verified recovery of a missing original assistant identity."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import sync_playwright

from prompta.manual_reply_dispatch import _recovery_probe

CONVERSATION = "00000000-0000-4000-8000-000000000001"
PARENT = "00000000-0000-4000-8000-000000000002"


@pytest.mark.parametrize(
    ("prompt", "copy_button", "streaming", "expected"),
    [
        ("Original prompt", True, False, PARENT),
        ("An unrelated prompt", True, False, None),
        ("Original prompt", False, False, None),
        ("Original prompt", True, True, None),
    ],
)
def test_missing_answer_recovers_only_a_completed_exact_original_turn(
    prompt: str, copy_button: bool, streaming: bool, expected: str | None,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    controls = '<button data-testid="copy-turn-action-button">Copy</button>' if copy_button else ""
    streaming_attribute = ' data-is-streaming="true"' if streaming else ""
    html = (
        '<main><div data-message-author-role="user">'
        f'<div class="whitespace-pre-wrap">{prompt}</div></div>'
        f'<div data-message-author-role="assistant" data-message-id="{PARENT}"'
        f'{streaming_attribute}><div class="markdown">Recovered final answer</div>'
        f'{controls}</div></main>'
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page()
        visits: list[str] = []

        def serve(route: object) -> None:
            from patchright.sync_api import Route

            assert isinstance(route, Route)
            visits.append(route.request.url)
            route.fulfill(status=200, content_type="text/html", body=html)

        page.route("https://chatgpt.com/**", serve)
        page.goto(f"https://chatgpt.com/c/{CONVERSATION}")
        probe = _recovery_probe(
            CONVERSATION, "", original_prompt="Original prompt", allow_partial=True,
        )
        assert page.evaluate(probe) == expected
        assert page.evaluate(_recovery_probe(
            CONVERSATION, "", original_prompt="Different original", allow_partial=True,
        )) is None
        assert visits == [f"https://chatgpt.com/c/{CONVERSATION}"]
        browser.close()


def test_missing_answer_recovery_dispatcher_uses_only_the_saved_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    from types import SimpleNamespace

    import prompta.manual_reply_dispatch as dispatch

    seen: list[str] = []

    class Store:
        def turns(self, send_id: str) -> list[dict[str, object]]:
            assert send_id == "saved-run"
            return [{
                "status": "unavailable", "conversation_id": CONVERSATION,
                "user_text": "Original prompt", "assistant_text": "",
                "message_id": "", "reply_id": "",
            }]

        def recover_original_parent(
            self, send_id: str, conversation: str, candidate: str, answer: str,
        ) -> bool:
            assert (send_id, conversation, candidate, answer) == (
                "saved-run", CONVERSATION, PARENT, "",
            )
            seen.append("saved")
            return True

    class Driver:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["ownership_prefix"] == "prompta:reply:"

        async def connect(self) -> None:
            seen.append("connect")

        async def new_tab(self, url: str) -> str:
            assert url == "https://chatgpt.com/c/" + CONVERSATION
            seen.append("exact-tab")
            return "owned"

        async def wait_for_composer(self) -> None:
            seen.append("composer")

        async def eval(self, script: str) -> str:
            assert "Original prompt" in script
            assert "__ORIGINAL_PROMPT__" not in script
            seen.append("read-only-probe")
            return PARENT

        async def close_context(self, context: str) -> None:
            assert context == "owned"
            seen.append("closed-tab")

        async def close(self) -> None:
            seen.append("closed")

    monkeypatch.setattr(dispatch, "BrowserDeliverySender", lambda *args, **kwargs: SimpleNamespace(
        runtime=SimpleNamespace(read_backoff_remaining=lambda: 0),
        profile=None, chrome_path="", debugger_address="", auth_timeout_seconds=0,
    ))
    monkeypatch.setattr(dispatch, "PlaywrightDriver", Driver)
    dispatcher = dispatch.ManualReplyDispatcher(Store(), Path("/tmp/isolated-test-state"))
    result = asyncio.run(dispatcher._recover_exact_parent("saved-run"))
    assert result == {"message_id": PARENT}
    assert seen == ["connect", "exact-tab", "composer", "read-only-probe", "saved", "closed-tab", "closed"]
