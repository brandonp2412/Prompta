"""Stage 5 fresh-composer contracts: one local enqueue per explicit send."""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from prompta.response_capture import CaptureResult
from prompta.strict_types import json_object
from prompta.web import PromptaJobServer

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLytQAAAABJRU5ErkJggg=="
)


@contextmanager
def serve_test_ui(tmp_path: Path) -> Generator[int]:
    app = PromptaJobServer(
        ("127.0.0.1", 0), state_path=tmp_path / "state.sqlite3",
        jobs_path=tmp_path / "jobs.sqlite3",
    )
    thread = threading.Thread(target=app.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(app.server_address[1])
    finally:
        app.shutdown()
        thread.join(timeout=3)
        app.server_close()


def post(port: int, path: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    connection = HTTPConnection("127.0.0.1", port, timeout=4)
    try:
        connection.request("POST", path, body=json.dumps(payload), headers={"content-type": "application/json"})
        response = connection.getresponse()
        return response.status, json_object(response.read(), label="fresh chat response")
    finally:
        connection.close()


def test_fresh_chat_endpoint_is_idempotent_and_payload_bound(tmp_path: Path) -> None:
    with serve_test_ui(tmp_path) as port:
        payload: dict[str, object] = {
            "request_id": "a" * 32, "prompt": "Private synthetic test", "images": [],
        }
        first_status, first = post(port, "/api/chats", payload)
        second_status, second = post(port, "/api/chats", payload)
        assert first_status == second_status == 202
        assert first["send_id"] == second["send_id"] == "manual-" + "a" * 32
        assert first["status"] == "queued" and second["status"] == "queued"
        assert post(port, "/api/chats", {**payload, "prompt": "Different immutable message"})[0] == 400
        assert post(port, "/api/chats", {**payload, "request_id": "bad"})[0] == 400
        assert post(port, "/api/chats", {**payload, "images": ["unverified-ref"]})[0] == 400
        assert post(port, "/api/chats", {**payload, "request_id": "b" * 32, "images": []})[0] == 202


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_real_composer_keyboard_image_and_overflow(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    images = Path(os.environ.get("PROMPTA_SCREENSHOT_DIR", str(tmp_path)))
    images.mkdir(parents=True, exist_ok=True, mode=0o700)
    requests: list[tuple[str, str]] = []
    with serve_test_ui(tmp_path) as port, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        page.on("request", lambda request: requests.append((request.method, request.url)))
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        composer = page.get_by_role("textbox", name="Message for new chat")
        composer.wait_for()
        composer.fill("Synthetic line one")
        composer.press("Shift+Enter")
        composer.type("Synthetic line two")
        assert composer.input_value() == "Synthetic line one\nSynthetic line two"

        image = page.get_by_label("Choose images")
        image.set_input_files({"name": "tiny.png", "mimeType": "image/png", "buffer": _PNG})
        page.get_by_role("img", name="tiny.png").wait_for()
        assert page.get_by_role("button", name="Remove tiny.png").count() == 1
        page.evaluate(
            """(payload) => {
              const bytes = Uint8Array.from(atob(payload), (char) => char.charCodeAt(0));
              const transfer = new DataTransfer();
              transfer.items.add(new File([bytes], "drop.png", { type: "image/png" }));
              document.querySelector(".chat-composer-wrap").dispatchEvent(
                new DragEvent("drop", { bubbles: true, dataTransfer: transfer })
              );
            }""",
            base64.b64encode(_PNG).decode(),
        )
        page.get_by_role("img", name="drop.png").wait_for()
        page.evaluate(
            """(payload) => {
              const bytes = Uint8Array.from(atob(payload), (char) => char.charCodeAt(0));
              const transfer = new DataTransfer();
              transfer.items.add(new File([bytes], "paste.png", { type: "image/png" }));
              document.querySelector(".chat-composer textarea").dispatchEvent(
                new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: transfer })
              );
            }""",
            base64.b64encode(_PNG).decode(),
        )
        page.get_by_role("img", name="paste.png").wait_for()
        assert page.locator(".composer-preview").count() == 3
        wrap = page.locator(".chat-composer-wrap").bounding_box()
        assert wrap is not None and wrap["y"] >= height * 0.5
        assert page.locator(".chat-composer").evaluate(
            "node => getComputedStyle(node).backgroundColor"
        ) == "rgb(48, 48, 48)"
        assert page.locator(".composer-attach input").evaluate(
            "node => getComputedStyle(node).display"
        ) == "none"
        page.screenshot(path=str(images / f"stage5-{width}x{height}-composer.png"), full_page=True)
        (images / f"stage5-{width}x{height}-composer.png").chmod(0o600)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        composer.press("Enter")
        page.wait_for_url("**/?view=chats&run=manual-*")
        assert len([url for method, url in requests if method == "POST" and "/api/chats" in url]) == 1
        assert all(url.startswith(f"http://127.0.0.1:{port}/") for _, url in requests)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_existing_chat_reply_composer_is_explicit_and_branch_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    app = PromptaJobServer(
        ("127.0.0.1", 0), state_path=tmp_path / "state.sqlite3",
        jobs_path=tmp_path / "jobs.sqlite3",
    )
    now = time.time()
    app.results.ensure_queued("run-1", "Synthetic original", now=now)
    assert app.results.accept("run-1", "owner", deadline=now + 4000)
    assert app.results.write(
        "run-1", "owner",
        CaptureResult("sse", "complete", "Synthetic original answer", "c" * 32, "m" * 32, "p" * 32),
    )
    calls: list[tuple[str, str, str]] = []

    def local_dispatch(send_id: str, intent: object) -> dict[str, object]:
        from prompta.reply_contracts import ReplyIntent
        assert isinstance(intent, ReplyIntent)
        calls.append((send_id, intent.conversation_id, intent.parent_id))
        return app.replies.prepare(send_id, intent)

    monkeypatch.setattr(app.reply_dispatch, "submit", local_dispatch)
    thread = threading.Thread(target=app.serve_forever, daemon=True)
    thread.start()
    port = int(app.server_address[1])
    screenshots = Path(os.environ.get("PROMPTA_SCREENSHOT_DIR", str(tmp_path)))
    screenshots.mkdir(parents=True, exist_ok=True, mode=0o700)
    observed: list[tuple[str, str]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("request", lambda request: observed.append((request.method, request.url)))
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=run-1")
            composer = page.get_by_role("textbox", name="Reply to this chat")
            composer.wait_for()
            composer.fill("Synthetic follow-up")
            composer.press("Shift+Enter")
            composer.type("second line")
            wrap = page.locator(".chat-composer-wrap").bounding_box()
            assert wrap is not None and wrap["y"] >= height * 0.5
            assert page.locator(".chat-composer").evaluate(
                "node => getComputedStyle(node).backgroundColor"
            ) == "rgb(48, 48, 48)"
            path = screenshots / f"stage5-{width}x{height}-reply.png"
            page.screenshot(path=str(path), full_page=True)
            path.chmod(0o600)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            composer.press("Enter")
            page.get_by_role("button", name="Send saved reply").wait_for()
            assert calls == [("run-1", "c" * 32, "m" * 32)]
            assert len([1 for method, url in observed if method == "POST" and "/reply-send" in url]) == 1
            assert all(url.startswith(f"http://127.0.0.1:{port}/") for _, url in observed)
            browser.close()
    finally:
        app.shutdown()
        thread.join(timeout=3)
        app.server_close()
