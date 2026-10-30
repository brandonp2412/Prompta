"""Browser regression for stable Prompta chat-switch geometry under slow local reads."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_web_results import completed_run, server


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844), (412, 915)])
def test_chat_switch_keeps_transcript_and_composer_shell_stable(
    tmp_path: Path, width: int, height: int,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "cls-alpha", "CLS Alpha", 100)
        completed_run(app, "cls-beta", "CLS Beta", 200)
        browser = playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            remote_posts: list[str] = []
            page.on("request", lambda request: remote_posts.append(request.url)
                    if request.method == "POST" and not request.url.startswith(
                        f"http://127.0.0.1:{port}/"
                    ) else None)
            page.route("**/api/events", lambda route: route.abort())
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=cls-alpha")
            expect(page.locator(".chat-detail-content")).to_be_visible()
            expect(page.locator(".chat-composer-wrap")).to_be_visible()
            page.evaluate("""() => {
                window.__geometry = () => {
                    const rect = (selector) => {
                        const { x, y, width, height } = document.querySelector(selector).getBoundingClientRect();
                        return { x, y, width, height };
                    };
                    return {
                        header: rect(".workspace-header"),
                        shell: rect(".chat-transcript-shell"),
                        composer: rect(".chat-composer-wrap"),
                    };
                };
                window.__before = window.__geometry();
                window.__shifts = [];
                new PerformanceObserver((list) => {
                    for (const entry of list.getEntries()) {
                        if (!entry.hadRecentInput) window.__shifts.push(entry.value);
                    }
                }).observe({ type: "layout-shift", buffered: false });
                const fetchOriginal = window.fetch.bind(window);
                window.fetch = (resource, options) => {
                    if (String(resource).includes("/api/results/cls-beta")) {
                        return new Promise((resolve) =>
                            setTimeout(() => resolve(fetchOriginal(resource, options)), 950));
                    }
                    return fetchOriginal(resource, options);
                };
            }""")
            if width <= 680:
                page.get_by_role("button", name="Back to chats").click()
            page.locator(".chats-list .chat-row").filter(has_text="CLS Beta").click()
            expect(page.locator(".workspace-header strong")).to_contain_text("CLS Beta")
            expect(page.locator(".chat-switch-cover")).to_be_visible()
            assert page.locator(".chat-transcript-scroll").evaluate(
                "(node) => getComputedStyle(node).visibility"
            ) == "hidden"
            during = page.evaluate("window.__geometry()")
            expect(page.locator(".chat-switch-cover")).to_have_count(0, timeout=10000)
            expect(page.locator(".chat-detail-content")).to_contain_text("CLS Beta")
            after = page.evaluate("window.__geometry()")
            for name in ("header", "shell", "composer"):
                for metric in ("x", "y", "width", "height"):
                    assert abs(during[name][metric] - after[name][metric]) <= 1, (
                        f"{width}px {name}.{metric} moved during chat loading: "
                        f"{during[name][metric]} -> {after[name][metric]}"
                    )
            if width > 680:
                before = page.evaluate("window.__before")
                for name in ("header", "shell", "composer"):
                    for metric in ("x", "y", "width", "height"):
                        assert abs(before[name][metric] - after[name][metric]) <= 1, (
                            f"{name}.{metric} shifted across chat navigation"
                        )
                assert page.evaluate("window.__shifts.reduce((a, b) => a + b, 0)") < 0.01
            assert remote_posts == []
        finally:
            browser.close()
