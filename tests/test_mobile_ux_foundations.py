from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_mobile_ux_inventory import populate
from test_web_results import server

VIEWPORTS = [
    (320, 700),
    (360, 800),
    (390, 844),
    (412, 915),
    (768, 1024),
    (844, 390),
    (1440, 900),
]


@pytest.fixture(autouse=True)
def serve_candidate_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.web as web_module

    assets = Path(__file__).resolve().parents[1] / "src/static"
    monkeypatch.setattr(web_module, "_STATIC_ROOT", assets)


def typography(page: object, selector: str) -> dict[str, float]:
    from playwright.sync_api import Page

    assert isinstance(page, Page)
    values: object = page.locator(selector).first.evaluate(
        r"""element => {
          const style = getComputedStyle(element);
          const rgb = style.color.match(/[\d.]+/g).slice(0, 3).map(Number);
          const background = element.closest('.job-row, .chats-sidebar, .chats-detail, .jobs-workspace');
          const backdrop = background?.classList.contains('job-row') ? [25,25,25]
            : background?.classList.contains('chats-sidebar') ? [23,23,23]
            : [33,33,33];
          const linear = c => (c / 255 <= .04045 ? c / 255 / 12.92 : ((c / 255 + .055) / 1.055) ** 2.4);
          const luminance = colors => .2126*linear(colors[0]) + .7152*linear(colors[1]) + .0722*linear(colors[2]);
          const a = luminance(rgb), b = luminance(backdrop);
          return { fontSize: parseFloat(style.fontSize), contrast: (Math.max(a,b)+.05)/(Math.min(a,b)+.05) };
        }"""
    )
    assert isinstance(values, dict)
    font_size = values.get("fontSize")
    contrast = values.get("contrast")
    assert isinstance(font_size, (float, int))
    assert isinstance(contrast, (float, int))
    return {"fontSize": float(font_size), "contrast": float(contrast)}


@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
def test_foundations_readability_and_editor_hit_testing(
    tmp_path: Path, width: int, height: int
) -> None:
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
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    is_mobile=width < 1000,
                    has_touch=width < 1000,
                    device_scale_factor=1,
                )
                page = context.new_page()
                requests: list[tuple[str, str]] = []
                page.on("request", lambda request: requests.append((request.method, request.url)))
                base = f"http://127.0.0.1:{port}/"
                page.goto(base, wait_until="networkidle")
                expect(page.get_by_role("heading", name="Jobs", exact=True)).to_be_visible()
                atlas_root = os.environ.get("PROMPTA_ATLAS_OUTPUT")
                tablet_dir = Path(atlas_root) / "768x1024" if atlas_root and width == 768 else None
                if tablet_dir is not None:
                    tablet_dir.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(tablet_dir / "01-jobs.png"))
                for selector in [".job-prompt", ".job-submeta", ".job-cell", ".filter-chip"]:
                    result = typography(page, selector)
                    assert result["fontSize"] >= 13, (selector, result, width)
                    assert result["contrast"] >= 4.5, (selector, result, width)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")

                page.get_by_role("button", name="New job").click()
                expect(page.locator(".job-image-picker")).to_be_visible()
                if tablet_dir is not None:
                    page.screenshot(path=str(tablet_dir / "03-new-job.png"))
                positions = page.evaluate(
                    """() => ({
                      imageBottom: document.querySelector('.job-image-picker').getBoundingClientRect().bottom,
                      footerTop: document.querySelector('.editor-footer').getBoundingClientRect().top,
                      viewportWidth: innerWidth
                    })"""
                )
                if width <= 420 or (width > 680 and height <= 520):
                    assert positions["imageBottom"] <= positions["footerTop"] + 1, positions
                if width <= 420:
                    assert page.locator(".editor-footer").evaluate(
                        "element => getComputedStyle(element).position"
                    ) == "static"
                    picker = page.get_by_role("button", name="Add images")
                    picker.scroll_into_view_if_needed()
                    assert picker.evaluate(
                        """element => {
                          const r = element.getBoundingClientRect();
                          const hit = document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
                          return hit === element || element.contains(hit);
                        }"""
                    )
                    with page.expect_file_chooser():
                        picker.click()
                    page.locator(".prompt-field textarea").fill("Synthetic draft")
                    page.set_viewport_size({"width": width, "height": min(520, height)})
                    page.locator(".prompt-field textarea").focus()
                    page.get_by_role("button", name="Cancel").click()
                    expect(page.get_by_role("alertdialog", name="Discard unsaved changes")).to_be_visible()
                    page.get_by_role("button", name="Keep editing").click()
                    page.get_by_role("button", name="Cancel").click()
                    page.get_by_role("button", name="Discard", exact=True).click()
                    expect(page.get_by_role("heading", name="Jobs", exact=True)).to_be_visible()

                page.goto(base + "?view=chats", wait_until="networkidle")
                if tablet_dir is not None:
                    page.screenshot(path=str(tablet_dir / "10-chats-list.png"))
                for selector in [".chat-entry .chat-row-top strong", ".chats-date", ".chats-count"]:
                    result = typography(page, selector)
                    assert result["fontSize"] >= 13, (selector, result, width)
                    assert result["contrast"] >= 4.5, (selector, result, width)
                page.get_by_role("button", name="Search chats").click()
                expect(page.locator(".chats-controls input")).to_be_visible()
                page.locator(".chats-controls input").fill("Synthetic")
                page.locator(".chats-controls input").fill("")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                assert all(
                    method in ("GET", "HEAD") and url.startswith(base) for method, url in requests
                ), requests
                context.close()
            finally:
                browser.close()
