from __future__ import annotations

import inspect
import json
import shutil
import subprocess

import pytest

from prompta.browser_script_loader import load_browser_script, render_browser_script
from prompta.playwright_driver import PlaywrightDriver

SCRIPT_NAMES = (
    "arm_page_send_probe.js",
    "page_send_probe.js",
    "clear_page_send_probe.js",
    "ensure_token.js",
    "conversation_final_event.js",
    "conversation_activity.js",
    "conversation_snapshot.js",
    "set_window_name.js",
    "get_window_name.js",
    "browser_user_agent.js",
    "element_tag_name.js",
    "file_input_names.js",
)


@pytest.mark.parametrize("script_name", SCRIPT_NAMES)
def test_browser_script_parses_as_javascript(tmp_path, script_name: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")

    script_path = tmp_path / script_name
    script_path.write_text(load_browser_script(script_name))
    subprocess.run(
        [node, "--check", str(script_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_playwright_eval_helpers_are_externalized() -> None:
    source = inspect.getsource(PlaywrightDriver)

    for embedded_javascript in (
        "window.name",
        "navigator.userAgent",
        "el => el.tagName",
        "input => Array.from",
    ):
        assert embedded_javascript not in source


def test_browser_script_template_json_encodes_values() -> None:
    conversation_id = 'conversation-"quoted"\nline\\slash'
    script = render_browser_script(
        "conversation_final_event.js",
        CONVERSATION_ID=conversation_id,
    )

    assert "__CONVERSATION_ID__" not in script
    assert f"encodeURIComponent({json.dumps(conversation_id)})" in script
