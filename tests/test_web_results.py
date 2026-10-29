from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from typing import Literal

import pytest
from playwright.sync_api import expect, sync_playwright

from prompta.jobs import add_job
from prompta.response_capture import CaptureResult
from prompta.strict_types import json_object, string_object_dict
from prompta.web import PromptaJobServer


@contextmanager
def server(tmp_path: Path) -> Generator[tuple[PromptaJobServer, int]]:
    app = PromptaJobServer(
        ("127.0.0.1", 0), state_path=tmp_path / "runtime.sqlite3",
        jobs_path=tmp_path / "jobs.sqlite3",
    )
    thread = threading.Thread(target=app.serve_forever, daemon=True)
    thread.start()
    try:
        yield app, int(app.server_address[1])
    finally:
        app.shutdown()
        thread.join(timeout=3)
        app.server_close()


def get(port: int, path: str, *, method: Literal["GET", "POST"] = "GET") -> tuple[int, dict[str, object], dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request(method, path)
        response = conn.getresponse()
        body = response.read()
        headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, json_object(body, label="result") if body.startswith(b"{") else {}, headers
    finally:
        conn.close()


def completed_run(app: PromptaJobServer, send_id: str, name: str, now: float) -> None:
    app.results.ensure_queued(send_id, f"Prompt for {name}", name, now=now)
    assert app.results.accept(send_id, f"100:{send_id}", deadline=now + 1000, now=now + 1)
    assert app.results.write(send_id, f"100:{send_id}", CaptureResult(
        "sse", "complete", f"**Answer** for {name}\n\n```py\nprint(1)\n```", "c1", "m1", "p1"
    ), now=now + 2)


def test_results_api_lists_only_local_runs_with_filter_search_and_pagination(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        completed_run(app, "run-1", "Daily review", 100)
        completed_run(app, "run-2", "Nightly summary", 200)
        app.results.ensure_queued("run-3", "Pending review", "Review job", now=300)

        status, body, headers = get(port, "/api/results?limit=2&offset=0")
        assert status == 200 and headers["cache-control"] == "no-store"
        assert body["total"] == 3
        rows = body["items"]
        assert isinstance(rows, list)
        assert len(rows) == 2
        first, second = string_object_dict(rows[0]), string_object_dict(rows[1])
        assert first is not None and second is not None
        assert [first["send_id"], second["send_id"]] == ["run-3", "run-2"]
        assert "assistant_text" not in first and "user_text" not in second
        assert "capture_owner" not in first
        other_rows = get(port, "/api/results?limit=2&offset=2")[1]["items"]
        assert isinstance(other_rows, list) and len(other_rows) == 1
        remaining = string_object_dict(other_rows[0])
        assert remaining is not None and remaining["send_id"] == "run-1"
        assert get(port, "/api/results?q=summary")[1]["total"] == 1
        assert get(port, "/api/results?q=%2A%2AAnswer%2A%2A")[1]["total"] == 2
        assert get(port, "/api/results?status=queued")[1]["total"] == 1
        assert get(port, "/api/results?status=completed")[1]["total"] == 2
        assert get(port, "/api/results?q=%25")[1]["total"] == 0

        status, detail, _ = get(port, "/api/results/run-2")
        assert status == 200 and isinstance(detail["assistant_text"], str)
        assert detail["assistant_text"].startswith("**Answer**")
        assert detail["user_text"] == "Prompt for Nightly summary"
        assert "capture_owner" not in detail and "conversation_id" not in detail
        assert get(port, "/api/results/absent")[0] == 404
        assert get(port, "/api/results?limit=5000")[0] == 400
        assert get(port, "/api/results?status=bogus")[0] == 400
        assert get(port, "/api/results?q=x&q=y")[0] == 400
        assert get(port, "/api/results?offset=-1")[0] == 400
        assert get(port, "/api/results/xx%2Fyy")[0] == 404
        assert get(port, "/api/results/run-1", method="POST")[0] == 404


def test_partial_and_unavailable_states_are_truthful_and_logs_private(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with server(tmp_path) as (app, port):
        app.results.ensure_queued("partial", "Secret prompt", "Job", now=100)
        assert app.results.accept("partial", "10:a", deadline=300, now=101)
        assert app.results.write("partial", "10:a", CaptureResult(
            "dom", "partial", "Secret partial answer", "c1", "m1", "p1"
        ), now=102)
        app.results.ensure_queued("failed", "Secret failed prompt", "Job", now=100)
        app.results.unavailable("failed", now=103)
        with caplog.at_level(logging.INFO):
            _, partial, _ = get(port, "/api/results/partial")
            _, unavailable, _ = get(port, "/api/results/failed")
            get(port, "/api/results?q=Secret%20prompt")
        assert partial["status"] == "generating" and partial["assistant_text"] == "Secret partial answer"
        assert unavailable["status"] == "unavailable" and unavailable["assistant_text"] == ""
        assert "Secret" not in caplog.text and "partial" not in caplog.text
        assert app.results.path.stat().st_mode & 0o077 == 0


def test_results_reads_do_not_call_chatgpt_or_open_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.playwright_driver as browser

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("UI attempted to open a ChatGPT browser")

    monkeypatch.setattr(browser, "PlaywrightDriver", fail)
    with server(tmp_path) as (_, port):
        for _ in range(10):
            assert get(port, "/api/results")[0] == 200
            assert get(port, "/api/results/absent")[0] == 404


def test_legacy_dom_table_is_rendered_as_table_on_desktop_and_mobile(tmp_path: Path) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    screenshots = Path(os.environ.get("PROMPTA_SCREENSHOT_DIR", str(tmp_path)))
    screenshots.mkdir(parents=True, exist_ok=True, mode=0o700)
    legacy = (
        "Intro paragraph.\n\nStage\n\n\t\n\nRestored job"
        "\n\n\n\n\n1\n\n\t\n\nOriginal game design"
        "\n\n\n\n\n2\n\n\t\n\nHexagonal board"
        "\n\nThe original jobs remain paused."
    )
    with server(tmp_path) as (app, port):
        app.results.ensure_queued("legacy", "Restore jobs", "Legacy table", now=100)
        assert app.results.accept("legacy", "100:legacy", deadline=1000, now=101)
        assert app.results.write("legacy", "100:legacy", CaptureResult(
            "dom", "complete", legacy, "c1", "m1", "p1"
        ), now=102)
        # The API must keep the original evidence for reply-parent verification.
        assert get(port, "/api/results/legacy")[1]["assistant_text"] == legacy

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium_path, headless=True,
                args=["--no-sandbox", "--single-process", "--no-zygote"],
            )
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                hosts: list[str] = []
                page.on("request", lambda request: hosts.append(request.url.split("/")[2]))
                page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                page.get_by_role("button", name="Chats", exact=True).click()
                page.locator(".chat-row").filter(has_text="Legacy table").click()
                expect(page.locator(".result-markdown table")).to_have_count(1)
                assert page.locator(".result-markdown th").all_inner_texts() == [
                    "Stage", "Restored job"
                ]
                assert page.locator(".result-markdown tbody tr").count() == 2
                assert page.locator(".result-markdown tbody tr").all_inner_texts() == [
                    "1\tOriginal game design", "2\tHexagonal board"
                ]
                assert "Intro paragraph." in page.locator(".result-markdown").inner_text()
                assert "The original jobs remain paused." in page.locator(".result-markdown").inner_text()
                for width, height, name in [
                    (1440, 900, "desktop"), (390, 844, "mobile"),
                ]:
                    page.set_viewport_size({"width": width, "height": height})
                    page.locator(".result-markdown table").scroll_into_view_if_needed()
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    screenshot = screenshots / f"legacy-response-{name}.png"
                    page.screenshot(path=str(screenshot), animations="disabled")
                    screenshot.chmod(0o600)
                assert all(host.startswith("127.0.0.1:") for host in hosts)
            finally:
                browser.close()


def test_chats_ui_desktop_mobile_and_no_chatgpt_requests(tmp_path: Path) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    screenshots = Path(os.environ.get("PROMPTA_SCREENSHOT_DIR", str(tmp_path)))
    screenshots.mkdir(parents=True, exist_ok=True, mode=0o700)
    with server(tmp_path) as (app, port):
        now = 1793020000.0
        from prompta.reply_contracts import ReplyIntent

        image = app.images.save(
            "preview.png",
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO9pB7sAAAAASUVORK5CYII=",
        )
        app.queue.enqueue_idempotent({
            "send_id": "daily", "message": "Prompt for Daily review", "images": [image],
        })
        completed_run(app, "daily", "Daily review", now)
        completed_run(app, "nightly", "Nightly summary", now - 90_000)
        app.replies.prepare("daily", ReplyIntent("reply-12345678901234", "c1", "m1", "What changed?"), now=now + 3)
        assert app.replies.claim("reply-12345678901234", "100:test", deadline=now + 1000, now=now + 4)
        assert app.replies.accepted("reply-12345678901234", "100:test", conversation_id="c1", parent_id="m1", message_id="m2", now=now + 5)
        assert app.replies.observe("reply-12345678901234", "100:test", CaptureResult(
            "sse", "complete", "### Follow-up\n\n" + "Verified paragraph. " * 120 + "\n\n```ts\nconst answer = 42;\n```",
            "c1", "m2", "m1",
        ), now=now + 6)
        assert get(port, "/api/results/daily")[1]["images"] == [
            {"name": "preview.png", "url": "./api/images/" + image},
        ]
        app.results.ensure_queued("partial", "Build release notes", "Release notes", now=now + 100)
        assert app.results.accept("partial", "10:partial", deadline=now + 1000, now=now + 101)
        assert app.results.write("partial", "10:partial", CaptureResult(
            "dom", "partial", "### So far\n\nStill generating a **partial** answer.",
            "c2", "m2", "p2",
        ), now=now + 102)
        app.results.ensure_queued("unsafe", "Render unsafe markup. " * 65, "Security", now=now - 180_000)
        assert app.results.accept("unsafe", "10:unsafe", deadline=now + 1000, now=now - 179_999)
        assert app.results.write("unsafe", "10:unsafe", CaptureResult(
            "sse", "complete", "<img src=x onerror=alert(1)> [bad](javascript:alert(1))",
            "c3", "m3", "p3",
        ), now=now - 179_998)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium_path, headless=True,
                args=["--no-sandbox", "--single-process", "--no-zygote"],
            )
            try:
                context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
                page = context.new_page()
                network_hosts: list[str] = []
                network_methods: list[str] = []
                page.on("request", lambda request: network_hosts.append(request.url.split("/")[2]))
                page.on("request", lambda request: network_methods.append(request.method))
                page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                page.get_by_role("button", name="Chats", exact=True).click()
                page.locator(".chat-row").first.wait_for()
                assert page.locator(".chat-row").count() == 4
                page.locator(".chat-row").filter(has_text="Daily review").click()
                assert page.locator(".result-markdown pre code").first.inner_text() == "print(1)"
                assert page.locator(".prompt-message").all_inner_texts() == ["Prompt for Daily review", "What changed?"]
                assert page.locator(".chat-attachments img").count() == 1
                assert page.locator(".assistant-group").count() == 2
                assert page.get_by_role("button", name="Copy code").count() == 2
                assert page.get_by_role("button", name="Copy assistant reply 2").count() == 1
                pane = page.locator(".chat-transcript-scroll")
                assert pane.evaluate("(element) => element.scrollHeight > element.clientHeight")
                pane.evaluate("(element) => { element.scrollTop = 90; }")
                before_scroll = pane.evaluate("(element) => element.scrollTop")
                page.get_by_role("button", name="Refresh local results").click()
                page.get_by_role("button", name="Refresh local results").click()
                expect(page.locator(".prompt-message")).to_have_count(2)
                page.wait_for_timeout(300)
                assert abs(pane.evaluate("(element) => element.scrollTop") - before_scroll) < 3
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(screenshots / "prompta-chats-desktop.png"), animations="disabled")

                page.locator(".chat-row").filter(has_text="Security").click()
                expect(page.locator(".prompt-message.collapsed")).to_have_count(1)
                bubble = page.locator(".prompt-bubble")
                bubble.scroll_into_view_if_needed()
                collapsed_box = bubble.bounding_box()
                page.get_by_role("button", name="Show full prompt").click()
                expect(page.locator(".prompt-message.collapsed")).to_have_count(0)
                expanded_box = bubble.bounding_box()
                assert collapsed_box and expanded_box
                assert expanded_box["height"] > collapsed_box["height"]
                assert abs(expanded_box["y"] - collapsed_box["y"]) < 4
                page.get_by_role("button", name="Show less").click()
                assert page.locator(".result-markdown img").count() == 0
                assert page.locator(".result-markdown a").count() == 0
                assert "<img" in page.locator(".result-markdown").inner_text()
                page.get_by_role("button", name="Search chats").click()
                page.locator(".chats-controls select").select_option("completed")
                expect(page.locator(".chat-row")).to_have_count(3)
                page.locator(".chats-controls select").select_option("")
                page.locator(".chats-controls input").fill("Nightly")
                expect(page.locator(".chat-row")).to_have_count(1)
                assert page.locator(".chat-row").inner_text().find("Nightly summary") >= 0
                page.locator(".sidebar-actions").get_by_role("button", name="New chat").click()
                composer = page.get_by_role("textbox", name="Message for new chat")
                initial_box = composer.bounding_box()
                assert initial_box is not None
                initial_height = initial_box["height"]
                assert initial_height >= 100
                draft_text = chr(10).join(["Draft survives reloading."] * 18)
                composer.fill(draft_text)
                expanded_composer_box = composer.bounding_box()
                assert expanded_composer_box is not None
                assert expanded_composer_box["height"] > initial_height
                page.reload(wait_until="networkidle")
                expect(page.get_by_role("textbox", name="Message for new chat")).to_have_value(draft_text)
                page.get_by_role("button", name="Chats", exact=True).click()
                page.locator(".sidebar-actions").get_by_role("button", name="New chat").click()
                expect(page.get_by_role("textbox", name="Message for new chat")).to_have_value(draft_text)
                page.get_by_role("textbox", name="Message for new chat").fill("")
                assert page.evaluate("localStorage.getItem('prompta.new-chat-draft.v1')") == ""
                assert all(host == f"127.0.0.1:{port}" for host in network_hosts)
                assert all(method == "GET" for method in network_methods)

                page.set_viewport_size({"width": 390, "height": 844})
                phone = page
                phone.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
                list_box = phone.locator(".chats-list").bounding_box()
                refresh_box = phone.locator(".chats-refresh").bounding_box()
                pin_box = phone.locator(".chat-pin").first.bounding_box()
                assert list_box and refresh_box and pin_box
                assert list_box["y"] < 300
                assert refresh_box["width"] >= 44
                assert pin_box["width"] >= 44
                first_title = phone.locator(".chat-row-top strong").first
                title_before = first_title.bounding_box()
                phone.locator(".chat-row-top").first.evaluate(
                    "(row) => { const dot = document.createElement('span'); "
                    "dot.className = 'unread-indicator'; row.prepend(dot); }"
                )
                title_after = first_title.bounding_box()
                assert title_before and title_after
                assert 0 < title_after["x"] - title_before["x"] <= 18
                phone.screenshot(path=str(screenshots / "mobile-chats-list.png"), animations="disabled")
                phone.locator(".chat-row").filter(has_text="Daily review").click()
                expect(phone.locator(".assistant-group")).to_have_count(2)
                assert phone.locator(".prompt-message").count() == 2
                assert phone.locator(".chats-sidebar").is_hidden()
                assert phone.locator(".chats-detail").is_visible()
                assert phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                phone.locator(".chats-detail").evaluate("(element) => { element.scrollTop = 0; }")
                phone.screenshot(path=str(screenshots / "prompta-stage4-mobile-top.png"), animations="disabled")
                phone.locator(".chats-detail").evaluate("(element) => { element.scrollTop = element.scrollHeight; }")
                phone.screenshot(path=str(screenshots / "prompta-chats-mobile.png"), animations="disabled")
                phone.get_by_role("button", name="All chats").click()
                phone.locator(".chat-row").filter(has_text="Security").click()
                expect(phone.locator(".prompt-message.collapsed")).to_have_count(1)
                phone.get_by_role("button", name="All chats").click()
                phone.locator(".chat-row").filter(has_text="Release notes").click()
                expect(phone.get_by_text("Partial response", exact=False)).to_be_visible()
                phone.get_by_role("button", name="All chats").click()
                assert phone.locator(".chats-sidebar").is_visible()
                assert phone.locator(".chats-detail").is_hidden()
                context.close()
            finally:
                browser.close()


def test_mobile_jobs_editor_navigation_and_touch_targets(tmp_path: Path) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    screenshots = Path(os.environ.get("PROMPTA_SCREENSHOT_DIR", str(tmp_path)))
    screenshots.mkdir(parents=True, exist_ok=True, mode=0o700)
    with server(tmp_path) as (app, port):
        for index in range(16):
            add_job(app.jobs_path, f"mobile-{index:02}", "Work safely on mobile", 2400)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium_path, headless=True,
                args=["--no-sandbox", "--single-process", "--no-zygote"],
            )
            try:
                page = browser.new_page(
                    viewport={"width": 390, "height": 844},
                    device_scale_factor=1, is_mobile=True, has_touch=True,
                )
                page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                expect(page.locator(".job-row")).to_have_count(10)
                page.screenshot(path=str(screenshots / "mobile-jobs-top.png"), animations="disabled")
                pane = page.locator(".jobs-workspace")
                target = page.locator(".job-row").nth(5).get_by_role("button", name="Edit")
                target.scroll_into_view_if_needed()
                before_scroll = pane.evaluate("(element) => element.scrollTop")
                assert before_scroll > 100
                page.screenshot(path=str(screenshots / "mobile-jobs-list.png"), animations="disabled")
                target.click()
                expect(page.get_by_role("heading", name="Edit job")).to_be_visible()
                page.locator(".prompt-field textarea").fill("Edited but unsaved")
                focused_box = page.locator(".prompt-field textarea").bounding_box()
                assert focused_box and focused_box["height"] <= 245
                page.screenshot(path=str(screenshots / "mobile-jobs-editor.png"), animations="disabled")
                page.set_viewport_size({"width": 390, "height": 520})
                page.locator(".prompt-field textarea").focus()
                page.wait_for_timeout(100)
                footer_box = page.locator(".editor-footer").bounding_box()
                prompt_box = page.locator(".prompt-field textarea").bounding_box()
                assert footer_box and prompt_box
                assert footer_box["y"] + footer_box["height"] <= 520
                assert prompt_box["y"] + prompt_box["height"] <= footer_box["y"] - 36
                page.screenshot(path=str(screenshots / "mobile-jobs-keyboard-viewport.png"), animations="disabled")
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator(".editor-back").click()
                expect(page.get_by_role("alertdialog", name="Discard unsaved changes")).to_be_visible()
                expect(page.locator(".editor-actions")).to_have_count(0)
                page.screenshot(path=str(screenshots / "mobile-jobs-discard.png"), animations="disabled")
                page.get_by_role("button", name="Keep editing").click()
                expect(page.locator(".prompt-field textarea")).to_have_value("Edited but unsaved")
                page.get_by_role("button", name="Cancel").click()
                page.get_by_role("button", name="Discard", exact=True).click()
                expect(page.locator(".job-row")).to_have_count(10)
                assert abs(pane.evaluate("(element) => element.scrollTop") - before_scroll) < 10
                page.get_by_role("button", name="Open chat sidebar").click()
                close_box = page.locator(".sidebar-close").bounding_box()
                assert close_box and close_box["width"] >= 44
                page.screenshot(path=str(screenshots / "mobile-jobs-drawer.png"), animations="disabled")
                page.get_by_role("button", name="Close sidebar").click()
                for width, height in [(360, 780), (430, 932), (1440, 900)]:
                    page.set_viewport_size({"width": width, "height": height})
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.close()
            finally:
                browser.close()


def test_explicit_reply_intent_contract_is_local_and_not_dispatched(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    from prompta.reply_contracts import ReplyIntent

    with server(tmp_path) as (app, port):
        app.results.ensure_queued("known", "Private seed", now=100)
        assert app.results.accept("known", "100:seed", deadline=300, now=101)
        assert app.results.write("known", "100:seed", CaptureResult(
            "sse", "complete", "Private answer", "conversation-1234567890",
            "assistant-1234567890", "user-1234567890123"
        ), now=102)
        payload: dict[str, object] = {
            "reply_id": "reply-1234567890123", "conversation_id": "conversation-1234567890",
            "parent_id": "assistant-1234567890", "text": "Private manual question",
        }
        assert ReplyIntent.parse(payload).text == payload["text"]

        def post(body: dict[str, object], *, content_type: str = "application/json") -> tuple[int, dict[str, object]]:
            conn = HTTPConnection("127.0.0.1", port, timeout=3)
            try:
                conn.request("POST", "/api/results/known/reply-intents",
                             body=json.dumps(body), headers={"content-type": content_type})
                response = conn.getresponse()
                result = json_object(response.read(), label="intent")
                return response.status, result
            finally:
                conn.close()

        with caplog.at_level(logging.INFO):
            status, result = post(payload)
            assert status == 202 and result["dispatched"] is False
            assert get(port, "/api/results/known/turns")[0] == 200
            assert post(payload)[0] == 202
            changed: dict[str, object] = {**payload, "text": "changed"}
            assert post(changed)[0] == 409
            assert post({**payload, "reply_id": "reply-9999999999999"})[0] == 409
            assert post(payload, content_type="text/plain")[0] == 400
            assert get(port, "/api/results/unknown/turns")[0] == 404
            assert get(port, "/api/results/known/turns", method="POST")[0] == 404
        turns = get(port, "/api/results/known/turns")[1]["turns"]
        assert isinstance(turns, list) and len(turns) == 2
        turn = string_object_dict(turns[1])
        assert turn is not None and turn["status"] == "prepared"
        assert "lease_owner" not in turn
        assert "Private manual question" not in caplog.text
        assert "Private answer" not in caplog.text


def test_unread_badges_follow_completed_answers_not_metadata(tmp_path: Path) -> None:
    """End-to-end: no false badge for queued/partial/status writes or unsent replies."""
    from sqlalchemy import update

    from prompta.reply_contracts import ReplyIntent
    from prompta.response_store import results

    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not chromium or not Path(chromium).is_file():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port):
        app.results.ensure_queued("pending", "Pending prompt", "Pending", now=300)
        app.results.ensure_queued("partial", "Partial prompt", "Partial", now=310)
        assert app.results.accept("partial", "100:partial", deadline=900, now=311)
        assert app.results.write("partial", "100:partial", CaptureResult(
            "dom", "partial", "Still writing...", "c1", "m1", "p1",
        ), now=312)
        completed_run(app, "answered", "Answered", 400)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium, headless=True,
                args=["--no-sandbox", "--single-process", "--no-zygote"],
            )
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.add_init_script("""if (!localStorage.getItem("prompta.local-sidebar.v1")) {
                    localStorage.setItem(
                        "prompta.local-sidebar.v1",
                        JSON.stringify({baselineAt: 100, pinnedIds: [], readAt: {}})
                    );
                }""")
                remote: list[str] = []
                page.on("request", lambda request: remote.append(request.url)
                        if not request.url.startswith(f"http://127.0.0.1:{port}/") else None)
                page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                page.get_by_role("button", name="Chats", exact=True).click()
                answered = page.locator(".chat-entry").filter(has_text="Answered")
                pending = page.locator(".chat-entry").filter(has_text="Pending")
                partial = page.locator(".chat-entry").filter(has_text="Partial")
                expect(answered.locator(".unread-indicator")).to_have_count(1)
                expect(pending.locator(".unread-indicator")).to_have_count(0)
                expect(partial.locator(".unread-indicator")).to_have_count(0)

                answered.locator(".chat-row").click()
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                pending.locator(".chat-row").click()
                page.reload(wait_until="networkidle")
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                with app.results.engine.begin() as connection:
                    connection.execute(update(results).where(
                        results.c.send_id == "answered",
                    ).values(updated_at=800))
                page.get_by_role("button", name="Refresh local results").click()
                expect(answered.locator(".unread-indicator")).to_have_count(0)

                intent = ReplyIntent("reply-12345678901234", "c1", "m1", "Follow up")
                assert app.replies.prepare("answered", intent, now=600)
                page.get_by_role("button", name="Refresh local results").click()
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                assert app.replies.claim(intent.reply_id, "100:manual", deadline=900, now=601)
                assert app.replies.accepted(
                    intent.reply_id, "100:manual", conversation_id="c1",
                    parent_id="m1", message_id="m2", now=602,
                )
                assert app.replies.observe(intent.reply_id, "100:manual", CaptureResult(
                    "dom", "partial", "Working on the answer", "c1", "m2", "m1",
                ), now=603)
                page.get_by_role("button", name="Refresh local results").click()
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                assert app.replies.observe(intent.reply_id, "100:manual", CaptureResult(
                    "sse", "complete", "New verified assistant reply", "c1", "m2", "m1",
                ), now=604)
                page.get_by_role("button", name="Refresh local results").click()
                expect(answered.locator(".unread-indicator")).to_have_count(1)
                answered.locator(".chat-row").click()
                expect(page.locator(".assistant-group")).to_have_count(2)
                expect(page.get_by_text("New verified assistant reply")).to_have_count(1)
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                assert remote == []
            finally:
                browser.close()
