from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import Page, expect, sync_playwright
from web_results_support import completed_run, server

from prompta.jobs import add_job
from prompta.reply_contracts import ReplyIntent
from prompta.response_capture import CaptureResult

VIEWPORTS = [(360, 800), (390, 844), (412, 915), (320, 700), (844, 390), (1440, 900)]


@pytest.fixture(autouse=True)
def serve_worktree_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    # The shared Nox virtualenv has an editable install pointing at main; browser
    # regression tests must serve the freshly built UI in this worktree instead.
    import prompta.web as web_module

    assets = Path(__file__).resolve().parents[1] / "src/static"
    assert (assets / "app.js").is_file()
    monkeypatch.setattr(web_module, "_STATIC_ROOT", assets)


def populate(app: object) -> None:
    from live_server import LiveServer

    assert isinstance(app, LiveServer)
    for index in range(16):
        add_job(
            app.jobs_path,
            f"Synthetic scheduled review {index:02}",
            "Inspect small-screen readability and very long wrapped job prompts. " * 5,
            3600 if index % 3 else 180,
        )
    now = time.time()
    completed_run(app, "daily", "Synthetic daily review", now - 20)
    completed_run(app, "nightly", "Synthetic evening review", now - 86400)
    app.results.ensure_queued(
        "long", "Long fixture prompt " * 75, "Synthetic long prompt", now=now - 5400
    )
    assert app.results.accept("long", "owner:long", deadline=now + 900, now=now - 5399)
    assert app.results.write(
        "long",
        "owner:long",
        CaptureResult(
            "sse",
            "complete",
            "## Detailed answer\n\n"
            + "A readable paragraph with some **bold** terms and a [safe link](https://example.com). "
            * 55
            + "\n\n```python\nprint(123)\n```",
            "conversation-3",
            "message-3",
            "parent-3",
        ),
        now=now - 5398,
    )
    app.results.ensure_queued(
        "partial", "Build release notes", "Synthetic partial response", now=now - 45
    )
    assert app.results.accept("partial", "owner:partial", deadline=now + 900, now=now - 44)
    assert app.results.write(
        "partial",
        "owner:partial",
        CaptureResult(
            "dom",
            "partial",
            "Still generating part of a response.",
            "conversation-4",
            "message-4",
            "parent-4",
        ),
        now=now - 43,
    )
    app.results.ensure_queued("queued", "A pending fixture", "Synthetic queued", now=now - 60)
    app.replies.prepare(
        "daily",
        ReplyIntent("reply-inventory-12345", "c1", "m1", "A second synthetic question"),
        now=now + 1,
    )
    assert app.replies.claim(
        "reply-inventory-12345", "owner:reply", deadline=now + 900, now=now + 2
    )
    assert app.replies.accepted(
        "reply-inventory-12345",
        "owner:reply",
        conversation_id="c1",
        parent_id="m1",
        message_id="m2",
        now=now + 3,
    )
    assert app.replies.observe(
        "reply-inventory-12345",
        "owner:reply",
        CaptureResult(
            "sse",
            "complete",
            "### Second answer\n\n" + "Visible synthetic content. " * 45,
            "c1",
            "m2",
            "m1",
        ),
        now=now + 4,
    )


def screenshot(page: Page, folder: Path, name: str, observations: list[str]) -> None:
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / f"{name}.png"
    page.screenshot(path=str(path), animations="disabled", full_page=False)
    path.chmod(0o600)
    measurements = page.evaluate("""() => ({xOverflow: document.documentElement.scrollWidth - innerWidth,
        bodyHeight: document.body.scrollHeight, viewportHeight: innerHeight,
        buttons: [...document.querySelectorAll('button')].filter(e=>e.getBoundingClientRect().width>0)
          .map(e=>({name:(e.getAttribute('aria-label')||e.textContent||'').trim().slice(0,35),
                   w:Math.round(e.getBoundingClientRect().width),h:Math.round(e.getBoundingClientRect().height)}))
          .filter(e=>e.w<44||e.h<40).slice(0,12)})""")
    observations.append(f"{name}: {measurements}")
    assert measurements["xOverflow"] <= 1, f"Horizontal overflow in {name}: {measurements}"


@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
def test_mobile_ux_inventory_atlas(tmp_path: Path, width: int, height: int) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium")
    if not Path(chromium).exists():
        pytest.skip("Chromium unavailable")
    root = Path(os.environ.get("PROMPTA_ATLAS_OUTPUT", str(tmp_path))) / f"{width}x{height}"
    notes: list[str] = []
    with server(tmp_path) as (app, port):
        populate(app)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium, headless=True, args=["--no-sandbox", "--no-zygote"]
            )
            try:
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    is_mobile=width < 1000,
                    has_touch=width < 1000,
                    device_scale_factor=1,
                )
                page = context.new_page()
                requests: list[tuple[str, str]] = []
                page.on("request", lambda request: requests.append((request.method, request.url)))
                page.on("dialog", lambda dialog: dialog.dismiss())
                base = f"http://127.0.0.1:{port}/"
                page.goto(base + "?view=jobs", wait_until="networkidle")
                expect(page.get_by_role("heading", name="Jobs", exact=True)).to_be_visible()
                screenshot(page, root, "01-jobs", notes)
                page.locator(".job-row").last.scroll_into_view_if_needed()
                screenshot(page, root, "02-jobs-scrolled", notes)
                page.get_by_role("button", name="New job").click()
                expect(page.locator(".job-editor")).to_be_visible()
                screenshot(page, root, "03-new-job", notes)
                expect(page.locator(".editor-settings select")).to_have_value("interval")
                expect(page.locator(".name-field input")).to_be_visible()
                page.locator(".editor-settings select").select_option("once")
                expect(page.locator(".name-field input")).to_be_visible()
                expect(page.get_by_role("button", name="Create job")).to_be_visible()
                screenshot(page, root, "03b-named-one-time-job", notes)
                page.locator(".editor-settings select").select_option("interval")
                page.locator(".name-field input").fill("Synthetic unsaved job")
                page.locator(".prompt-field textarea").fill(
                    "A long unsaved synthetic prompt. " * 14
                )
                screenshot(page, root, "04-new-job-filled", notes)
                if width == 844 and height == 390:
                    bounds = page.evaluate("""() => ({
                        promptBottom: document.querySelector('.prompt-field textarea').getBoundingClientRect().bottom,
                        footerTop: document.querySelector('.editor-footer').getBoundingClientRect().top
                    })""")
                    assert bounds["footerTop"] >= bounds["promptBottom"] - 1, bounds
                    page.locator(".editor-footer").scroll_into_view_if_needed()
                    screenshot(page, root, "04b-landscape-actions", notes)
                if width <= 412:
                    page.set_viewport_size({"width": width, "height": min(height, 520)})
                    page.locator(".prompt-field textarea").focus()
                    page.wait_for_timeout(90)
                    screenshot(page, root, "05-job-soft-keyboard", notes)
                    page.set_viewport_size({"width": width, "height": height})
                page.get_by_role("button", name="Cancel").click()
                expect(
                    page.get_by_role("alertdialog", name="Discard unsaved changes")
                ).to_be_visible()
                screenshot(page, root, "06-discard-confirm", notes)
                page.get_by_role("button", name="Discard", exact=True).click()
                page.get_by_role("button", name="Run once").click()
                expect(page.locator(".editor-settings select")).to_have_value("once")
                expect(page.locator(".editor-settings select")).to_be_disabled()
                expect(page.locator(".name-field input")).to_have_count(0)
                screenshot(page, root, "07-run-once", notes)
                page.get_by_role("button", name="Cancel").click()
                page.goto(base + "?view=jobs", wait_until="networkidle")
                page.locator(".job-row").first.get_by_role("button", name="Edit").click()
                screenshot(page, root, "08-edit-job", notes)
                page.get_by_role("button", name="Cancel").click()
                if width <= 680:
                    page.get_by_role("button", name="Open chat sidebar").click()
                    screenshot(page, root, "09-sidebar-drawer", notes)
                    page.get_by_role("button", name="Close sidebar").click()
                page.goto(base + "?view=chats", wait_until="networkidle")
                expect(page.locator(".chat-row")).to_have_count(5)
                screenshot(page, root, "10-chats-list", notes)
                page.get_by_role("button", name="Search chats").click()
                assert page.locator(".chats-controls input").evaluate(
                    "element => document.activeElement === element"
                )
                page.locator(".chats-controls select").select_option("completed")
                expect(page.locator(".chat-row")).to_have_count(3)
                page.locator(".chats-controls select").select_option("")
                page.locator(".chat-pin").first.click()
                expect(page.locator(".chat-pin.active")).to_have_count(1)
                if width < 1000:
                    page.locator(".chats-controls input").fill("absent-nonmatch")
                    expect(page.locator(".chat-row")).to_have_count(0)
                    screenshot(page, root, "11-chats-empty-search", notes)
                    page.locator(".chats-controls input").fill("")
                page.locator(".chat-row").filter(has_text="Synthetic daily review").click()
                expect(page.locator(".assistant-group")).to_have_count(2)
                scroll = page.locator(".chat-transcript-scroll")
                scroll.evaluate("element => element.scrollTop = 0")
                screenshot(page, root, "12-thread-top", notes)
                scroll.evaluate("element => element.scrollTop = element.scrollHeight")
                screenshot(page, root, "13-thread-bottom", notes)
                if width <= 412:
                    composer = page.get_by_role("textbox", name="Message for current chat")
                    composer.fill("Synthetic unsent reply and a second line")
                    composer.press("Shift+Enter")
                    page.set_viewport_size({"width": width, "height": min(height, 520)})
                    screenshot(page, root, "14-reply-keyboard", notes)
                    page.set_viewport_size({"width": width, "height": height})
                expect(page.locator(".chat-detail-toolbar")).to_have_count(0)
                if width <= 680:
                    page.get_by_role("button", name="Back to chats").click()
                else:
                    expect(page.locator(".chat-header-back")).to_be_hidden()
                page.locator(".chat-row").filter(has_text="Synthetic long prompt").click()
                expect(page.get_by_role("button", name="Show full prompt")).to_be_visible()
                screenshot(page, root, "15-long-prompt-collapsed", notes)
                page.get_by_role("button", name="Show full prompt").click()
                screenshot(page, root, "16-long-prompt-expanded", notes)
                page.goto(base + "?view=chats&draft=new", wait_until="networkidle")
                screenshot(page, root, "17-fresh-chat", notes)
                composer = page.get_by_role("textbox", name="Message for new chat")
                initial = composer.bounding_box()
                assert initial is not None and 25 <= initial["height"] <= 40
                attach_initial = page.get_by_role("button", name="Attach images").bounding_box()
                create_initial = page.locator(".chat-composer-wrap").get_by_role(
                    "button", name="New chat"
                ).bounding_box()
                assert attach_initial is not None and create_initial is not None
                # The textarea owns the top row; attach and Create occupy its footer.
                assert create_initial["y"] >= initial["y"] + initial["height"] - 2
                assert create_initial["x"] > attach_initial["x"]
                # Attachment is now a compact bottom-left footer icon, not a text column.
                assert attach_initial["y"] >= initial["y"] + initial["height"] - 2
                assert abs(attach_initial["x"] - initial["x"]) <= 4
                assert attach_initial["width"] == 44
                composer.fill("A wrapped synthetic line of text. " * 70)
                expanded = composer.bounding_box()
                assert expanded is not None
                max_height = 67 if width <= 680 else 110
                assert initial["height"] < expanded["height"] <= max_height + 1
                assert composer.evaluate("(element) => getComputedStyle(element).overflowY") == "auto"
                composer.fill("")
                collapsed = composer.bounding_box()
                assert collapsed is not None and abs(collapsed["height"] - initial["height"]) <= 1
                composer.fill("An unsent synthetic new-chat draft")
                screenshot(page, root, "18-fresh-draft", notes)
                if width <= 412:
                    attach_box = page.get_by_role("button", name="Attach images").bounding_box()
                    send_box = page.get_by_role("button", name="Send fresh chat").bounding_box()
                    assert attach_box and send_box
                    assert (
                        min(
                            attach_box["width"],
                            attach_box["height"],
                            send_box["width"],
                            send_box["height"],
                        )
                        >= 44
                    )
                if width <= 412:
                    page.set_viewport_size({"width": width, "height": min(height, 520)})
                    composer.focus()
                    screenshot(page, root, "19-fresh-keyboard", notes)
                assert all(
                    url.startswith(base)
                    and (
                        method in ("GET", "HEAD")
                        or (
                            method == "POST" and url in {
                                base + "api/local-chat-pins",
                                base + "api/local-chat-reads",
                                base + "api/local-chat-reads/import",
                            }
                        )
                    )
                    for method, url in requests
                ), requests
                context.close()
            finally:
                browser.close()
    (root / "measurements.txt").write_text("\n".join(notes) + "\n")


@pytest.mark.parametrize(("width", "height"), [(390, 844), (1440, 900)])
def test_mobile_ux_empty_and_error_states(tmp_path: Path, width: int, height: int) -> None:
    output = Path(os.environ.get("PROMPTA_ATLAS_OUTPUT", str(tmp_path))) / f"{width}x{height}"
    notes: list[str] = []
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"),
            headless=True,
            args=["--no-sandbox", "--no-zygote"],
        )
        try:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                is_mobile=width < 1000,
                has_touch=width < 1000,
            )
            page = context.new_page()
            base = f"http://127.0.0.1:{port}/"
            page.goto(base + "?view=jobs", wait_until="networkidle")
            screenshot(page, output, "20-jobs-empty", notes)
            page.goto(base + "?view=chats", wait_until="networkidle")
            screenshot(page, output, "21-chats-empty", notes)
            page.route(
                "**/api/results?**",
                lambda route: route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"error":"Synthetic unavailable"}',
                ),
            )
            page.goto(base + "?view=chats", wait_until="networkidle")
            expect(page.get_by_role("alert")).to_be_visible()
            screenshot(page, output, "22-chats-error", notes)
            page.unroute("**/api/results?**")
            page.route(
                "**/api/jobs",
                lambda route: route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"error":"Synthetic unavailable"}',
                ),
            )
            page.goto(base + "?view=jobs", wait_until="networkidle")
            screenshot(page, output, "23-jobs-error", notes)
            context.close()
        finally:
            browser.close()
    with (output / "measurements.txt").open("a") as handle:
        handle.write("\n".join(notes) + "\n")


def test_mobile_ux_named_one_time_job_is_persisted_only_in_fixture(tmp_path: Path) -> None:
    """The New job → Once path must save a *named* job, not dispatch a fresh chat."""
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium")
    if not Path(chromium).exists():
        pytest.skip("Chromium unavailable")
    with server(tmp_path) as (_app, port):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium, headless=True, args=["--no-sandbox", "--no-zygote"]
            )
            try:
                page = browser.new_page(
                    viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
                )
                base = f"http://127.0.0.1:{port}/"
                page.goto(base + "?view=jobs", wait_until="networkidle")
                page.get_by_role("button", name="New job").click()
                page.locator(".name-field input").fill("Synthetic one-time fixture")
                page.locator(".editor-settings select").select_option("once")
                page.get_by_role("spinbutton", name="Delay (minutes, 0 = now)").fill("120")
                page.locator(".prompt-field textarea").fill(
                    "Synthetic named once: no message should be sent"
                )
                page.get_by_role("button", name="Create job").click()
                expect(
                    page.locator(".job-row").filter(has_text="Synthetic one-time fixture")
                ).to_have_count(1)
                root = Path(os.environ.get("PROMPTA_ATLAS_OUTPUT", str(tmp_path))) / "390x844"
                screenshot(page, root, "21-named-once-persisted", [])
            finally:
                browser.close()


def test_mobile_ux_destructive_job_confirmation_is_dismissed_in_fixture(tmp_path: Path) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium")
    if not Path(chromium).exists():
        pytest.skip("Chromium unavailable")
    with server(tmp_path) as (app, port):
        populate(app)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium, headless=True, args=["--no-sandbox", "--no-zygote"]
            )
            try:
                page = browser.new_page(
                    viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
                )
                dialogs: list[str] = []

                def dismiss(dialog: object) -> None:
                    from patchright.sync_api import Dialog

                    assert isinstance(dialog, Dialog)
                    dialogs.append(dialog.message)
                    dialog.dismiss()

                page.on("dialog", dismiss)
                page.goto(f"http://127.0.0.1:{port}/?view=jobs", wait_until="networkidle")
                page.locator(".job-row").first.get_by_role("button", name="Remove").click()
                page.get_by_role("button", name="Clear all jobs").click()
                assert len(dialogs) == 2, dialogs
                assert "Remove" in dialogs[0] and "all" in dialogs[1].lower(), dialogs
                expect(page.get_by_text("16 configured jobs.")).to_be_visible()
            finally:
                browser.close()


@pytest.mark.parametrize(("width", "height"), [(320, 700), (360, 800), (390, 844), (412, 915)])
def test_new_chat_composer_keyboard_layout(tmp_path: Path, width: int, height: int) -> None:
    """Chrome Android must resize the layout viewport for the on-screen keyboard."""
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium")
    if not Path(chromium).exists():
        pytest.skip("Chromium unavailable")
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox", "--no-zygote"]
        )
        try:
            page = browser.new_page(
                viewport={"width": width, "height": height},
                is_mobile=True,
                has_touch=True,
                device_scale_factor=1,
            )
            requests: list[str] = []
            page.on("request", lambda request: requests.append(request.method))
            page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new", wait_until="networkidle")
            viewport = page.locator('meta[name="viewport"]').get_attribute("content") or ""
            assert "interactive-widget=resizes-content" in viewport
            composer = page.get_by_role("textbox", name="Message for new chat")
            expect(composer).to_be_visible()
            page.wait_for_timeout(80)
            initial_height = composer.bounding_box()
            assert initial_height is not None
            assert initial_height["height"] <= 90, initial_height

            # The second viewport models the layout dimensions after the Android keyboard opens.
            page.set_viewport_size({"width": width, "height": 430})
            composer.focus()
            composer.fill("A draft that should remain visible as the keyboard opens.")
            form = page.locator("form.chat-composer-wrap")
            bounds = form.bounding_box()
            assert bounds is not None
            assert bounds["y"] >= -1, bounds
            assert bounds["y"] + bounds["height"] <= 431, bounds
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            assert composer.input_value().startswith("A draft")
            assert requests.count("POST") == 0
        finally:
            browser.close()
