"""Legacy read migration must not gate the first local Chats render."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from test_web_results import completed_run, server


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_chat_list_and_detail_load_while_legacy_import_never_returns(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "legacy-read-run", "Visible despite blocked migration", time.time())
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        remote: list[str] = []
        posts: list[str] = []
        page.on("request", lambda request: remote.append(request.url) if not request.url.startswith(
            f"http://127.0.0.1:{port}/"
        ) else None)
        page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
        page.add_init_script("""(() => {
          localStorage.setItem('prompta.local-sidebar.v1', JSON.stringify({
            baselineAt: 0,
            readRevisions: {'legacy-read-run': 'a'.repeat(64)}
          }));
          const original = window.fetch;
          window.fetch = (input, options) => {
            if (new URL(input, location.href).pathname === '/api/local-chat-reads/import') {
              window.pendingLegacyReadImport = true;
              return new Promise(() => {});
            }
            return original(input, options);
          };
        })()""")
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        expect(page.locator(".chats-list .chat-row").filter(
            has_text="Visible despite blocked migration"
        )).to_be_visible(timeout=5000)
        assert page.evaluate("window.pendingLegacyReadImport", isolated_context=False) is True
        page.locator(".chats-list .chat-row").filter(
            has_text="Visible despite blocked migration"
        ).click()
        expect(page.get_by_text("Answer for Visible despite blocked migration")).to_be_visible()
        assert remote == []
        assert not any("/api/chats" in path or "/reply" in path for path in posts)
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_failed_read_receipt_has_a_working_retry(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "read-retry-run", "Read-retry probe", time.time())
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.route("**/api/local-chat-reads", lambda route: route.fulfill(status=503))
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        page.locator(".chats-list .chat-row").filter(has_text="Read-retry probe").click()
        retry = page.locator(".chats-detail .result-error button")
        expect(retry).to_be_visible()
        # Selection also loads the detailed turn, which can trigger a second
        # initial read attempt. Let both intercepted requests settle.
        page.wait_for_timeout(400)
        expect(retry).to_be_visible()
        if width <= 680:
            expect(page.locator(".chats-sidebar")).to_have_css("visibility", "hidden")
        page.unroute("**/api/local-chat-reads")
        retry.click()
        page.wait_for_function("""async () => {
          const response = await fetch('./api/results?limit=10');
          const body = await response.json();
          const item = body.items.find(item => item.send_id === 'read-retry-run');
          return item && item.last_read_revision === item.last_reply_revision;
        }""", timeout=5000)
        expect(retry).to_have_count(0)
        browser.close()
