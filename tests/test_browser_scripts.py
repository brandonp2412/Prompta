from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

import pytest

from prompta.browser_script_loader import load_browser_script

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
SCRIPT_ROOT = SOURCE_ROOT / "browser_scripts"


def test_inline_browser_expressions_are_valid_javascript() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in ast.walk(tree):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr in {"eval", "evaluate"}
                and call.args
            ):
                continue
            source = call.args[0]
            if isinstance(source, ast.Constant) and isinstance(source.value, str):
                result = subprocess.run(
                    [node, "--check"],
                    input=f"({source.value});",
                    capture_output=True,
                    text=True,
                )
                assert result.returncode == 0, (
                    f"{path.relative_to(ROOT)}:{call.lineno}: {result.stderr}"
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


def test_composer_focus_contract() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    subprocess.run(
        [node, "--test", "tests/composer_focus.test.cjs"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_browser_script_loader_reads_packaged_assets() -> None:
    for script_path in SCRIPT_ROOT.glob("*.js"):
        assert load_browser_script(script_path.name)


def test_browser_script_loader_refreshes_after_asset_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prompta import browser_script_loader

    monkeypatch.setattr(browser_script_loader, "_SCRIPT_ROOT", tmp_path)
    path = tmp_path / "observer.js"
    path.write_text("old")
    assert browser_script_loader.load_browser_script("observer.js") == "old"
    path.write_text("new longer script")
    assert browser_script_loader.load_browser_script("observer.js") == "new longer script"


def test_browser_script_loader_rejects_nested_paths() -> None:
    with pytest.raises(ValueError, match="Invalid browser script name"):
        load_browser_script("../conversation_snapshot.js")


def test_transcript_scripts_are_removed() -> None:
    removed = {
        "conversation_snapshot.js",
        "conversation_activity.js",
        "conversation_final_event.js",
        "message_discovery.js",
        "react_tool_messages.js",
        "transcript_browser_engine.js",
        "last_user_text.js",
    }
    assert removed.isdisjoint({path.name for path in SCRIPT_ROOT.glob("*.js")})
