"""Browser proof that an unverified send continues only by explicit action."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import expect
from patchright.sync_api import sync_playwright as sync_patchright
from web_results_support import server


@pytest.fixture(autouse=True)
def serve_current_worktree_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static"
    )


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
@pytest.mark.parametrize("initial_status", ["unavailable", "outcome_unknown"])
def test_failed_initial_chat_explicit_continue_uses_new_id(
    tmp_path: Path,
    width: int,
    height: int,
    initial_status: str,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Headless Chromium unavailable")

    original_id = "manual-failed-original"
    original_prompt = "Preserve the exact failed message"
    with server(tmp_path) as (app, port):
        app.results.ensure_queued(original_id, original_prompt, "", now=time.time())
        if initial_status == "outcome_unknown":
            app.results.uncertain(original_id)
        else:
            app.results.unavailable(original_id)
        original_detail = app.results.detail(original_id)
        assert original_detail is not None and original_detail["user_text"] == original_prompt

        with sync_patchright() as patchright:
            browser = patchright.chromium.launch(
                executable_path=str(chromium),
                headless=True,
                args=["--no-sandbox"],
            )
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                sent_posts: list[str] = []
                page.on(
                    "request",
                    lambda request: (
                        sent_posts.append(request.post_data or "")
                        if request.url.endswith("/api/chats") and request.method == "POST"
                        else None
                    ),
                )
                page.goto(f"http://127.0.0.1:{port}/?view=chats&run={original_id}")
                retry = page.get_by_role("button", name="Continue in new chat")
                expect(retry).to_be_visible()
                expect(page.get_by_text("Nothing will be resent automatically.", exact=False)).to_be_visible()
                if initial_status == "outcome_unknown":
                    expect(page.locator(".response-state")).to_have_text("Send unverified")
                assert not sent_posts

                with page.expect_response(
                    lambda response: (
                        response.url.endswith("/api/chats") and response.request.method == "POST"
                    ),
                ) as receipt:
                    retry.click()
                assert receipt.value.status == 202
                sent_id = receipt.value.json()["send_id"]
                assert sent_id != original_id
                queued = app.queue.get(sent_id)
                assert queued is not None
                assert original_prompt in str(queued["message"])
                assert queued["message"] != original_prompt
                assert "New user message:" in str(queued["message"])
                assert len(sent_posts) == 1
                original = app.results.detail(original_id)
                assert original is not None
                assert original["status"] == initial_status
            finally:
                browser.close()


def test_stale_continue_button_does_not_resend_after_acceptance(
    tmp_path: Path,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Headless Chromium unavailable")

    original_id = "manual-stale-unverified"
    with server(tmp_path) as (app, port):
        app.results.ensure_queued(original_id, "Synthetic original request")
        app.results.uncertain(original_id)
        with sync_patchright() as patchright:
            browser = patchright.chromium.launch(
                executable_path=str(chromium), headless=True, args=["--no-sandbox"]
            )
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                posts: list[str] = []
                page.on(
                    "request",
                    lambda request: (
                        posts.append(request.post_data or "")
                        if request.url.endswith("/api/chats") and request.method == "POST"
                        else None
                    ),
                )
                page.goto(f"http://127.0.0.1:{port}/?view=chats&run={original_id}")
                button = page.get_by_role("button", name="Continue in new chat")
                expect(button).to_be_visible()

                # The server gains proof after the browser rendered its stale
                # unverified state but before the explicit Continue click.
                assert app.results.accept(
                    original_id, "capture-owner", deadline=time.time() + 100
                )
                button.click()
                page.wait_for_timeout(300)
                assert posts == []
                assert app.queue.records() == []
                saved = app.results.detail(original_id)
                assert saved is not None
                assert isinstance(saved["accepted_at"], (int, float))
                assert saved["accepted_at"] > 0
            finally:
                browser.close()
