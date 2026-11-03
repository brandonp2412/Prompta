"""Browser E2E of terminal chat reply availability without live ChatGPT sends."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from patchright.sync_api import Route, expect
from patchright.sync_api import sync_playwright as sync_patchright
from web_results_support import server

from prompta.reply_contracts import ReplyIntent
from prompta.response_capture import CaptureResult
from prompta.strict_types import json_object

CONVERSATION = "00000000-0000-4000-8000-000000000001"
ASSISTANT = "00000000-0000-4000-8000-000000000002"
USER = "00000000-0000-4000-8000-000000000003"


def seed_terminal(app: object, *, send_id: str, missing_id: bool) -> None:
    from live_server import LiveServer

    assert isinstance(app, LiveServer)
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
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        seed_terminal(app, send_id=send_id, missing_id=missing_id)
        browser = patchright.chromium.launch(
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
                    body=json.dumps({"ok": True, "turn": {"status": "queued"}}),
                )

            def fresh_route(route: Route) -> None:
                fresh.append(json_object(route.request.post_data or "{}", label="fresh payload"))
                route.fulfill(
                    status=202,
                    content_type="application/json",
                    body=json.dumps({"send_id": "new-run"}),
                )

            page.route(f"**/api/results/{send_id}/reply-queue", reply_route)
            page.route("**/api/chats", fresh_route)
            saved_image_ref = "a" * 64 + "/saved.png"
            if missing_id:

                def saved_image_detail(route: Route) -> None:
                    response = route.fetch()
                    record = response.json()
                    record["images"] = [
                        {"name": "saved.png", "url": "./api/images/" + saved_image_ref}
                    ]
                    route.fulfill(
                        status=response.status,
                        content_type="application/json",
                        body=json.dumps(record),
                    )

                page.route(f"**/api/results/{send_id}", saved_image_detail)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run={send_id}")
            if not missing_id:
                copy = page.get_by_role("button", name="Copy assistant reply 1")
                continuation = page.get_by_role("button", name="Continue in new chat")
                expect(copy).to_be_visible()
                expect(continuation).to_be_visible()
                copy_box = copy.bounding_box()
                continuation_box = continuation.bounding_box()
                assert copy_box is not None and continuation_box is not None
                assert abs(copy_box["x"] - continuation_box["x"]) <= 1
            field = page.get_by_role("textbox", name="Message for current chat")
            expect(field).to_be_visible()
            field.fill("Please continue")
            button = page.get_by_role("button", name="Send reply")
            expect(button).to_be_enabled()
            if missing_id:
                button.click()
                expect(
                    page.get_by_text("Continue in a new chat instead.", exact=False)
                ).to_be_visible()
                assert not fresh
                fallback = page.get_by_role("form", name="Reply composer").get_by_role(
                    "button", name="Continue in new chat"
                )
                expect(fallback).to_be_visible()
                with page.expect_request("**/api/chats"):
                    fallback.click()
            else:
                with page.expect_request(f"**/api/results/{send_id}/reply-queue"):
                    button.click()
            page.wait_for_timeout(200)
            if missing_id:
                assert len(fresh) == 1
                assert len(sent) == 0
                assert "Original private question" in str(fresh[0]["prompt"])
                assert "Please continue" in str(fresh[0]["prompt"])
                assert fresh[0]["images"] == [saved_image_ref]
            else:
                assert len(sent) == 1
                assert len(fresh) == 0
                assert sent[0]["text"] == "Please continue"
                assert isinstance(sent[0]["reply_id"], str)
        finally:
            browser.close()


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_concluded_chat_reply_starts_fresh_chat_without_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    width: int,
    height: int,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static"
    )
    send_id = "old-concluded"
    final_answer = "The implementation is complete and all tests passed."
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        app.results.ensure_queued(send_id, "Implement the feature", now=100)
        assert app.results.accept(send_id, "test:owner", deadline=300, now=101)
        assert app.results.write(
            send_id,
            "test:owner",
            CaptureResult(
                "sse", "complete", final_answer, CONVERSATION, ASSISTANT, USER
            ),
            now=102,
        )
        browser = patchright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"]
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            fresh: list[dict[str, object]] = []
            old_branch_requests: list[str] = []

            def fresh_route(route: Route) -> None:
                payload = json_object(route.request.post_data or "{}", label="new chat")
                fresh.append(payload)
                route.fulfill(
                    status=202,
                    content_type="application/json",
                    body=json.dumps(
                        {"send_id": "manual-" + str(payload["request_id"]), "status": "queued"}
                    ),
                )

            def old_branch_route(route: Route) -> None:
                old_branch_requests.append(route.request.url)
                route.fulfill(status=409)

            page.route("**/api/chats", fresh_route)
            page.route(f"**/api/results/{send_id}/reply-queue", old_branch_route)
            page.route(f"**/api/results/{send_id}/reply-recover", old_branch_route)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run={send_id}")
            field = page.get_by_role("textbox", name="Message for current chat")
            expect(field).to_be_visible()
            field.fill("Please add a follow-up improvement")
            with page.expect_request("**/api/chats"):
                page.get_by_role("button", name="Send reply").click()
            expect(page).to_have_url(re.compile(r"\?view=chats&run=manual-[a-f0-9]{32}$"))
            assert len(fresh) == 1
            assert old_branch_requests == []
            prompt = fresh[0]["prompt"]
            assert isinstance(prompt, str)
            assert prompt.startswith("Last saved assistant result:\n" + final_answer)
            assert prompt.endswith("New user message:\nPlease add a follow-up improvement")
            original = app.results.get(send_id)
            assert original is not None and original["status"] == "completed"
        finally:
            browser.close()


def test_queued_reply_does_not_wait_for_exact_parent_recovery(
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
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        seed_terminal(app, send_id="recover", missing_id=False)
        with app.results.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE job_responses SET message_id = '' WHERE send_id = 'recover'",
            )
        browser = patchright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            recoveries: list[str] = []
            page.on(
                "request",
                lambda request: (
                    recoveries.append(request.url)
                    if request.url.endswith("/reply-recover")
                    else None
                ),
            )
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=recover")
            field = page.get_by_role("textbox", name="Message for current chat")
            field.fill("Still here")
            with page.expect_response("**/api/results/recover/reply-queue") as queued:
                page.get_by_role("button", name="Send reply").click()
            assert queued.value.status == 202
            expect(field).to_have_value("")
            expect(page.get_by_role("button", name="New chat", exact=True)).to_be_enabled()
            assert page.get_by_role("button", name="Sending").count() == 0
            assert recoveries == []
            saved = app.replies.turns("recover") or []
            assert saved[-1]["status"] == "queued"
            assert saved[-1]["user_text"] == "Still here"
        finally:
            browser.close()


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
@pytest.mark.parametrize("failed_reply", [False, True])
def test_stuck_reply_starts_new_chat_with_latest_saved_result_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    width: int,
    height: int,
    failed_reply: bool,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static"
    )
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        seed_terminal(app, send_id="broken-reply", missing_id=False)
        if failed_reply:
            assert app.replies.prepare(
                "broken-reply",
                ReplyIntent("f" * 32, CONVERSATION, ASSISTANT, "My follow-up was not sent"),
                now=103,
            )
            assert app.replies.mark_preflight_failed("f" * 32)
        browser = patchright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"]
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            posted: list[dict[str, object]] = []

            def fresh_route(route: Route) -> None:
                payload = json_object(route.request.post_data or "{}", label="new chat payload")
                posted.append(payload)
                route.fulfill(
                    status=202,
                    content_type="application/json",
                    body=json.dumps(
                        {"send_id": "manual-" + str(payload["request_id"]), "status": "queued"}
                    ),
                )

            page.route("**/api/chats", fresh_route)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=broken-reply")
            action = page.get_by_role("button", name="Continue in new chat")
            expect(action).to_be_visible()
            with page.expect_request("**/api/chats"):
                action.click()
            expect(page).to_have_url(re.compile(r"\?view=chats&run=manual-[a-f0-9]{32}$"))
            assert len(posted) == 1
            prompt = posted[0]["prompt"]
            assert isinstance(prompt, str)
            assert prompt.startswith("Last saved assistant result:\nSaved partial answer")
            assert prompt.endswith(
                "New user message:\n"
                + (
                    "My follow-up was not sent"
                    if failed_reply
                    else "Please continue from the last saved result."
                )
            )
            assert "Original private question" in prompt
            assert prompt.index("Saved partial answer") < prompt.index("Original private question")
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
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        seed_terminal(app, send_id="no-conversation", missing_id=True)
        browser = patchright.chromium.launch(
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
            fallback = page.get_by_role("form", name="Reply composer").get_by_role(
                "button", name="Continue in new chat"
            )
            expect(fallback).to_be_visible()
            button.click()
            expect(page.get_by_text("Continue in a new chat instead.", exact=False)).to_be_visible()
            assert not requests
            with page.expect_request("**/api/chats"):
                fallback.click()
            expect(page.get_by_text("Queue receipt is uncertain.", exact=False)).to_be_visible()
            expect(button).to_be_enabled()
            assert field.input_value() == "Try to deliver"
            with page.expect_request("**/api/chats"):
                fallback.click()
            page.wait_for_timeout(200)
            assert len(requests) == 2
            assert requests[0]["request_id"] == requests[1]["request_id"]
            assert requests[0]["prompt"] == requests[1]["prompt"]
        finally:
            browser.close()
