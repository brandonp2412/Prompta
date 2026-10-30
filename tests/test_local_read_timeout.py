"""Read-only local API stalls must recover without freezing the UI."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_web_results import completed_run, server


def _chromium() -> str:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    return executable


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_hung_local_results_get_times_out_then_retries(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "stalled-read-run", "Stalled local read", time.time())
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        remote: list[str] = []
        writes: list[str] = []
        page.on("request", lambda req: remote.append(req.url) if not req.url.startswith(
            f"http://127.0.0.1:{port}/"
        ) else None)
        page.on("request", lambda req: writes.append(req.url) if req.method == "POST" else None)
        # Keep this test's recovery explicitly user-triggered, without a live
        # SSE sync removing the Retry control between visibility and click.
        page.route("**/api/events", lambda route: route.abort())
        page.add_init_script("""(() => {
          const timeout = AbortSignal.timeout.bind(AbortSignal);
          AbortSignal.timeout = () => timeout(100);
          const original = window.fetch;
          window.blockLocalResults = true;
          window.fetch = (input, options) => {
            if (window.blockLocalResults && new URL(input, location.href).pathname === '/api/results') {
              return new Promise((resolve, reject) => {
                options.signal.addEventListener('abort', () =>
                  reject(new DOMException('Local read timed out', 'AbortError')), {once: true});
              });
            }
            return original(input, options);
          };
        })()""")
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        expect(page.get_by_role("button", name="Retry chats")).to_be_visible(timeout=5000)
        page.evaluate("window.blockLocalResults = false")
        # A disconnected-stream repair can finish between the Retry control
        # appearing and Playwright waiting for its animation to stabilize.
        # Click if still present; either path must restore the local chat.
        page.evaluate("""() => {
          const retry = Array.from(document.querySelectorAll('button')).find(
            (button) => button.textContent?.trim() === 'Retry chats'
          );
          retry?.click();
        }""")
        expect(page.locator(".chats-list .chat-row").filter(has_text="Stalled local read")).to_be_visible()
        assert remote == [] and writes == []
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_failed_queue_status_is_labeled_stale_and_can_recover(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.route("**/api/queue-status", lambda route: route.fulfill(status=503))
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        expect(page.get_by_role("button", name="Retry queue status")).to_be_visible()
        expect(page.get_by_text("Waiting-job status may be out of date.")).to_be_visible()
        page.unroute("**/api/queue-status")
        page.get_by_role("button", name="Retry queue status").click()
        expect(page.get_by_role("button", name="Retry queue status")).to_have_count(0)
        browser.close()
