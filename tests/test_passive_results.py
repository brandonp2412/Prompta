from __future__ import annotations

import asyncio
import os
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import event, inspect

from prompta.delivery_browser import BrowserDeliverySender
from prompta.delivery_queue import DeliveryQueueStore
from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from prompta.strict_types import string_object_dict

_RECOVERED_CHAT = "12345678-1234-4123-8123-123456789abc"


def _capture(text: str, status: str = "partial", message: str = "m1") -> CaptureResult:
    from prompta.response_capture import CaptureStatus

    resolved: CaptureStatus = "complete" if status == "complete" else "partial"
    return CaptureResult("dom", resolved, text, None, message, None)


def test_private_wal_migration_and_queued_identity(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "private" / "chat-results.sqlite3")
    assert "job_responses" in inspect(store.engine).get_table_names()
    store.ensure_queued("s1", "Private user prompt", "job", now=100)
    store.ensure_queued("s1", "should not overwrite", now=101)
    row = store.get("s1")
    assert row is not None and row["user_text"] == "Private user prompt"
    assert row["status"] == "queued" and row["job_name"] == "job"
    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700
    for path in [store.path, Path(str(store.path) + "-wal"), Path(str(store.path) + "-shm")]:
        if path.exists():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_atomic_lease_complete_is_immutable_and_branch_safe(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    store.ensure_queued("s1", "prompt", now=100)

    def claim(owner: str) -> bool:
        return store.accept("s1", owner, deadline=300, now=101)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ["11:a", "22:b"]))
    assert claims.count(True) == 1
    owner = "11:a" if claims[0] else "22:b"
    other = "22:b" if owner == "11:a" else "11:a"
    assert not store.write("s1", other, _capture("wrong"), now=102)
    assert store.write("s1", owner, _capture("Partial"), now=103)
    assert not store.write("s1", owner, _capture("Branch change", message="m2"), now=104)
    assert store.write("s1", owner, _capture("Finished response", "complete"), now=105)
    assert not store.write("s1", owner, _capture("Downgraded"), now=106)
    assert not store.finish("s1", owner, "interrupted", now=107)
    row = store.get("s1")
    assert row is not None and row["status"] == "completed"
    assert row["assistant_text"] == "Finished response"
    assert row["message_id"] == "m1" and row["finished_at"] == 105


def test_timeout_and_crash_keep_partial_without_fake_completion(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    store.ensure_queued("ttl", "prompt", now=100)
    assert store.accept("ttl", f"{os.getpid()}:lease", deadline=120, now=101)
    assert store.write("ttl", f"{os.getpid()}:lease", _capture("Incomplete"), now=110)
    assert store.recover_orphans(now=121) == 1
    row = store.get("ttl")
    assert row is not None
    assert row["status"] == "interrupted"
    assert row["assistant_text"] == "Incomplete"
    store.ensure_queued("crash", "prompt", now=100)
    assert store.accept("crash", "99999999:dead", deadline=200, now=101)
    assert store.recover_orphans(now=110) == 1
    row = store.get("crash")
    assert row is not None
    assert row["status"] == "interrupted"
    assert not store.write("crash", "99999999:dead", _capture("Late", "complete"), now=111)


def test_empty_answer_cannot_be_completed(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    store.ensure_queued("s", "prompt", now=10)
    assert store.accept("s", "100:a", deadline=40, now=11)
    assert store.write("s", "100:a", _capture("", "complete"), now=12)
    row = store.get("s")
    assert row is not None
    assert row["status"] == "accepted"


class StreamDriver:
    def __init__(self, updates: list[CaptureResult | None]) -> None:
        self.updates = updates
        self.is_connected = True
        self.eval_calls = 0
        self.dom_reads = 0
        self.stop_after_first = False

    async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
        await asyncio.sleep(0)
        if self.updates:
            result = self.updates.pop(0)
            if self.stop_after_first:
                self.is_connected = False
            return result
        await asyncio.sleep(min(timeout, 0.01))
        return None

    def captured_assistant_response(self, capture: dict[str, object]) -> CaptureResult | None:
        result = capture.get("assistant_result")
        return result if isinstance(result, CaptureResult) else None

    async def observed_assistant_response(self) -> CaptureResult:
        self.dom_reads += 1
        return _capture("")

    async def eval(self, _script: str) -> object:
        self.eval_calls += 1
        return False


@pytest.mark.asyncio
async def test_passive_sse_completion_without_network_or_dom_scrape(tmp_path: Path) -> None:
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", connector_approval=False)
    sender.results.ensure_queued("s", "private")
    owner = f"{os.getpid()}:test"
    assert sender.results.accept("s", owner, deadline=time.time() + 60)
    sse = CaptureResult("sse", "complete", "Verified SSE answer", "c1", "m1", "p1")
    driver = StreamDriver([sse])
    await sender._capture_until_complete(driver, {"assistant_result": sse, "status": 200}, "s", owner, deadline=asyncio.get_running_loop().time() + 2)
    row = sender.results.get("s")
    assert row is not None
    assert row["status"] == "completed"
    assert row["source"] == "sse"
    assert driver.dom_reads == 0 and driver.eval_calls == 0


@pytest.mark.asyncio
async def test_disconnect_keeps_partial_and_approval_task_stops(tmp_path: Path) -> None:
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", connector_approval=True)
    sender.results.ensure_queued("s", "private")
    owner = f"{os.getpid()}:test"
    assert sender.results.accept("s", owner, deadline=time.time() + 60)
    driver = StreamDriver([_capture("So far")])
    driver.stop_after_first = True
    await sender._capture_until_complete(driver, {"status": 200}, "s", owner, deadline=asyncio.get_running_loop().time() + 2)
    row = sender.results.get("s")
    assert row is not None
    assert row["status"] == "interrupted"
    assert row["assistant_text"] == "So far"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("conversation_id", "message_id", "expect_renewal"),
    [(_RECOVERED_CHAT, "m1", True), (None, "m1", False), (_RECOVERED_CHAT, None, False)],
)
async def test_partial_response_activity_renews_lease_without_parent_id(
    tmp_path: Path,
    conversation_id: str | None,
    message_id: str | None,
    expect_renewal: bool,
) -> None:
    from prompta.browser_ownership import MAX_OWNED_TAB_AGE_SECONDS

    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", connector_approval=False)
    sender.results.ensure_queued("s", "Long-running prompt")
    owner = f"{os.getpid()}:activity"
    original_deadline = time.time() + 30
    assert sender.results.accept("s", owner, deadline=original_deadline)

    class OwnedDriver(StreamDriver):
        touches = 0

        def record_verified_activity(self) -> bool:
            self.touches += 1
            return True

    partial = CaptureResult("dom", "partial", "Still working", conversation_id, message_id, None)
    driver = OwnedDriver([partial])
    driver.stop_after_first = True
    await sender._capture_until_complete(
        driver, {"status": 200}, "s", owner,
        deadline=asyncio.get_running_loop().time() + 2,
    )
    row = sender.results.get("s")
    assert row is not None and row["status"] == "interrupted"
    assert row["assistant_text"] == "Still working"
    assert driver.touches == int(expect_renewal)
    capture_deadline = row["capture_deadline"]
    assert isinstance(capture_deadline, float)
    if expect_renewal:
        assert capture_deadline > original_deadline + MAX_OWNED_TAB_AGE_SECONDS - 90
    else:
        assert capture_deadline == original_deadline


@pytest.mark.asyncio
async def test_rate_limit_during_capture_updates_read_backoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", connector_approval=False)
    sender.results.ensure_queued("s", "private")
    owner = f"{os.getpid()}:test"
    assert sender.results.accept("s", owner, deadline=time.time() + 60)
    seen: list[int] = []
    monkeypatch.setattr(sender.runtime, "record_read_rate_limit", lambda exc: seen.append(exc.retry_after))
    await sender._capture_until_complete(StreamDriver([None]), {"status": 429, "retry_after": "900"}, "s", owner, deadline=asyncio.get_running_loop().time() + 2)
    assert seen == [900]
    row = sender.results.get("s")
    assert row is not None
    assert row["status"] == "unavailable"


@pytest.mark.asyncio
async def test_extra_chatgpt_continuation_post_uses_dom_without_closing_early(tmp_path: Path) -> None:
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", connector_approval=True)
    sender.results.ensure_queued("s", "prompt")
    owner = f"{os.getpid()}:test"
    assert sender.results.accept("s", owner, deadline=time.time() + 60)
    driver = StreamDriver([_capture("Approved answer", "complete")])
    await sender._capture_until_complete(
        driver, {"ambiguous_request": True, "status": 200}, "s", owner,
        deadline=asyncio.get_running_loop().time() + 2,
    )
    row = sender.results.get("s")
    assert row is not None and row["status"] == "completed"
    assert row["source"] == "dom" and row["assistant_text"] == "Approved answer"
    assert driver.dom_reads == 0


@pytest.mark.asyncio
async def test_late_same_tab_recovery_after_observer_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prompta import delivery_browser

    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", connector_approval=False)
    sender.results.ensure_queued("recover", "private prompt")
    owner = f"{os.getpid()}:recovery"
    assert sender.results.accept("recover", owner, deadline=time.time() + 60)
    monkeypatch.setattr(delivery_browser, "_PASSIVE_RECOVERY_PROBE_SECONDS", 0.03)

    class RecoveringDriver(StreamDriver):
        def __init__(self) -> None:
            super().__init__([])
            self.fail_once = True

        async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError("temporary callback failure")
            return await super().wait_capture_update(timeout=timeout)

        async def observed_assistant_response(self) -> CaptureResult:
            self.dom_reads += 1
            return CaptureResult(
                "dom", "complete", "Recovered final answer", None,
                "11111111-1111-4111-8111-111111111111", None,
                observer_id="owned-answer",
            )

        async def eval(self, _script: str) -> str:
            self.eval_calls += 1
            return f"/c/{_RECOVERED_CHAT}"

    driver = RecoveringDriver()
    await sender._capture_until_complete(
        driver, {"status": 200}, "recover", owner,
        deadline=asyncio.get_running_loop().time() + 2.0,
    )
    row = sender.results.get("recover")
    assert row is not None
    assert row["status"] == "completed"
    assert row["assistant_text"] == "Recovered final answer"
    assert row["conversation_id"] == _RECOVERED_CHAT
    assert driver.dom_reads == 1 and driver.eval_calls == 1


@pytest.mark.asyncio
async def test_real_browser_late_answer_recovers_without_external_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    from playwright.async_api import async_playwright

    from prompta import delivery_browser
    from prompta.browser_script_loader import load_browser_script
    from prompta.response_capture import normalize_dom_snapshot

    chromium = shutil.which("chromium")
    if chromium is None:
        pytest.skip("Local Chromium unavailable")
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", connector_approval=False)
    sender.results.ensure_queued("browser-recover", "private synthetic prompt")
    owner = f"{os.getpid()}:browser-recovery"
    assert sender.results.accept("browser-recover", owner, deadline=time.time() + 60)
    monkeypatch.setattr(delivery_browser, "_PASSIVE_RECOVERY_PROBE_SECONDS", 0.08)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox"],
        )
        try:
            page = await browser.new_page()
            requests: list[str] = []
            page.on("request", lambda request: requests.append(request.url))
            await page.route(
                "**/*",
                lambda route: route.fulfill(
                    status=200, content_type="text/html", body="<html><main></main></html>",
                ),
            )
            await page.goto(f"http://127.0.0.1:9876/c/{_RECOVERED_CHAT}")
            assert await page.evaluate(load_browser_script("passive_response_observer.js"))
            await page.evaluate(
                """() => {
                  const answer = document.createElement("section");
                  answer.setAttribute("data-chatgpt-search-unit-key", "synthetic:assistant");
                  answer.setAttribute(
                    "data-chatgpt-search-message-ids",
                    '["11111111-1111-4111-8111-111111111111"]'
                  );
                  answer.innerHTML =
                    '<div class="markdown"><p>Real browser recovered answer</p></div>' +
                    '<button data-testid="copy-turn-action-button">Copy</button>';
                  document.querySelector("main").append(answer);
                }"""
            )

            class SilentBrowserDriver:
                is_connected = True
                reads = 0

                async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
                    await asyncio.sleep(min(timeout, 0.03))
                    return None

                def captured_assistant_response(
                    self, _capture: dict[str, object],
                ) -> CaptureResult | None:
                    return None

                async def observed_assistant_response(self) -> CaptureResult:
                    self.reads += 1
                    payload = await page.evaluate(
                        load_browser_script("passive_response_read.js")
                    )
                    return normalize_dom_snapshot(payload)

                async def eval(self, script: str) -> object:
                    return await page.evaluate(script)

            driver = SilentBrowserDriver()
            await sender._capture_until_complete(
                driver, {"status": 200}, "browser-recover", owner,
                deadline=asyncio.get_running_loop().time() + 3.0,
            )
            row = sender.results.get("browser-recover")
            assert row is not None
            assert row["status"] == "completed"
            assert row["assistant_text"] == "Real browser recovered answer"
            assert row["conversation_id"] == _RECOVERED_CHAT
            assert driver.reads > 1
            assert requests and all(
                url.startswith("http://127.0.0.1:9876/") for url in requests
            )
        finally:
            await browser.close()


def test_delivery_queue_persists_scheduled_run_and_terminal_status(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    receipt, created = queue.enqueue_idempotent({
        "send_id": "scheduled-1", "client_id": "scheduled:key:review-job",
        "message": "Review the code", "created_at": 123.0,
    })
    assert created and receipt["status"] == "queued"
    row = queue.results.get("scheduled-1")
    assert row is not None and row["status"] == "queued"
    assert row["job_name"] == "review-job" and row["created_at"] == 123.0
    assert queue.cancel_pending("scheduled-1", now=130)
    row = queue.results.get("scheduled-1")
    assert row is not None and row["status"] == "unavailable"


def test_long_run_previews_project_only_bounded_sql_substrings(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    store.ensure_queued("long", "Prompt" * 400_000, "A job", now=10)
    assert store.accept("long", "42:a", deadline=30, now=11)
    assert store.write("long", "42:a", _capture("A" * 2_000_000), now=12)
    statements: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, _params: object,
               _context: object, _many: bool) -> None:
        statements.append(statement)

    event.listen(store.engine, "before_cursor_execute", record)
    try:
        page = store.page(query="", limit=20)
    finally:
        event.remove(store.engine, "before_cursor_execute", record)
    items = page["items"]
    assert isinstance(items, list) and len(items) == 1
    item = string_object_dict(items[0])
    assert item is not None and item["preview"] == "A" * 180
    assert len(str(item["title"])) < 100
    listing = next(sql for sql in statements if "ORDER BY" in sql)
    assert "substr(job_responses.assistant_text" in listing
    assert "substr(job_responses.user_text" in listing
    assert listing.count("job_responses.assistant_text") == 1


def test_repeated_partial_snapshots_do_not_write_duplicate_wal_updates(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    store.ensure_queued("s", "Synthetic prompt", now=10)
    assert store.accept("s", "42:a", deadline=30, now=11)
    writes: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, _params: object,
               _context: object, _many: bool) -> None:
        if statement.startswith("UPDATE job_responses"):
            writes.append(statement)

    event.listen(store.engine, "before_cursor_execute", record)
    try:
        assert store.write("s", "42:a", _capture("Partial"), now=12)
        assert store.write("s", "42:a", _capture("Partial"), now=17)
        assert store.write("s", "42:a", _capture("Partial"), now=22)
        assert store.write("s", "42:a", _capture("Final", "complete"), now=23)
    finally:
        event.remove(store.engine, "before_cursor_execute", record)
    assert len(writes) == 2
    row = store.get("s")
    assert row is not None and row["status"] == "completed"


@pytest.mark.asyncio
async def test_dom_branch_rollover_preserves_partial_without_false_completion(tmp_path: Path) -> None:
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", connector_approval=False)
    sender.results.ensure_queued("s", "Synthetic prompt")
    owner = f"{os.getpid()}:rollover"
    assert sender.results.accept("s", owner, deadline=time.time() + 60)
    invalid = CaptureResult("dom", "unknown", "", None, None, None)
    driver = StreamDriver([_capture("Original partial"), invalid, _capture("Wrong branch", "complete", "m2")])
    await sender._capture_until_complete(
        driver, {"status": 200}, "s", owner, deadline=asyncio.get_running_loop().time() + 5,
    )
    row = sender.results.get("s")
    assert row is not None
    assert row["status"] == "unavailable"
    assert row["assistant_text"] == "Original partial"
    assert len(driver.updates) == 1
