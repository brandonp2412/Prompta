"""Browser proof that a failed initial chat can only be resent by an explicit action."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from test_web_results import server


@pytest.fixture(autouse=True)
def serve_current_worktree_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.web as web_module

    monkeypatch.setattr(web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static")


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_failed_initial_chat_explicit_retry_uses_new_id(
    tmp_path: Path, width: int, height: int,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Headless Chromium unavailable")

    original_id = "manual-failed-original"
    original_prompt = "Preserve the exact failed message"
    with server(tmp_path) as (app, port):
        app.results.ensure_queued(original_id, original_prompt, "", now=time.time())
        app.results.unavailable(original_id)
        original_detail = app.results.detail(original_id)
        assert original_detail is not None and original_detail["user_text"] == original_prompt

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=str(chromium), headless=True, args=["--no-sandbox"],
            )
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                sent_posts: list[str] = []
                page.on(
                    "request",
                    lambda request: sent_posts.append(request.post_data or "")
                    if request.url.endswith("/api/chats") and request.method == "POST"
                    else None,
                )
                page.goto(f"http://127.0.0.1:{port}/?view=chats&run={original_id}")
                retry = page.get_by_role("button", name="Retry original prompt in new chat")
                expect(retry).to_be_visible()
                expect(page.get_by_text("could duplicate it.", exact=False)).to_be_visible()
                assert not sent_posts

                with page.expect_response(
                    lambda response: response.url.endswith("/api/chats")
                    and response.request.method == "POST",
                ) as receipt:
                    retry.click()
                assert receipt.value.status == 202
                sent_id = receipt.value.json()["send_id"]
                assert sent_id != original_id
                queued = app.queue.get(sent_id)
                assert queued is not None
                assert queued["message"] == original_prompt
                assert len(sent_posts) == 1
                original = app.results.detail(original_id)
                assert original is not None
                assert original["status"] == "unavailable"
            finally:
                browser.close()
