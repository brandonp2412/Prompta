"""Real Chromium tests for old-route uploads and SSE read-only recovery."""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path

import pytest
from playwright.sync_api import FilePayload, expect, sync_playwright
from test_web_results import completed_run, server

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Uw2FSsAAAAASUVORK5CYII="
)


def _chromium() -> str:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    return executable


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_late_image_upload_cannot_attach_to_a_different_chat(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "image-isolation", "Image isolation probe", time.time())
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        remote: list[str] = []
        page.on("request", lambda request: remote.append(request.url) if not request.url.startswith(
            f"http://127.0.0.1:{port}/"
        ) else None)
        page.add_init_script("""(() => {
          const previous = window.fetch;
          window.fetch = (input, init) => {
            if (new URL(input, location.href).pathname === '/api/images') {
              return new Promise(resolve => {
                window.finishUpload = () => resolve(new Response(JSON.stringify({
                  image: {ref: 'a'.repeat(64), name: 'old.png', url: './api/images/' + 'a'.repeat(64)}
                }), {status: 200, headers: {'content-type': 'application/json'}}));
              });
            }
            return previous(input, init);
          };
        })()""")
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        page.get_by_label("Choose images").set_input_files(
            {"name": "old.png", "mimeType": "image/png", "buffer": PNG}
        )
        expect(page.get_by_text("Uploading images…")).to_be_visible()
        if width <= 680:
            page.get_by_role("button", name="Open chat sidebar").click()
        page.locator(".chats-list .chat-row").filter(has_text="Image isolation probe").click()
        page.wait_for_url("**/?view=chats&run=image-isolation")
        page.evaluate("window.finishUpload()")
        expect(page.get_by_role("textbox", name="Message for current chat")).to_be_visible()
        if width <= 680:
            page.get_by_role("button", name="Back to chats").click()
        page.locator(".chats-sidebar .sidebar-primary").click()
        page.wait_for_url("**/?view=chats&draft=new")
        expect(page.locator(".composer-preview")).to_have_count(0)
        expect(page.get_by_role("button", name="Attach images")).to_be_enabled()
        assert remote == []
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_invalid_batch_rejected_without_partially_uploading(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        uploads: list[str] = []
        page.on("request", lambda request: uploads.append(request.url) if request.url.endswith(
            "/api/images") else None)
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        page.get_by_label("Choose images").set_input_files([
            {"name": "valid.png", "mimeType": "image/png", "buffer": PNG},
            {"name": "invalid.txt", "mimeType": "text/plain", "buffer": b"not an image"},
        ])
        expect(page.get_by_text("Only PNG, JPEG, GIF or WebP images are supported.")).to_be_visible()
        assert uploads == []
        expect(page.locator(".composer-preview")).to_have_count(0)
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_browser_reconnect_and_periodic_repair_only_refresh_local_views(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.clock.install()
        requests: list[tuple[str, str]] = []
        page.on("request", lambda request: requests.append((request.method, request.url)))
        page.goto(f"http://127.0.0.1:{port}/?view=jobs")
        expect(page.get_by_role("button", name="Refresh jobs")).to_be_visible()
        page.wait_for_timeout(500)
        baseline = sum("/api/jobs" in url for _, url in requests)
        page.evaluate("window.dispatchEvent(new Event('online'))")
        page.wait_for_timeout(400)
        assert sum("/api/jobs" in url for _, url in requests) > baseline
        baseline = sum("/api/jobs" in url for _, url in requests)
        page.clock.fast_forward(120001)
        page.wait_for_timeout(400)
        assert sum("/api/jobs" in url for _, url in requests) > baseline
        assert not any(method == "POST" for method, _ in requests)
        assert all(url.startswith(f"http://127.0.0.1:{port}/") for _, url in requests)
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_drafts_survive_spa_navigation_with_unavailable_browser_storage(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "draft-alpha", "Draft alpha", time.time())
        completed_run(app, "draft-beta", "Draft beta", time.time())
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.add_init_script("""(() => {
          const read = Storage.prototype.getItem;
          const write = Storage.prototype.setItem;
          Storage.prototype.getItem = function(key) {
            if (key.startsWith('prompta.new-chat-draft') || key.startsWith('prompta.reply-draft')) {
              throw new DOMException('Storage unavailable', 'SecurityError');
            }
            return read.call(this, key);
          };
          Storage.prototype.setItem = function(key, value) {
            if (key.startsWith('prompta.new-chat-draft') || key.startsWith('prompta.reply-draft')) {
              throw new DOMException('Storage unavailable', 'SecurityError');
            }
            return write.call(this, key, value);
          };
        })()""")
        posts: list[str] = []
        page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        fresh = page.get_by_role("textbox", name="Message for new chat")
        fresh.fill("Unsent fresh draft")

        def select(title: str, send_id: str) -> None:
            if width <= 680:
                back = page.get_by_role("button", name="Back to chats")
                if back.count():
                    back.click()
                else:
                    page.get_by_role("button", name="Open chat sidebar").click()
            page.locator(".chats-list .chat-row").filter(has_text=title).click()
            page.wait_for_url("**/?view=chats&run=" + send_id)

        select("Draft alpha", "draft-alpha")
        reply = page.get_by_role("textbox", name="Message for current chat")
        reply.fill("Unsent Alpha draft")
        select("Draft beta", "draft-beta")
        reply.fill("Unsent Beta draft")
        select("Draft alpha", "draft-alpha")
        expect(reply).to_have_value("Unsent Alpha draft")
        select("Draft beta", "draft-beta")
        expect(reply).to_have_value("Unsent Beta draft")
        if width <= 680:
            page.get_by_role("button", name="Back to chats").click()
        page.locator(".chats-sidebar .sidebar-primary").click()
        expect(fresh).to_have_value("Unsent fresh draft")
        assert all(url.endswith("/api/local-chat-reads") for url in posts)
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_attached_image_cannot_be_discarded_by_empty_draft_new_chat_action(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        sends: list[str] = []
        page.on("request", lambda request: sends.append(request.url) if request.method == "POST" and
                request.url.endswith("/api/chats") else None)
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        page.get_by_label("Choose images").set_input_files(
            {"name": "one.png", "mimeType": "image/png", "buffer": PNG}
        )
        expect(page.locator(".composer-preview")).to_have_count(1)
        expect(page.locator(".chat-composer-wrap").get_by_role("button", name="New chat")).to_have_count(0)
        send = page.get_by_role("button", name="Send fresh chat")
        expect(send).to_be_disabled()
        page.get_by_role("textbox", name="Message for new chat").fill("Keep the attachment")
        expect(send).to_be_enabled()
        assert sends == []
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_uploaded_image_and_draft_survive_navigation_until_removed(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "navigate-image", "Navigation image", time.time())
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        posts: list[str] = []
        page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        message = page.get_by_role("textbox", name="Message for new chat")
        message.fill("Keep draft with uploaded image")
        page.get_by_label("Choose images").set_input_files(
            {"name": "one.png", "mimeType": "image/png", "buffer": PNG}
        )
        expect(page.locator(".composer-preview")).to_have_count(1)

        def visit_chat() -> None:
            if width <= 680:
                page.get_by_role("button", name="Open chat sidebar").click()
            page.locator(".chats-list .chat-row").filter(has_text="Navigation image").click()
            page.wait_for_url("**/?view=chats&run=navigate-image")

        def back_to_fresh() -> None:
            if width <= 680:
                page.get_by_role("button", name="Back to chats").click()
            page.locator(".chats-sidebar .sidebar-primary").click()
            page.wait_for_url("**/?view=chats&draft=new")

        visit_chat()
        back_to_fresh()
        expect(message).to_have_value("Keep draft with uploaded image")
        expect(page.locator(".composer-preview")).to_have_count(1)
        page.get_by_role("button", name="Remove one.png").click()
        expect(page.locator(".composer-preview")).to_have_count(0)
        visit_chat()
        back_to_fresh()
        expect(page.locator(".composer-preview")).to_have_count(0)
        assert sum(url.endswith("/api/images") for url in posts) == 1
        assert not any(url.endswith("/api/chats") for url in posts)
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_failed_upload_batch_rolls_back_and_duplicate_image_is_deduped(
    tmp_path: Path, width: int, height: int,
) -> None:
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        same: FilePayload = {"name": "same.png", "mimeType": "image/png", "buffer": PNG}
        # The server uses content-addressed image references. A repeated
        # attachment must not create duplicate keyed Svelte preview nodes.
        page.get_by_label("Choose images").set_input_files([same, same])
        expect(page.locator(".composer-preview")).to_have_count(1)
        page.get_by_role("button", name="Remove same.png").click()
        expect(page.locator(".composer-preview")).to_have_count(0)

        calls = [0]

        def fail_second(route) -> None:
            calls[0] += 1
            if calls[0] == 2:
                route.fulfill(status=503, body="temporary upload failure")
            else:
                route.continue_()
        page.route("**/api/images", fail_second)
        page.get_by_label("Choose images").set_input_files([
            {"name": "a.png", "mimeType": "image/png", "buffer": PNG},
            {"name": "b.png", "mimeType": "image/png", "buffer": PNG},
        ])
        expect(page.get_by_text("Image upload failed.")).to_be_visible()
        expect(page.locator(".composer-preview")).to_have_count(0)
        assert calls == [2]
        browser.close()
