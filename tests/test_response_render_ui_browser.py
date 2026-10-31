"""Browser proof for ChatGPT-like, unboxed local assistant rendering."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from test_reply_ui_browser import seed_terminal
from test_web_results import server

from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.response_capture import CaptureResult


@pytest.mark.parametrize(
    ("status", "label"),
    [
        ("completed", None),
        ("generating", "Live"),
        ("interrupted", "Interrupted"),
    ],
)
def test_response_is_unboxed_and_preserves_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    label: str | None,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    import prompta.web as web_module

    monkeypatch.setattr(
        web_module,
        "_STATIC_ROOT",
        Path(__file__).resolve().parents[1] / "src/static",
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        send_id = "response-style"
        seed_terminal(app, send_id=send_id, missing_id=False)
        ticks = chr(96)
        markdown = (
            "## Section title\n\n> A quoted note\n\nInline "
            + ticks
            + "code"
            + ticks
            + " is distinct."
            + "\n\n"
            + ticks * 3
            + "ts\nconst value = 1;\n"
            + ticks * 3
            + "\n\n| Name | State |\n| --- | --- |\n| Alpha | Ready |"
        )
        with app.results.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE job_responses SET status = ?, assistant_text = ? WHERE send_id = ?",
                (status, markdown, send_id),
            )
        browser = playwright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            for width, height in [(390, 844), (1440, 900), (320, 700)]:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(f"http://127.0.0.1:{port}/?view=chats&run={send_id}")
                response = page.locator(".assistant-group")
                expect(response).to_be_visible()
                if label:
                    expect(response.locator(".response-state")).to_have_text(label)
                else:
                    expect(response.locator(".response-state")).to_have_count(0)
                assert f"response-{status}" in (response.get_attribute("class") or "")
                computed = response.evaluate(
                    """node => ({
                        width: getComputedStyle(node).borderLeftWidth,
                        background: getComputedStyle(node).backgroundImage,
                        shadow: getComputedStyle(node).boxShadow,
                        font: getComputedStyle(node.querySelector('.result-markdown')).fontSize,
                    })"""
                )
                assert computed == {
                    "width": "0px",
                    "background": "none",
                    "shadow": "none",
                    "font": "16px",
                }
                expect(
                    response.get_by_role("button", name="Copy assistant reply 1")
                ).to_be_visible()
                expect(response.locator("h2")).to_have_text("Section title")
                expect(response.locator("blockquote")).to_contain_text("A quoted note")
                expect(response.locator(".code-snippet")).to_contain_text("const value = 1;")
                expect(response.locator("table")).to_contain_text("Alpha")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                if screenshot_dir := os.environ.get("PROMPTA_RESPONSE_SCREENSHOT_DIR"):
                    destination = Path(screenshot_dir)
                    destination.mkdir(parents=True, exist_ok=True)
                    page.screenshot(
                        path=str(destination / f"{status}-{width}.png"),
                        full_page=True,
                    )
                page.close()
        finally:
            browser.close()


def test_multiple_local_responses_keep_distinct_turns_and_tool_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    import prompta.web as web_module

    monkeypatch.setattr(
        web_module,
        "_STATIC_ROOT",
        Path(__file__).resolve().parents[1] / "src/static",
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        send_id = "two-response-cards"
        conversation = "00000000-0000-4000-8000-000000000101"
        app.results.ensure_queued(send_id, "First question", now=100)
        assert app.results.accept(send_id, "test:owner", deadline=500, now=101)
        assert app.results.write(
            send_id,
            "test:owner",
            CaptureResult(
                "sse",
                "complete",
                "First final answer",
                conversation,
                "assistant-one",
                "user-one",
            ),
            now=102,
        )
        replies = ManualReplyStore(Path(str(app.results.engine.url.database)))
        reply_id = "reply-1234567890-ab"
        assert replies.prepare(
            send_id,
            ReplyIntent(reply_id, conversation, "assistant-one", "Follow up"),
            now=103,
        )
        assert replies.claim(reply_id, "test:reply", deadline=500, now=104)
        assert replies.accepted(
            reply_id,
            "test:reply",
            conversation_id=conversation,
            parent_id="assistant-one",
            message_id="assistant-two",
            now=105,
        )
        calls: tuple[dict[str, object], ...] = (
            {
                "id": "tool-one",
                "connector": "Search",
                "action": "lookup",
                "status": "completed",
                "arguments": "{}",
                "result": "Two results",
                "error": "",
            },
        )
        assert replies.observe(
            reply_id,
            "test:reply",
            CaptureResult(
                "sse",
                "complete",
                "Second final answer",
                conversation,
                "assistant-two",
                "assistant-one",
                tool_calls=calls,
            ),
            now=106,
        )
        browser = playwright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run={send_id}")
            responses = page.locator(".assistant-group")
            expect(responses).to_have_count(2)
            expect(responses.locator(".assistant-avatar")).to_have_count(0)
            expect(responses.locator(".response-state")).to_have_count(0)
            expect(
                responses.nth(0).get_by_role("button", name="Copy assistant reply 1")
            ).to_be_visible()
            expect(
                responses.nth(1).get_by_role("button", name="Copy assistant reply 2")
            ).to_be_visible()
            expect(responses.nth(1).locator(".tool-call")).to_have_count(1)
            expect(responses.nth(1).locator(".tool-call-name")).to_contain_text("Search")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            if screenshot_dir := os.environ.get("PROMPTA_RESPONSE_SCREENSHOT_DIR"):
                page.screenshot(
                    path=str(Path(screenshot_dir) / "multiple-responses-390.png"),
                    full_page=True,
                )
        finally:
            browser.close()


def test_legacy_chatgpt_metrics_and_checklist_are_reconstructed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    import prompta.web as web_module

    monkeypatch.setattr(
        web_module,
        "_STATIC_ROOT",
        Path(__file__).resolve().parents[1] / "src/static",
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        send_id = "legacy-metrics"
        seed_terminal(app, send_id=send_id, missing_id=False)
        dom_capture = (
            "I found a significant pattern in Prompta’s live database on Nox:\n\n"
            "28\nInterrupted\n9\nUnavailable\n107\nCompleted\n\n"
            "The interrupted results frequently occur exactly 45 minutes later.\n\n"
            "The verification is:\n\n"
            "528 Python tests passed\nRuff: passed\nTy: passed\n"
            "New focused regression: 3/3 passed\nFix commit: fa1ea8f"
        )
        with app.results.engine.begin() as connection:
            columns = [
                row[1] for row in connection.exec_driver_sql("PRAGMA table_info(job_responses)")
            ]
            source_column = "source" if "source" in columns else "capture_source"
            connection.exec_driver_sql(
                f"UPDATE job_responses SET {source_column} = ?, status = ?, assistant_text = ? "
                "WHERE send_id = ?",
                ("dom", "completed", dom_capture, send_id),
            )
        browser = playwright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            for width, height in [(1440, 900), (390, 844), (320, 700)]:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(f"http://127.0.0.1:{port}/?view=chats&run={send_id}")
                metrics = page.get_by_role("group", name="Response metrics")
                expect(metrics).to_be_visible()
                expect(metrics.locator(".response-metric")).to_have_count(3)
                expect(metrics.locator(".tone-error")).to_have_text("28")
                expect(metrics.locator(".tone-success")).to_have_text("107")
                expect(page.locator(".result-recovered-list li")).to_have_count(5)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                if screenshot_dir := os.environ.get("PROMPTA_RESPONSE_SCREENSHOT_DIR"):
                    destination = Path(screenshot_dir)
                    destination.mkdir(parents=True, exist_ok=True)
                    page.screenshot(
                        path=str(destination / f"legacy-metrics-{width}.png"),
                        full_page=True,
                    )
                page.close()
        finally:
            browser.close()
