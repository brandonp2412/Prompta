"""Browser regression: layout shrink at the tail must not disable live transcript following."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import expect
from patchright.sync_api import sync_playwright as sync_patchright
from web_results_support import server

from prompta.response_capture import CaptureResult


@pytest.fixture(autouse=True)
def serve_current_worktree_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static"
    )


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_live_transcript_follows_after_layout_shrinks_at_tail(
    tmp_path: Path, width: int, height: int
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    now = time.time()
    initial = "\n\n".join(f"Paragraph {i}: " + "Visible answer. " * 10 for i in range(90))
    updated = initial + "\n\nNewest live content " + "Another sentence. " * 50
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        app.results.ensure_queued("layout-shrink", "A long answer", now=now)
        assert app.results.accept(
            "layout-shrink", "100:layout-shrink", deadline=now + 120, now=now + 1
        )
        assert app.results.write(
            "layout-shrink",
            "100:layout-shrink",
            CaptureResult("dom", "partial", initial, "conversation", "message", "parent"),
            now=now + 2,
        )
        browser = patchright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"]
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=layout-shrink")
            pane = page.locator(".chat-transcript-scroll")
            expect(pane).to_contain_text("Paragraph 89")
            page.wait_for_function("""() => {
                const p = document.querySelector('.chat-transcript-scroll');
                return p && p.scrollHeight > 2 * p.clientHeight &&
                    p.scrollHeight - p.scrollTop - p.clientHeight <= 2;
            }""")

            # A disappearing footer, a resized viewport, or a collapsed status
            # region can clamp scrollTop upwards without an upward user gesture.
            pane.evaluate("p => { p.style.paddingBottom = '160px'; p.scrollTop = p.scrollHeight; }")
            page.wait_for_timeout(150)
            before = pane.evaluate("p => p.scrollTop")
            pane.evaluate("p => { p.style.paddingBottom = ''; }")
            page.wait_for_function(
                """previous => {
                    const p = document.querySelector('.chat-transcript-scroll');
                    return p && p.scrollTop < previous - 100 &&
                        p.scrollHeight - p.scrollTop - p.clientHeight <= 2;
                }""",
                arg=before,
            )
            page.wait_for_timeout(150)

            assert app.results.write(
                "layout-shrink",
                "100:layout-shrink",
                CaptureResult("dom", "partial", updated, "conversation", "message", "parent"),
                now=now + 3,
            )
            expect(pane).to_contain_text("Newest live content", timeout=12000)
            page.wait_for_function(
                """() => {
                const p = document.querySelector('.chat-transcript-scroll');
                return p && p.scrollHeight - p.scrollTop - p.clientHeight <= 3;
            }""",
                timeout=3000,
            )
        finally:
            browser.close()
