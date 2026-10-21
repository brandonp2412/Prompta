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


@pytest.mark.asyncio
async def test_connector_permission_controls() -> None:
    chromium = shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=chromium, headless=True,
                                                   args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            script = load_browser_script("approve_connector.js")
            await page.set_content('<button onclick="window.clicked=true;this.remove()">Always allow</button>')
            assert await page.evaluate(script) is False
            assert await page.evaluate('window.clicked === true') is False
            await page.set_content('<div role="dialog"><button onclick="window.clicked=true;this.remove()">Always allow</button></div>')
            assert await page.evaluate(script) is True
            assert await page.evaluate('window.clicked') is True
            await page.set_content('<section><button onclick="window.clicked=true;this.remove()">Always allow</button><button>Allow once</button></section>')
            assert await page.evaluate(script) is True
            await page.set_content('<div role="dialog"><label><input type="checkbox">Always allow</label><button onclick="window.checked=document.querySelector(\'input\').checked;this.remove()">Allow</button></div>')
            assert await page.evaluate(script) is True
            assert await page.evaluate('window.checked') is True
            await page.set_content(
                '<div><form><button type="button" onclick="window.approved=true;this.remove()">'
                '<span>Always allow</span></button>'
                '<button>Deny<kbd aria-hidden="true">Esc</kbd></button>'
                '<button><span>Allow once</span><kbd aria-hidden="true">⏎</kbd></button>'
                '</form></div>'
            )
            assert await page.evaluate(script) is True
            assert await page.evaluate('window.approved') is True
            await page.set_content(
                '<section><div><div><button aria-labelledby="choice" '
                'onclick="this.remove()"><span id="choice">Always&nbsp; allow</span>'
                '</button></div></div><aside><button>Deny</button></aside></section>'
            )
            assert await page.evaluate(script) is True
            await page.set_content(
                '<div role="dialog"><button onclick="window.attempts=(window.attempts||0)+1">'
                'Always allow</button></div>'
            )
            assert await page.evaluate(script) == "stuck"
            assert await page.evaluate(script) is False
            assert await page.evaluate('window.attempts') == 1
            await page.wait_for_timeout(3000)
            assert await page.evaluate(script) == "stuck"
            await page.wait_for_timeout(3000)
            assert await page.evaluate(script) is False
            assert await page.evaluate('window.attempts') == 2
            await page.set_content(
                '<div role="dialog"><button disabled>Always allow</button>'
                '<button onclick="setTimeout(() => this.remove(), 200)">Always allow</button></div>'
            )
            assert await page.evaluate(script) is True
            await page.set_content(
                '<div role="dialog"><button style="visibility:hidden" '
                'onclick="window.hiddenClicked=true">Always allow</button></div>'
            )
            assert await page.evaluate(script) is False
            assert await page.evaluate('window.hiddenClicked === true') is False
            await page.set_content('<div role="dialog"><button disabled>Always allow</button></div>')
            assert await page.evaluate(script) is False
        finally:
            await browser.close()
