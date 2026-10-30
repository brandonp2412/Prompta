from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_web_results import server


@pytest.mark.parametrize(("width", "height"), [(390, 844), (1440, 900)])
def test_jobs_table_sorts_next_run_before_pagination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int, height: int
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    import prompta.web as web_module

    monkeypatch.setattr(web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static")
    jobs: list[dict[str, object]] = []
    for index in range(14):
        next_due = 1_800_000_000 + (12 - index) * 60
        jobs.append({
            "name": f"Job-{index:02}",
            "created_order": index,
            "prompt": "Synthetic scheduling proof",
            "images": [],
            "status": "pending",
            "status_message": "",
            "paused": index == 12,
            "run_at_epoch": next_due if index == 11 else None,
            "pin_chat": False,
            "daily_at": "08:00" if index == 8 else None,
            "interval_minutes": 1 if index == 0 else 40,
            "exact_interval": False,
            "source_revision": "",
            "next_due_at_epoch": 0 if index == 13 else next_due,
            "last_sent_at": 0,
            "last_uncertain_send_at": 0,
        })

    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"]
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route(
                "**/api/jobs",
                lambda route: route.fulfill(
                    status=200, content_type="application/json", body=json.dumps({"jobs": jobs})
                ),
            )
            page.goto(f"http://127.0.0.1:{port}/?view=jobs", wait_until="domcontentloaded")
            first_page = [f"Job-{index:02}" for index in range(11, 1, -1)]
            expect(page.locator(".job-row")).to_have_count(10)
            assert page.locator(".job-row .job-name").all_text_contents() == first_page
            page.get_by_role("button", name="Next", exact=True).click()
            expect(page.locator(".job-row")).to_have_count(4)
            assert page.locator(".job-row .job-name").all_text_contents() == [
                "Job-01", "Job-00", "Job-13", "Job-12"
            ]
            jobs[0]["next_due_at_epoch"] = 1_700_000_000
            page.get_by_role("button", name="Refresh jobs", exact=True).click()
            page.get_by_role("button", name="Previous", exact=True).click()
            expect(page.locator(".job-row .job-name").first).to_have_text("Job-00")
        finally:
            browser.close()
