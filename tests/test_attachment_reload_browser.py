"""A browser reload must not discard accepted but unsent image upload receipts."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from test_web_results import server

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Uw2FSsAAAAASUVORK5CYII="
)


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_upload_refs_survive_reload_but_removed_refs_do_not(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        uploads: list[str] = []
        page.on("request", lambda request: uploads.append(request.url) if request.method == "POST"
                and request.url.endswith("/api/images") else None)
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        message = page.get_by_role("textbox", name="Message for new chat")
        message.fill("Unsent message with image")
        page.get_by_label("Choose images").set_input_files(
            {"name": "one.png", "mimeType": "image/png", "buffer": PNG},
        )
        expect(page.locator(".composer-preview")).to_have_count(1)
        page.reload()
        expect(page.get_by_role("textbox", name="Message for new chat")).to_have_value(
            "Unsent message with image",
        )
        expect(page.locator(".composer-preview")).to_have_count(1)
        page.get_by_role("button", name="Remove one.png").click()
        page.reload()
        expect(page.locator(".composer-preview")).to_have_count(0)
        assert len(uploads) == 1
        browser.close()
