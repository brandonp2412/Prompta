"""Regression coverage for transient delivery, partial local reads and editor navigation."""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from test_web_results import completed_run, server

from prompta.delivery_queue import DeliveryQueueStore
from prompta.delivery_worker import _deliver_one
from prompta.rate_limit import RateLimitError
from prompta.scheduler_runtime import SchedulerRuntime
from prompta.service_health import ServiceHealthStore

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Uw2FSsAAAAASUVORK5CYII="
)


def _chromium() -> str:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    return executable


def test_scheduled_prefixes_are_literals_not_sql_wildcards(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "queue.sqlite3")
    for send_id, job_name in [
        ("underscore", "stage_1-first"),
        ("other", "stageX1-first"),
        ("percent", "stage%1-first"),
        ("backslash", "stage\\1-first"),
    ]:
        queue.upsert(
            {
                "send_id": send_id,
                "message": "Scheduled test",
                "client_id": "scheduled:request:" + job_name,
                "status": "queued",
                "created_at": 10.0,
            }
        )
    assert queue.pending_scheduled_send_ids(("stage_1",)) == {"underscore"}
    assert queue.pending_scheduled_send_ids(("stage%",)) == {"percent"}
    assert queue.pending_scheduled_send_ids(("stage\\",)) == {"backslash"}
    assert queue.pending_scheduled_send_ids(()) == set()
    assert len(queue.pending_scheduled_send_ids()) == 4


def test_extended_429_never_dead_letters_a_proven_rejection(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "queue.sqlite3")
    receipt = queue.enqueue_manual("Do not lose this job", now=10.0)
    queue.upsert(
        {
            "send_id": receipt["send_id"],
            "message": "Do not lose this job",
            "client_id": receipt["client_id"],
            "status": "rate_limited",
            "retry_attempt": 12,
            "retry_at": 0.0,
            "created_at": 10.0,
        }
    )
    claimed = queue.claim_next("worker", now=time.time(), lease_seconds=30.0)
    assert claimed is not None

    def rejected(message: str, *, pin_chat: bool = False) -> None:
        del message, pin_chat
        raise RateLimitError("429 retry later", retry_after=7200)

    state = tmp_path / "state.sqlite3"
    _deliver_one(
        queue,
        rejected,
        SchedulerRuntime(state, state),
        ServiceHealthStore(tmp_path / "health.sqlite3"),
        "worker",
        claimed,
    )
    saved = queue.get(str(receipt["send_id"]))
    assert saved is not None
    assert saved["status"] == "rate_limited"
    assert saved["retry_attempt"] == 13
    retry_at = saved["retry_at"]
    assert isinstance(retry_at, (int, float))
    assert retry_at >= time.time() + 7190
    assert queue.claim_next("other", now=time.time(), lease_seconds=30.0) is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Try again in 1 day", 86400),
        ("Retry after 1.5 hours and 30 minutes", 7200),
        ("Try again in 2h 15m 20s", 8120),
        ("Wait for 0.5 minutes", 30),
        ("5 requests per 3 hours; try again in 20 minutes", 1200),
        ("Wait a few minutes", 300),
        ("Too many requests", 300),
    ],
)
def test_rate_limit_retry_text_preserves_the_full_wait(
    message: str,
    expected: int,
) -> None:
    from prompta.rate_limit import parse_retry_after

    assert parse_retry_after(message) == expected


def test_delivery_health_reports_next_future_retry(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "queue.sqlite3")
    for name, status, retry_at in (
        ("later", "rate_limited", 500.0),
        ("soon", "retrying", 250.0),
        ("already-due", "rate_limited", 150.0),
    ):
        queue.upsert(
            {
                "send_id": name,
                "message": "Queued",
                "client_id": "scheduled:request:" + name,
                "status": status,
                "retry_at": retry_at,
                "created_at": 10.0,
            }
        )
    assert queue.health_metrics(now=200.0)["next_retry_at_epoch"] == 250.0
    assert queue.health_metrics(now=600.0)["next_retry_at_epoch"] == 0.0


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
@pytest.mark.parametrize("failure", ["network", "malformed"])
def test_chat_result_survives_optional_reply_read_failure(
    tmp_path: Path,
    width: int,
    height: int,
    failure: str,
) -> None:
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "partial-local-read", "Partial read probe", time.time())
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        posts: list[str] = []
        page.on(
            "request",
            lambda request: posts.append(request.url) if request.method == "POST" else None,
        )
        page.route("**/api/events", lambda route: route.abort())
        turns_url = "**/api/results/partial-local-read/turns"
        if failure == "network":
            page.route(turns_url, lambda route: route.abort("failed"))
        else:
            page.route(
                turns_url,
                lambda route: route.fulfill(
                    status=200,
                    body="{broken",
                    headers={"content-type": "application/json"},
                ),
            )
        page.goto(f"http://127.0.0.1:{port}/?view=chats&run=partial-local-read")
        expect(page.locator(".chat-transcript-scroll").get_by_text("Answer for Partial read probe")).to_be_visible()
        expect(page.get_by_role("button", name="Retry replies")).to_be_visible()
        expect(page.get_by_role("button", name="Retry chat")).to_have_count(0)
        page.unroute(turns_url)
        page.get_by_role("button", name="Retry replies").click()
        expect(page.get_by_role("button", name="Retry replies")).to_have_count(0)
        assert all(url.endswith("/api/local-chat-reads") for url in posts)
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_old_job_image_upload_cannot_reappear_in_reopened_editor(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.add_init_script("""(() => {
          const original = window.fetch.bind(window);
          window.uploadAborted = false;
          window.fetch = (resource, options) => {
            if (new URL(resource, location.href).pathname === '/api/images') {
              return new Promise((resolve, reject) => {
                options.signal.addEventListener('abort', () => {
                  window.uploadAborted = true;
                  reject(new DOMException('Cancelled', 'AbortError'));
                }, { once: true });
                window.finishOldUpload = () => resolve(new Response(JSON.stringify({
                  image: {ref: 'a'.repeat(64), name: 'old.png', url: './api/images/' + 'a'.repeat(64)}
                }), {status: 200, headers: {'content-type': 'application/json'}}));
              });
            }
            return original(resource, options);
          };
        })()""")
        page.goto(f"http://127.0.0.1:{port}/?view=jobs")
        page.get_by_role("button", name="New job").click()
        page.locator(".job-image-picker input[type=file]").set_input_files(
            {"name": "old.png", "mimeType": "image/png", "buffer": PNG}
        )
        expect(page.get_by_text("Uploading…")).to_be_visible()
        page.get_by_role("button", name="Cancel").click()
        expect(page.get_by_role("button", name="New job")).to_be_visible()
        assert page.evaluate("window.uploadAborted", isolated_context=False) is True
        page.get_by_role("button", name="New job").click()
        expect(page.get_by_role("button", name="Add images")).to_be_enabled()
        expect(page.locator(".job-image-preview")).to_have_count(0)
        page.evaluate("window.finishOldUpload?.()", isolated_context=False)
        expect(page.locator(".job-image-preview")).to_have_count(0)
        browser.close()


@pytest.mark.parametrize("width,height", [(360, 800), (390, 844), (412, 915), (680, 900)])
def test_mobile_job_filters_are_discoverable_without_sideways_scroll(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"http://127.0.0.1:{port}/?view=jobs")
        filters = page.get_by_role("group", name="Filter jobs")
        expect(filters.locator("button")).to_have_count(5)
        dimensions = filters.evaluate("""element => {
          const outer = element.getBoundingClientRect();
          return {
            width: element.clientWidth,
            scrollWidth: element.scrollWidth,
            visible: [...element.querySelectorAll('button')].every(button => {
              const box = button.getBoundingClientRect();
              return box.left >= outer.left - 1 && box.right <= outer.right + 1;
            })
          };
        }""")
        assert dimensions["scrollWidth"] <= dimensions["width"] + 1
        assert dimensions["visible"]
        expect(page.get_by_role("button", name="Repeating jobs")).to_be_visible()
        expect(page.get_by_role("button", name="Clear all jobs")).to_have_count(0)
        browser.close()
