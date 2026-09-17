from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import time
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from prompta import core

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "assets" / "prompta-ls.png"
FIXED_NOW = datetime(2026, 9, 17, 17, 15, tzinfo=ZoneInfo("Pacific/Auckland")).timestamp()
ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")
BACKGROUND = "#11111b"
FOREGROUND = "#cdd6f4"
DIM = "#7f849c"
COLORS = {
    31: "#f38ba8",
    32: "#a6e3a1",
    33: "#f9e2af",
    34: "#89b4fa",
    36: "#89dceb",
}


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def _font_path(bold: bool) -> Path:
    filename = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu") / filename,
        Path("/usr/share/fonts/TTF") / filename,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"Could not find {filename}; install the DejaVu Sans Mono font")


def _sample_output() -> str:
    with tempfile.TemporaryDirectory(prefix="prompta-readme-") as temporary:
        root = Path(temporary)
        jobs_path = root / "jobs.json"
        state_path = root / "state.json"
        core.add_job(
            jobs_path,
            "ci-watch",
            "Check the latest CI run and fix any failing tests.",
            30 * 60,
        )
        core.add_job(
            jobs_path,
            "morning-review",
            "Review open pull requests and summarize anything blocked.",
            daily_at="09:00",
        )
        core.add_job(
            jobs_path,
            "release-notes",
            "Draft release notes from changes merged since the last release.",
            60 * 60,
        )
        state_path.write_text(
            json.dumps(
                {
                    "jobs": {
                        "ci-watch": {
                            "last_sent_at": FIXED_NOW - 10 * 60,
                            "next_due_at_epoch": FIXED_NOW + 20 * 60,
                            "status": "healthy",
                        },
                        "morning-review": {
                            "initial_due_at_epoch": FIXED_NOW + 45 * 60,
                        },
                        "release-notes": {"paused": True},
                    }
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        output = TtyBuffer()
        environment = {
            "TERM": os.environ.get("TERM"),
            "TZ": os.environ.get("TZ"),
            "NO_COLOR": os.environ.get("NO_COLOR"),
        }
        os.environ["TERM"] = "xterm-256color"
        os.environ["TZ"] = "Pacific/Auckland"
        os.environ.pop("NO_COLOR", None)
        if hasattr(time, "tzset"):
            time.tzset()
        try:
            argv = [
                "prompta",
                "ls",
                "--jobs-file",
                str(jobs_path),
                "--state",
                str(state_path),
            ]
            with (
                redirect_stdout(output),
                patch.object(core.time, "time", return_value=FIXED_NOW),
                patch.object(sys, "argv", argv),
            ):
                core.main()
        finally:
            for name, value in environment.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            if hasattr(time, "tzset"):
                time.tzset()

    prompt = "\x1b[1;32mbrandon@glass\x1b[0m:\x1b[1;34m~/prompta\x1b[0m$ prompta ls\n"
    return prompt + output.getvalue()


def _ansi_segments(line: str) -> list[tuple[str, bool, bool, int | None]]:
    segments: list[tuple[str, bool, bool, int | None]] = []
    bold = False
    dim = False
    foreground: int | None = None
    position = 0
    for match in ANSI_RE.finditer(line):
        if match.start() > position:
            segments.append((line[position : match.start()], bold, dim, foreground))
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
    if position < len(line):
        segments.append((line[position:], bold, dim, foreground))
    return segments


def _render(output: str) -> None:
    regular = ImageFont.truetype(str(_font_path(False)), 15)
    bold_font = ImageFont.truetype(str(_font_path(True)), 15)
    lines = output.rstrip().splitlines()
    parsed = [_ansi_segments(line) for line in lines]
    line_height = 22
    padding_x = 28
    padding_y = 20

    scratch = Image.new("RGB", (1, 1))
    scratch_draw = ImageDraw.Draw(scratch)
    content_width = max(
        sum(
            scratch_draw.textlength(text, font=bold_font if is_bold else regular)
            for text, is_bold, _, _ in segments
        )
        for segments in parsed
    )
    image = Image.new(
        "RGB",
        (int(content_width) + padding_x * 2, len(lines) * line_height + padding_y * 2),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(image)

    y = padding_y
    for segments in parsed:
        x = padding_x
        for text, is_bold, is_dim, foreground in segments:
            font = bold_font if is_bold else regular
            color = DIM if is_dim else COLORS.get(foreground, FOREGROUND)
            draw.text((x, y), text, font=font, fill=color)
            x += draw.textlength(text, font=font)
        y += line_height

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, optimize=True)
    print(f"Generated {OUTPUT.relative_to(ROOT)}")


def main() -> None:
    _render(_sample_output())


if __name__ == "__main__":
    main()
