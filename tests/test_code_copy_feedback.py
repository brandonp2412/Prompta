"""Real-browser feedback for copying stored response code snippets."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from test_reply_ui_browser import seed_terminal
from test_web_results import server


def test_code_copy_reports_success_failure_and_resets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static",
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        send_id = "copy-code-feedback"
        seed_terminal(app, send_id=send_id, missing_id=False)
        with app.results.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE job_responses SET status = ?, assistant_text = ? WHERE send_id = ?",
                ("completed", "```js\nhello()\n```", send_id),
            )
        browser = playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.add_init_script(
                "Object.defineProperty(navigator, 'clipboard', {configurable: true, "
                "value: {writeText: async () => {}}})"
            )
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run={send_id}")
            button = page.get_by_role("button", name="Copy code")
            expect(button).to_have_text("Copy code")
            button.click()
            expect(button).to_have_text("Copied")
            expect(button).to_have_text("Copy code", timeout=4000)

            page.evaluate(
                "Object.defineProperty(navigator, 'clipboard', {configurable: true, "
                "value: {writeText: async () => {throw new Error('denied')}}})"
            , isolated_context=False)
            button.click()
            expect(button).to_have_text("Copy failed")
            expect(button).to_have_text("Copy code", timeout=4000)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)
        finally:
            browser.close()


def test_mobile_chat_sidebar_keeps_readable_status_indicators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static",
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        seed_terminal(app, send_id="readable-sidebar", missing_id=False)
        browser = playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            for width, height in [(360, 800), (390, 844), (412, 915), (1440, 900)]:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(f"http://127.0.0.1:{port}/?view=chats")
                entry = page.locator(".chat-entry").first
                expect(entry).to_be_visible()
                dimensions = entry.evaluate(
                    """node => {
                      const title = node.querySelector('.chat-row-top strong');
                      const dot = node.querySelector('.result-dot');
                      return {
                        font: parseFloat(getComputedStyle(title).fontSize),
                        dot: parseFloat(getComputedStyle(dot).width),
                        overflow: document.documentElement.scrollWidth > innerWidth,
                      };
                    }"""
                )
                assert dimensions["font"] >= 15.0
                assert dimensions["dot"] >= 9.0
                assert not dimensions["overflow"]
                page.close()
        finally:
            browser.close()
