"""Browser fault injection: a lost local POST must release busy UI without replaying ChatGPT."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest
from playwright.sync_api import Route, expect, sync_playwright
from test_stage5_composer import serve_test_ui
from test_web_results import server

from prompta.reply_contracts import ManualReplyStore
from prompta.response_store import ResponseStore

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLytQAAAABJRU5ErkJggg=="
)

# Intercept only the first selected local mutation. It never reaches the test
# server, exactly like a network handoff whose outcome is not knowable to UI.
# Keep GETs and the second POST genuine to prove durable receipt reconciliation.
_STALLED_POST = """(() => {
  const realFetch = window.fetch.bind(window);
  const timeout = AbortSignal.timeout.bind(AbortSignal);
  AbortSignal.timeout = (ms) => timeout(ms >= 30000 ? 350 : ms);
  window.__postIds = [];
  window.fetch = (input, init) => {
    const url = String(input);
    if (init?.method === "POST" && url.endsWith(window.__stallRoute)) {
      const payload = JSON.parse(String(init.body));
      window.__postIds.push(payload.request_id || payload.reply_id || payload.name);
      if (window.__postIds.length === 1) {
        return new Promise((_resolve, reject) => {
          init.signal.addEventListener("abort", () => reject(init.signal.reason), { once: true });
        });
      }
    }
    return realFetch(input, init);
  };
})()"""


def _browser_executable() -> str:
    path = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not path or not Path(path).exists():
        pytest.skip("Headless Chromium unavailable")
    return path


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_stalled_fresh_send_unlocks_composer_and_reuses_exact_request(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_browser_executable(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.add_init_script("window.__stallRoute = '/api/chats';")
        page.add_init_script(_STALLED_POST)
        page.route("**/api/events", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        composer = page.get_by_role("textbox", name="Message for new chat")
        composer.fill("Synthetic timed-out receipt")
        send = page.get_by_role("button", name="Send fresh chat")
        send.click()
        expect(page.get_by_text("Queue receipt is uncertain.", exact=False)).to_be_visible()
        expect(send).to_be_enabled()
        expect(composer).to_have_value("Synthetic timed-out receipt")
        assert app.queue.records() == [], "A stalled client-side request cannot hit the server"
        receipt = page.evaluate("localStorage.getItem('prompta.pending-fresh-requests.v1')")
        assert isinstance(receipt, str)
        assert "Synthetic timed-out receipt" not in receipt

        send.click()
        page.wait_for_url("**/?view=chats&run=manual-*")
        post_ids = page.evaluate("window.__postIds")
        assert len(post_ids) == 2 and post_ids[0] == post_ids[1]
        assert len(app.queue.records()) == 1
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_stalled_queued_followup_reuses_exact_id_and_clears_busy_state(
    tmp_path: Path, width: int, height: int,
) -> None:
    results = ResponseStore(tmp_path / "chat-results.sqlite3")
    results.ensure_queued("early", "Original synthetic prompt")
    with serve_test_ui(tmp_path) as port, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_browser_executable(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.add_init_script("window.__stallRoute = '/reply-queue';")
        page.add_init_script(_STALLED_POST)
        page.route("**/api/events", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{port}/?view=chats&run=early")
        composer = page.get_by_role("textbox", name="Message for current chat")
        composer.fill("Synthetic timed-out follow-up")
        send = page.get_by_role("button", name="Send reply")
        send.click()
        expect(page.get_by_text("Queue receipt was lost.", exact=False)).to_be_visible()
        expect(send).to_be_enabled()
        expect(composer).to_have_value("Synthetic timed-out follow-up")

        send.click()
        expect(composer).to_have_value("")
        post_ids = page.evaluate("window.__postIds")
        assert len(post_ids) == 2 and post_ids[0] == post_ids[1]
        turns = ManualReplyStore(results.path).turns("early")
        assert turns is not None and len(turns) == 2
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_stalled_image_upload_restores_editor_without_sending(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_browser_executable(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.add_init_script("window.__stallRoute = '/api/images';")
        page.add_init_script(_STALLED_POST)
        page.route("**/api/events", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        composer = page.get_by_role("textbox", name="Message for new chat")
        composer.fill("Keep this unsent draft")
        page.get_by_role("textbox", name="Message for new chat").focus()
        page.get_by_label("Choose images").set_input_files(
            {"name": "tiny.png", "mimeType": "image/png", "buffer": _PNG},
        )
        expect(page.get_by_text("Image upload timed out.", exact=False)).to_be_visible()
        expect(page.get_by_text("Uploading images…")).to_have_count(0)
        expect(page.locator(".composer-preview")).to_have_count(0)
        expect(composer).to_have_value("Keep this unsent draft")
        assert app.queue.records() == []
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_failed_second_job_image_rolls_back_first_upload(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_browser_executable(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.route("**/api/events", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{port}/?view=jobs")
        page.get_by_role("button", name="Run once").first.click()
        page.locator("textarea").fill("Synthetic job image rollback probe")

        requests = [0]

        def fail_second(route: Route) -> None:
            requests[0] += 1
            if requests[0] == 2:
                route.fulfill(status=503, body="Synthetic second upload failure")
            else:
                route.continue_()

        page.route("**/api/images", fail_second)
        page.locator('input[type="file"]').set_input_files([
            {"name": "first.png", "mimeType": "image/png", "buffer": _PNG},
            {"name": "second.png", "mimeType": "image/png", "buffer": _PNG},
        ])
        expect(page.get_by_text("Image upload failed.", exact=False)).to_be_visible()
        expect(page.locator(".job-image-preview")).to_have_count(0)
        expect(page.locator("textarea")).to_have_value("Synthetic job image rollback probe")
        assert requests[0] == 2
        assert app.queue.records() == []

        page.unroute("**/api/images")
        page.locator('input[type="file"]').set_input_files(
            {"name": "retry.png", "mimeType": "image/png", "buffer": _PNG},
        )
        expect(page.locator(".job-image-preview")).to_have_count(1)
        browser.close()
