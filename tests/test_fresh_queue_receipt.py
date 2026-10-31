"""Fresh-chat queue receipts survive HTTP loss and browser reload without a duplicate send."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from patchright.sync_api import Route, expect, sync_playwright
from test_web_results import get, post_json, server


def test_exact_local_queue_receipt_is_read_only_and_idempotent(tmp_path: Path) -> None:
    request_id = "b" * 32
    with server(tmp_path) as (app, port):
        assert get(port, "/api/chats/requests/" + request_id)[0] == 404
        status, first = post_json(
            port, "/api/chats", {"request_id": request_id, "prompt": "One prompt", "images": []}
        )
        assert status == 202
        assert first["send_id"] == "manual-" + request_id
        status, receipt, headers = get(port, "/api/chats/requests/" + request_id)
        assert status == 200
        assert headers["cache-control"] == "no-store"
        assert receipt == {"send_id": first["send_id"], "status": "queued"}
        assert get(port, "/api/chats/requests/../invalid")[0] == 404
        assert get(port, "/api/chats/requests/" + "A" * 32)[0] == 400

        status, replay = post_json(
            port, "/api/chats", {"request_id": request_id, "prompt": "One prompt", "images": []}
        )
        assert status == 202
        assert replay["send_id"] == first["send_id"]
        assert len(app.queue.records()) == 1
        with patch.object(app.queue, "enqueue_manual", side_effect=AssertionError("GET must not enqueue")):
            assert get(port, "/api/chats/requests/" + request_id)[0] == 200


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_lost_receipt_is_reconciled_after_reload_without_second_post(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")

    with server(tmp_path) as (app, port):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            posts: list[str] = []
            remote: list[str] = []
            page.on("request", lambda request: remote.append(request.url) if not request.url.startswith(
                f"http://127.0.0.1:{port}/"
            ) else None)

            def lose_post_receipt(route: Route) -> None:
                posts.append(route.request.post_data or "")
                actual = route.fetch()
                assert actual.status == 202
                route.fulfill(status=503, body="Simulated lost queue acknowledgement")

            page.route("**/api/chats", lose_post_receipt)
            page.route("**/api/chats/requests/*", lambda route: route.fulfill(status=503))
            page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
            draft = page.get_by_role("textbox", name="Message for new chat")
            draft.fill("Unique receipt probe")
            page.get_by_role("button", name="Send fresh chat").click()
            expect(page.get_by_text("Queue receipt is uncertain.", exact=False)).to_be_visible()
            assert len(posts) == 1
            assert len(app.queue.records()) == 1
            saved = page.evaluate("localStorage.getItem('prompta.pending-fresh-requests.v1')")
            assert isinstance(saved, str) and "Unique receipt probe" not in saved
            assert "requestId" in saved

            page.unroute("**/api/chats/requests/*")
            page.reload()
            expect(draft).to_have_value("Unique receipt probe")
            page.get_by_role("button", name="Send fresh chat").click()
            page.wait_for_url("**/?view=chats&run=manual-*")
            expect(page.get_by_role("textbox", name="Message for current chat")).to_be_visible()
            assert len(posts) == 1, "Recovery must use a local GET, never a second POST"
            assert len(app.queue.records()) == 1
            assert page.evaluate("localStorage.getItem('prompta.pending-fresh-requests.v1')") == "[]"
            assert remote == []
            browser.close()
