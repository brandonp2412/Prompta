from __future__ import annotations

import json
import logging
import os
import threading
import time
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


@pytest.fixture(autouse=True)
def serve_worktree_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    # Nox's editable installation points at main even in an isolated worktree.
    import prompta.web as web_module

    assets = Path(__file__).resolve().parents[1] / "src/static"
    assert (assets / "app.js").is_file()
    monkeypatch.setattr(web_module, "_STATIC_ROOT", assets)


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


def post_json(port: int, path: str, data: dict[str, object]) -> tuple[int, dict[str, object]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request("POST", path, body=json.dumps(data), headers={"content-type": "application/json"})
        response = conn.getresponse()
        return response.status, json_object(response.read(), label="pin response")
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


def pin_ids(payload: dict[str, object]) -> list[str]:
    items = payload.get("items")
    assert isinstance(items, list)
    ids: list[str] = []
    for item in items:
        row = string_object_dict(item)
        assert row is not None
        send_id = row.get("send_id")
        assert isinstance(send_id, str)
        ids.append(send_id)
    return ids


def test_local_pins_persist_in_sqlite_and_never_change_chatgpt_pins(tmp_path: Path) -> None:
    from sqlalchemy import text

    from prompta.response_store import ResponseStore

    with server(tmp_path) as (app, port):
        completed_run(app, "a", "First", 100)
        completed_run(app, "b", "Second", 200)
        completed_run(app, "c", "Third", 300)
        path = app.results.path
        assert get(port, "/api/local-chat-pins")[1] == {"items": []}
        assert post_json(port, "/api/local-chat-pins", {"send_id": "missing", "pinned": True})[0] == 404
        assert post_json(port, "/api/local-chat-pins", {"send_id": "a", "pinned": "yes"})[0] == 400
        assert post_json(port, "/api/local-chat-pins", {"send_id": "a", "pinned": True, "extra": 1})[0] == 400
        assert post_json(port, "/api/local-chat-pins", {"send_id": "../a", "pinned": True})[0] == 400
        assert post_json(port, "/api/local-chat-pins/import", {"send_ids": ["missing", "b", "a"]})[0] == 200
        assert post_json(port, "/api/local-chat-pins/import", {"send_ids": ["c"]})[0] == 200
        _, initial, headers = get(port, "/api/local-chat-pins")
        assert headers["cache-control"] == "no-store"
        assert pin_ids(initial) == ["b", "a"]
        initial_items = initial["items"]
        assert isinstance(initial_items, list)
        assert all(isinstance(row, dict) and "assistant_text" not in row and "conversation_id" not in row for row in initial_items)
        assert all(isinstance(row, dict) and row.get("last_reply_revision") and row.get("last_reply_at") for row in initial_items)
        assert post_json(port, "/api/local-chat-pins", {"send_id": "a", "pinned": True})[0] == 200
        assert post_json(port, "/api/local-chat-pins", {"send_id": "b", "pinned": False})[0] == 200
        assert post_json(port, "/api/local-chat-pins", {"send_id": "c", "pinned": True})[0] == 200
        expected = ["c", "a"]
        assert pin_ids(get(port, "/api/local-chat-pins")[1]) == expected
        fresh_store = ResponseStore(path)
        assert [row["send_id"] for row in fresh_store.local_pinned_runs()] == expected
        with fresh_store.engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM local_chat_pins")).scalar_one() == 2
        assert path.stat().st_mode & 0o077 == 0
        assert str(path) not in str(initial)


def test_server_local_pins_across_browser_contexts_and_rapid_clicks(tmp_path: Path) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    with server(tmp_path) as (app, port):
        for i in range(26):
            completed_run(app, f"run-{i:02}", f"Chat {i:02}", 1000 + i)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium_path, headless=True,
                args=["--no-sandbox"],
            )
            try:
                first = browser.new_context(viewport={"width": 390, "height": 844})
                second = browser.new_context(viewport={"width": 1440, "height": 900})
                a = first.new_page()
                b = second.new_page()
                host = f"127.0.0.1:{port}"
                remote_hosts: list[str] = []
                a.on("request", lambda request: remote_hosts.append(request.url.split("/")[2]))
                b.on("request", lambda request: remote_hosts.append(request.url.split("/")[2]))
                a.goto(f"http://{host}/?view=chats", wait_until="domcontentloaded")
                a.evaluate("""() => localStorage.setItem("prompta.local-sidebar.v1",
                    JSON.stringify({ baselineAt: 1, readAt: {}, pinnedIds: ["run-00"] }))""")
                a.reload(wait_until="domcontentloaded")
                expect(a.locator(".chats-date")).to_have_count(0)
                expect(a.locator(".chats-pagination")).to_have_count(0)
                expect(a.locator(".chat-entry").filter(has_text="Chat 00")).to_have_count(1)
                assert "pinnedIds" not in json.loads(a.evaluate(
                    "localStorage.getItem('prompta.local-sidebar.v1')"))
                b.goto(f"http://{host}/?view=chats", wait_until="domcontentloaded")
                expect(b.locator(".chat-entry").filter(has_text="Chat 00")).to_have_count(1)
                target = b.locator(".chat-entry").filter(has_text="Chat 25").locator(".chat-pin")
                target.click()
                expect(a.locator(".chat-entry").filter(has_text="Chat 25").locator(".chat-pin")).to_have_attribute("aria-pressed", "true")
                target.click()
                target.click()
                target.click()
                expect(a.locator(".chat-entry").filter(has_text="Chat 25").locator(".chat-pin")).to_have_attribute("aria-pressed", "false")
                expect(b.locator(".chat-entry").filter(has_text="Chat 00").locator(".chat-pin")).to_have_attribute("aria-pressed", "true")
                b.route(f"http://{host}/api/local-chat-pins", lambda route: (
                    route.abort() if route.request.method == "POST" else route.continue_()
                ))
                target.click()
                expect(b.get_by_role("alert").filter(has_text="Could not save pinned chat")).to_be_visible()
                expect(target).to_have_attribute("aria-pressed", "false")
                b.unroute(f"http://{host}/api/local-chat-pins")
                a.reload(wait_until="domcontentloaded")
                assert pin_ids(get(port, "/api/local-chat-pins")[1]) == ["run-00"]
                assert all(value == host for value in remote_hosts)
            finally:
                browser.close()


@pytest.mark.parametrize("width,height", [(360, 800), (390, 844), (412, 915)])
def test_sidebar_infinite_scroll_search_focus_and_wide_mobile_swipe(
    tmp_path: Path, width: int, height: int,
) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        for index in range(65):
            completed_run(app, f"scroll-{index:03}", f"Scroll entry {index:03}", 1000 + index)
        browser = playwright.chromium.launch(
            executable_path=chromium_path, headless=True, args=["--no-sandbox"],
        )
        try:
            context = browser.new_context(
                viewport={"width": width, "height": height}, is_mobile=True, has_touch=True,
            )
            page = context.new_page()
            host = f"127.0.0.1:{port}"
            observed: list[tuple[str, str]] = []
            page.on("request", lambda request: observed.append((request.method, request.url)))
            page.goto(f"http://{host}/?view=chats", wait_until="networkidle")
            # Tall viewports may prefetch a second page before the first scroll.
            page.wait_for_function("() => document.querySelectorAll('.chat-entry').length >= 20")
            expect(page.locator(".chats-pagination, .chats-heading, .chats-date")).to_have_count(0)
            nav = page.locator(".sidebar-actions")
            jobs_button = nav.get_by_role("button", name="Jobs")
            assert jobs_button.get_attribute("class") == "sidebar-jobs"
            assert jobs_button.inner_text() == ""
            jobs = jobs_button.bounding_box()
            new_chat = nav.get_by_role("button", name="New chat").bounding_box()
            search = nav.get_by_role("button", name="Search chats").bounding_box()
            assert jobs and new_chat and search
            assert max(jobs["y"], new_chat["y"], search["y"]) - min(jobs["y"], new_chat["y"], search["y"]) < 2
            assert jobs["width"] == 44
            assert new_chat["width"] <= 44 and search["width"] <= 44
            nav.get_by_role("button", name="Search chats").click()
            assert page.locator(".chats-controls input").evaluate(
                "element => document.activeElement === element"
            )
            nav.get_by_role("button", name="Search chats").click()
            for _ in range(4):
                previous = page.locator(".chat-entry").count()
                if previous == 65:
                    break
                page.locator(".chats-list").evaluate(
                    "element => element.scrollTop = element.scrollHeight"
                )
                page.wait_for_function(
                    f"() => document.querySelectorAll('.chat-entry').length > {previous}"
                )
            expect(page.locator(".chat-entry")).to_have_count(65)
            assert page.locator(".chat-row-top strong").last.inner_text() == "Scroll entry 000"

            page.locator(".chat-row").first.click()
            expect(page.locator(".chats-sidebar")).to_be_hidden()
            cdp = context.new_cdp_session(page)

            def swipe(start_x: int, end_x: int) -> None:
                cdp.send("Input.dispatchTouchEvent", {
                    "type": "touchStart", "touchPoints": [{"x": start_x, "y": 300}],
                })
                for step in range(1, 7):
                    cdp.send("Input.dispatchTouchEvent", {
                        "type": "touchMove", "touchPoints": [{
                            "x": start_x + (end_x - start_x) * step / 6, "y": 300,
                        }],
                    })
                cdp.send("Input.dispatchTouchEvent", {
                    "type": "touchEnd", "touchPoints": [],
                })

            swipe(105, 260)  # Starts well beyond a narrow OS edge-swipe zone.
            expect(page.locator(".chats-sidebar")).to_be_visible()
            swipe(240, 50)
            expect(page.locator(".chats-sidebar")).to_be_hidden()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            assert all(url.startswith(f"http://{host}/") for _, url in observed)
            assert all(method == "GET" for method, _ in observed)
            context.close()
        finally:
            browser.close()


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
                page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
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
                page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
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
                # All three actions share one row, with desktop Create/Search labels.
                sidebar_nav = page.locator(".sidebar-actions")
                jobs_action = sidebar_nav.get_by_role("button", name="Jobs")
                jobs_box = jobs_action.bounding_box()
                assert jobs_box and jobs_box["width"] == 44
                assert jobs_action.inner_text() == ""
                assert jobs_action.get_attribute("title") == "Jobs"
                for label in ("New chat", "Search chats"):
                    action = page.locator(".sidebar-actions").get_by_role("button", name=label)
                    text = action.locator(".action-label")
                    assert text.is_visible()
                    assert text.evaluate("element => element.scrollWidth <= element.clientWidth")
                    action_box = action.bounding_box()
                    assert action_box is not None and action_box["height"] <= 55
                    assert abs(action_box["y"] - jobs_box["y"]) < 2
                    assert action_box["x"] > jobs_box["x"]
                jobs_action.click()
                expect(page.get_by_role("heading", name="Jobs", exact=True)).to_be_visible()
                expect(jobs_action).to_have_attribute("aria-current", "page")
                page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
                page.get_by_role("button", name="Search chats").click()
                assert page.locator(".chats-controls input").evaluate(
                    "element => document.activeElement === element"
                )
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
                assert 25 <= initial_height <= 40  # Exactly one text row when empty.
                attach = page.get_by_role("button", name="Attach images").bounding_box()
                send = page.get_by_role("button", name="Send fresh chat").bounding_box()
                assert attach and send
                # Attachment is a small bottom-left icon; textarea spans the composer width.
                assert attach["y"] >= initial_box["y"] + initial_height - 2
                assert abs(attach["x"] - initial_box["x"]) <= 4
                assert attach["width"] == 44
                assert abs(
                    (initial_box["y"] + initial_height / 2) - (send["y"] + send["height"] / 2)
                ) <= 2
                assert send["x"] > initial_box["x"] + initial_box["width"] / 2
                draft_text = chr(10).join(["Draft survives reloading."] * 18)
                composer.fill(draft_text)
                expanded_composer_box = composer.bounding_box()
                assert expanded_composer_box is not None
                assert initial_height < expanded_composer_box["height"] <= 111
                assert composer.evaluate("(element) => getComputedStyle(element).overflowY") == "auto"
                composer.fill("")
                shrunk_box = composer.bounding_box()
                assert shrunk_box is not None
                assert abs(shrunk_box["height"] - initial_height) <= 1
                composer.fill(draft_text)
                page.reload(wait_until="networkidle")
                expect(page.get_by_role("textbox", name="Message for new chat")).to_have_value(draft_text)
                page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
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
                jobs_box = phone.locator(".sidebar-jobs").bounding_box()
                search_box = phone.locator(".sidebar-search").bounding_box()
                new_box = phone.locator(".sidebar-actions .sidebar-primary").bounding_box()
                pin_box = phone.locator(".chat-pin").first.bounding_box()
                assert list_box and jobs_box and search_box and new_box and pin_box
                assert abs(jobs_box["y"] - new_box["y"]) < 2
                assert jobs_box["width"] == 44
                assert list_box["y"] < 300
                assert search_box["width"] <= 44
                assert new_box["width"] <= 44
                assert abs(search_box["y"] - new_box["y"]) < 2
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
                page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
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
                page.reload(wait_until="networkidle")
                expect(answered.locator(".unread-indicator")).to_have_count(0)

                intent = ReplyIntent("reply-12345678901234", "c1", "m1", "Follow up")
                assert app.replies.prepare("answered", intent, now=600)
                page.reload(wait_until="networkidle")
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                assert app.replies.claim(intent.reply_id, "100:manual", deadline=900, now=601)
                assert app.replies.accepted(
                    intent.reply_id, "100:manual", conversation_id="c1",
                    parent_id="m1", message_id="m2", now=602,
                )
                assert app.replies.observe(intent.reply_id, "100:manual", CaptureResult(
                    "dom", "partial", "Working on the answer", "c1", "m2", "m1",
                ), now=603)
                page.reload(wait_until="networkidle")
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                assert app.replies.observe(intent.reply_id, "100:manual", CaptureResult(
                    "sse", "complete", "New verified assistant reply", "c1", "m2", "m1",
                ), now=604)
                page.reload(wait_until="networkidle")
                expect(answered.locator(".unread-indicator")).to_have_count(1)
                answered.locator(".chat-row").click()
                expect(page.locator(".assistant-group")).to_have_count(2)
                expect(page.get_by_text("New verified assistant reply")).to_have_count(1)
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                assert remote == []
            finally:
                browser.close()


def test_queue_status_api_is_private_read_only_and_exposes_worker_wait_order(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[parallelism]\nmax_workers = 1\n")
        app.queue_view.concurrency_config_path = config_path
        for name in ("alpha", "beta", "gamma"):
            add_job(app.jobs_path, name, f"Secret prompt {name}", 60, exact_interval=True)
            app.queue_view.runtime.update_job_state(name, {"initial_due_at_epoch": 1000.0})
        assert app.queue_view.tick(now=1000.0) == 1

        status, payload, headers = get(port, "/api/queue-status")
        assert status == 200 and headers["cache-control"] == "no-store"
        assert payload == {
            "max_workers": 1, "occupied_slots": 1,
            "waiting": [{"name": "beta", "position": 1, "reason": "global", "occupied": 1, "limit": 1}, {"name": "gamma", "position": 2, "reason": "global", "occupied": 1, "limit": 1}],
        }
        assert "Secret prompt" not in str(payload)
        assert get(port, "/api/queue-status", method="POST")[0] == 404
        assert len(app.queue.records()) == 1


def test_waiting_chats_render_and_advance_on_desktop_and_mobile(tmp_path: Path) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    with server(tmp_path) as (app, port):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[parallelism]\nmax_workers = 1\n")
        app.queue_view.concurrency_config_path = config_path
        at = time.time()
        for name in ("alpha", "beta", "gamma"):
            add_job(app.jobs_path, name, f"Synthetic prompt for {name}", 60, exact_interval=True)
            app.queue_view.runtime.update_job_state(name, {"initial_due_at_epoch": at})
        assert app.queue_view.tick(now=at) == 1
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium_path, headless=True, args=["--no-sandbox"]
            )
            try:
                for width, height in ((1440, 900), (390, 844), (320, 700)):
                    context = browser.new_context(viewport={"width": width, "height": height})
                    page = context.new_page()
                    requests: list[tuple[str, str]] = []
                    page.on("request", lambda req: requests.append((req.method, req.url)))
                    page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="domcontentloaded")
                    expect(page.locator(".queue-heading")).to_contain_text("1/1 global slots")
                    rows = page.locator(".queue-waiting")
                    expect(rows).to_have_count(2)
                    expect(rows.nth(0)).to_contain_text("beta")
                    expect(rows.nth(0)).to_contain_text("#1")
                    expect(rows.nth(1)).to_contain_text("gamma")
                    expect(rows.nth(1)).to_contain_text("#2")
                    top = rows.nth(0).locator(".chat-row-top").bounding_box()
                    subtitle = rows.nth(0).locator(".queue-subtitle").bounding_box()
                    assert top is not None and subtitle is not None
                    assert subtitle["y"] >= top["y"] + top["height"] - 2
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=str(tmp_path / f"queued-{width}x{height}.png"))
                    assert all(method == "GET" for method, _ in requests)
                    assert all(url.startswith(f"http://127.0.0.1:{port}/") for _, url in requests)
                    if width == 1440:
                        rows.first.locator("button").click()
                        expect(page.locator(".jobs-workspace")).to_be_visible()
                        assert all(method == "GET" for method, _ in requests)
                    context.close()
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{port}/?view=chats")
                rows = page.locator(".queue-waiting")
                expect(rows).to_have_count(2)
                claimed = app.queue.claim_next("worker", now=at + 1, lease_seconds=30.0)
                assert claimed is not None
                assert app.queue.complete_claim(str(claimed["send_id"]), "worker", now=at + 2)
                assert app.queue_view.tick(now=at + 3) >= 1
                # SSE invalidates the local queue snapshot without a navigation or refresh.
                expect(rows).to_have_count(1)
                expect(rows.first).to_contain_text("gamma")
                expect(rows.first).to_contain_text("#1")
                expect(page.locator(".chat-entry:not(.queue-waiting)").filter(has_text="beta")).to_have_count(1)
                context.close()
            finally:
                browser.close()


def test_tool_cards_desktop_mobile_local_only(tmp_path: Path) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    screenshots = Path(os.environ.get("PROMPTA_SCREENSHOT_DIR", str(tmp_path)))
    screenshots.mkdir(parents=True, exist_ok=True, mode=0o700)
    with server(tmp_path) as (app, port):
        app.results.ensure_queued("tool-demo", "Summarise the checks", "Tool verification", now=200)
        assert app.results.accept("tool-demo", "100:tool", deadline=500, now=201)
        calls: tuple[dict[str, object], ...] = (
            {"id": "one", "connector": "GitHub", "action": "search_issues",
             "status": "completed", "arguments": '{"repo": "demo/project"}',
             "result": '{"count": 2}', "error": ""},
            {"id": "two", "connector": "Terminal", "action": "run_tests",
             "status": "error", "arguments": '{"suite": "e2e"}',
             "result": "", "error": "One example failed"},
        )
        assert app.results.write("tool-demo", "100:tool", CaptureResult(
            "sse", "complete", "## Final answer\n\nTwo checks were performed.",
            "c1", "m1", "p1", tool_calls=calls,
        ), now=202)
        status, body, _ = get(port, "/api/results/tool-demo")
        returned_calls = body["tool_calls"]
        assert status == 200 and isinstance(returned_calls, list) and len(returned_calls) == 2
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium_path, headless=True,
                args=["--no-sandbox", "--disable-gpu"],
            )
            try:
                for width, height, mobile in [(1440, 900, False), (320, 700, True), (360, 800, True), (390, 844, True), (412, 915, True)]:
                    page = browser.new_page(viewport={"width": width, "height": height},
                                            is_mobile=mobile, has_touch=mobile)
                    requests: list[tuple[str, str]] = []
                    page.on("request", lambda req: requests.append((req.method, req.url)))
                    page.goto(f"http://127.0.0.1:{port}/?view=chats&run=tool-demo", wait_until="networkidle")
                    expect(page.locator(".tool-call")).to_have_count(2)
                    expect(page.locator(".tool-timeline-summary")).to_contain_text("2 tool calls")
                    expect(page.locator(".tool-failure-count")).to_have_text("1 failed")
                    expect(page.get_by_role("heading", name="Final answer")).to_be_visible()
                    page.locator(".tool-call-summary").first.click()
                    expect(page.locator(".tool-call-body pre").first).to_contain_text("demo/project")
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    assert requests and all(method == "GET" and url.startswith(f"http://127.0.0.1:{port}/")
                                            for method, url in requests)
                    target = screenshots / f"tool-events-{width}.png"
                    page.screenshot(path=str(target), animations="disabled", full_page=True)
                    target.chmod(0o600)
                    page.close()
            finally:
                browser.close()
