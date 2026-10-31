from __future__ import annotations

import json
import logging
import os
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from web_results_support import (
    completed_run,
    get,
    post_json,
    server,
)
from web_results_support import (
    serve_worktree_assets as serve_worktree_assets,
)

from prompta.jobs import add_job
from prompta.response_capture import CaptureResult
from prompta.strict_types import json_object, string_object_dict


def test_explicit_reply_intent_contract_is_local_and_not_dispatched(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from prompta.reply_contracts import ReplyIntent

    with server(tmp_path) as (app, port):
        app.results.ensure_queued("known", "Private seed", now=100)
        assert app.results.accept("known", "100:seed", deadline=300, now=101)
        assert app.results.write(
            "known",
            "100:seed",
            CaptureResult(
                "sse",
                "complete",
                "Private answer",
                "conversation-1234567890",
                "assistant-1234567890",
                "user-1234567890123",
            ),
            now=102,
        )
        payload: dict[str, object] = {
            "reply_id": "reply-1234567890123",
            "conversation_id": "conversation-1234567890",
            "parent_id": "assistant-1234567890",
            "text": "Private manual question",
        }
        assert ReplyIntent.parse(payload).text == payload["text"]

        def post(
            body: dict[str, object], *, content_type: str = "application/json"
        ) -> tuple[int, dict[str, object]]:
            conn = HTTPConnection("127.0.0.1", port, timeout=3)
            try:
                conn.request(
                    "POST",
                    "/api/results/known/reply-intents",
                    body=json.dumps(body),
                    headers={"content-type": content_type},
                )
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
            assert get(port, "/api/results/known/turns", method="POST")[0] == 405
        turns = get(port, "/api/results/known/turns")[1]["turns"]
        assert isinstance(turns, list) and len(turns) == 2
        turn = string_object_dict(turns[1])
        assert turn is not None and turn["status"] == "prepared"
        assert "lease_owner" not in turn
        assert "Private manual question" not in caplog.text
        assert "Private answer" not in caplog.text


def test_explicit_reply_is_durably_handed_to_worker_not_ui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A UI restart cannot own or duplicate a user-authorized reply."""
    from prompta.reply_contracts import ReplyIntent

    payload: dict[str, object] = {
        "reply_id": "reply-independent-worker-1234",
        "conversation_id": "conversation-1234567890",
        "parent_id": "assistant-1234567890",
        "text": "Reply from the real Send button",
    }
    with server(tmp_path) as (app, port):
        app.results.ensure_queued("known", "Original", now=100)
        assert app.results.accept("known", "test-owner", deadline=300, now=101)
        assert app.results.write(
            "known",
            "test-owner",
            CaptureResult(
                "sse",
                "complete",
                "Original answer",
                "conversation-1234567890",
                "assistant-1234567890",
                "user-1234567890123",
            ),
            now=102,
        )
        intent = ReplyIntent.parse(payload)
        assert app.replies.prepare("known", intent)["status"] == "prepared"
        assert app.replies.next_queued_intent() is None

        def no_ui_dispatch(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("The UI process must never dispatch a reply")

        monkeypatch.setattr(app.reply_dispatch, "submit", no_ui_dispatch)
        monkeypatch.setattr(app.reply_dispatch, "pump_queued", no_ui_dispatch)
        status, response = post_json(port, "/api/results/known/reply-send", payload)
        assert status == 202 and response["dispatched"] is False
        turn = string_object_dict(response["turn"])
        assert turn is not None and turn["queued_by_user"] is True
        assert app.replies.next_queued_intent() == ("known", intent)
        # A lost HTTP receipt or second click must not create another turn.
        assert post_json(port, "/api/results/known/reply-send", payload)[0] == 202
        assert len(app.replies.turns("known") or []) == 2

    # Restart the whole UI; only the separate worker can claim this durable row.
    with server(tmp_path) as (restored, _port):
        assert restored.replies.next_queued_intent() == ("known", ReplyIntent.parse(payload))
        assert len(restored.replies.turns("known") or []) == 2


def test_unread_badges_follow_completed_answers_not_metadata(tmp_path: Path) -> None:
    """End-to-end: no false badge for queued/partial/status writes or unsent replies."""
    from sqlalchemy import update

    from prompta.reply_contracts import ReplyIntent
    from prompta.response_store import results

    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not chromium or not Path(chromium).is_file():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port):
        app.results.ensure_queued("pending", "Pending prompt", "Pending", now=300)
        app.results.ensure_queued("partial", "Partial prompt", "Partial", now=310)
        assert app.results.accept("partial", "100:partial", deadline=900, now=311)
        assert app.results.write(
            "partial",
            "100:partial",
            CaptureResult(
                "dom",
                "partial",
                "Still writing...",
                "c1",
                "m1",
                "p1",
            ),
            now=312,
        )
        completed_run(app, "answered", "Answered", 400)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium,
                headless=True,
                args=["--no-sandbox", "--no-zygote"],
            )
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.add_init_script("""if (!localStorage.getItem("prompta.local-sidebar.v1")) {
                    localStorage.setItem(
                        "prompta.local-sidebar.v1",
                        JSON.stringify({baselineAt: 100, pinnedIds: [], readAt: {}})
                    );
                }""")
                remote: list[str] = []
                page.on(
                    "request",
                    lambda request: (
                        remote.append(request.url)
                        if not request.url.startswith(f"http://127.0.0.1:{port}/")
                        else None
                    ),
                )
                page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
                answered = page.locator(".chat-entry").filter(has_text="Answered")
                pending = page.locator(".chat-entry").filter(has_text="Pending")
                partial = page.locator(".chat-entry").filter(has_text="Partial")
                expect(answered.locator(".unread-indicator")).to_have_count(1)
                expect(pending.locator(".unread-indicator")).to_have_count(0)
                expect(partial.locator(".unread-indicator")).to_have_count(0)

                answered.locator(".chat-row").click()
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                pending.locator(".chat-row").click()
                page.reload(wait_until="networkidle")
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                with app.results.engine.begin() as connection:
                    connection.execute(
                        update(results)
                        .where(
                            results.c.send_id == "answered",
                        )
                        .values(updated_at=800)
                    )
                page.reload(wait_until="networkidle")
                expect(answered.locator(".unread-indicator")).to_have_count(0)

                # The live test server performs orphan recovery during reloads.
                # Use a real, live process owner and a future lease deadline.
                owner = f"{os.getpid()}:manual"
                intent = ReplyIntent("reply-12345678901234", "c1", "m1", "Follow up")
                assert app.replies.prepare("answered", intent, now=600)
                page.reload(wait_until="networkidle")
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                assert app.replies.claim(
                    intent.reply_id, owner, deadline=time.time() + 3600, now=601
                )
                assert app.replies.accepted(
                    intent.reply_id,
                    owner,
                    conversation_id="c1",
                    parent_id="m1",
                    message_id="m2",
                    now=602,
                )
                assert app.replies.observe(
                    intent.reply_id,
                    owner,
                    CaptureResult(
                        "dom",
                        "partial",
                        "Working on the answer",
                        "c1",
                        "m2",
                        "m1",
                    ),
                    now=603,
                )
                page.reload(wait_until="networkidle")
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                assert app.replies.observe(
                    intent.reply_id,
                    owner,
                    CaptureResult(
                        "sse",
                        "complete",
                        "New verified assistant reply",
                        "c1",
                        "m2",
                        "m1",
                    ),
                    now=604,
                )
                page.reload(wait_until="networkidle")
                expect(answered.locator(".unread-indicator")).to_have_count(1)
                answered.locator(".chat-row").click()
                expect(page.locator(".assistant-group")).to_have_count(2)
                expect(page.get_by_text("New verified assistant reply")).to_have_count(1)
                expect(answered.locator(".unread-indicator")).to_have_count(0)
                assert remote == []
            finally:
                browser.close()


def test_read_receipts_survive_independent_browser_tabs(tmp_path: Path) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not chromium or not Path(chromium).is_file():
        pytest.skip("Headless Chromium unavailable")
    from sqlalchemy import update

    from prompta.response_store import results

    with server(tmp_path) as (app, port):
        completed_run(app, "multi-tab", "Cross-tab receipt", 400)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium,
                headless=True,
                args=["--no-sandbox"],
            )
            try:
                first = browser.new_context()
                second = browser.new_context()
                a = first.new_page()
                b = second.new_page()
                for page in (a, b):
                    page.add_init_script("""if (!localStorage.getItem("prompta.local-sidebar.v1"))
                        localStorage.setItem("prompta.local-sidebar.v1",
                            JSON.stringify({baselineAt: 1, readAt: {}}));""")
                    page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
                row_a = a.locator(".chat-entry").filter(has_text="Cross-tab receipt")
                row_b = b.locator(".chat-entry").filter(has_text="Cross-tab receipt")
                expect(row_a.locator(".unread-indicator")).to_have_count(1)
                expect(row_b.locator(".unread-indicator")).to_have_count(1)

                row_a.locator(".chat-row").click()
                expect(row_a.locator(".unread-indicator")).to_have_count(0)
                a.wait_for_function("""async () => {
                    const response = await fetch("./api/results/multi-tab");
                    const result = await response.json();
                    return result.last_read_revision === result.last_reply_revision;
                }""")
                b.reload(wait_until="networkidle")
                expect(row_b.locator(".unread-indicator")).to_have_count(0)
                a.evaluate("localStorage.clear()")
                a.reload(wait_until="networkidle")
                expect(row_a.locator(".unread-indicator")).to_have_count(0)

                # A selected chat in another live tab auto-acknowledges newly
                # observed answers; deselect it before testing a fresh unread reply.
                a.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
                prior = get(port, "/api/results/multi-tab")[1]
                with app.results.engine.begin() as connection:
                    connection.execute(
                        update(results)
                        .where(results.c.send_id == "multi-tab")
                        .values(assistant_text="New completed response")
                    )
                latest = get(port, "/api/results/multi-tab")[1]
                assert latest["last_reply_revision"] != prior["last_reply_revision"]
                assert latest["last_read_revision"] == prior["last_reply_revision"]
                b.reload(wait_until="networkidle")
                expect(row_b.locator(".unread-indicator")).to_have_count(1)
                row_b.locator(".chat-row").click()
                expect(row_b.locator(".unread-indicator")).to_have_count(0)
                a.reload(wait_until="networkidle")
                expect(row_a.locator(".unread-indicator")).to_have_count(0)
            finally:
                browser.close()


def test_queue_status_api_is_private_read_only_and_exposes_worker_wait_order(
    tmp_path: Path,
) -> None:
    with server(tmp_path) as (app, port):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[parallelism]\nmax_workers = 1\n")
        app.queue_view.concurrency_config_path = config_path
        for name in ("alpha", "beta", "gamma"):
            add_job(app.jobs_path, name, f"Secret prompt {name}", 60, exact_interval=True)
            app.queue_view.runtime.update_job_state(name, {"initial_due_at_epoch": 1000.0})
        assert app.queue_view.tick(now=1000.0) == 1

        status, payload, headers = get(port, "/api/queue-status")
        assert status == 200 and headers["cache-control"] == "no-store"
        assert payload == {
            "max_workers": 1,
            "occupied_slots": 1,
            "estimated_run_seconds": 600,
            "estimate_samples": 0,
            "waiting": [
                {
                    "name": "beta",
                    "position": 1,
                    "reason": "global",
                    "occupied": 1,
                    "limit": 1,
                    "eta_seconds": 600,
                },
                {
                    "name": "gamma",
                    "position": 2,
                    "reason": "global",
                    "occupied": 1,
                    "limit": 1,
                    "eta_seconds": 1200,
                },
            ],
        }
        assert "Secret prompt" not in str(payload)
        assert get(port, "/api/queue-status", method="POST")[0] == 405
        assert len(app.queue.records()) == 1


def test_waiting_chats_render_and_advance_on_desktop_and_mobile(tmp_path: Path) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    with server(tmp_path) as (app, port):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[parallelism]\nmax_workers = 1\n")
        app.queue_view.concurrency_config_path = config_path
        at = time.time()
        for name in ("alpha", "beta", "gamma"):
            add_job(app.jobs_path, name, f"Synthetic prompt for {name}", 60, exact_interval=True)
            app.queue_view.runtime.update_job_state(name, {"initial_due_at_epoch": at})
        assert app.queue_view.tick(now=at) == 1
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium_path, headless=True, args=["--no-sandbox"]
            )
            try:
                for width, height in (
                    (1440, 900),
                    (360, 800),
                    (390, 844),
                    (412, 915),
                    (320, 700),
                ):
                    context = browser.new_context(viewport={"width": width, "height": height})
                    page = context.new_page()
                    requests: list[tuple[str, str]] = []
                    page.on("request", lambda req: requests.append((req.method, req.url)))
                    page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="domcontentloaded")
                    expect(page.locator(".queue-heading")).to_contain_text("1/1 global slots")
                    rows = page.locator(".queue-waiting")
                    expect(rows).to_have_count(2)
                    expect(rows.nth(0)).to_contain_text("beta")
                    expect(rows.nth(0)).to_contain_text("#1 of 2")
                    expect(rows.nth(0)).to_contain_text("ETA ~10 min")
                    expect(rows.nth(1)).to_contain_text("gamma")
                    expect(rows.nth(1)).to_contain_text("#2 of 2")
                    expect(rows.nth(1)).to_contain_text("ETA ~20 min")
                    top = rows.nth(0).locator(".chat-row-top").bounding_box()
                    subtitle = rows.nth(0).locator(".queue-subtitle").bounding_box()
                    assert top is not None and subtitle is not None
                    assert subtitle["y"] >= top["y"] + top["height"] - 2
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=str(tmp_path / f"queued-{width}x{height}.png"))
                    assert all(method == "GET" for method, _ in requests)
                    assert all(url.startswith(f"http://127.0.0.1:{port}/") for _, url in requests)
                    if width == 1440:
                        rows.first.locator("button").click()
                        expect(page.locator(".jobs-workspace")).to_be_visible()
                        expect(
                            page.locator(".jobs-workspace .job-row")
                            .filter(has_text="beta")
                            .locator(".job-queue-eta")
                        ).to_contain_text("Queue #1 of 2 · ETA ~10 min")
                        assert all(method == "GET" for method, _ in requests)
                    context.close()
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{port}/?view=chats")
                rows = page.locator(".queue-waiting")
                expect(rows).to_have_count(2)
                claimed = app.queue.claim_next("worker", now=at + 1, lease_seconds=30.0)
                assert claimed is not None
                assert app.queue.complete_claim(str(claimed["send_id"]), "worker", now=at + 2)
                assert app.queue_view.tick(now=at + 3) >= 1
                # SSE invalidates the local queue snapshot without a navigation or refresh.
                expect(rows).to_have_count(1)
                expect(rows.first).to_contain_text("gamma")
                expect(rows.first).to_contain_text("#1 of 1")
                expect(rows.first).to_contain_text("ETA ~10 min")
                expect(
                    page.locator(".chat-entry:not(.queue-waiting)").filter(has_text="beta")
                ).to_have_count(1)
                context.close()
            finally:
                browser.close()


def test_tool_cards_desktop_mobile_local_only(tmp_path: Path) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    screenshots = Path(os.environ.get("PROMPTA_SCREENSHOT_DIR", str(tmp_path)))
    screenshots.mkdir(parents=True, exist_ok=True, mode=0o700)
    with server(tmp_path) as (app, port):
        app.results.ensure_queued("tool-demo", "Summarise the checks", "Tool verification", now=200)
        assert app.results.accept("tool-demo", "100:tool", deadline=500, now=201)
        calls: tuple[dict[str, object], ...] = (
            {
                "id": "one",
                "connector": "GitHub",
                "action": "search_issues",
                "status": "completed",
                "arguments": '{"repo": "demo/project"}',
                "result": '{"count": 2}',
                "error": "",
            },
            {
                "id": "two",
                "connector": "Terminal",
                "action": "run_tests",
                "status": "error",
                "arguments": '{"suite": "e2e"}',
                "result": "",
                "error": "One example failed",
            },
        )
        assert app.results.write(
            "tool-demo",
            "100:tool",
            CaptureResult(
                "sse",
                "complete",
                "## Final answer\n\nTwo checks were performed.",
                "c1",
                "m1",
                "p1",
                tool_calls=calls,
            ),
            now=202,
        )
        status, body, _ = get(port, "/api/results/tool-demo")
        returned_calls = body["tool_calls"]
        assert status == 200 and isinstance(returned_calls, list) and len(returned_calls) == 2
        app.results.ensure_queued("tool-interrupted", "Check the server", now=210)
        assert app.results.accept("tool-interrupted", "100:interrupted", deadline=500, now=211)
        assert app.results.write(
            "tool-interrupted",
            "100:interrupted",
            CaptureResult(
                "sse",
                "unknown",
                "",
                "c2",
                None,
                None,
                tool_calls=(calls[0],),
            ),
            now=212,
        )
        assert app.results.finish("tool-interrupted", "100:interrupted", "interrupted", now=213)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium_path,
                headless=True,
                args=["--no-sandbox", "--disable-gpu"],
            )
            try:
                for width, height, mobile in [
                    (1440, 900, False),
                    (320, 700, True),
                    (360, 800, True),
                    (390, 844, True),
                    (412, 915, True),
                ]:
                    page = browser.new_page(
                        viewport={"width": width, "height": height},
                        is_mobile=mobile,
                        has_touch=mobile,
                    )
                    requests: list[tuple[str, str]] = []
                    page.on("request", lambda req: requests.append((req.method, req.url)))
                    page.goto(
                        f"http://127.0.0.1:{port}/?view=chats&run=tool-demo",
                        wait_until="domcontentloaded",
                    )
                    expect(page.locator(".tool-call")).to_have_count(2)
                    expect(page.locator(".tool-timeline-summary")).to_contain_text("2 tool calls")
                    expect(page.locator(".tool-failure-count")).to_have_text("1 failed")
                    expect(page.get_by_role("heading", name="Final answer")).to_be_visible()
                    expect(page.locator(".tool-call-summary").first).to_be_visible()
                    page.locator(".tool-call-summary").first.click()
                    expect(page.locator(".tool-call-body pre").first).to_contain_text(
                        "demo/project"
                    )
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    )
                    assert requests and all(
                        url.startswith(f"http://127.0.0.1:{port}/")
                        and (
                            method == "GET"
                            or (
                                method == "POST"
                                and url.split("?", 1)[0].endswith(
                                    ("/api/local-chat-reads", "/api/local-chat-reads/import")
                                )
                            )
                        )
                        for method, url in requests
                    )
                    target = screenshots / f"tool-events-{width}.png"
                    page.screenshot(path=str(target), animations="disabled", full_page=True)
                    target.chmod(0o600)
                    page.close()
                interrupted = browser.new_page(
                    viewport={"width": 320, "height": 700}, is_mobile=True, has_touch=True
                )
                interrupted.goto(
                    f"http://127.0.0.1:{port}/?view=chats&run=tool-interrupted",
                    wait_until="domcontentloaded",
                )
                expect(interrupted.locator(".tool-timeline-summary")).to_contain_text("1 tool call")
                expect(interrupted.get_by_text("Response capture interrupted")).to_be_visible()
                assert interrupted.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                )
                interrupted.close()
            finally:
                browser.close()
