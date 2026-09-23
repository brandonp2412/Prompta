from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from prompta.browser_script_loader import load_browser_script, render_browser_script

SCRIPT_NAMES = (
    "arm_page_send_probe.js",
    "page_send_probe.js",
    "clear_page_send_probe.js",
    "ensure_token.js",
    "conversation_final_event.js",
    "conversation_activity.js",
    "conversation_snapshot.js",
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


def test_browser_script_template_json_encodes_values() -> None:
    conversation_id = 'conversation-"quoted"\nline\\slash'
    script = render_browser_script(
        "conversation_final_event.js",
        CONVERSATION_ID=conversation_id,
    )

    assert "__CONVERSATION_ID__" not in script
    assert f"encodeURIComponent({json.dumps(conversation_id)})" in script
