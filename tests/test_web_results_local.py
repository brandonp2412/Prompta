from __future__ import annotations

import json
import os
import re
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

from prompta.response_capture import CaptureResult
from prompta.strict_types import string_object_dict


def test_default_route_opens_chats_and_jobs_remains_linkable(tmp_path: Path) -> None:
    with server(tmp_path) as (_app, port):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                executable_path=os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"),
            )
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(f"http://127.0.0.1:{port}/")
                expect(page).to_have_title(re.compile(r"^Prompta · Chats · "))
                expect(page.locator(".chats-layout")).to_be_visible()
                page.locator(".sidebar-jobs").click()
                expect(page).to_have_url(f"http://127.0.0.1:{port}/?view=jobs")
                expect(page).to_have_title(re.compile(r"^Prompta · Jobs · "))
                page.reload()
                expect(page).to_have_title(re.compile(r"^Prompta · Jobs · "))
                page.goto(f"http://127.0.0.1:{port}/?view=chats")
                expect(page).to_have_title(re.compile(r"^Prompta · Chats · "))
            finally:
                browser.close()


@pytest.mark.parametrize("width,height", [(360, 800), (390, 844), (412, 915), (1440, 900)])
def test_attention_filter_marks_interrupted_chats_in_react_sidebar(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    from sqlalchemy import update

    from prompta.response_store import results as result_table

    with server(tmp_path) as (app, port):
        completed_run(app, "healthy", "Healthy", 100)
        completed_run(app, "needs-help", "Recoverable", 200)
        with app.results.engine.begin() as connection:
            connection.execute(
                update(result_table)
                .where(result_table.c.send_id == "needs-help")
                .values(status="interrupted")
            )
        assert get(port, "/api/results?status=needs_attention")[1]["total"] == 1

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                executable_path=os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"),
            )
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(f"http://127.0.0.1:{port}/?view=chats")
                shortcut = page.locator(".chat-attention-shortcut")
                expect(shortcut).to_contain_text("1 chat")
                shortcut.click()
                expect(page.locator(".chats-controls select")).to_have_value("needs_attention")
                expect(page.locator(".chat-entry")).to_have_count(1)
                expect(page.locator(".chat-entry")).to_contain_text("Needs attention")
                expect(page.locator(".chat-entry")).to_contain_text("Recoverable")
                expect(page.locator(".chat-entry")).not_to_contain_text("Healthy")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            finally:
                browser.close()


def test_results_api_lists_only_local_runs_with_filter_search_and_pagination(
    tmp_path: Path,
) -> None:
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
        assert get(port, "/api/results/run-1", method="POST")[0] == 405


def pin_ids(payload: dict[str, object]) -> list[str]:
    items = payload.get("items")
    assert isinstance(items, list)
    ids: list[str] = []
    for item in items:
        row = string_object_dict(item)
        assert row is not None
        send_id = row.get("send_id")
        assert isinstance(send_id, str)
        ids.append(send_id)
    return ids


def test_local_pins_persist_in_sqlite_and_never_change_chatgpt_pins(tmp_path: Path) -> None:
    from sqlalchemy import text

    from prompta.response_store import ResponseStore

    with server(tmp_path) as (app, port):
        completed_run(app, "a", "First", 100)
        completed_run(app, "b", "Second", 200)
        completed_run(app, "c", "Third", 300)
        path = app.results.path
        assert get(port, "/api/local-chat-pins")[1] == {"items": []}
        assert (
            post_json(port, "/api/local-chat-pins", {"send_id": "missing", "pinned": True})[0]
            == 404
        )
        assert post_json(port, "/api/local-chat-pins", {"send_id": "a", "pinned": "yes"})[0] == 400
        assert (
            post_json(port, "/api/local-chat-pins", {"send_id": "a", "pinned": True, "extra": 1})[0]
            == 400
        )
        assert (
            post_json(port, "/api/local-chat-pins", {"send_id": "../a", "pinned": True})[0] == 400
        )
        assert (
            post_json(port, "/api/local-chat-pins/import", {"send_ids": ["missing", "b", "a"]})[0]
            == 200
        )
        assert post_json(port, "/api/local-chat-pins/import", {"send_ids": ["c"]})[0] == 200
        _, initial, headers = get(port, "/api/local-chat-pins")
        assert headers["cache-control"] == "no-store"
        assert pin_ids(initial) == ["b", "a"]
        initial_items = initial["items"]
        assert isinstance(initial_items, list)
        assert all(
            isinstance(row, dict) and "assistant_text" not in row and "conversation_id" not in row
            for row in initial_items
        )
        assert all(
            isinstance(row, dict) and row.get("last_reply_revision") and row.get("last_reply_at")
            for row in initial_items
        )
        assert post_json(port, "/api/local-chat-pins", {"send_id": "a", "pinned": True})[0] == 200
        assert post_json(port, "/api/local-chat-pins", {"send_id": "b", "pinned": False})[0] == 200
        assert post_json(port, "/api/local-chat-pins", {"send_id": "c", "pinned": True})[0] == 200
        expected = ["c", "a"]
        assert pin_ids(get(port, "/api/local-chat-pins")[1]) == expected
        fresh_store = ResponseStore(path)
        assert [row["send_id"] for row in fresh_store.local_pinned_runs()] == expected
        with fresh_store.engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM local_chat_pins")).scalar_one() == 2
            )
        assert path.stat().st_mode & 0o077 == 0
        assert str(path) not in str(initial)


def test_local_read_receipts_persist_and_reject_stale_revisions(tmp_path: Path) -> None:
    from sqlalchemy import update

    from prompta.response_store import ResponseStore, results

    with server(tmp_path) as (app, port):
        completed_run(app, "read-one", "Read one", 100)
        completed_run(app, "read-two", "Read two", 200)
        detail = get(port, "/api/results/read-one")[1]
        revision = detail["last_reply_revision"]
        assert isinstance(revision, str) and len(revision) == 64
        assert detail["last_read_revision"] == ""
        assert (
            post_json(port, "/api/local-chat-reads", {"send_id": "absent", "revision": revision})[0]
            == 404
        )
        assert (
            post_json(port, "/api/local-chat-reads", {"send_id": "read-one", "revision": "no"})[0]
            == 409
        )
        assert (
            post_json(
                port,
                "/api/local-chat-reads",
                {"send_id": "read-one", "revision": revision, "extra": True},
            )[0]
            == 400
        )
        assert (
            post_json(
                port, "/api/local-chat-reads", {"send_id": "../read-one", "revision": revision}
            )[0]
            == 404
        )
        assert (
            post_json(port, "/api/local-chat-reads/import", {"reads": {"unknown": revision}})[0]
            == 200
        )

        assert (
            post_json(port, "/api/local-chat-reads", {"send_id": "read-one", "revision": revision})[
                0
            ]
            == 200
        )
        assert get(port, "/api/results/read-one")[1]["last_read_revision"] == revision
        second_revision = get(port, "/api/results/read-two")[1]["last_reply_revision"]
        assert isinstance(second_revision, str)
        assert (
            post_json(
                port, "/api/local-chat-reads/import", {"reads": {"read-two": second_revision}}
            )[0]
            == 200
        )
        assert get(port, "/api/results/read-two")[1]["last_read_revision"] == second_revision

        # A stale browser import must never overwrite a later, acknowledged revision.
        with app.results.engine.begin() as connection:
            connection.execute(
                update(results)
                .where(results.c.send_id == "read-one")
                .values(assistant_text="A newer final answer")
            )
        fresh_revision = get(port, "/api/results/read-one")[1]["last_reply_revision"]
        assert fresh_revision != revision
        assert (
            post_json(port, "/api/local-chat-reads", {"send_id": "read-one", "revision": revision})[
                0
            ]
            == 409
        )
        assert (
            post_json(
                port, "/api/local-chat-reads", {"send_id": "read-one", "revision": fresh_revision}
            )[0]
            == 200
        )
        assert (
            post_json(port, "/api/local-chat-reads/import", {"reads": {"read-one": revision}})[0]
            == 200
        )
        store = ResponseStore(app.results.path)
        items = store.page(limit=10)["items"]
        store.annotate_local_reads(items)
        received = {item["send_id"]: item["last_read_revision"] for item in items}
        assert received["read-one"] == fresh_revision
        assert received["read-two"] == second_revision


def test_mark_all_local_chats_read_uses_completed_revisions_across_pages(tmp_path: Path) -> None:
    from sqlalchemy import select, update

    from prompta.response_tables import local_chat_reads, results

    with server(tmp_path) as (app, port):
        for index in range(31):
            completed_run(app, f"bulk-{index:02}", f"Bulk {index}", 100 + index)
        app.results.ensure_queued("no-answer", "Waiting", "Waiting", now=500)
        app.results.ensure_queued("partial-answer", "Partial", "Partial", now=510)
        assert app.results.accept("partial-answer", "100:partial", deadline=999, now=511)
        assert app.results.write(
            "partial-answer",
            "100:partial",
            CaptureResult(
                "dom",
                "partial",
                "Not final",
                "cp",
                "mp",
                "pp",
            ),
            now=512,
        )

        status, payload = post_json(port, "/api/local-chat-reads/all", {})
        assert status == 200 and payload == {"ok": True, "count": 31}
        assert post_json(port, "/api/local-chat-reads/all", {}) == (
            200,
            {"ok": True, "count": 0},
        )
        assert post_json(port, "/api/local-chat-reads/all", {"send_id": "bulk-01"})[0] == 400
        assert get(port, "/api/local-chat-reads/all")[0] == 405
        for index in range(31):
            detail = get(port, f"/api/results/bulk-{index:02}")[1]
            assert detail["last_read_revision"] == detail["last_reply_revision"]
        for send_id in ("no-answer", "partial-answer"):
            detail = get(port, f"/api/results/{send_id}")[1]
            assert detail["last_reply_revision"] == ""
            assert detail["last_read_revision"] == ""
        with app.results.engine.connect() as connection:
            assert len(connection.execute(select(local_chat_reads.c.send_id)).all()) == 31

        with app.results.engine.begin() as connection:
            connection.execute(
                update(results)
                .where(
                    results.c.send_id == "bulk-30",
                )
                .values(assistant_text="New final reply after bulk action")
            )
        revised = get(port, "/api/results/bulk-30")[1]
        assert revised["last_read_revision"] != revised["last_reply_revision"]
        assert post_json(port, "/api/local-chat-reads/all", {}) == (
            200,
            {"ok": True, "count": 1},
        )
        assert (
            get(port, "/api/results/bulk-30")[1]["last_read_revision"]
            == (revised["last_reply_revision"])
        )

        from prompta.reply_contracts import ReplyIntent

        intent = ReplyIntent("bulk-reply-123456789", "c1", "m1", "Follow-up")
        assert app.replies.prepare("bulk-30", intent, now=600)
        assert app.replies.claim(intent.reply_id, "100:bulk", deadline=900, now=601)
        assert app.replies.accepted(
            intent.reply_id,
            "100:bulk",
            conversation_id="c1",
            parent_id="m1",
            message_id="m2",
            now=602,
        )
        assert app.replies.observe(
            intent.reply_id,
            "100:bulk",
            CaptureResult(
                "sse",
                "complete",
                "A completed manual follow-up",
                "c1",
                "m2",
                "m1",
            ),
            now=603,
        )
        newer = get(port, "/api/results/bulk-30")[1]
        assert newer["last_reply_revision"] != revised["last_reply_revision"]
        assert post_json(port, "/api/local-chat-reads/all", {}) == (
            200,
            {"ok": True, "count": 1},
        )
        assert (
            get(port, "/api/results/bulk-30")[1]["last_read_revision"]
            == (newer["last_reply_revision"])
        )


def test_mark_all_as_read_button_persists_across_tabs_and_reload(tmp_path: Path) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not chromium or not Path(chromium).is_file():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port):
        for index in range(65):
            completed_run(app, f"button-{index:02}", f"Button {index}", 100 + index)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium,
                headless=True,
                args=["--no-sandbox"],
            )
            try:
                first = browser.new_context(viewport={"width": 390, "height": 844})
                second = browser.new_context(viewport={"width": 1440, "height": 900})
                mobile = first.new_page()
                desktop = second.new_page()
                for page in (mobile, desktop):
                    page.add_init_script("""localStorage.setItem(
                        "prompta.local-sidebar.v1",
                        JSON.stringify({baselineAt: 1, readAt: {}})
                    );""")
                    page.goto(f"http://127.0.0.1:{port}/?view=chats", wait_until="networkidle")
                    page.wait_for_function(
                        "() => document.querySelectorAll('.unread-indicator').length >= 20"
                    )
                assert page.locator(".unread-indicator").count() < 65

                for _ in range(6):
                    mobile.locator(".chats-list").evaluate(
                        "(element) => { element.scrollTop = element.scrollHeight; }"
                    )
                    mobile.wait_for_timeout(150)
                    if mobile.locator(".chat-entry").count() == 65:
                        break
                expect(mobile.locator(".chat-entry")).to_have_count(65)

                button = mobile.get_by_role("button", name="Mark all local chats as read")
                expect(button).to_be_visible()
                button.click()
                expect(mobile.locator(".unread-indicator")).to_have_count(0)
                mobile.reload(wait_until="networkidle")
                expect(mobile.locator(".unread-indicator")).to_have_count(0)
                desktop.reload(wait_until="networkidle")
                expect(desktop.locator(".unread-indicator")).to_have_count(0)

                mobile.evaluate("localStorage.clear()")
                mobile.reload(wait_until="networkidle")
                expect(mobile.locator(".unread-indicator")).to_have_count(0)
                off_page = get(port, "/api/results/button-00")[1]
                assert off_page["last_read_revision"] == off_page["last_reply_revision"]
            finally:
                browser.close()


def test_server_local_pins_across_browser_contexts_and_rapid_clicks(tmp_path: Path) -> None:
    chromium_path = os.environ.get("PROMPTA_TEST_CHROMIUM")
    if not chromium_path or not Path(chromium_path).is_file():
        pytest.skip("Visual Chromium binary unavailable")
    with server(tmp_path) as (app, port):
        for i in range(26):
            completed_run(app, f"run-{i:02}", f"Chat {i:02}", 1000 + i)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium_path,
                headless=True,
                args=["--no-sandbox"],
            )
            try:
                first = browser.new_context(viewport={"width": 390, "height": 844})
                second = browser.new_context(viewport={"width": 1440, "height": 900})
                a = first.new_page()
                b = second.new_page()
                host = f"127.0.0.1:{port}"
                remote_hosts: list[str] = []
                a.on("request", lambda request: remote_hosts.append(request.url.split("/")[2]))
                b.on("request", lambda request: remote_hosts.append(request.url.split("/")[2]))
                a.goto(f"http://{host}/?view=chats", wait_until="domcontentloaded")
                a.evaluate("""() => localStorage.setItem("prompta.local-sidebar.v1",
                    JSON.stringify({ baselineAt: 1, readAt: {}, pinnedIds: ["run-00"] }))""")
                a.reload(wait_until="domcontentloaded")
                expect(a.locator(".chats-date")).to_have_count(0)
                expect(a.locator(".chats-pagination")).to_have_count(0)
                expect(a.locator(".chat-entry").filter(has_text="Chat 00")).to_have_count(1)
                assert "pinnedIds" not in json.loads(
                    a.evaluate("localStorage.getItem('prompta.local-sidebar.v1')")
                )
                b.goto(f"http://{host}/?view=chats", wait_until="domcontentloaded")
                expect(b.locator(".chat-entry").filter(has_text="Chat 00")).to_have_count(1)
                target = b.locator(".chat-entry").filter(has_text="Chat 25").locator(".chat-pin")
                target.click()
                expect(
                    a.locator(".chat-entry").filter(has_text="Chat 25").locator(".chat-pin")
                ).to_have_attribute("aria-pressed", "true")
                target.click()
                target.click()
                target.click()
                expect(
                    a.locator(".chat-entry").filter(has_text="Chat 25").locator(".chat-pin")
                ).to_have_attribute("aria-pressed", "false")
                expect(
                    b.locator(".chat-entry").filter(has_text="Chat 00").locator(".chat-pin")
                ).to_have_attribute("aria-pressed", "true")
                b.route(
                    f"http://{host}/api/local-chat-pins",
                    lambda route: (
                        route.abort() if route.request.method == "POST" else route.continue_()
                    ),
                )
                target.click()
                expect(
                    b.get_by_role("alert").filter(has_text="Pin change could not be confirmed")
                ).to_be_visible()
                expect(target).to_have_attribute("aria-pressed", "false")
                b.unroute(f"http://{host}/api/local-chat-pins")
                a.reload(wait_until="domcontentloaded")
                assert pin_ids(get(port, "/api/local-chat-pins")[1]) == ["run-00"]
                assert all(value == host for value in remote_hosts)
            finally:
                browser.close()
