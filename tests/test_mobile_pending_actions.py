from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from threading import Thread

import pytest

import prompta.web as web
from prompta.cache import ChatCache
from prompta.web import PromptaUIServer, ReadOnlyChatStore


def _build_current_ui(tmp_path: Path) -> Path:
    project_root = Path(__file__).resolve().parents[1]
    bundle_root = tmp_path / "bundle"
    subprocess.run(
        [
            "bun",
            "x",
            "vite",
            "build",
            "--outDir",
            str(bundle_root),
            "--emptyOutDir",
        ],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )

    static_root = tmp_path / "static"
    shutil.copytree(project_root / "src" / "static", static_root)
    shutil.copy2(bundle_root / "app.js", static_root / "app.js")
    return static_root


def _seed_chat(path: Path) -> None:
    cache = ChatCache(path)
    try:
        cache.start(
            "chat-1",
            context_id="context-1",
            job_name="",
            prompt="Existing conversation",
        )
        cache.write_snapshot(
            "chat-1",
            {
                "title": "Existing conversation",
                "streaming": False,
                "messages": [
                    {
                        "id": "u1",
                        "role": "user",
                        "content": "Existing conversation",
                    },
                    {
                        "id": "a1",
                        "role": "assistant",
                        "content": "Existing response",
                    },
                ],
            },
        )
    finally:
        cache.close()


def test_mobile_long_press_opens_pending_message_bottom_sheet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = shutil.which("chromium") or shutil.which("brave")
    if executable is None:
        pytest.skip("A Chromium-compatible browser is unavailable")

    from playwright.sync_api import sync_playwright

    static_root = _build_current_ui(tmp_path)
    monkeypatch.setattr(web, "_STATIC_ROOT", static_root)

    cache_path = tmp_path / "chats.sqlite3"
    _seed_chat(cache_path)
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        ReadOnlyChatStore(cache_path),
        tmp_path / "state.json",
    )
    server.send_jobs.submit(
        operation="once",
        message="Queue blocker",
        client_id="other-session:blocker",
    )
    queued = server.send_jobs.submit(
        operation="reply",
        conversation_id="chat-1",
        message="Pending long press regression",
        client_id="test-session:pending",
    )
    assert int(queued["queue_position"]) > 1

    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            try:
                context = browser.new_context(
                    viewport={"width": 390, "height": 844},
                    has_touch=True,
                    is_mobile=True,
                )
                page = context.new_page()
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/#/chat-1",
                    wait_until="domcontentloaded",
                )

                target = page.locator(
                    "section.pending-message-action-target",
                    has_text="Pending long press regression",
                )
                target.wait_for(state="visible", timeout=10_000)
                box = target.bounding_box()
                assert box is not None

                cdp = context.new_cdp_session(page)
                x = box["x"] + min(box["width"] / 2, 120)
                y = box["y"] + box["height"] / 2
                cdp.send(
                    "Input.dispatchTouchEvent",
                    {
                        "type": "touchStart",
                        "touchPoints": [{"x": x, "y": y}],
                    },
                )
                try:
                    page.wait_for_timeout(550)
                    actions = page.locator('dialog[aria-labelledby="pendingMessageActionsTitle"]')
                    assert actions.evaluate("(element) => element.open") is True
                    assert actions.locator("button").all_inner_texts() == [
                        "Send next",
                        "Edit message",
                        "Delete message",
                        "Cancel",
                    ]
                finally:
                    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        if thread.is_alive():
            thread.join(timeout=2)
