"""Real Chromium proof that tool payloads use language-aware highlighting."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from patchright.sync_api import expect
from patchright.sync_api import sync_playwright as sync_patchright
from test_reply_ui_browser import seed_terminal
from web_results_support import server


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900), (320, 700)])
def test_tool_calls_display_code_instead_of_json_wrappers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int, height: int
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static"
    )
    calls = [
        {
            "id": "python",
            "connector": "Nox Python",
            "action": "execute_python",
            "status": "completed",
            "arguments": json.dumps({"code": "from pathlib import Path\nprint(Path.cwd())"}),
            "result": json.dumps({"ok": True}),
            "error": "",
        },
        {
            "id": "serena",
            "connector": "Nox Serena",
            "action": "execute_shell_command",
            "status": "completed",
            "arguments": json.dumps({"command": "rg -n 'hello' src | head -10"}),
            "result": "Found 2 lines",
            "error": "",
        },
        {
            "id": "json",
            "connector": "Search",
            "action": "lookup",
            "status": "completed",
            "arguments": json.dumps({"query": "kiwi", "limit": 2}),
            "result": "",
            "error": "",
        },
    ]
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        send_id = "syntax-tools"
        seed_terminal(app, send_id=send_id, missing_id=False)
        with app.results.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE job_responses SET tool_calls_json = ?, status = 'completed' WHERE send_id = ?",
                (json.dumps(calls), send_id),
            )
        browser = patchright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run={send_id}")
            groups = page.locator(".tool-type-group")
            expect(groups).to_have_count(3)
            for index in range(3):
                groups.nth(index).locator(":scope > summary").click()
                groups.nth(index).locator(".tool-call-summary").click()
            python = page.locator("code.language-python")
            expect(python).to_have_text("from pathlib import Path\nprint(Path.cwd())")
            assert python.locator(".token.keyword").count() > 0
            assert '"code"' not in python.inner_text()
            bash = page.locator("code.language-bash")
            expect(bash).to_have_text("rg -n 'hello' src | head -10")
            assert bash.locator(".token.string").count() > 0
            expect(page.locator("code.language-json")).to_have_count(2)
            assert page.locator("code.language-json .token.property").count() > 0
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            if screenshot_dir := os.environ.get("PROMPTA_RESPONSE_SCREENSHOT_DIR"):
                destination = Path(screenshot_dir)
                destination.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(destination / f"tool-syntax-{width}.png"), full_page=True)
        finally:
            browser.close()
