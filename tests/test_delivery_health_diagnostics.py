"""Delivery readiness is honest while the existing UI health contract stays stable."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from playwright.sync_api import expect, sync_playwright
from test_web_results import get, server


def test_health_distinguishes_http_liveness_from_browser_readiness(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        for service in ("ui", "scheduler", "delivery_worker", "browser"):
            assert app.health.beat(service)
        with patch("prompta.web.browser_page_count", return_value=(False, 0)):
            status, health, _ = get(port, "/api/health")
        assert status == 200
        assert health["ok"] is True  # Existing external watchdog contract.
        assert health["ready"] is False
        issues = health["issues"]
        assert isinstance(issues, list)
        assert "ChatGPT browser unreachable" in issues

        with patch("prompta.web.browser_page_count", return_value=(True, 2)):
            status, health, _ = get(port, "/api/health")
        assert status == 200
        assert health["ready"] is True
        assert health["issues"] == []
        assert health["browser"] == {"reachable": True, "page_count": 2}


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_jobs_shows_real_readiness_and_uncertain_queue_metrics(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port):
        with patch("prompta.web.browser_page_count", return_value=(False, 0)), sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"http://127.0.0.1:{port}/?view=jobs")
            summary = page.locator(".delivery-diagnostics summary")
            expect(summary).to_contain_text("Delivery needs attention")
            expect(summary).to_contain_text("0 pending")
            summary.click()
            expect(page.get_by_text("ChatGPT browser unreachable")).to_be_visible()
            expect(page.get_by_text("Unconfirmed sends", exact=True)).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            browser.close()
