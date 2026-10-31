"""Browser faults: committed queue receipts survive misleading HTTP conflicts."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from patchright.sync_api import Route, expect, sync_playwright
from test_reply_ui_browser import CONVERSATION, seed_terminal
from web_results_support import server

CHROMIUM = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_fresh_chat_committed_before_http_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    width: int,
    height: int,
) -> None:
    if not CHROMIUM.is_file():
        pytest.skip("Chromium unavailable")
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module,
        "_STATIC_ROOT",
        Path(__file__).resolve().parents[1] / "src/static",
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(CHROMIUM),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            posted: list[str] = []

            def conflict_after_commit(route: Route) -> None:
                posted.append(route.request.post_data or "")
                response = route.fetch()
                assert response.status == 202
                route.fulfill(
                    status=409,
                    content_type="application/json",
                    body='{"error":"Proxy reported a conflict"}',
                )

            page.route("**/api/chats", conflict_after_commit)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
            field = page.get_by_role("textbox", name="Message for new chat")
            field.fill("Unique immutable queue ID")
            page.get_by_role("button", name="Send fresh chat").click()
            page.wait_for_url("**/?view=chats&run=manual-*", timeout=10000)
            assert len(posted) == 1
            assert len(app.queue.records()) == 1
            assert (
                page.evaluate("localStorage.getItem('prompta.pending-fresh-requests.v1')") == "[]"
            )
        finally:
            browser.close()


def test_exact_reply_committed_receipt_survives_http_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not CHROMIUM.is_file():
        pytest.skip("Chromium unavailable")
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module,
        "_STATIC_ROOT",
        Path(__file__).resolve().parents[1] / "src/static",
    )
    send_id = "conflicted-reply"
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        seed_terminal(app, send_id=send_id, missing_id=False)
        browser = playwright.chromium.launch(
            executable_path=str(CHROMIUM),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            posted: list[dict[str, object]] = []

            def conflict_after_commit(route: Route) -> None:
                payload = json.loads(route.request.post_data or "{}")
                assert isinstance(payload, dict)
                posted.append(payload)
                route.fulfill(
                    status=409,
                    content_type="application/json",
                    body='{"error":"Proxy reported a conflict"}',
                )

            def durable_receipt(route: Route) -> None:
                # The local record is already committed, with exactly the ID and
                # immutable payload from the single explicit user click.
                if not posted:
                    route.continue_()
                    return
                payload = posted[0]
                saved = route.fetch().json()
                assert isinstance(saved, dict) and isinstance(saved.get("turns"), list)
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "turns": [
                                *saved["turns"],
                                {
                                    "send_id": send_id,
                                    "reply_id": payload["reply_id"],
                                    "conversation_id": payload["conversation_id"],
                                    "parent_id": payload["parent_id"],
                                    "user_text": payload["text"],
                                    "status": "prepared",
                                    "queued_by_user": True,
                                },
                            ]
                        }
                    ),
                )

            page.route(f"**/api/results/{send_id}/reply-send", conflict_after_commit)
            page.route(f"**/api/results/{send_id}/turns", durable_receipt)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run={send_id}")
            expect(page.get_by_role("link", name="Open exact chat in ChatGPT")).to_have_attribute(
                "href",
                "https://chatgpt.com/c/" + CONVERSATION,
            )
            field = page.get_by_role("textbox", name="Message for current chat")
            field.fill("Verify the local receipt")
            page.get_by_role("button", name="Send reply").click()
            expect(field).to_have_value("")
            assert len(posted) == 1
        finally:
            browser.close()
