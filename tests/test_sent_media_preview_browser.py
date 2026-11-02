from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import sync_playwright as sync_patchright
from web_results_support import completed_run, server
from web_results_support import serve_worktree_assets as serve_worktree_assets


@pytest.mark.parametrize(
    "width,height,min_width",
    [(1440, 900, 380), (390, 844, 300), (320, 800, 260)],
)
def test_sent_images_and_videos_have_readable_previews(
    tmp_path: Path, width: int, height: int, min_width: int
) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium or not Path(chromium).is_file():
        pytest.skip("Visual Chromium binary unavailable")

    with server(tmp_path) as (app, port):
        photo = app.images.save(
            "photo.png",
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO9pB7sAAAAASUVORK5CYII=",
        )
        clip = app.images.save("clip.mp4", "AAAAGGZ0eXBpc29tAAACAGlzb21pc28y")
        app.queue.enqueue_idempotent(
            {"send_id": "media-preview", "message": "Review these files", "images": [photo, clip]}
        )
        completed_run(app, "media-preview", "Media preview", 1793020000.0)

        with sync_patchright() as patchright:
            browser = patchright.chromium.launch(
                executable_path=chromium,
                headless=True,
                args=["--no-sandbox", "--no-zygote"],
            )
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
                page.locator(".chat-row").filter(has_text="Media preview").click()
                image = page.locator(".chat-attachments a img")
                video = page.locator(".chat-attachments > video")
                image.wait_for()
                video.wait_for()
                assert image.evaluate("element => element.naturalWidth > 0")
                assert image.evaluate("element => getComputedStyle(element).objectFit") == "contain"
                assert video.evaluate("element => getComputedStyle(element).objectFit") == "contain"
                assert video.get_attribute("controls") is not None
                for selector in (".chat-attachments a", ".chat-attachments > video"):
                    box = page.locator(selector).bounding_box()
                    assert box is not None
                    assert min_width <= box["width"] <= 402
                    assert box["x"] >= 0
                    assert box["x"] + box["width"] <= width + 1
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            finally:
                browser.close()
