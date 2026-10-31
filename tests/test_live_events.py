"""End-to-end contract for the local SSE stream and its store revisions."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from http.client import HTTPConnection, HTTPResponse
from pathlib import Path
from unittest.mock import patch

from live_server import LiveServer
from patchright.sync_api import expect, sync_playwright

from prompta.jobs import add_job
from prompta.live_events import LocalEventSignals


@contextmanager
def live_server(tmp_path: Path) -> Generator[tuple[LiveServer, int, Path]]:
    jobs_path = tmp_path / "jobs.sqlite3"
    app = LiveServer(
        ("127.0.0.1", 0), state_path=tmp_path / "runtime.sqlite3",
        jobs_path=jobs_path,
    )
    worker = threading.Thread(target=app.serve_forever, daemon=True)
    worker.start()
    try:
        yield app, int(app.server_address[1]), jobs_path
    finally:
        app.shutdown()
        worker.join(timeout=3)
        app.server_close()


def next_event(response: HTTPResponse) -> tuple[str, str, str]:
    """Read a complete SSE event, ignoring comments/retry control frames."""
    while True:
        fields: dict[str, str] = {}
        while True:
            line = response.readline().decode("utf-8").strip()
            if not line:
                break
            if line.startswith(":"):
                continue
            key, separator, value = line.partition(":")
            if separator:
                fields[key] = value.strip()
        if fields.get("event"):
            return fields["event"], fields.get("data", ""), fields.get("id", "")


def test_sse_stream_signals_cross_process_store_changes_and_reconnects(tmp_path: Path) -> None:
    with live_server(tmp_path) as (app, port, jobs_path):
        client = HTTPConnection("127.0.0.1", port, timeout=6)
        try:
            client.request("GET", "/api/events")
            response = client.getresponse()
            assert response.status == 200
            assert response.getheader("content-type") == "text/event-stream; charset=utf-8"
            assert response.getheader("transfer-encoding") == "chunked"
            assert response.getheader("cache-control") == "no-cache, no-transform"
            assert next_event(response)[0] == "sync"

            app.results.ensure_queued("sse-run", "Sensitive prompt not transmitted", "Audit")
            topic, data, cursor = next_event(response)
            assert (topic, data) == ("chats", "refresh")
            assert cursor.isdecimal()

            add_job(jobs_path, "Live audit", "Never put job prompts on the stream", 3600)
            topic, data, cursor = next_event(response)
            assert (topic, data) == ("jobs", "refresh")
            assert cursor.isdecimal()
        finally:
            client.close()

        # The source may disconnect between two writes. Its next connection
        # always forces a full local refresh, even with Last-Event-ID supplied.
        app.results.ensure_queued("after-disconnect", "Another private prompt", "Audit")
        restored = HTTPConnection("127.0.0.1", port, timeout=6)
        try:
            restored.request("GET", "/api/events", headers={"Last-Event-ID": cursor})
            stream = restored.getresponse()
            assert next_event(stream)[0] == "sync"
        finally:
            restored.close()

        head = HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            head.request("HEAD", "/api/events")
            response = head.getresponse()
            assert response.status == 200
            assert response.read() == b""
            assert response.getheader("content-length") == "0"
        finally:
            head.close()


def test_sse_survives_temporary_jobs_read_failure_and_recovers(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path) as (app, port, jobs_path):
        scheduled_jobs = app.jobs.scheduled_jobs
        remaining_failures = 2

        def flaky_jobs() -> dict[str, object]:
            nonlocal remaining_failures
            if remaining_failures:
                remaining_failures -= 1
                raise OSError("temporary SQLite read failure")
            return dict(scheduled_jobs())

        monkeypatch.setattr(app.jobs, "scheduled_jobs", flaky_jobs)
        client = HTTPConnection("127.0.0.1", port, timeout=6)
        try:
            client.request("GET", "/api/events")
            stream = client.getresponse()
            assert stream.status == 200
            assert next_event(stream)[0] == "sync"
            add_job(jobs_path, "Recovered read", "Private content", 300)
            assert next_event(stream)[0] == "jobs"
            assert remaining_failures == 0
        finally:
            client.close()


def test_slow_sse_database_snapshot_does_not_block_other_http_requests(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path) as (app, port, _):
        snapshot = app.live_events.snapshot
        entered = threading.Event()
        release = threading.Event()
        first = True

        def slow_snapshot():
            nonlocal first
            if first:
                first = False
                entered.set()
                assert release.wait(3)
            return snapshot()

        monkeypatch.setattr(app.live_events, "snapshot", slow_snapshot)
        stream_client = HTTPConnection("127.0.0.1", port, timeout=5)
        stream_ready = threading.Event()

        def open_stream() -> None:
            stream_client.request("GET", "/api/events")
            stream_ready.set()

        reader = threading.Thread(target=open_stream)
        reader.start()
        try:
            assert entered.wait(2)
            health = HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                health.request("GET", "/api/jobs")
                assert health.getresponse().status == 200
            finally:
                health.close()
        finally:
            release.set()
            reader.join(timeout=3)
            stream_client.close()
        assert stream_ready.is_set()


def test_live_revisions_do_not_depend_on_private_payloads(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.sqlite3"
    app = LiveServer(
        ("127.0.0.1", 0), state_path=tmp_path / "runtime.sqlite3",
        jobs_path=jobs_path,
    )
    try:
        before = app.live_events.snapshot()
        app.results.ensure_queued("first", "Confidential result", "Audit")
        after_result = app.live_events.snapshot()
        assert after_result.chats != before.chats
        assert after_result.jobs == before.jobs

        add_job(jobs_path, "Sample", "Confidential job", 600)
        after_job = app.live_events.snapshot()
        assert after_job.jobs != after_result.jobs
        assert after_job.chats == after_result.chats

        app.queue.enqueue_manual(
            "A new fresh chat", images=(), request_id="0123456789abcdef0123456789abcdef"
        )
        after_queue = app.live_events.snapshot()
        assert after_queue.chats != after_job.chats
        assert after_queue.jobs == after_job.jobs
    finally:
        app.server_close()


def test_service_heartbeats_do_not_reload_jobs_but_scheduler_changes_do(tmp_path: Path) -> None:
    app = LiveServer(
        ("127.0.0.1", 0), state_path=tmp_path / "runtime.sqlite3",
        jobs_path=tmp_path / "jobs.sqlite3",
    )
    try:
        before = app.live_events.snapshot()
        assert app.health.beat("ui", now=time.time() + 10)
        after_heartbeat = app.live_events.snapshot()
        assert after_heartbeat.jobs == before.jobs
        assert after_heartbeat.chats == before.chats

        app.queue_view.runtime.update_scheduler_state({"live_jobs_probe": 1})
        after_job_state = app.live_events.snapshot()
        assert after_job_state.jobs != after_heartbeat.jobs
        assert after_job_state.chats == after_heartbeat.chats
    finally:
        app.server_close()


def test_live_revision_stat_failure_does_not_break_event_observation(tmp_path: Path) -> None:
    signals = LocalEventSignals(tmp_path / "jobs.sqlite3", tmp_path / "runtime.sqlite3")
    with patch.object(Path, "stat", side_effect=PermissionError("temporary IO failure")):
        snapshot = signals.snapshot()
    assert set(snapshot.jobs) == {(0, 0, 0)}
    assert set(snapshot.chats) == {(0, 0, 0)}


def test_browser_updates_jobs_and_chats_without_timer_polling(tmp_path: Path) -> None:
    """Real Chromium receives SSE invalidations and updates without clicking Refresh."""
    with live_server(tmp_path) as (app, port, jobs_path):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, executable_path=os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"),
                args=["--no-sandbox"],
            )
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                requests: list[str] = []
                page.on("request", lambda request: requests.append(request.url))
                page.goto(f"http://127.0.0.1:{port}/?view=jobs", wait_until="domcontentloaded")
                expect(page.locator(".jobs-panel")).to_be_visible()
                expect(page.locator(".job-name")).to_have_count(0)
                page.wait_for_timeout(1000)
                assert sum("/api/events" in request for request in requests) == 1

                add_job(jobs_path, "SSE visible job", "Private prompt", 3600)
                expect(page.locator(".job-name", has_text="SSE visible job")).to_be_visible(
                    timeout=5000
                )
                baseline_gets = sum("/api/jobs" in request for request in requests)
                page.wait_for_timeout(5500)
                # Heartbeats and idle time must not cause the old 5-second reload.
                assert sum("/api/jobs" in request for request in requests) == baseline_gets

                # A queue transition is a chats revision, even when the
                # scheduled job definitions did not change.
                app.queue.enqueue_manual("Queued synthetic prompt")
                expect(page.locator(".delivery-count", has_text="1 pending")).to_be_visible(
                    timeout=5000
                )
                assert sum("/api/jobs" in request for request in requests) == baseline_gets

                page.goto(
                    f"http://127.0.0.1:{port}/?view=chats", wait_until="domcontentloaded"
                )
                expect(page.locator(".chat-entry")).to_have_count(0)
                app.results.ensure_queued(
                    "sse-browser-run", "Private text", "SSE live chat"
                )
                expect(page.locator(".chat-entry")).to_have_count(1, timeout=5000)
                expect(page.locator(".chat-row strong", has_text="SSE live chat")).to_be_visible()
                assert all(f"127.0.0.1:{port}" in request for request in requests)
            finally:
                browser.close()


def test_browser_polls_during_sse_outage_and_recovers_without_reloading(tmp_path: Path) -> None:
    """If SSE fails but the API works, stale Jobs recover without a full-page reload."""
    with live_server(tmp_path) as (_, port, jobs_path):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, executable_path=os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"),
                args=["--no-sandbox"],
            )
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page_errors: list[str] = []
                request_methods: list[str] = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on("request", lambda request: request_methods.append(request.method))
                page.route("**/api/events", lambda route: route.abort())
                page.goto(f"http://127.0.0.1:{port}/?view=jobs", wait_until="domcontentloaded")
                expect(page.locator(".jobs-panel")).to_be_visible()
                expect(page.locator(".live-updates-warning")).to_be_visible(
                    timeout=14000
                )
                for width, height in ((360, 800), (390, 844), (412, 915), (1440, 900)):
                    page.set_viewport_size({"width": width, "height": height})
                    bounds = page.locator(".live-updates-warning").bounding_box()
                    assert bounds is not None
                    assert bounds["x"] >= 0
                    assert bounds["x"] + bounds["width"] <= width + 1
                    assert bounds["y"] > height / 2
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
                    )
                    page.screenshot(path=str(tmp_path / f"stream-outage-{width}.png"))
                page.set_viewport_size({"width": 390, "height": 844})

                add_job(jobs_path, "Offline SSE recovery", "Private prompt", 3600)
                expect(page.locator(".job-name", has_text="Offline SSE recovery")).to_be_visible(
                    timeout=19000
                )

                # EventSource retries its exact same-origin stream after the route
                # is restored. The banner clears and SSE is again the fast path.
                page.unroute("**/api/events")
                expect(page.locator(".live-updates-warning")).to_have_count(
                    0, timeout=15000
                )
                add_job(jobs_path, "Restored SSE", "Private prompt", 3600)
                expect(page.locator(".job-name", has_text="Restored SSE")).to_be_visible(
                    timeout=5000
                )
                page.route("**/api/events", lambda route: route.abort())
                page.goto(
                    f"http://127.0.0.1:{port}/?view=chats&draft=new",
                    wait_until="domcontentloaded",
                )
                expect(page.locator(".live-updates-warning")).to_be_visible(timeout=14000)
                page.screenshot(path=str(tmp_path / "stream-outage-chats-390.png"))
                assert page_errors == []
                assert "POST" not in request_methods
            finally:
                browser.close()


def test_idle_sse_sends_named_ping_visible_to_eventsource(tmp_path: Path) -> None:
    with live_server(tmp_path) as (_, port, _):
        client = HTTPConnection("127.0.0.1", port, timeout=19)
        try:
            client.request("GET", "/api/events")
            stream = client.getresponse()
            assert next_event(stream)[0] == "sync"
            topic, data, _ = next_event(stream)
            assert (topic, data) == ("ping", "keepalive")
        finally:
            client.close()
