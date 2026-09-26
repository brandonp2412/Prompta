from __future__ import annotations

import ast
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from prompta.browser_script_loader import load_browser_script, render_browser_script

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
SCRIPT_ROOT = SOURCE_ROOT / "browser_scripts"

_BROWSER_JS_MARKERS = (
    "=>",
    "document.",
    "window.",
    "navigator.",
    "querySelector",
    "JSON.stringify(",
    "fetch(",
    "getComputedStyle",
    "new Request(",
    "encodeURIComponent(",
)


def _literal_text(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
            else "{...}"
            for part in node.values
        )
    return ""


def test_production_python_contains_no_inline_browser_javascript() -> None:
    offenders: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            text = _literal_text(node)
            if text and any(marker in text for marker in _BROWSER_JS_MARKERS):
                offenders.append(f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}")
                continue
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"eval", "evaluate"}
                and node.args
                and _literal_text(node.args[0])
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}")
                continue
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "expression"
                        and _literal_text(value)
                    ):
                        offenders.append(f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}")

    assert offenders == [], (
        "Inline browser JavaScript belongs in src/browser_scripts: " + ", ".join(offenders)
    )


@pytest.mark.parametrize(
    "script_path",
    sorted(SCRIPT_ROOT.glob("*.js")),
    ids=lambda path: path.name,
)
def test_browser_script_is_valid_javascript(script_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")

    subprocess.run(
        [node, "--check", str(script_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_send_probe_protocol_and_cleanup() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    subprocess.run(
        [node, "--test", "tests/send_probe.test.cjs"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_browser_script_loader_reads_packaged_assets() -> None:
    for script_path in SCRIPT_ROOT.glob("*.js"):
        assert load_browser_script(script_path.name)


def test_browser_script_template_json_encodes_values() -> None:
    conversation_id = 'conversation-"quoted"\nline\\slash'
    script = render_browser_script(
        "conversation_final_event.js",
        conversation_id=conversation_id,
    )

    assert "__CONVERSATION_ID__" not in script
    assert f"encodeURIComponent({json.dumps(conversation_id)})" in script


def test_browser_script_template_rejects_unknown_marker() -> None:
    with pytest.raises(ValueError, match="has no template marker"):
        render_browser_script("ensure_token.js", missing="value")


def test_browser_script_loader_rejects_nested_paths() -> None:
    with pytest.raises(ValueError, match="Invalid browser script name"):
        load_browser_script("../conversation_snapshot.js")
