"""Small-screen and keyboard regression checks for the compact Prompta sidebar footer."""

from __future__ import annotations

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


@pytest.mark.parametrize("width,height", [(320, 700), (390, 844), (1440, 900)])
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
