from __future__ import annotations

import shutil

import pytest
from playwright.async_api import async_playwright

from prompta.browser_script_loader import load_browser_script


@pytest.mark.asyncio
async def test_browser_composer_focus_rejects_embedded_button_and_focus_steal() -> None:
    chromium = shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox"]
        )
        try:
            page = await browser.new_page()
            await page.set_content(
                '<div id="editor" contenteditable="true">Hello '
                '<span id="text" tabindex="0" contenteditable="true">world</span>'
                '<button id="action" contenteditable="false">Help</button></div>'
                '<button id="popup">Popup</button>'
            )
            editor = page.locator("#editor")
            script = load_browser_script("composer_has_focus.js")
            await page.locator("#text").focus()
            assert await editor.evaluate(script) is True
            await page.locator("#action").focus()
            assert await editor.evaluate(script) is False
            await page.locator("#popup").focus()
            assert await editor.evaluate(script) is False
            await editor.focus()
            assert await editor.evaluate(script) is True
        finally:
            await browser.close()
