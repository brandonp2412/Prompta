"""Browser proof that a corrupt upload acknowledgement cannot poison the draft."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest
from patchright.sync_api import FilePayload, expect, sync_playwright
from web_results_support import server

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZ0AAAAASUVORK5CYII="
)


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_malformed_upload_receipt_rejects_then_recovers(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.add_init_script("""(() => {
          const realFetch = window.fetch;
          let attempts = 0;
          window.fetch = (url, options) => {
            if (new URL(url, location.href).pathname === '/api/images' && ++attempts === 1) {
              return Promise.resolve(new Response(JSON.stringify({
                image: {ref: 'f'.repeat(64) + '/photo.png', name: 'photo.png'}
              }), {status: 200, headers: {'content-type': 'application/json'}}));
            }
            return realFetch(url, options);
          };
        })()""")
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
            lambda request: posts.append(request.url) if request.method == "POST" else None,
        )
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        draft = page.get_by_role("textbox", name="Message for new chat")
        draft.fill("Keep this draft")
        chooser = page.get_by_label("Choose images")
        file: FilePayload = {"name": "photo.png", "mimeType": "image/png", "buffer": PNG}
        chooser.set_input_files(file)
        expect(page.get_by_text("Image upload receipt was invalid.")).to_be_visible()
        expect(page.locator(".composer-preview")).to_have_count(0)
        expect(draft).to_have_value("Keep this draft")
        chooser.set_input_files(file)
        expect(page.locator(".composer-preview")).to_have_count(1)
        expect(draft).to_have_value("Keep this draft")
        assert not any(url.endswith("/api/chats") for url in posts)
        assert remote == []
        browser.close()
