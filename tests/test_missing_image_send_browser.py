"""A rejected attachment send keeps its draft and retries with the same request ID."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from patchright.sync_api import expect, sync_playwright
from web_results_support import server

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZ0AAAAASUVORK5CYII="
)


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_rejected_image_send_recovers_without_duplicate(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        remote: list[str] = []
        posts: list[str] = []
        page.on(
            "request",
            lambda request: (
                remote.append(request.url)
                if not request.url.startswith(f"http://127.0.0.1:{port}/")
                else None
            ),
        )
        page.on(
            "request",
            lambda request: (
                posts.append(request.url)
                if request.method == "POST" and request.url.endswith("/api/chats")
                else None
            ),
        )
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        chooser = page.get_by_label("Choose images")
        chooser.set_input_files(
            {
                "name": "photo.png",
                "mimeType": "image/png",
                "buffer": PNG,
            }
        )
        expect(page.locator(".composer-preview")).to_have_count(1)
        draft = page.get_by_role("textbox", name="Message for new chat")
        draft.fill("Describe this photo")
        with patch.object(app.images, "path", side_effect=ValueError("Image no longer exists")):
            page.get_by_role("button", name="Send fresh chat").click()
            expect(
                page.get_by_text("Image unavailable. Reattach it before sending.")
            ).to_be_visible()
            assert app.queue.records() == []

        expect(draft).to_have_value("Describe this photo")
        page.get_by_role("button", name="Send fresh chat").click()
        page.wait_for_url("**/?view=chats&run=manual-*")
        assert len(posts) == 2
        assert len(app.queue.records()) == 1
        assert remote == []
        browser.close()
