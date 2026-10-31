"""Browser proof that transient queue failures remain visible and retryable."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from web_results_support import server


@pytest.mark.parametrize(("width", "height"), [(390, 844), (1440, 900)])
def test_queue_estimate_failure_and_manual_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int, height: int
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    import prompta.web as web_module

    monkeypatch.setattr(web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static")
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"]
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route(
                "**/api/queue-status",
                lambda route: route.fulfill(status=500, body="Temporary gateway failure"),
            )
            page.goto(f"http://127.0.0.1:{port}/?view=jobs")
            warning = page.get_by_text("Queue position and ETA are temporarily unavailable.")
            expect(warning).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")

            page.unroute("**/api/queue-status")
            page.get_by_role("button", name="Retry queue estimates").click()
            expect(warning).to_have_count(0)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        finally:
            browser.close()
