"""Browser proof that a lost exact-reply receipt survives a page reload."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from patchright.sync_api import Route, expect, sync_playwright
from test_reply_ui_browser import CONVERSATION, seed_terminal
from test_web_results import server


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_ambiguous_exact_reply_uses_the_same_id_after_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int, height: int,
) -> None:
    executable = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not executable.is_file():
        pytest.skip("Chromium unavailable")
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static"
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        seed_terminal(app, send_id="durable-reply", missing_id=False)
        browser = playwright.chromium.launch(
            executable_path=str(executable), headless=True, args=["--no-sandbox"]
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            attempts: list[dict[str, object]] = []
            foreign: list[str] = []
            errors: list[str] = []
            page.on("request", lambda req: foreign.append(req.url) if not req.url.startswith(
                f"http://127.0.0.1:{port}/"
            ) else None)
            page.on("pageerror", lambda error: errors.append(str(error)))

            def uncertain(route: Route) -> None:
                attempts.append(json.loads(route.request.post_data or "{}"))
                route.fulfill(status=503, content_type="application/json", body='{"error":"unknown"}')

            page.route("**/api/results/durable-reply/reply-send", uncertain)
            page.route("**/api/events", lambda route: route.abort())
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=durable-reply")
            field = page.get_by_role("textbox", name="Message for current chat")
            expect(field).to_be_visible()
            field.fill("Retain this exact draft across a lost receipt")
            page.get_by_role("button", name="Send reply").click()
            expect(page.get_by_text("Reply outcome could not be confirmed.")).to_be_visible()
            assert len(attempts) == 1

            page.reload()
            field = page.get_by_role("textbox", name="Message for current chat")
            expect(field).to_have_value("Retain this exact draft across a lost receipt")
            page.get_by_role("button", name="Send reply").click()
            expect(page.get_by_text("Reply outcome could not be confirmed.")).to_be_visible()
            assert len(attempts) == 2
            assert attempts[0]["reply_id"] == attempts[1]["reply_id"]
            assert attempts[0]["conversation_id"] == CONVERSATION
            assert attempts[1]["parent_id"] == attempts[0]["parent_id"]
            assert not foreign and not errors
            assert page.evaluate("""() => JSON.stringify(localStorage)""").find(
                "Retain this exact draft across a lost receipt"
            ) >= 0  # Draft recovery is intentional and local to this browser.
            receipt = page.evaluate(
                "() => localStorage.getItem('prompta.pending-exact-replies.v1')"
            )
            assert isinstance(receipt, str)
            assert "Retain this exact draft" not in receipt
        finally:
            browser.close()
