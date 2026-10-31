"""Live Chromium/CDP regression: tools arrive before an SSE POST ends."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from patchright.async_api import async_playwright as async_patchright

from prompta.owned_tool_stream import OwnedToolStream
from prompta.response_capture import CaptureResult


@pytest.mark.asyncio
async def test_cdp_observes_tool_before_owned_post_finishes() -> None:
    executable = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not executable.is_file():
        pytest.skip("Chromium unavailable")
    sent = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Owned test page</body></html>")

        def do_POST(self) -> None:
            if self.path != "/conversation":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            tool = {
                "conversation_id": "owned-chat",
                "message": {
                    "id": "tool-call-1",
                    "author": {"role": "assistant"},
                    "recipient": "api_tool.call_tool",
                    "content": {"content_type": "text", "parts": [json.dumps({
                        "type": "mcpToolCall", "tool": "web.search",
                        "arguments": {"query": "PRIVATE_LOCAL"},
                    })]},
                },
            }
            payload = ("data: " + json.dumps(tool) + "\n\n").encode()
            try:
                self.wfile.write(payload)
                self.wfile.flush()
                sent.set()
                release.wait(6.0)
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stream: OwnedToolStream | None = None
    try:
        async with async_patchright() as patchright:
            browser = await patchright.chromium.launch(
                executable_path=str(executable), headless=True, args=["--no-sandbox"],
            )
            try:
                page = await browser.new_page()
                base = f"http://127.0.0.1:{server.server_port}"
                await page.goto(base)
                observed: list[CaptureResult] = []
                stream = await OwnedToolStream.attach(
                    page, lambda: True,
                    lambda url: url == base + "/conversation", observed.append,
                )
                await page.evaluate("() => { void fetch('/conversation', {method: 'POST'}); }")
                assert await asyncio.to_thread(sent.wait, 5.0)
                for _ in range(60):
                    if observed:
                        break
                    await asyncio.sleep(0.05)
                assert observed, "No tool event before the SSE response ended"
                assert observed[-1].tool_calls[0]["action"] == "search"
                assert observed[-1].tool_calls[0]["status"] == "running"
                assert "PRIVATE_LOCAL" not in str(observed)
            finally:
                release.set()
                if stream is not None:
                    await stream.stop()
                await browser.close()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3.0)
