from __future__ import annotations

from prompta.browser_script_loader import load_browser_script, render_browser_script


def test_loads_standalone_browser_script() -> None:
    script = load_browser_script("conversation_snapshot.js")

    assert script.startswith("JSON.stringify((()=>{")
    assert "__MESSAGE_ROLE_SELECTOR__" in script


def test_renders_browser_script_values_as_json() -> None:
    script = render_browser_script(
        "react_tool_messages.js",
        ASSISTANT_SELECTOR="assistant-selector",
        MESSAGE_ROLE_SELECTOR="role-selector",
        TURN_SELECTOR="turn-selector",
    )

    assert "__ASSISTANT_SELECTOR__" not in script
    assert 'const assistantSelector="assistant-selector";' in script
    assert 'const messageRoleSelector="role-selector";' in script
    assert 'const turnSelector="turn-selector";' in script
