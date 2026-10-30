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
from playwright.sync_api import expect, sync_playwright

from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from prompta.strict_types import json_object
from prompta.web import PromptaJobServer

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLytQAAAABJRU5ErkJggg=="
)


@contextmanager
def serve_test_ui(tmp_path: Path) -> Generator[int]:
    app = PromptaJobServer(
        ("127.0.0.1", 0),
        state_path=tmp_path / "state.sqlite3",
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
        connection.request(
            "POST", path, body=json.dumps(payload), headers={"content-type": "application/json"}
        )
        response = connection.getresponse()
        return response.status, json_object(response.read(), label="fresh chat response")
    finally:
        connection.close()


def test_fresh_chat_endpoint_is_idempotent_and_payload_bound(tmp_path: Path) -> None:
    with serve_test_ui(tmp_path) as port:
        payload: dict[str, object] = {
            "request_id": "a" * 32,
            "prompt": "Private synthetic test",
            "images": [],
        }
        first_status, first = post(port, "/api/chats", payload)
        second_status, second = post(port, "/api/chats", payload)
        assert first_status == second_status == 202
        assert first["send_id"] == second["send_id"] == "manual-" + "a" * 32
        assert first["status"] == "queued" and second["status"] == "queued"
        results = ResponseStore(tmp_path / "chat-results.sqlite3")
        assert [item["send_id"] for item in results.local_pinned_runs()] == [first["send_id"]]
        assert results.set_local_pin(str(first["send_id"]), pinned=False)
        assert post(port, "/api/chats", payload)[0] == 202
        assert results.local_pinned_runs() == []
        assert (
            post(port, "/api/chats", {**payload, "prompt": "Different immutable message"})[0] == 400
        )
        assert post(port, "/api/chats", {**payload, "request_id": "bad"})[0] == 400
        assert post(port, "/api/chats", {**payload, "images": ["unverified-ref"]})[0] == 400
        assert post(port, "/api/chats", {**payload, "request_id": "b" * 32, "images": []})[0] == 202
        assert [item["send_id"] for item in results.local_pinned_runs()] == ["manual-" + "b" * 32]


def test_early_followup_http_queue_is_durable_and_idempotent(tmp_path: Path) -> None:
    with serve_test_ui(tmp_path) as port:
        results = ResponseStore(tmp_path / "chat-results.sqlite3")
        results.ensure_queued("early", "Original private prompt")
        payload: dict[str, object] = {
            "reply_id": "queued-" + "a" * 32,
            "text": "Additional context",
        }
        first_status, first = post(port, "/api/results/early/reply-queue", payload)
        second_status, second = post(port, "/api/results/early/reply-queue", payload)
        assert first_status == second_status == 202
        assert first["turn"] == second["turn"]
        turn = json_object(json.dumps(first["turn"]).encode(), label="queued follow-up")
        assert turn["status"] == "queued"
        assert (
            post(port, "/api/results/early/reply-queue", {**payload, "text": "Different"})[0] == 409
        )
        assert post(port, "/api/results/absent/reply-queue", payload)[0] == 409
        from prompta.reply_contracts import ManualReplyStore

        turns = ManualReplyStore(results.path).turns("early")
        assert turns is not None
        assert [turn["status"] for turn in turns] == ["queued", "queued"]
        assert turns[1]["user_text"] == "Additional context"


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_composer_queues_followup_while_first_answer_is_pending(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    results = ResponseStore(tmp_path / "chat-results.sqlite3")
    results.ensure_queued("early", "Original private prompt")
    assert results.accept("early", "owner", deadline=time.time() + 4000)
    with serve_test_ui(tmp_path) as port, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"http://127.0.0.1:{port}/?view=chats&run=early")
        composer = page.get_by_role("textbox", name="Message for current chat")
        composer.fill("Important follow-up before first answer")
        expect(page.get_by_role("button", name="Send reply")).to_be_enabled()
        with page.expect_response(lambda response: response.url.endswith("/reply-queue")) as queued:
            composer.press("Enter")
        assert queued.value.status == 202
        expect(composer).to_have_value("")
        expect(page.get_by_text("Important follow-up before first answer")).to_be_visible()
        expect(page.get_by_text("Follow-up queued", exact=False)).to_be_visible()
        composer.fill("Another queued instruction")
        with page.expect_response(lambda response: response.url.endswith("/reply-queue")):
            composer.press("Enter")
        expect(page.get_by_text("Another queued instruction")).to_be_visible()
        assert page.locator(".message-group.user-group").count() == 3
        page.reload()
        expect(page.locator(".message-group.user-group")).to_have_count(3)
        expect(page.get_by_role("textbox", name="Message for current chat")).to_be_enabled()
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_real_composer_keyboard_image_and_overflow(
    tmp_path: Path,
    width: int,
    height: int,
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
        empty_action = page.locator(".chat-composer-wrap").get_by_role("button", name="New chat")
        expect(empty_action).to_be_enabled()
        assert page.get_by_role("button", name="Send fresh chat").count() == 0
        empty_action.click()
        expect(composer).to_have_value("")
        composer.fill("   ")
        expect(empty_action).to_be_enabled()
        composer.fill("Synthetic line one")
        expect(page.get_by_role("button", name="Send fresh chat")).to_be_enabled()
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
        assert (
            page.locator(".chat-composer").evaluate(
                "node => getComputedStyle(node).backgroundColor"
            )
            == "rgb(48, 48, 48)"
        )
        assert (
            page.locator(".composer-attach input").evaluate(
                "node => getComputedStyle(node).display"
            )
            == "none"
        )
        page.screenshot(path=str(images / f"stage5-{width}x{height}-composer.png"), full_page=True)
        (images / f"stage5-{width}x{height}-composer.png").chmod(0o600)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        composer.press("Enter")
        page.wait_for_url("**/?view=chats&run=manual-*")
        assert page.evaluate("localStorage.getItem('prompta.new-chat-draft.v1')") is None
        assert (
            len([url for method, url in requests if method == "POST" and "/api/chats" in url]) == 1
        )
        assert all(url.startswith(f"http://127.0.0.1:{port}/") for _, url in requests)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
@pytest.mark.parametrize("missing_parent", [False, True])
def test_existing_chat_reply_composer_is_explicit_and_branch_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    width: int,
    height: int,
    missing_parent: bool,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    app = PromptaJobServer(
        ("127.0.0.1", 0),
        state_path=tmp_path / "state.sqlite3",
        jobs_path=tmp_path / "jobs.sqlite3",
    )
    now = time.time()
    conversation_id = "11111111-1111-4111-8111-111111111111" if missing_parent else "c" * 32
    parent_id = "22222222-2222-4222-8222-222222222222" if missing_parent else "m" * 32
    app.results.ensure_queued("run-1", "Synthetic original", now=now)
    assert app.results.accept("run-1", "owner", deadline=now + 4000)
    assert app.results.write(
        "run-1",
        "owner",
        CaptureResult(
            "sse",
            "complete",
            "Synthetic original answer",
            conversation_id,
            "" if missing_parent else parent_id,
            "p" * 32,
            "observer-1" if missing_parent else None,
        ),
    )
    calls: list[tuple[str, str, str]] = []
    recoveries: list[str] = []

    def recover(send_id: str) -> dict[str, str]:
        recoveries.append(send_id)
        assert app.replies.recover_original_parent(
            send_id,
            conversation_id,
            parent_id,
            "Synthetic original answer",
        )
        return {"message_id": parent_id}

    monkeypatch.setattr(app.reply_dispatch, "recover", recover)

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
            composer = page.get_by_role("textbox", name="Message for current chat")
            composer.wait_for()
            expect(composer).to_be_enabled()
            page.locator(".user-group .message-timestamp").first.wait_for()
            assert page.locator(".chat-detail-title").count() == 0
            assert page.locator(".chat-detail-content h2").count() == 0
            assert page.locator(".user-group .message-timestamp").first.get_attribute("datetime")
            assert (
                "Time unavailable"
                not in page.locator(".user-group .message-timestamp").first.inner_text()
            )
            assert page.get_by_role("button", name="Reply to this chat").count() == 0
            assert page.get_by_role("button", name="Send saved reply").count() == 0
            assert not recoveries and not calls
            empty_action = page.locator(".chat-composer-wrap").get_by_role(
                "button", name="New chat"
            )
            expect(empty_action).to_be_enabled()
            assert page.get_by_role("button", name="Send reply").count() == 0
            empty_action.click()
            page.wait_for_url("**/?view=chats&draft=new")
            assert not recoveries and not calls
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=run-1")
            composer = page.get_by_role("textbox", name="Message for current chat")
            composer.fill("Synthetic follow-up")
            composer.press("Shift+Enter")
            composer.type("second line")
            wrap = page.locator(".chat-composer-wrap").bounding_box()
            assert wrap is not None and wrap["y"] >= height * 0.5
            assert (
                page.locator(".chat-composer").evaluate(
                    "node => getComputedStyle(node).backgroundColor"
                )
                == "rgb(48, 48, 48)"
            )
            suffix = "recover" if missing_parent else "known"
            path = screenshots / f"stage5-{width}x{height}-reply-{suffix}.png"
            page.screenshot(path=str(path), full_page=True)
            path.chmod(0o600)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            with page.expect_response(
                lambda response: response.url.endswith("/reply-send")
            ) as sent:
                composer.press("Enter")
            assert sent.value.status == 202
            page.locator(".message-group.user-group").nth(1).wait_for()
            assert calls == [("run-1", conversation_id, parent_id)]
            assert recoveries == (["run-1"] if missing_parent else [])
            assert len(
                [1 for method, url in observed if method == "POST" and "/reply-recover" in url]
            ) == int(missing_parent)
            assert (
                len([1 for method, url in observed if method == "POST" and "/reply-send" in url])
                == 1
            )
            assert page.get_by_role("button", name="Reply to this chat").count() == 0
            assert page.get_by_role("button", name="Send saved reply").count() == 0
            assert composer.count() == 1
            expect(composer).to_be_enabled()
            expect(composer).to_have_value("")
            expect(
                page.locator(".chat-composer-wrap").get_by_role("button", name="New chat")
            ).to_be_enabled()
            # Acknowledged prepared replies survive reload in the transcript,
            # not the composer: replay must require a separate explicit intent.
            page.reload()
            composer = page.get_by_role("textbox", name="Message for current chat")
            expect(composer).to_have_value("")
            expect(page.locator(".message-group.user-group")).to_have_count(2)
            assert calls == [("run-1", conversation_id, parent_id)]
            assert (
                len([1 for method, url in observed if method == "POST" and "/reply-send" in url])
                == 1
            )
            assert all(url.startswith(f"http://127.0.0.1:{port}/") for _, url in observed)
            browser.close()
    finally:
        app.shutdown()
        thread.join(timeout=3)
        app.server_close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
@pytest.mark.parametrize(
    ("status", "missing_conversation", "reply_allowed"),
    [
        ("completed", True, True),
        ("interrupted", False, True),
    ],
)
def test_reply_composer_preserves_terminal_recovery_without_sending(
    tmp_path: Path,
    width: int,
    height: int,
    status: str,
    missing_conversation: bool,
    reply_allowed: bool,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    app = PromptaJobServer(
        ("127.0.0.1", 0),
        state_path=tmp_path / "state.sqlite3",
        jobs_path=tmp_path / "jobs.sqlite3",
    )
    now = time.time()
    app.results.ensure_queued("run-1", "Synthetic original", now=now)
    assert app.results.accept("run-1", "owner", deadline=now + 4000)
    if status == "completed":
        assert app.results.write(
            "run-1",
            "owner",
            CaptureResult(
                "dom",
                "complete",
                "Synthetic answer",
                None if missing_conversation else "c" * 32,
                "m" * 32,
                None,
            ),
        )
    elif status == "interrupted":
        assert app.results.finish("run-1", "owner", "interrupted")
    thread = threading.Thread(target=app.serve_forever, daemon=True)
    thread.start()
    observed: list[tuple[str, str]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("request", lambda request: observed.append((request.method, request.url)))
            page.goto(f"http://127.0.0.1:{app.server_address[1]}/?view=chats&run=run-1")
            composer = page.get_by_role("textbox", name="Message for current chat")
            composer.wait_for()
            composer.fill("Unsent local draft")
            send_button = page.get_by_role("button", name="Send reply")
            if reply_allowed:
                # Missing capture identity and interrupted reads cannot permanently block Send.
                expect(send_button).to_be_enabled()
            else:
                expect(
                    page.get_by_text("Wait for the current response", exact=False)
                ).to_be_visible()
                expect(send_button).to_be_disabled()
                composer.press("Enter")
            assert not [
                request
                for request in observed
                if request[0] == "POST"
                and any(
                    path in request[1]
                    for path in (
                        "/api/chats",
                        "/reply-send",
                        "/reply-recover",
                    )
                )
            ]
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            browser.close()
    finally:
        app.shutdown()
        thread.join(timeout=3)
        app.server_close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_fresh_chat_immediately_enters_sidebar_without_horizontal_scroll(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with serve_test_ui(tmp_path) as port, sync_playwright() as playwright:
        results = ResponseStore(tmp_path / "chat-results.sqlite3")
        for index in range(35):
            results.ensure_queued(
                f"synthetic-{index:03}",
                f"A very long synthetic chat {index} " + "X" * 250,
                now=time.time() - 100 - index,
            )
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        page.get_by_role("textbox", name="Message for new chat").fill("Instant new sidebar chat")
        page.get_by_role("button", name="Send fresh chat").click()
        page.wait_for_url("**/?view=chats&run=manual-*")
        if width < 681:
            page.get_by_role("button", name="Open chat sidebar").click()
        page.locator(".chats-list .chat-row").filter(has_text="Instant new sidebar chat").wait_for(
            timeout=2000,
        )
        page.locator(".chat-entry").filter(has_text="Instant new sidebar chat").locator(
            ".chat-pin[aria-pressed='true']"
        ).wait_for(timeout=3000)
        page.reload()
        if width < 681:
            page.get_by_role("button", name="Open chat sidebar").click()
        page.locator(".chat-entry").filter(has_text="Instant new sidebar chat").locator(
            ".chat-pin[aria-pressed='true']"
        ).wait_for(timeout=3000)
        assert (
            page.locator(".chats-list .chat-row")
            .first.inner_text()
            .startswith(
                "Instant new sidebar chat",
            )
        )
        assert (
            page.locator(".chats-list").evaluate(
                "node => getComputedStyle(node).overflowX",
            )
            == "hidden"
        )
        sidebar = page.locator(".chats-sidebar")
        assert sidebar.evaluate("node => getComputedStyle(node).overflowX") == "clip"
        dimensions = page.locator(".chats-list").evaluate(
            "node => ({clientWidth:node.clientWidth, scrollWidth:node.scrollWidth, "
            "clientHeight:node.clientHeight, scrollHeight:node.scrollHeight})",
        )
        assert dimensions["scrollWidth"] <= dimensions["clientWidth"] + 1
        assert dimensions["scrollHeight"] > dimensions["clientHeight"]
        page.locator(".chats-list").evaluate("node => node.scrollTop = 300")
        assert page.locator(".chats-list").evaluate("node => node.scrollTop") > 0
        assert page.get_by_text("Local Prompta runs only").count() == 0
        assert page.get_by_text("paste or drop").count() == 0
        assert page.get_by_text("Exact saved branch only").count() == 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        browser.close()
