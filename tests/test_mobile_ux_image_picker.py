from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import Page, expect, sync_playwright
from test_mobile_ux_inventory import populate
from test_web_results import server

VIEWPORTS = [(320, 700), (360, 800), (390, 844), (412, 915), (844, 390), (1440, 900)]


@pytest.fixture(autouse=True)
def serve_isolated_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.web as web_module

    assets = Path(__file__).resolve().parents[1] / "src/static"
    monkeypatch.setattr(web_module, "_STATIC_ROOT", assets)


def capture(page: Page, viewport: str, stage: str) -> None:
    evidence = os.environ.get("PROMPTA_UX01_EVIDENCE")
    if not evidence:
        return
    folder = Path(evidence) / viewport
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / f"{stage}.png"
    page.screenshot(path=str(path), animations="disabled")
    path.chmod(0o600)


def touch_center(page: Page, selector: str, *, touch: bool) -> None:
    target = page.locator(selector)
    target.scroll_into_view_if_needed()
    expect(target).to_be_visible()
    rect = target.bounding_box()
    assert rect is not None
    x, y = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2
    viewport_size = page.viewport_size
    assert viewport_size is not None
    assert 0 <= x < viewport_size["width"]
    assert 0 <= y < viewport_size["height"]
    assert target.evaluate(
        """element => {
          const r = element.getBoundingClientRect();
          const hit = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
          return hit === element || element.contains(hit);
        }"""
    ), f"Touch center of {selector} is occluded"
    if touch:
        page.touchscreen.tap(x, y)
    else:
        page.mouse.click(x, y)


@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
def test_ux01_004_image_picker_and_footer_real_touch(
    tmp_path: Path, width: int, height: int
) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium")
    if not Path(chromium).exists():
        pytest.skip("Chromium unavailable")
    touch = width < 1000
    viewport = f"{width}x{height}"
    with server(tmp_path) as (app, port):
        populate(app)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium, headless=True, args=["--no-sandbox", "--no-zygote"]
            )
            try:
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    is_mobile=touch,
                    has_touch=touch,
                    device_scale_factor=1,
                )
                page = context.new_page()
                requests: list[tuple[str, str]] = []
                page.on("request", lambda request: requests.append((request.method, request.url)))
                base = f"http://127.0.0.1:{port}/"
                page.goto(f"{base}?view=jobs", wait_until="networkidle")
                page.get_by_role("button", name="New job").click()
                expect(page.locator(".job-editor")).to_be_visible()
                expect(page.get_by_role("button", name="Add images")).to_be_visible()
                capture(page, viewport, "01-new-job")

                positions = page.evaluate(
                    """() => ({
                      pickerBottom: document.querySelector('.job-image-picker').getBoundingClientRect().bottom,
                      footerTop: document.querySelector('.editor-footer').getBoundingClientRect().top,
                      footerPosition: getComputedStyle(document.querySelector('.editor-footer')).position,
                      overflow: document.documentElement.scrollWidth - innerWidth
                    })"""
                )
                assert positions["overflow"] <= 1, positions
                if width <= 420 or (width == 844 and height == 390):
                    assert positions["pickerBottom"] <= positions["footerTop"] + 1, positions
                if width <= 420:
                    assert positions["footerPosition"] == "static", positions

                picker = page.get_by_role("button", name="Add images")
                picker.scroll_into_view_if_needed()
                capture(page, viewport, "02-picker-visible")
                with page.expect_file_chooser():
                    touch_center(page, ".job-image-picker button", touch=touch)

                page.locator(".name-field input").fill("Synthetic unsaved job")
                page.locator(".prompt-field textarea").fill(
                    "A synthetic draft with no live dispatch."
                )
                if width <= 420:
                    page.set_viewport_size({"width": width, "height": 430})
                    page.locator(".prompt-field textarea").focus()
                    capture(page, viewport, "03-keyboard-focused")
                    for _ in range(3):
                        page.locator(".jobs-workspace").evaluate(
                            "(element) => { element.scrollTop = 0; }"
                        )
                        page.locator(".job-image-picker button").scroll_into_view_if_needed()
                        with page.expect_file_chooser():
                            touch_center(page, ".job-image-picker button", touch=True)
                        page.locator(".editor-footer").scroll_into_view_if_needed()
                        capture(page, viewport, "04-keyboard-actions")
                        touch_center(page, ".editor-actions button:first-child", touch=True)
                        expect(
                            page.get_by_role("alertdialog", name="Discard unsaved changes")
                        ).to_be_visible()
                        touch_center(page, ".editor-feedback button:first-of-type", touch=True)
                        expect(page.get_by_role("alertdialog")).to_have_count(0)
                else:
                    page.locator(".editor-footer").scroll_into_view_if_needed()

                touch_center(page, ".editor-actions button:first-child", touch=touch)
                expect(
                    page.get_by_role("alertdialog", name="Discard unsaved changes")
                ).to_be_visible()
                capture(page, viewport, "05-discard-confirm")
                touch_center(page, ".editor-feedback button:last-of-type", touch=touch)
                expect(page.get_by_role("heading", name="Jobs", exact=True)).to_be_visible()

                page.locator(".job-row").first.get_by_role("button", name="Edit").click()
                expect(page.get_by_role("heading", name="Edit job")).to_be_visible()
                capture(page, viewport, "06-edit-job")
                touch_center(page, ".editor-actions button:first-child", touch=touch)
                expect(page.get_by_role("heading", name="Jobs", exact=True)).to_be_visible()
                assert all(
                    method in ("GET", "HEAD") and url.startswith(base) for method, url in requests
                ), requests
                context.close()
            finally:
                browser.close()
