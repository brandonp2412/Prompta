"""End-to-end proof that completed turn durations precede Copy in the transcript."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import expect
from patchright.sync_api import sync_playwright as sync_patchright
from web_results_support import server

from prompta.reply_contracts import ReplyIntent
from prompta.response_capture import CaptureResult

CONVERSATION = "00000000-0000-4000-8000-000000000001"
FIRST_ASSISTANT = "00000000-0000-4000-8000-000000000002"
FOLLOWUP_ASSISTANT = "00000000-0000-4000-8000-000000000004"
USER_MESSAGE = "00000000-0000-4000-8000-000000000003"


def test_completed_work_durations_precede_copy_without_counting_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    import prompta.web as web_module

    monkeypatch.setattr(
        web_module,
        "_STATIC_ROOT",
        Path(__file__).resolve().parents[1] / "src/static",
    )
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        app.results.ensure_queued("duration-run", "Original question", now=100)
        assert app.results.accept("duration-run", "test:owner", deadline=1000, now=110)
        assert app.results.write(
            "duration-run",
            "test:owner",
            CaptureResult(
                "sse",
                "complete",
                "Original answer",
                CONVERSATION,
                FIRST_ASSISTANT,
                USER_MESSAGE,
            ),
            now=205,
        )
        reply_id = "f" * 32
        reply = ReplyIntent(reply_id, CONVERSATION, FIRST_ASSISTANT, "Follow-up question")
        app.replies.prepare("duration-run", reply, now=250)
        assert app.replies.claim(reply_id, "test:reply", deadline=1000, now=300)
        assert app.replies.accepted(
            reply_id,
            "test:reply",
            conversation_id=CONVERSATION,
            parent_id=FIRST_ASSISTANT,
            message_id=FOLLOWUP_ASSISTANT,
            now=310,
        )
        assert app.replies.observe(
            reply_id,
            "test:reply",
            CaptureResult(
                "sse",
                "complete",
                "Follow-up answer",
                CONVERSATION,
                FOLLOWUP_ASSISTANT,
                FIRST_ASSISTANT,
            ),
            now=382,
        )

        browser = patchright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            for width in (390, 1440):
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.goto(f"http://127.0.0.1:{port}/?view=chats&run=duration-run")
                responses = page.locator(".assistant-group")
                expect(responses).to_have_count(2)
                for index, duration in enumerate(("Worked for 1m 35s", "Worked for 1m 12s")):
                    label = responses.nth(index).locator(".response-worked-duration")
                    expect(label).to_have_text(duration)
                    copy = responses.nth(index).locator(".copy-message")
                    assert copy.evaluate(
                        "node => node.previousElementSibling?.classList.contains('response-worked-duration')"
                    )
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.close()
        finally:
            browser.close()
