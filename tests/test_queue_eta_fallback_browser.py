"""Browser proof that missing queue ETAs disappear without changing queued status."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import expect
from patchright.sync_api import sync_playwright as sync_patchright
from web_results_support import server


@pytest.mark.parametrize(("width", "height"), [(390, 844), (1440, 900)])
def test_missing_queue_eta_displays_only_queued(
    tmp_path: Path, width: int, height: int
) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium or not Path(chromium).is_file():
        pytest.skip("Chromium unavailable")

    with server(tmp_path) as (app, port):
        app.queue.enqueue_manual("Chat without estimate", now=time.time(), request_id="d" * 32)
        with sync_patchright() as patchright:
            browser = patchright.chromium.launch(
                executable_path=chromium, headless=True, args=["--no-sandbox"]
            )
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.route(
                    "**/api/queue-status",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "max_workers": 1,
                                "occupied_slots": 0,
                                "estimated_run_seconds": 600,
                                "estimate_samples": 0,
                                "waiting": [],
                                "waiting_runs": [],
                            }
                        ),
                    ),
                )
                page.goto(f"http://127.0.0.1:{port}/?view=chats")
                row = page.locator(".chat-entry").filter(has_text="Chat without estimate")
                expect(row.locator(".chat-row-meta")).to_have_text("Queued")
                expect(page.get_by_text("ETA unavailable")).to_have_count(0)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            finally:
                browser.close()
