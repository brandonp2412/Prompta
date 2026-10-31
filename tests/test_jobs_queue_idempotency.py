"""Explicit Jobs dispatch actions reconcile durable queue receipts after HTTP loss."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from patchright.sync_api import Route, expect, sync_playwright
from test_web_results import post_json, server


def test_fire_now_and_immediate_run_once_reuse_queue_request_ids(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        app.jobs.start_scheduler = lambda: True
        status, _ = post_json(port, "/api/jobs", {
            "action": "add", "name": "Receipt job", "prompt": "An interval prompt",
            "interval_minutes": 45, "schedule": "interval",
        })
        assert status == 200
        fire_id = "a" * 32
        for _ in range(2):
            status, payload = post_json(port, "/api/jobs", {
                "action": "fire_now", "name": "Receipt job", "request_id": fire_id,
            })
            assert status == 200
            assert payload["ok"] is True
        state = app.jobs.runtime.job_state("Receipt job")
        last_fired = state["last_manual_fire_at_epoch"]
        assert isinstance(last_fired, (int, float)) and last_fired > 0
        assert len(app.queue.records()) == 1

        once_id = "b" * 32
        for _ in range(2):
            status, payload = post_json(port, "/api/jobs", {
                "action": "run_once", "prompt": "One-time job prompt", "images": [],
                "delay_minutes": 0, "pin_chat": False, "request_id": once_id,
            })
            assert status == 200
            assert payload["ok"] is True
        assert len(app.queue.records()) == 2
        stored = app.queue.get("manual-" + once_id)
        assert stored is not None and stored["message"] == "One-time job prompt"

        # An already accepted ID cannot silently switch to a different job payload.
        status, _ = post_json(port, "/api/jobs", {
            "action": "run_once", "prompt": "Different prompt", "images": [],
            "delay_minutes": 0, "pin_chat": False, "request_id": once_id,
        })
        assert status == 400
        assert len(app.queue.records()) == 2


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_fire_now_lost_ack_after_reload_does_not_fire_twice(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port):
        app.jobs.start_scheduler = lambda: True
        assert app.jobs.apply("add", {
            "name": "Browser fire probe", "prompt": "One scheduled prompt",
            "interval_minutes": 60, "schedule": "interval",
        })["ok"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            posted: list[dict[str, object]] = []
            remote: list[str] = []
            page.on("request", lambda request: remote.append(request.url) if not request.url.startswith(
                f"http://127.0.0.1:{port}/"
            ) else None)

            def lose_jobs_ack(route: Route) -> None:
                if route.request.method != "POST":
                    route.continue_()
                    return
                body = json.loads(route.request.post_data or "{}")
                if body.get("action") != "fire_now":
                    route.continue_()
                    return
                posted.append(body)
                actual = route.fetch()
                assert actual.status == 200
                route.fulfill(status=503, body="Simulated lost Jobs acknowledgement")

            page.route("**/api/jobs", lose_jobs_ack)
            page.route("**/api/chats/requests/*", lambda route: route.fulfill(status=503))
            page.goto(f"http://127.0.0.1:{port}/?view=jobs")
            expect(page.get_by_role("button", name="Fire now")).to_be_visible()
            page.get_by_role("button", name="Fire now").click()
            expect(page.get_by_text("Queue receipt uncertain.", exact=False)).to_be_visible()
            assert len(posted) == 1
            assert len(app.queue.records()) == 1

            page.unroute("**/api/chats/requests/*")
            page.reload()
            page.get_by_role("button", name="Fire now").click()
            expect(page.get_by_text("Queued one fresh chat for Browser fire probe.")).to_be_visible()
            assert len(posted) == 1
            assert len(app.queue.records()) == 1
            assert remote == []
            browser.close()
