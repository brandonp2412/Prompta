from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import expect
from patchright.sync_api import sync_playwright as sync_patchright
from web_results_support import completed_run, server


@pytest.fixture(autouse=True)
def serve_current_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.web as web_module

    monkeypatch.setattr(web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static")


def test_touch_swipes_open_and_close_sidebar_without_network_mutation(tmp_path: Path) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        completed_run(app, "swipe-alpha", "Swipe Test", 100)
        browser = patchright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"]
        )
        try:
            page = browser.new_page(
                viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
            )
            posts: list[str] = []
            page.on(
                "request",
                lambda request: posts.append(request.url)
                if request.method == "POST"
                and ("/api/chats" in request.url or "/reply-" in request.url)
                else None,
            )
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=swipe-alpha")
            expect(page.get_by_role("button", name="Back to chats")).to_be_visible()
            page.wait_for_timeout(100)
            expect(page.locator(".chats-layout.drawer-open")).to_have_count(0)
            cdp = page.context.new_cdp_session(page)

            def swipe(xs: tuple[int, ...]) -> None:
                for index, x in enumerate(xs):
                    mode = "touchStart" if index == 0 else "touchMove"
                    cdp.send("Input.dispatchTouchEvent", {
                        "type": mode, "touchPoints": [{"x": x, "y": 450}],
                    })
                    page.wait_for_timeout(30)
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})

            swipe((20, 80, 150, 230))
            expect(page.locator(".chats-layout.drawer-open")).to_be_visible()
            swipe((230, 180, 100, 20))
            expect(page.locator(".chats-layout.drawer-open")).to_have_count(0)
            assert posts == []
        finally:
            browser.close()
