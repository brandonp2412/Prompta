"""Small-screen and keyboard regression checks for the compact Prompta sidebar footer."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from patchright.sync_api import expect
from patchright.sync_api import sync_playwright as sync_patchright
from web_results_support import server


@pytest.fixture(autouse=True)
def serve_candidate_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static"
    )


@pytest.mark.parametrize(
    "width,height", [(320, 700), (360, 800), (390, 844), (412, 915), (1440, 900)]
)
def test_profile_menu_dismissal_and_footer_single_line(
    tmp_path: Path, width: int, height: int
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    with server(tmp_path) as (_app, port), sync_patchright() as patchright:
        browser = patchright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox", "--no-zygote"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())
            page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="domcontentloaded")
            new_chat = page.locator(".sidebar-footer-new")
            profile = page.get_by_role("button", name="Profile")
            expect(new_chat).to_be_visible()
            expect(profile).to_be_visible()

            for button in (new_chat, profile):
                assert button.evaluate(
                    """element => {
                      const label = element.querySelector('span');
                      const fontSize = parseFloat(getComputedStyle(label).fontSize);
                      return label.getBoundingClientRect().height <= fontSize * 1.7;
                    }"""
                )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

            profile.click()
            menu = page.get_by_role("group", name="Profile actions")
            expect(menu).to_be_visible()
            expect(profile).to_have_attribute("aria-expanded", "true")
            page.keyboard.press("Escape")
            expect(menu).to_have_count(0)
            expect(profile).to_be_focused()

            profile.click()
            page.get_by_role("button", name="Search chats").click()
            expect(menu).to_have_count(0)
            expect(profile).to_have_attribute("aria-expanded", "false")

            profile.click()
            page.get_by_role("button", name="Settings", exact=True).click()
            dialog = page.get_by_role("dialog", name="Prompta settings")
            expect(dialog).to_be_visible()
            expect(page.get_by_role("button", name="Close settings")).to_be_focused()
            page.keyboard.press("Shift+Tab")
            expect(page.get_by_role("button", name="Save settings")).to_be_focused()
            page.keyboard.press("Tab")
            expect(page.get_by_role("button", name="Close settings")).to_be_focused()
            page.keyboard.press("Escape")
            expect(dialog).to_have_count(0)
            expect(profile).to_be_focused()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            browser.close()


@pytest.mark.parametrize("width,height", [(320, 700), (360, 800), (390, 844), (412, 915)])
def test_settings_modal_covers_viewport_from_mobile_drawer(
    tmp_path: Path, width: int, height: int
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    with server(tmp_path) as (_app, port), sync_patchright() as patchright:
        browser = patchright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox", "--no-zygote"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())
            page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="domcontentloaded")
            page.locator(".sidebar-footer-new").click()
            page.get_by_role("button", name="Open chat sidebar").click()
            expect(page.locator(".chats-layout")).to_have_class("chats-layout drawer-open")
            profile = page.get_by_role("button", name="Profile")
            profile.click()
            page.keyboard.press("Escape")
            expect(page.locator(".chats-layout")).to_have_class("chats-layout drawer-open")
            expect(profile).to_be_focused()
            profile.click()
            page.get_by_role("button", name="Settings", exact=True).click()
            overlay = page.locator(".settings-backdrop")
            expect(overlay).to_be_visible()
            assert overlay.evaluate(
                """element => {
                  const r = element.getBoundingClientRect();
                  return Math.abs(r.left) <= 1 && Math.abs(r.top) <= 1 &&
                    Math.abs(r.width - innerWidth) <= 1 &&
                    Math.abs(r.height - innerHeight) <= 1;
                }"""
            )
            # A gesture over the modal must never close the drawer behind it.
            cdp = page.context.new_cdp_session(page)
            for index, x in enumerate((width - 12, width - 80, 24)):
                cdp.send(
                    "Input.dispatchTouchEvent",
                    {
                        "type": "touchStart" if index == 0 else "touchMove",
                        "touchPoints": [{"x": x, "y": height // 2}],
                    },
                )
                page.wait_for_timeout(35)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            expect(overlay).to_be_visible()
            expect(page.locator(".chats-layout")).to_have_class("chats-layout drawer-open")
            page.keyboard.press("Escape")
            expect(overlay).to_have_count(0)
            expect(page.locator(".chats-layout")).to_have_class("chats-layout drawer-open")
            expect(profile).to_be_focused()
        finally:
            browser.close()


@pytest.mark.parametrize("width,height", [(360, 800), (1440, 900)])
def test_settings_load_retry_recovers_without_reopening(
    tmp_path: Path, width: int, height: int
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    with server(tmp_path) as (_app, port), sync_patchright() as patchright:
        browser = patchright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox", "--no-zygote"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())
            requests: list[str] = []

            def settings_response(route: object) -> None:
                from patchright.sync_api import Route

                assert isinstance(route, Route)
                if route.request.method != "GET":
                    route.continue_()
                    return
                requests.append(route.request.url)
                if len(requests) == 1:
                    route.fulfill(status=503, body="Temporarily unavailable")
                else:
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body='{"stage_concurrency":{"enabled":true,"max_workers":3},"connector_approval":{"enabled":false}}',
                    )

            page.route("**/api/settings", settings_response)
            page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="domcontentloaded")
            page.get_by_role("button", name="Profile").click()
            page.get_by_role("button", name="Settings", exact=True).click()
            dialog = page.get_by_role("dialog", name="Prompta settings")
            expect(dialog).to_be_visible()
            retry = page.get_by_role("button", name="Retry loading settings")
            expect(retry).to_be_enabled()
            expect(page.get_by_role("alert")).to_have_text("Could not load settings")
            retry.click()
            expect(page.get_by_role("button", name="Save settings")).to_be_enabled()
            expect(page.get_by_role("alert")).to_have_count(0)
            assert len(requests) == 2
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            browser.close()


@pytest.mark.parametrize("width,height", [(320, 700), (390, 844), (1440, 900)])
def test_settings_worker_count_can_be_retyped_without_saving_zero(
    tmp_path: Path, width: int, height: int
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    with server(tmp_path) as (_app, port), sync_patchright() as patchright:
        browser = patchright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox", "--no-zygote"]
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())
            saved: list[dict[str, object]] = []

            def settings_response(route: object) -> None:
                from patchright.sync_api import Route

                assert isinstance(route, Route)
                if route.request.method == "PUT":
                    saved.append(json.loads(route.request.post_data or "{}"))
                    route.fulfill(status=200, content_type="application/json", body="{}")
                else:
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body='{"stage_concurrency":{"enabled":true,"max_workers":3},"connector_approval":{"enabled":false}}',
                    )

            page.route("**/api/settings", settings_response)
            page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="domcontentloaded")
            page.get_by_role("button", name="Profile").click()
            page.get_by_role("button", name="Settings", exact=True).click()
            workers = page.get_by_role("spinbutton", name="Maximum workers")
            save = page.get_by_role("button", name="Save settings")
            expect(workers).to_have_value("3")
            workers.fill("")
            expect(workers).to_have_value("")
            expect(save).to_be_disabled()
            workers.fill("12")
            expect(workers).to_have_value("12")
            expect(save).to_be_enabled()
            save.click()
            expect(page.get_by_role("dialog", name="Prompta settings")).to_have_count(0)
            assert saved == [
                {
                    "stage_concurrency": {"enabled": True, "max_workers": 12},
                    "connector_approval": {"enabled": False},
                }
            ]
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            browser.close()
