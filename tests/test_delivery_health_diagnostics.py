"""Delivery readiness is honest while the existing UI health contract stays stable."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from patchright.sync_api import expect, sync_playwright
from test_web_results import get, server


def test_health_distinguishes_http_liveness_from_browser_readiness(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        for service in ("ui", "scheduler", "delivery_worker", "manual_reply_worker", "browser"):
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
        admission = health["admission"]
        assert isinstance(admission, dict) and admission.get("blocked") is False


def test_health_exposes_local_recovery_counts_without_branch_identity(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        app.results.ensure_queued("hidden-send", "Private prompt", now=10)
        assert app.results.accept("hidden-send", "123:owner", deadline=40, now=11)
        assert app.results.finish("hidden-send", "123:owner", "interrupted", now=41)
        with patch("prompta.web.browser_page_count", return_value=(True, 1)):
            status, health, body = get(port, "/api/health")
        assert status == 200
        recovery = health["recovery"]
        assert isinstance(recovery, dict)
        assert recovery.get("missing_verified_identity") == 1
        assert recovery.get("recoverable") == 0
        assert recovery.get("unresolved_reply_captures") == 0
        assert recovery.get("recoverable_reply_captures") == 0
        assert recovery.get("due_reply_recovery_probes") == 0
        backoff = recovery.get("account_read_backoff_seconds")
        assert isinstance(backoff, int) and backoff >= 0
        assert "hidden-send" not in body and "Private prompt" not in body

        app.queue_view.runtime.set_resource_admission(False, "available RAM below threshold")
        for service in ("ui", "scheduler", "delivery_worker", "manual_reply_worker", "browser"):
            assert app.health.beat(service)
        with patch("prompta.web.browser_page_count", return_value=(True, 1)):
            status, health, body = get(port, "/api/health")
        assert status == 200 and health["ready"] is True
        assert health["admission"] == {
            "blocked": True, "kind": "resource_pressure",
            "reason": "available RAM below threshold",
            "retry_after_seconds": 0, "retry_at_epoch": 0.0,
        }
        assert "Private prompt" not in body


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_jobs_shows_real_readiness_and_uncertain_queue_metrics(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port):
        app.results.ensure_queued("known", "Synthetic browser recovery", now=10)
        assert app.results.accept("known", "123:owner", deadline=50, now=11)
        assert app.results.bind_conversation_route(
            "known", "123:owner", "/c/12345678-1234-4123-8123-123456789abc", now=12,
        )
        assert app.results.finish("known", "123:owner", "interrupted", now=50)
        app.queue_view.runtime.set_resource_admission(False, "Host memory pressure")
        with (
            patch("prompta.web.browser_page_count", return_value=(False, 0)),
            patch.object(app.queue_view.runtime, "read_backoff_status", return_value=(120.0, 1)),
            sync_playwright() as playwright,
        ):
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"http://127.0.0.1:{port}/?view=jobs")
            summary = page.locator(".delivery-diagnostics summary")
            expect(summary).to_contain_text("Delivery needs attention")
            expect(summary).to_contain_text("0 pending")
            expect(summary).to_contain_text("Recovery paused")
            summary.click()
            expect(page.get_by_text("ChatGPT browser unreachable")).to_be_visible()
            expect(page.get_by_text("Unconfirmed sends", exact=True)).to_be_visible()
            expect(page.get_by_text("Dispatch paused:", exact=False)).to_be_visible()
            expect(page.get_by_text("Chats eligible for read-only recovery")).to_be_visible()
            expect(page.get_by_text("Unresolved follow-up captures")).to_be_visible()
            expect(page.get_by_text("Follow-ups eligible for recovery")).to_be_visible()
            expect(page.get_by_text("Read-only recovery is waiting", exact=False)).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            browser.close()
