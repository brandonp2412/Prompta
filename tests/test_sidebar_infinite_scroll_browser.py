"""The sidebar loads older chats without a pagination control."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from patchright.sync_api import Route, expect
from patchright.sync_api import sync_playwright as sync_patchright
from web_results_support import server


@pytest.mark.parametrize("width,height", [(320, 700), (390, 844), (412, 915), (1440, 900)])
def test_scroll_loads_older_chats_without_pagination_button(
    tmp_path: Path, width: int, height: int
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    def chat(index: int) -> dict[str, object]:
        return {
            "send_id": f"scroll-test-{index:03d}",
            "job_name": "",
            "title": f"Scrollable chat {index:03d}",
            "preview": "Answer",
            "status": "completed",
            "has_response": True,
            "last_reply_revision": "",
            "last_read_revision": "",
            "last_reply_at": index,
            "created_at": index,
            "updated_at": index,
            "finished_at": index,
        }

    offsets: list[int] = []
    with server(tmp_path) as (_app, port), sync_patchright() as patchright:
        browser = patchright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"]
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())

            def results(route: Route) -> None:
                offset = int(parse_qs(urlparse(route.request.url).query).get("offset", ["0"])[0])
                offsets.append(offset)
                items = [chat(100)] if offset else [chat(index) for index in range(100)]
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"items": items, "total": 101}),
                )

            page.route("**/api/results?*", results)
            page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="domcontentloaded")
            rows = page.locator(".chats-list .chat-row")
            expect(rows).to_have_count(100)
            expect(page.get_by_role("button", name="Load more chats")).to_have_count(0)
            page.locator(".chats-list").evaluate(
                "pane => { pane.scrollTop = pane.scrollHeight; pane.dispatchEvent(new Event('scroll')); }"
            )
            expect(rows).to_have_count(101)
            assert offsets.count(100) == 1
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            browser.close()


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_invalid_older_page_retry_restarts_from_first_page(
    tmp_path: Path, width: int, height: int
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    requests: list[int] = []
    stale_page = True
    with server(tmp_path) as (_app, port), sync_patchright() as patchright:
        browser = patchright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"]
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())

            def results(route: Route) -> None:
                offset = int(parse_qs(urlparse(route.request.url).query).get("offset", ["0"])[0])
                requests.append(offset)
                items = (
                    []
                    if stale_page and offset == 100
                    else [chat(index) for index in range(offset, min(offset + 100, 150))]
                )
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"items": items, "total": 150}),
                )

            def chat(index: int) -> dict[str, object]:
                return {
                    "send_id": f"retry-chat-{index:03d}",
                    "job_name": "",
                    "title": f"Retry chat {index:03d}",
                    "preview": "Answer",
                    "status": "completed",
                    "has_response": True,
                    "last_reply_revision": "",
                    "last_read_revision": "",
                    "last_reply_at": index,
                    "created_at": index,
                    "updated_at": index,
                    "finished_at": index,
                }

            page.route("**/api/results?*", results)
            page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="domcontentloaded")
            rows = page.locator(".chats-list .chat-row")
            expect(rows).to_have_count(100)
            page.locator(".chats-list").evaluate(
                "pane => { pane.scrollTop = pane.scrollHeight; pane.dispatchEvent(new Event('scroll')); }"
            )
            retry = page.get_by_role("button", name="Retry loading older chats")
            expect(retry).to_be_visible()
            assert requests == [0, 100]

            stale_page = False
            retry.click()
            expect(retry).to_have_count(0)
            assert requests == [0, 100, 0]
            page.locator(".chats-list").evaluate(
                "pane => { pane.scrollTop = pane.scrollHeight; pane.dispatchEvent(new Event('scroll')); }"
            )
            expect(rows).to_have_count(150)
            assert requests == [0, 100, 0, 100]
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            browser.close()
