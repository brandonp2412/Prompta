"""Browser E2E of terminal chat reply availability without live ChatGPT sends."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import Route, expect, sync_playwright
from test_web_results import server

from prompta.response_capture import CaptureResult
from prompta.strict_types import json_object

CONVERSATION = "00000000-0000-4000-8000-000000000001"
ASSISTANT = "00000000-0000-4000-8000-000000000002"
USER = "00000000-0000-4000-8000-000000000003"


def seed_terminal(app: object, *, send_id: str, missing_id: bool) -> None:
    from prompta.web import PromptaJobServer

    assert isinstance(app, PromptaJobServer)
    app.results.ensure_queued(send_id, "Original private question", now=100)
    if missing_id:
        app.results.unavailable(send_id, now=102)
    else:
        assert app.results.accept(send_id, "test:owner", deadline=300, now=101)
        assert app.results.write(
            send_id,
            "test:owner",
            CaptureResult(
                "dom",
                "partial",
                "Saved partial answer",
                CONVERSATION,
                ASSISTANT,
                USER,
            ),
            now=102,
        )
        with app.results.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE job_responses SET status = 'interrupted' WHERE send_id = ?",
                (send_id,),
            )


@pytest.mark.parametrize("missing_id", [False, True])
def test_terminal_chat_send_is_enabled_and_routes_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_id: bool,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static"
    )
    send_id = "missing-id" if missing_id else "known-branch"
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        seed_terminal(app, send_id=send_id, missing_id=missing_id)
        browser = playwright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            sent: list[dict[str, object]] = []
            fresh: list[dict[str, object]] = []

            def reply_route(route: Route) -> None:
                sent.append(json_object(route.request.post_data or "{}", label="reply payload"))
                route.fulfill(
                    status=202,
                    content_type="application/json",
                    body=json.dumps({"ok": True, "turn": {"status": "prepared"}}),
                )

            def fresh_route(route: Route) -> None:
                fresh.append(json_object(route.request.post_data or "{}", label="fresh payload"))
                route.fulfill(
                    status=202,
                    content_type="application/json",
                    body=json.dumps({"send_id": "new-run"}),
                )

            page.route(f"**/api/results/{send_id}/reply-send", reply_route)
            page.route("**/api/chats", fresh_route)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run={send_id}")
            field = page.get_by_role("textbox", name="Message for current chat")
            expect(field).to_be_visible()
            field.fill("Please continue")
            button = page.get_by_role("button", name="Send reply")
            expect(button).to_be_enabled()
            with page.expect_request(
                "**/api/chats" if missing_id else f"**/api/results/{send_id}/reply-send"
            ):
                button.click()
            page.wait_for_timeout(200)
            if missing_id:
                assert len(fresh) == 1
                assert len(sent) == 0
                assert "Original private question" in str(fresh[0]["prompt"])
                assert "Please continue" in str(fresh[0]["prompt"])
            else:
                assert len(sent) == 1
                assert len(fresh) == 0
                assert sent[0]["conversation_id"] == CONVERSATION
                assert sent[0]["parent_id"] == ASSISTANT
        finally:
            browser.close()


def test_failed_exact_recovery_keeps_draft_and_allows_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static"
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        seed_terminal(app, send_id="recover", missing_id=False)
        # Simulate a captured conversation without a verified assistant identity.
        with app.results.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE job_responses SET message_id = '' WHERE send_id = 'recover'",
            )
        browser = playwright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            recoveries: list[str] = []
            fresh: list[str] = []

            def recover_route(route: Route) -> None:
                recoveries.append(route.request.method)
                route.fulfill(
                    status=409,
                    content_type="application/json",
                    body='{"error":"Verification unavailable"}',
                )

            page.route("**/api/results/recover/reply-recover", recover_route)

            def fresh_fallback(route: Route) -> None:
                fresh.append(route.request.post_data or "")
                route.fulfill(
                    status=202, content_type="application/json", body='{"send_id":"continued-run"}'
                )

            page.route("**/api/chats", fresh_fallback)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=recover")
            field = page.get_by_role("textbox", name="Message for current chat")
            field.fill("Still here")
            button = page.get_by_role("button", name="Send reply")
            with page.expect_request("**/api/results/recover/reply-recover"):
                button.click()
            expect(
                page.get_by_text("The exact ChatGPT branch could not be verified yet.", exact=False)
            ).to_be_visible()
            expect(button).to_be_enabled()
            assert field.input_value() == "Still here"
            with page.expect_request("**/api/results/recover/reply-recover"):
                button.click()
            page.wait_for_timeout(200)
            assert len(recoveries) == 2
            assert not fresh
            with page.expect_request("**/api/chats"):
                page.get_by_role("button", name="Continue in new chat").click()
            page.wait_for_timeout(200)
            assert len(fresh) == 1
            assert "Still here" in fresh[0]
        finally:
            browser.close()


def test_uncertain_fresh_queue_reuses_idempotency_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static"
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        seed_terminal(app, send_id="no-conversation", missing_id=True)
        browser = playwright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            requests: list[dict[str, object]] = []

            def fresh_route(route: Route) -> None:
                requests.append(
                    json_object(route.request.post_data or "{}", label="fresh retry payload")
                )
                if len(requests) == 1:
                    route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"error":"queue uncertain"}',
                    )
                else:
                    route.fulfill(
                        status=202,
                        content_type="application/json",
                        body=json.dumps({"send_id": "manual-" + str(requests[-1]["request_id"])}),
                    )

            page.route("**/api/chats", fresh_route)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=no-conversation")
            field = page.get_by_role("textbox", name="Message for current chat")
            field.fill("Try to deliver")
            button = page.get_by_role("button", name="Send reply")
            with page.expect_request("**/api/chats"):
                button.click()
            expect(page.get_by_text("Queue receipt is uncertain.", exact=False)).to_be_visible()
            expect(button).to_be_enabled()
            assert field.input_value() == "Try to deliver"
            with page.expect_request("**/api/chats"):
                button.click()
            page.wait_for_timeout(200)
            assert len(requests) == 2
            assert requests[0]["request_id"] == requests[1]["request_id"]
            assert requests[0]["prompt"] == requests[1]["prompt"]
        finally:
            browser.close()
