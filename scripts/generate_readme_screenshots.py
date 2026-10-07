from __future__ import annotations

import html
import io
import os
import re
import sys
import tempfile
import threading
import time
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import Browser, Playwright, sync_playwright

from prompta import core
from prompta.scheduler_runtime import SchedulerRuntime
from prompta.web import PromptaJobServer

ROOT = Path(__file__).resolve().parents[1]
CLI_OUTPUT = ROOT / "docs" / "prompta-cli.png"
UI_OUTPUT = ROOT / "docs" / "prompta-ui-mobile.png"
FIXED_NOW = datetime(
    2026,
    10,
    1,
    9,
    0,
    tzinfo=timezone(timedelta(hours=13)),
).timestamp()
ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")
ANSI_COLORS = {
    31: "#f85149",
    32: "#3fb950",
    33: "#d29922",
    34: "#58a6ff",
    36: "#39c5cf",
}


def _set_timezone() -> str | None:
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Pacific/Auckland"
    tzset = getattr(time, "tzset", None)
    if callable(tzset):
        tzset()
    return previous


def _restore_timezone(previous: str | None) -> None:
    if previous is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = previous
    tzset = getattr(time, "tzset", None)
    if callable(tzset):
        tzset()


def _create_demo_runtime(root: Path) -> Path:
    runtime_path = root / "runtime.sqlite3"
    core.add_job(
        runtime_path,
        "ci-watch",
        "Check CI and surface anything that needs attention.",
        40 * 60,
        exact_interval=True,
        source_revision="",
    )
    core.add_job(
        runtime_path,
        "daily-review",
        "Review overnight changes and summarize anything important.",
        daily_at="09:00",
        source_revision="",
    )
    core.add_job(
        runtime_path,
        "release-notes",
        "Prepare release notes when the project has new changes.",
        daily_at="17:30",
        source_revision="",
    )

    runtime = SchedulerRuntime(runtime_path, runtime_path)
    runtime.update_job_state(
        "ci-watch",
        {
            "last_sent_at": FIXED_NOW - 10 * 60,
            "next_due_at_epoch": FIXED_NOW + 30 * 60,
            "status": "healthy",
        },
    )
    runtime.update_job_state(
        "daily-review",
        {
            "initial_due_at_epoch": FIXED_NOW + 24 * 60 * 60,
            "status": "pending",
        },
    )
    runtime.update_job_state(
        "release-notes",
        {
            "initial_due_at_epoch": FIXED_NOW + 8.5 * 60 * 60,
            "paused": True,
            "status": "paused",
        },
    )
    return runtime_path


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def _capture_cli(runtime_path: Path) -> str:
    output = TtyBuffer()
    argv = [
        "prompta",
        "list",
        "--jobs-file",
        str(runtime_path),
        "--state",
        str(runtime_path),
    ]
    previous_term = os.environ.get("TERM")
    previous_no_color = os.environ.pop("NO_COLOR", None)
    os.environ["TERM"] = "xterm-256color"
    try:
        with (
            redirect_stdout(output),
            patch.object(core.time, "time", return_value=FIXED_NOW),
            patch.object(sys, "argv", argv),
        ):
            core.main()
    finally:
        if previous_term is None:
            os.environ.pop("TERM", None)
        else:
            os.environ["TERM"] = previous_term
        if previous_no_color is not None:
            os.environ["NO_COLOR"] = previous_no_color
    return "$ prompta list\n" + output.getvalue()


def _browser(playwright: Playwright) -> Browser:
    configured = os.environ.get("PROMPTA_README_BROWSER")
    if configured:
        return playwright.chromium.launch(headless=True, executable_path=configured)

    for candidate in (
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/google-chrome-stable"),
    ):
        if candidate.is_file():
            return playwright.chromium.launch(headless=True, executable_path=str(candidate))

    return playwright.chromium.launch(headless=True)


def _ansi_html(text: str) -> str:
    parts: list[str] = []
    bold = False
    dim = False
    foreground: int | None = None
    position = 0

    def append_segment(segment: str) -> None:
        if not segment:
            return
        escaped = html.escape(segment)
        styles: list[str] = []
        if bold:
            styles.append("font-weight:700")
        if dim:
            styles.append("opacity:.6")
        if foreground is not None and foreground in ANSI_COLORS:
            styles.append(f"color:{ANSI_COLORS[foreground]}")
        if styles:
            parts.append(f'<span style="{";".join(styles)}">{escaped}</span>')
        else:
            parts.append(escaped)

    for match in ANSI_RE.finditer(text):
        append_segment(text[position : match.start()])
        codes = [int(value) if value else 0 for value in match.group(1).split(";")]
        for code in codes:
            if code == 0:
                bold = False
                dim = False
                foreground = None
            elif code == 1:
                bold = True
            elif code == 2:
                dim = True
            elif code == 22:
                bold = False
                dim = False
            elif 30 <= code <= 37:
                foreground = code
            elif code == 39:
                foreground = None
        position = match.end()

    append_segment(text[position:])
    return "".join(parts)


def _render_cli(browser: Browser, output: str) -> None:
    context = browser.new_context(
        viewport={"width": 1200, "height": 520},
        device_scale_factor=2,
        locale="en-NZ",
        timezone_id="Pacific/Auckland",
        color_scheme="dark",
    )
    try:
        page = context.new_page()
        rendered = _ansi_html(output)
        page.set_content(
            f"""
            <!doctype html>
            <meta charset="utf-8">
            <style>
              html, body {{
                margin: 0;
                background: #0d1117;
                color: #e6edf3;
                font-family: "DejaVu Sans Mono", "Noto Sans Mono", monospace;
              }}
              body {{ padding: 28px; }}
              .terminal {{
                display: inline-block;
                overflow: hidden;
                border: 1px solid #30363d;
                border-radius: 12px;
                background: #0d1117;
                box-shadow: 0 12px 36px rgba(0, 0, 0, 0.28);
              }}
              .bar {{
                height: 34px;
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 0 14px;
                border-bottom: 1px solid #30363d;
                background: #161b22;
              }}
              .dot {{
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: #30363d;
              }}
              .title {{
                margin-left: 8px;
                color: #8b949e;
                font: 12px system-ui, sans-serif;
              }}
              pre {{
                width: max-content;
                margin: 0;
                padding: 22px 24px 24px;
                font: 15px/1.5 "DejaVu Sans Mono", "Noto Sans Mono", monospace;
              }}
            </style>
            <div class="terminal">
              <div class="bar">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="title">Prompta CLI</span>
              </div>
              <pre>{rendered}</pre>
            </div>
            """
        )
        CLI_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        page.locator(".terminal").screenshot(path=str(CLI_OUTPUT), animations="disabled")
    finally:
        context.close()


def _render_ui(browser: Browser, runtime_path: Path) -> None:
    with patch("prompta.web.socket.gethostname", return_value="demo"):
        server = PromptaJobServer(
            ("127.0.0.1", 0),
            state_path=runtime_path,
            jobs_path=runtime_path,
        )
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()

    context = browser.new_context(
        viewport={"width": 480, "height": 1040},
        device_scale_factor=2,
        locale="en-NZ",
        timezone_id="Pacific/Auckland",
        color_scheme="dark",
        is_mobile=True,
        has_touch=True,
    )
    try:
        page = context.new_page()
        port = int(server.server_address[1])
        page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
        page.get_by_role("table", name="Scheduled jobs").wait_for()
        UI_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(UI_OUTPUT), animations="disabled")
    finally:
        context.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main() -> None:
    previous_timezone = _set_timezone()
    try:
        with tempfile.TemporaryDirectory(prefix="prompta-readme-") as temporary:
            runtime_path = _create_demo_runtime(Path(temporary))
            cli_output = _capture_cli(runtime_path)
            with sync_playwright() as playwright:
                browser = _browser(playwright)
                try:
                    _render_cli(browser, cli_output)
                    _render_ui(browser, runtime_path)
                finally:
                    browser.close()
    finally:
        _restore_timezone(previous_timezone)

    print(f"Generated {CLI_OUTPUT.relative_to(ROOT)}")
    print(f"Generated {UI_OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
