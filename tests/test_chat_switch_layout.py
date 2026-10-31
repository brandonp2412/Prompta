"""Browser regression for stable Prompta chat-switch geometry under slow local reads."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from test_web_results import completed_run, server


@pytest.fixture(autouse=True)
def serve_current_worktree_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.web as web_module

    monkeypatch.setattr(web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static")


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
            }""", isolated_context=False)
            if width <= 680:
                page.get_by_role("button", name="Back to chats").click()
            page.locator(".chats-list .chat-row").filter(has_text="CLS Beta").click()
            expect(page.locator(".workspace-header strong")).to_contain_text("CLS Beta")
            expect(page.locator(".chat-switch-cover")).to_be_visible()
            assert page.locator(".chat-transcript-scroll").evaluate(
                "(node) => getComputedStyle(node).visibility"
            ) == "hidden"
            during = page.evaluate("window.__geometry()", isolated_context=False)
            expect(page.locator(".chat-switch-cover")).to_have_count(0, timeout=10000)
            expect(page.locator(".chat-detail-content")).to_contain_text("CLS Beta")
            after = page.evaluate("window.__geometry()", isolated_context=False)
            for name in ("header", "shell", "composer"):
                for metric in ("x", "y", "width", "height"):
                    assert abs(during[name][metric] - after[name][metric]) <= 1, (
                        f"{width}px {name}.{metric} moved during chat loading: "
                        f"{during[name][metric]} -> {after[name][metric]}"
                    )
            if width > 680:
                before = page.evaluate("window.__before", isolated_context=False)
                for name in ("header", "shell", "composer"):
                    for metric in ("x", "y", "width", "height"):
                        assert abs(before[name][metric] - after[name][metric]) <= 1, (
                            f"{name}.{metric} shifted across chat navigation"
                        )
                assert page.evaluate("window.__shifts.reduce((a, b) => a + b, 0)", isolated_context=False) < 0.01
            assert remote_posts == []
        finally:
            browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_slow_saved_turns_does_not_block_primary_chat(
    tmp_path: Path, width: int, height: int,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "fast-alpha", "Fast Alpha", 100)
        completed_run(app, "fast-beta", "Fast Beta", 200)
        browser = playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=fast-alpha")
            expect(page.locator(".chat-detail-content")).to_contain_text("Fast Alpha")
            page.evaluate("""() => {
                const original = window.fetch.bind(window);
                window.fetch = (resource, options) => {
                    if (String(resource).includes("/api/results/fast-beta/turns")) {
                        return new Promise((resolve) =>
                            setTimeout(() => resolve(original(resource, options)), 4000));
                    }
                    return original(resource, options);
                };
            }""", isolated_context=False)
            if width <= 680:
                page.get_by_role("button", name="Back to chats").click()
            page.locator(".chats-list .chat-row").filter(has_text="Fast Beta").click()
            expect(page.locator(".chat-detail-content")).to_contain_text(
                "Fast Beta", timeout=2000,
            )
            expect(page.locator(".chat-switch-cover")).to_have_count(0, timeout=2000)
            # The optional reply read still has seconds to go, but the
            # confirmed primary response is already visible and usable.
            expect(page.locator(".chat-composer-wrap")).to_be_visible()
        finally:
            browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_fast_saved_replies_reveal_with_final_scroll_position(
    tmp_path: Path, width: int, height: int,
) -> None:
    """The loading cover must not expose a half-hydrated transcript or scroll jump."""
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "reveal-alpha", "Reveal Alpha", 100)
        completed_run(app, "reveal-beta", "Reveal Beta", 200)
        browser = playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=reveal-alpha")
            expect(page.locator(".chat-detail-content")).to_contain_text("Reveal Alpha")
            page.evaluate("""() => {
                const originalFetch = window.fetch.bind(window);
                window.fetch = (resource, options) => {
                    if (String(resource).endsWith("/api/results/reveal-beta")) {
                        return new Promise((resolve) => setTimeout(
                            () => resolve(originalFetch(resource, options)), 120
                        ));
                    }
                    if (!String(resource).includes("/api/results/reveal-beta/turns")) {
                        return originalFetch(resource, options);
                    }
                    const paragraphs = Array.from({ length: 100 }, (_, i) => "Paragraph " + i).join("\\n\\n");
                    const original = {
                        reply_id: "", user_text: "Prompt for Reveal Beta",
                        assistant_text: "**Answer** for Reveal Beta",
                        status: "completed", created_at: 200, updated_at: 202
                    };
                    const reply = {
                        reply_id: "reply-reveal-beta", user_text: "Explain in detail",
                        assistant_text: paragraphs,
                        status: "completed", created_at: 203, updated_at: 204
                    };
                    return new Promise((resolve) => setTimeout(() => resolve(
                        new Response(JSON.stringify({ turns: [original, reply] }), {
                            status: 200, headers: { "Content-Type": "application/json" }
                        })
                    ), 20));
                };
                window.__sawSwitchCover = false;
                window.__revealGeometry = null;
                const observer = new MutationObserver(() => {
                    if (new URLSearchParams(location.search).get("run") !== "reveal-beta") return;
                    const cover = document.querySelector(".chat-switch-cover");
                    if (cover) window.__sawSwitchCover = true;
                    if (!window.__sawSwitchCover || cover || window.__revealGeometry) return;
                    const pane = document.querySelector(".chat-transcript-scroll");
                    if (!pane) return;
                    window.__revealGeometry = {
                        assistantCount: document.querySelectorAll(".assistant-group").length,
                        distanceFromBottom: pane.scrollHeight - pane.clientHeight - pane.scrollTop
                    };
                    observer.disconnect();
                });
                observer.observe(document.body, { childList: true, subtree: true });
            }""", isolated_context=False)
            if width <= 680:
                page.get_by_role("button", name="Back to chats").click()
            page.locator(".chats-list .chat-row").filter(has_text="Reveal Beta").click()
            expect(page.locator(".chat-switch-cover")).to_have_count(0, timeout=10000)
            page.wait_for_function("window.__revealGeometry !== null")
            revealed = page.evaluate("window.__revealGeometry", isolated_context=False)
            assert revealed["assistantCount"] == 2, revealed
            assert abs(revealed["distanceFromBottom"]) <= 2, revealed
            assert page.locator(".assistant-group").count() == 2
        finally:
            browser.close()
