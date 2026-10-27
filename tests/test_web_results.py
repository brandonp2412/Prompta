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


def test_chats_ui_desktop_mobile_and_no_chatgpt_requests(tmp_path: Path) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    screenshots = Path(os.environ.get("PROMPTA_SCREENSHOT_DIR", str(tmp_path)))
    screenshots.mkdir(parents=True, exist_ok=True, mode=0o700)
    with server(tmp_path) as (app, port):
        now = 1793020000.0
        completed_run(app, "daily", "Daily review", now)
        completed_run(app, "nightly", "Nightly summary", now - 90_000)
        app.results.ensure_queued("partial", "Build release notes", "Release notes", now=now + 100)
        assert app.results.accept("partial", "10:partial", deadline=now + 1000, now=now + 101)
        assert app.results.write("partial", "10:partial", CaptureResult(
            "dom", "partial", "### So far\n\nStill generating a **partial** answer.",
            "c2", "m2", "p2",
        ), now=now + 102)
        app.results.ensure_queued("unsafe", "Render unsafe markup", "Security", now=now - 180_000)
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
                context = browser.new_context(viewport={"width": 1365, "height": 900}, device_scale_factor=1)
                page = context.new_page()
                network_hosts: list[str] = []
                page.on("request", lambda request: network_hosts.append(request.url.split("/")[2]))
                page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                page.get_by_role("button", name="Chats").click()
                page.locator(".chat-row").first.wait_for()
                assert page.locator(".chat-row").count() == 4
                page.locator(".chat-row").filter(has_text="Daily review").click()
                assert page.locator(".result-markdown pre code").inner_text() == "print(1)"
                assert page.locator(".prompt-message").inner_text() == "Prompt for Daily review"
                page.get_by_role("button", name="Refresh local results").click()
                page.get_by_role("button", name="Refresh local results").click()
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(screenshots / "prompta-chats-desktop.png"), animations="disabled")

                page.locator(".chat-row").filter(has_text="Security").click()
                assert page.locator(".result-markdown img").count() == 0
                assert page.locator(".result-markdown a").count() == 0
                assert "<img" in page.locator(".result-markdown").inner_text()
                page.locator(".chats-controls select").select_option("completed")
                expect(page.locator(".chat-row")).to_have_count(3)
                page.locator(".chats-controls select").select_option("")
                page.locator(".chats-controls input").fill("Nightly")
                expect(page.locator(".chat-row")).to_have_count(1)
                assert page.locator(".chat-row").inner_text().find("Nightly summary") >= 0
                assert all(host == f"127.0.0.1:{port}" for host in network_hosts)

                page.set_viewport_size({"width": 390, "height": 844})
                phone = page
                phone.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
                phone.locator(".chat-row").filter(has_text="Release notes").click()
                expect(phone.get_by_text("Partial response", exact=False)).to_be_visible()
                assert phone.locator(".chats-sidebar").is_hidden()
                assert phone.locator(".chats-detail").is_visible()
                assert phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                phone.screenshot(path=str(screenshots / "prompta-chats-mobile.png"), animations="disabled")
                phone.get_by_role("button", name="All chats").click()
                assert phone.locator(".chats-sidebar").is_visible()
                assert phone.locator(".chats-detail").is_hidden()
                context.close()
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
