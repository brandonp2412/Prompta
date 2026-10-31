from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from web_results_support import (
    completed_run,
    get,
    server,
)
from web_results_support import (
    serve_worktree_assets as serve_worktree_assets,
)

from prompta.jobs import add_job
from prompta.response_capture import CaptureResult


@pytest.mark.parametrize("width,height", [(360, 800), (390, 844), (412, 915)])
def test_sidebar_infinite_scroll_search_focus_and_wide_mobile_swipe(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        for index in range(65):
            completed_run(app, f"scroll-{index:03}", f"Scroll entry {index:03}", 1000 + index)
        browser = playwright.chromium.launch(
            executable_path=chromium_path,
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                is_mobile=True,
                has_touch=True,
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
            jobs = jobs_button.bounding_box()
            new_chat = nav.get_by_role("button", name="New chat").bounding_box()
            search = nav.get_by_role("button", name="Search chats").bounding_box()
            assert jobs and new_chat and search
            # Mobile keeps the three accessible actions in one row.
            assert (
                max(jobs["y"], new_chat["y"], search["y"])
                - min(jobs["y"], new_chat["y"], search["y"])
                < 2
            )
            assert min(jobs["width"], new_chat["width"], search["width"]) >= 40
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
            sidebar = page.locator(".chats-sidebar")
            backdrop = page.locator(".drawer-backdrop")
            expect(sidebar).to_be_hidden()
            cdp = context.new_cdp_session(page)

            def touch(event_type: str, x: int = 0, y: int = 300) -> None:
                points = [{"x": x, "y": y}] if event_type != "touchEnd" else []
                cdp.send(
                    "Input.dispatchTouchEvent",
                    {
                        "type": event_type,
                        "touchPoints": points,
                    },
                )

            def swipe(start_x: int, end_x: int) -> None:
                touch("touchStart", start_x)
                for step in range(1, 7):
                    touch("touchMove", round(start_x + (end_x - start_x) * step / 6))
                touch("touchEnd")

            # Vertical page movement must not steal scrolling or open the drawer.
            touch("touchStart", 105)
            touch("touchMove", 115, 410)
            touch("touchEnd")
            expect(sidebar).to_be_hidden()

            # The drawer and dimming layer follow a partial drag in both directions.
            touch("touchStart", 105)
            touch("touchMove", 155)
            page.wait_for_function(
                "() => document.querySelector('.chats-layout')?.classList.contains('drawer-interacting')"
            )
            first_box = sidebar.bounding_box()
            assert first_box is not None and -first_box["width"] < first_box["x"] < 0
            first_opacity = float(backdrop.evaluate("element => getComputedStyle(element).opacity"))
            assert 0 < first_opacity < 0.6
            touch("touchMove", 205)
            second_box = sidebar.bounding_box()
            assert second_box is not None and second_box["x"] > first_box["x"] + 25
            touch("touchMove", 175)
            reversed_box = sidebar.bounding_box()
            assert reversed_box is not None and reversed_box["x"] < second_box["x"] - 10
            touch("touchEnd")
            expect(sidebar).to_be_hidden()  # A reversed pull settles closed.

            # Pausing before release must not preserve an old high swipe velocity.
            touch("touchStart", 105)
            touch("touchMove", 155)
            time.sleep(0.18)
            touch("touchEnd")
            expect(sidebar).to_be_hidden()

            swipe(105, 260)  # Starts beyond the narrow OS edge-swipe zone.
            expect(sidebar).to_be_visible()
            assert page.locator(".chats-layout").evaluate(
                "(element) => element.classList.contains('drawer-open')"
            )
            touch("touchStart", 240)
            touch("touchMove", 165)
            dragging_box = sidebar.bounding_box()
            assert dragging_box is not None and dragging_box["x"] < -30
            touch("touchMove", 215)
            reversed_box = sidebar.bounding_box()
            assert reversed_box is not None and reversed_box["x"] > dragging_box["x"] + 20
            touch("touchEnd")
            expect(sidebar).to_be_visible()  # Reverse direction before release.
            swipe(240, 50)
            expect(sidebar).to_be_hidden()
            expect(backdrop).to_be_hidden()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            assert all(url.startswith(f"http://{host}/") for _, url in observed)
            assert all(
                method == "GET" or (method == "POST" and url.endswith("/api/local-chat-reads"))
                for method, url in observed
            )
            context.close()
        finally:
            browser.close()


def test_partial_and_unavailable_states_are_truthful_and_logs_private(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with server(tmp_path) as (app, port):
        app.results.ensure_queued("partial", "Secret prompt", "Job", now=100)
        assert app.results.accept("partial", "10:a", deadline=300, now=101)
        assert app.results.write(
            "partial",
            "10:a",
            CaptureResult("dom", "partial", "Secret partial answer", "c1", "m1", "p1"),
            now=102,
        )
        app.results.ensure_queued("failed", "Secret failed prompt", "Job", now=100)
        app.results.unavailable("failed", now=103)
        with caplog.at_level(logging.INFO):
            _, partial, _ = get(port, "/api/results/partial")
            _, unavailable, _ = get(port, "/api/results/failed")
            get(port, "/api/results?q=Secret%20prompt")
        assert (
            partial["status"] == "generating"
            and partial["assistant_text"] == "Secret partial answer"
        )
        assert unavailable["status"] == "unavailable" and unavailable["assistant_text"] == ""
        assert "Secret" not in caplog.text and "partial" not in caplog.text
        assert app.results.path.stat().st_mode & 0o077 == 0


def test_results_reads_do_not_call_chatgpt_or_open_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        assert app.results.write(
            "legacy",
            "100:legacy",
            CaptureResult("dom", "complete", legacy, "c1", "m1", "p1"),
            now=102,
        )
        # The API must keep the original evidence for reply-parent verification.
        assert get(port, "/api/results/legacy")[1]["assistant_text"] == legacy

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium_path,
                headless=True,
                args=["--no-sandbox", "--no-zygote"],
            )
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                hosts: list[str] = []
                page.on("request", lambda request: hosts.append(request.url.split("/")[2]))
                page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
                page.locator(".chat-row").filter(has_text="Legacy table").click()
                expect(page.locator(".result-markdown table")).to_have_count(1)
                assert page.locator(".result-markdown th").all_inner_texts() == [
                    "Stage",
                    "Restored job",
                ]
                assert page.locator(".result-markdown tbody tr").count() == 2
                assert page.locator(".result-markdown tbody tr").all_inner_texts() == [
                    "1\tOriginal game design",
                    "2\tHexagonal board",
                ]
                assert "Intro paragraph." in page.locator(".result-markdown").inner_text()
                assert (
                    "The original jobs remain paused."
                    in page.locator(".result-markdown").inner_text()
                )
                for width, height, name in [
                    (1440, 900, "desktop"),
                    (390, 844, "mobile"),
                ]:
                    page.set_viewport_size({"width": width, "height": height})
                    page.locator(".result-markdown table").scroll_into_view_if_needed()
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    )
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
        app.queue.enqueue_idempotent(
            {
                "send_id": "daily",
                "message": "Prompt for Daily review",
                "images": [image],
            }
        )
        completed_run(app, "daily", "Daily review", now)
        completed_run(app, "nightly", "Nightly summary", now - 90_000)
        app.replies.prepare(
            "daily", ReplyIntent("reply-12345678901234", "c1", "m1", "What changed?"), now=now + 3
        )
        assert app.replies.claim(
            "reply-12345678901234", "100:test", deadline=now + 1000, now=now + 4
        )
        assert app.replies.accepted(
            "reply-12345678901234",
            "100:test",
            conversation_id="c1",
            parent_id="m1",
            message_id="m2",
            now=now + 5,
        )
        assert app.replies.observe(
            "reply-12345678901234",
            "100:test",
            CaptureResult(
                "sse",
                "complete",
                "### Follow-up\n\n"
                + "Verified paragraph. " * 120
                + "\n\n```ts\nconst answer = 42;\n```",
                "c1",
                "m2",
                "m1",
            ),
            now=now + 6,
        )
        assert get(port, "/api/results/daily")[1]["images"] == [
            {"name": "preview.png", "url": "./api/images/" + image},
        ]
        app.results.ensure_queued("partial", "Build release notes", "Release notes", now=now + 100)
        assert app.results.accept("partial", "10:partial", deadline=now + 1000, now=now + 101)
        assert app.results.write(
            "partial",
            "10:partial",
            CaptureResult(
                "dom",
                "partial",
                "### So far\n\nStill generating a **partial** answer.",
                "c2",
                "m2",
                "p2",
            ),
            now=now + 102,
        )
        app.results.ensure_queued(
            "unsafe", "Render unsafe markup. " * 65, "Security", now=now - 180_000
        )
        assert app.results.accept("unsafe", "10:unsafe", deadline=now + 1000, now=now - 179_999)
        assert app.results.write(
            "unsafe",
            "10:unsafe",
            CaptureResult(
                "sse",
                "complete",
                "<img src=x onerror=alert(1)> [bad](javascript:alert(1))",
                "c3",
                "m3",
                "p3",
            ),
            now=now - 179_998,
        )

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium_path,
                headless=True,
                args=["--no-sandbox", "--no-zygote"],
            )
            try:
                context = browser.new_context(
                    viewport={"width": 1440, "height": 900}, device_scale_factor=1
                )
                page = context.new_page()
                network_hosts: list[str] = []
                network_requests: list[tuple[str, str]] = []
                page.on("request", lambda request: network_hosts.append(request.url.split("/")[2]))
                page.on(
                    "request",
                    lambda request: network_requests.append((request.method, request.url)),
                )
                page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
                page.locator(".chat-row").first.wait_for()
                assert page.locator(".chat-row").count() == 4
                page.locator(".chat-row").filter(has_text="Daily review").click()
                expect(page.locator(".result-markdown pre code").first).to_have_text("print(1)")
                expect(page.locator(".prompt-message")).to_have_count(2)
                assert page.locator(".prompt-message").all_inner_texts() == [
                    "Prompt for Daily review",
                    "What changed?",
                ]
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
                page.screenshot(
                    path=str(screenshots / "prompta-chats-desktop.png"), animations="disabled"
                )

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
                assert jobs_box and jobs_box["width"] >= 44
                assert jobs_action.inner_text().strip() == "Jobs"
                assert jobs_action.get_attribute("title") == "Jobs"
                for label in ("New chat", "Search chats"):
                    action = page.locator(".sidebar-actions").get_by_role("button", name=label)
                    text = action.locator(".action-label")
                    assert text.is_visible()
                    assert text.evaluate("element => element.scrollWidth <= element.clientWidth")
                    action_box = action.bounding_box()
                    assert action_box is not None and 44 <= action_box["height"] <= 64
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
                expect(page.get_by_role("button", name="Send fresh chat")).to_have_count(0)
                composer.fill("Draft")
                send = page.get_by_role("button", name="Send fresh chat").bounding_box()
                assert attach and send
                # Attachment is a small bottom-left icon; textarea spans the composer width.
                assert attach["y"] >= initial_box["y"] + initial_height - 2
                assert abs(attach["x"] - initial_box["x"]) <= 4
                assert attach["width"] == 44
                assert abs(send["y"] - attach["y"]) <= 2
                assert send["x"] > initial_box["x"] + initial_box["width"] / 2
                draft_text = chr(10).join(["Draft survives reloading."] * 18)
                composer.fill(draft_text)
                expanded_composer_box = composer.bounding_box()
                assert expanded_composer_box is not None
                assert initial_height < expanded_composer_box["height"] <= 111
                assert (
                    composer.evaluate("(element) => getComputedStyle(element).overflowY") == "auto"
                )
                composer.fill("")
                shrunk_box = composer.bounding_box()
                assert shrunk_box is not None
                assert abs(shrunk_box["height"] - initial_height) <= 1
                composer.fill(draft_text)
                page.reload(wait_until="networkidle")
                expect(page.get_by_role("textbox", name="Message for new chat")).to_have_value(
                    draft_text
                )
                page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
                page.locator(".sidebar-actions").get_by_role("button", name="New chat").click()
                expect(page.get_by_role("textbox", name="Message for new chat")).to_have_value(
                    draft_text
                )
                page.get_by_role("textbox", name="Message for new chat").fill("")
                assert page.evaluate("localStorage.getItem('prompta.new-chat-draft.v1')") == ""
                assert all(host == f"127.0.0.1:{port}" for host in network_hosts)
                assert all(
                    method == "GET" or "/api/local-chat-reads" in url
                    for method, url in network_requests
                )

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
                assert jobs_box["width"] >= 44
                assert list_box["y"] < 300
                assert search_box["width"] >= 44
                assert new_box["width"] >= 44
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
                phone.screenshot(
                    path=str(screenshots / "mobile-chats-list.png"), animations="disabled"
                )
                phone.locator(".chat-row").filter(has_text="Daily review").click()
                expect(phone.locator(".assistant-group")).to_have_count(2)
                assert phone.locator(".prompt-message").count() == 2
                expect(phone.locator(".chats-sidebar")).to_be_hidden()
                expect(phone.locator(".chats-detail")).to_be_visible()
                assert phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                phone.locator(".chats-detail").evaluate("(element) => { element.scrollTop = 0; }")
                phone.screenshot(
                    path=str(screenshots / "prompta-stage4-mobile-top.png"), animations="disabled"
                )
                phone.locator(".chats-detail").evaluate(
                    "(element) => { element.scrollTop = element.scrollHeight; }"
                )
                phone.screenshot(
                    path=str(screenshots / "prompta-chats-mobile.png"), animations="disabled"
                )
                phone.get_by_role("button", name="Back to chats").click()
                phone.locator(".chat-row").filter(has_text="Security").click()
                expect(phone.locator(".prompt-message.collapsed")).to_have_count(1)
                phone.get_by_role("button", name="Back to chats").click()
                phone.locator(".chat-row").filter(has_text="Release notes").click()
                expect(phone.get_by_text("Partial response", exact=False)).to_be_visible()
                phone.get_by_role("button", name="Back to chats").click()
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
                executable_path=chromium_path,
                headless=True,
                args=["--no-sandbox", "--no-zygote"],
            )
            try:
                page = browser.new_page(
                    viewport={"width": 390, "height": 844},
                    device_scale_factor=1,
                    is_mobile=True,
                    has_touch=True,
                )
                page.goto(f"http://127.0.0.1:{port}/?view=jobs", wait_until="networkidle")
                expect(page.locator(".job-row")).to_have_count(10)
                page.screenshot(
                    path=str(screenshots / "mobile-jobs-top.png"), animations="disabled"
                )
                pane = page.locator(".jobs-workspace")
                target = page.locator(".job-row").nth(5).get_by_role("button", name="Edit")
                target.scroll_into_view_if_needed()
                before_scroll = pane.evaluate("(element) => element.scrollTop")
                assert before_scroll > 100
                page.screenshot(
                    path=str(screenshots / "mobile-jobs-list.png"), animations="disabled"
                )
                target.click()
                expect(page.get_by_role("heading", name="Edit job")).to_be_visible()
                page.locator(".prompt-field textarea").fill("Edited but unsaved")
                focused_box = page.locator(".prompt-field textarea").bounding_box()
                assert focused_box and focused_box["height"] <= 245
                page.screenshot(
                    path=str(screenshots / "mobile-jobs-editor.png"), animations="disabled"
                )
                page.set_viewport_size({"width": 390, "height": 520})
                page.locator(".prompt-field textarea").focus()
                page.wait_for_timeout(100)
                footer_box = page.locator(".editor-footer").bounding_box()
                prompt_box = page.locator(".prompt-field textarea").bounding_box()
                assert footer_box and prompt_box
                # Compact portrait editors deliberately keep actions in normal
                # scroll order: the virtual keyboard must never overlay the prompt.
                assert prompt_box["y"] + prompt_box["height"] <= 520
                assert prompt_box["y"] + prompt_box["height"] < footer_box["y"]
                page.locator(".editor-footer").scroll_into_view_if_needed()
                footer_box = page.locator(".editor-footer").bounding_box()
                assert footer_box and footer_box["y"] >= 0
                assert footer_box["y"] + footer_box["height"] <= 521
                page.screenshot(
                    path=str(screenshots / "mobile-jobs-keyboard-viewport.png"),
                    animations="disabled",
                )
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator(".editor-back").click()
                expect(
                    page.get_by_role("alertdialog", name="Discard unsaved changes")
                ).to_be_visible()
                expect(page.locator(".editor-actions")).to_have_count(0)
                page.screenshot(
                    path=str(screenshots / "mobile-jobs-discard.png"), animations="disabled"
                )
                page.get_by_role("button", name="Keep editing").click()
                expect(page.locator(".prompt-field textarea")).to_have_value("Edited but unsaved")
                page.get_by_role("button", name="Cancel").click()
                page.get_by_role("button", name="Discard", exact=True).click()
                expect(page.locator(".job-row")).to_have_count(10)
                # Scroll restoration runs in requestAnimationFrame after the list remounts.
                page.wait_for_function(
                    "expected => { const pane = document.querySelector('.jobs-workspace'); "
                    "return pane && Math.abs(pane.scrollTop - expected) < 10; }",
                    arg=before_scroll,
                )
                page.get_by_role("button", name="Open chat sidebar").click()
                close_box = page.locator(".sidebar-close").bounding_box()
                assert close_box and close_box["width"] >= 44
                page.screenshot(
                    path=str(screenshots / "mobile-jobs-drawer.png"), animations="disabled"
                )
                page.get_by_role("button", name="Close sidebar").click()
                for width, height in [(360, 780), (430, 932), (1440, 900)]:
                    page.set_viewport_size({"width": width, "height": height})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    )
                page.close()
            finally:
                browser.close()
