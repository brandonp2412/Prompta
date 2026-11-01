"""Mobile drawer continuity and visible tool/job controls."""

import os
import re
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from web_results_support import server

from prompta.response_capture import CaptureResult


def test_mobile_drawer_tools_and_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.web as web_module

    monkeypatch.setattr(web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static")
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as runtime:
        app.results.ensure_queued("tools", "Tool preview")
        assert app.results.accept("tools", "owner", deadline=10**12)
        assert app.results.write("tools", "owner", CaptureResult(
            "sse", "complete", "Answer", "chat", "answer", None,
            tool_calls=({"id": "shell", "connector": "Nox", "action": "command",
                         "status": "completed", "arguments": '{"cmd":"echo hello | head -1"}',
                         "result": "hello", "error": "", "observed_at": 1793500000},),
        ))
        queued = app.queue.enqueue_manual("Pending stop example", request_id="b" * 32)
        browser = runtime.chromium.launch(executable_path=str(chromium), headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=tools")
            page.locator(".tool-type-group > summary").click()
            page.locator(".tool-call-summary").click()
            expect(page.locator(".tool-call-time")).to_contain_text(re.compile(r"[ap]m", re.I))
            expect(page.locator("code.language-bash .token").first).to_be_visible()
            page.screenshot(path="/tmp/prompta-mobile-tools.png", full_page=True)
            # Real layout sampling across frames catches transitions fighting a drag.
            positions = page.evaluate('''async () => {
                const sidebar = document.querySelector('.chats-sidebar');
                const frame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                const event = (type, x) => {
                    const touch = new Touch({identifier: 1, target: document.body, clientX: x, clientY: 120});
                    window.dispatchEvent(new TouchEvent(type, {touches: type === 'touchend' ? [] : [touch], changedTouches: [touch], cancelable: true}));
                };
                event('touchstart', 10);
                const positions = [];
                for (const x of [40, 80, 130, 180, 240]) {
                    event('touchmove', x);
                    await frame();
                    positions.push(sidebar.getBoundingClientRect().x);
                }
                event('touchend', 240);
                await frame();
                positions.push(sidebar.getBoundingClientRect().x);
                return positions;
            }''')
            assert isinstance(positions, list)
            coordinates: list[float] = []
            for value in positions:
                assert isinstance(value, (int, float))
                coordinates.append(float(value))
            assert coordinates == sorted(coordinates)
            expect(page.locator(".chats-layout")).to_have_class(re.compile("drawer-open"))
            expect(page.get_by_text("Waiting to start", exact=False)).to_have_count(0)
            page.get_by_role("button", name="Stop Pending stop example", exact=True).click()
            row = page.locator(".chat-entry").filter(has_text="Pending stop example")
            expect(row).to_contain_text("Stopped")
            pending = app.queue.get(str(queued["send_id"]))
            assert pending is not None and pending["status"] == "cancelled"
            page.evaluate('''async () => {
                const send = (type, x) => {
                    const touch = new Touch({identifier: 2, target: document.body, clientX: x, clientY: 120});
                    window.dispatchEvent(new TouchEvent(type, {touches: type === 'touchend' ? [] : [touch], changedTouches: [touch], cancelable: true}));
                };
                send('touchstart', 280);
                for (const x of [240, 180, 100, 30]) {
                    send('touchmove', x);
                    await new Promise(resolve => requestAnimationFrame(resolve));
                }
                send('touchend', 30);
            }''')
            expect(page.locator(".chats-layout")).not_to_have_class(re.compile("drawer-open"))
        finally:
            browser.close()
