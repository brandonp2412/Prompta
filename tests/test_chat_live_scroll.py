"""Live transcript refresh must not pull a reader away from older messages."""

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
def test_live_refresh_respects_upward_scroll_during_request(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    now = time.time()
    initial = "\n\n".join(f"Initial paragraph {i}: " + "A long answer. " * 8 for i in range(130))
    appended = (
        initial
        + "\n\n"
        + "\n\n".join(f"New paragraph {i}: " + "Fresh response text. " * 8 for i in range(40))
    )
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        app.results.ensure_queued("live-scroll", "Long response", now=now)
        assert app.results.accept("live-scroll", "100:live-scroll", deadline=now + 120, now=now + 1)
        assert app.results.write(
            "live-scroll",
            "100:live-scroll",
            CaptureResult("dom", "partial", initial, "conversation", "message", "parent"),
            now=now + 2,
        )
        browser = patchright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=live-scroll")
            pane = page.locator(".chat-transcript-scroll")
            expect(pane).to_contain_text("Initial paragraph 129")
            page.wait_for_function("""() => {
                const pane = document.querySelector('.chat-transcript-scroll');
                return pane && pane.scrollHeight > 2 * pane.clientHeight &&
                    pane.scrollHeight - pane.scrollTop - pane.clientHeight <= 2;
            }""")
            # Make the next five-second poll slow, so the user can move toward
            # history AFTER the controller has already decided whether to follow.
            page.evaluate(
                """() => {
                const originalFetch = window.fetch.bind(window);
                window.__delayedRefreshStarted = false;
                window.__delayedOnce = false;
                window.fetch = (resource, options) => {
                    const url = String(resource);
                    if (!window.__delayedOnce && url.endsWith('/api/results/live-scroll')) {
                        window.__delayedOnce = true;
                        window.__delayedRefreshStarted = true;
                        return new Promise(resolve => setTimeout(
                            () => resolve(originalFetch(resource, options)), 850
                        ));
                    }
                    return originalFetch(resource, options);
                };
            }""",
                isolated_context=False,
            )
            assert app.results.write(
                "live-scroll",
                "100:live-scroll",
                CaptureResult("dom", "partial", appended, "conversation", "message", "parent"),
                now=now + 3,
            )
            page.wait_for_function("window.__delayedRefreshStarted", timeout=12000)
            # Move only 18px upward: close enough to the tail that the old
            # 96px distance heuristic would forcibly snap it back down.
            pane.evaluate(
                "node => { node.scrollTop = node.scrollHeight - node.clientHeight - 18; }"
            )
            page.wait_for_function("""() => {
                const pane = document.querySelector('.chat-transcript-scroll');
                return pane && pane.scrollHeight - pane.scrollTop - pane.clientHeight >= 16;
            }""")
            top_before_wheel = pane.evaluate("node => node.scrollTop")
            page.mouse.move(width * 0.7, height * 0.45)
            page.mouse.wheel(0, -10)
            page.wait_for_function(
                """previous => {
                const pane = document.querySelector('.chat-transcript-scroll');
                return pane && pane.scrollTop <= previous - 8;
            }""",
                arg=top_before_wheel,
            )
            top_before = pane.evaluate("node => node.scrollTop")
            expect(pane).to_contain_text("New paragraph 39", timeout=12000)
            page.wait_for_timeout(250)
            state = pane.evaluate("""node => ({
                top: node.scrollTop,
                gap: node.scrollHeight - node.scrollTop - node.clientHeight,
            })""")
            assert abs(state["top"] - top_before) <= 5, state
            assert state["gap"] > 100, state

            # Explicitly returning to the bottom re-enables following.
            pane.evaluate("node => { node.scrollTop = node.scrollHeight; }")
            page.wait_for_function("""() => {
                const pane = document.querySelector('.chat-transcript-scroll');
                return pane && pane.scrollHeight - pane.scrollTop - pane.clientHeight <= 2;
            }""")
            more = appended + "\n\nNewest content after rejoining tail " + "More text. " * 40
            assert app.results.write(
                "live-scroll",
                "100:live-scroll",
                CaptureResult("dom", "partial", more, "conversation", "message", "parent"),
                now=now + 4,
            )
            expect(pane).to_contain_text("Newest content after rejoining tail", timeout=12000)
            page.wait_for_function("""() => {
                const pane = document.querySelector('.chat-transcript-scroll');
                return pane && pane.scrollHeight - pane.scrollTop - pane.clientHeight <= 3;
            }""")
        finally:
            browser.close()
