"""Browser resilience when locally stored reply turns briefly fail to load."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import Route, expect, sync_playwright
from web_results_support import completed_run, server


@pytest.mark.parametrize("width,height", [(360, 800), (390, 844), (412, 915), (1440, 900)])
@pytest.mark.parametrize("failure_mode", ["http", "network", "invalid_json"])
def test_transient_turn_outage_keeps_confirmed_reply_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int, height: int,
    failure_mode: str,
) -> None:
    executable = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not executable.is_file():
        pytest.skip("Chromium unavailable")
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static"
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "turn-outage-run", "Private thread", time.time())
        browser = playwright.chromium.launch(
            executable_path=str(executable), headless=True, args=["--no-sandbox"]
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            fail = False
            writes: list[str] = []
            errors: list[str] = []
            page.on("request", lambda req: writes.append(req.url) if req.method == "POST" else None)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/api/events", lambda route: route.abort())

            def turns_route(route: Route) -> None:
                if fail:
                    if failure_mode == "network":
                        route.abort("failed")
                    elif failure_mode == "invalid_json":
                        route.fulfill(status=200, content_type="application/json", body="{broken")
                    else:
                        route.fulfill(status=503)
                else:
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({"turns": [
                            {"reply_id": "", "user_text": "Private thread",
                             "assistant_text": "First saved response", "status": "completed",
                             "created_at": 1, "updated_at": 2},
                            {"reply_id": "reply-2", "user_text": "Private follow-up",
                             "assistant_text": "Second saved response", "status": "completed",
                             "created_at": 3, "updated_at": 4},
                        ]}),
                    )

            page.route("**/api/results/turn-outage-run/turns", turns_route)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=turn-outage-run")
            expect(page.get_by_text("Second saved response")).to_be_visible()
            fail = True
            page.evaluate("window.dispatchEvent(new Event('online'))")
            expect(page.get_by_role("button", name="Retry replies")).to_be_visible()
            expect(page.get_by_text("Second saved response")).to_be_visible()
            fail = False
            # A simultaneous local refresh can recover the turns before a user
            # reaches Retry. Click it if still present, accepting either path.
            page.evaluate("""() => {
                const retry = [...document.querySelectorAll('button')].find(
                    button => button.textContent?.trim() === 'Retry replies'
                );
                retry?.click();
            }""")
            expect(page.get_by_role("button", name="Retry replies")).to_have_count(0)
            expect(page.get_by_text("Second saved response")).to_be_visible()
            # Opening a local chat may persist its read receipt; never dispatch a reply.
            assert all(url.endswith("/api/local-chat-reads") for url in writes)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            assert not errors
        finally:
            browser.close()
