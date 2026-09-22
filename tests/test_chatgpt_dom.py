import shutil
import subprocess

import pytest

from prompta.chatgpt_dom import (
    COMPOSER_SELECTORS,
    FILE_INPUT_SELECTORS,
    MARKDOWN_SELECTORS,
    SEND_BUTTON_SELECTORS,
    STOP_BUTTON_SELECTORS,
    TURN_SELECTORS,
)
from prompta.conversation_snapshot import CONVERSATION_SNAPSHOT_SCRIPT


def test_selector_contract_prioritizes_current_semantic_composer() -> None:
    assert COMPOSER_SELECTORS[0] == 'textarea[name="prompt-textarea"]'
    assert "[data-composer-surface] textarea" in COMPOSER_SELECTORS
    assert 'form[data-type="unified-composer"] textarea' in COMPOSER_SELECTORS
    assert 'main textarea[aria-label*="Chat" i]' in COMPOSER_SELECTORS
    assert 'main textarea[placeholder*="Ask" i]' in COMPOSER_SELECTORS


def test_selector_contract_keeps_semantic_action_and_attachment_fallbacks() -> None:
    assert SEND_BUTTON_SELECTORS[:3] == (
        '[data-testid="send-button"]',
        "#composer-submit-button",
        'button[aria-label="Send prompt"]',
    )
    assert 'button[type="submit"]' in SEND_BUTTON_SELECTORS
    assert '[data-testid="stop-button"]' in STOP_BUTTON_SELECTORS
    assert 'button[aria-label*="stop" i]' in STOP_BUTTON_SELECTORS
    assert FILE_INPUT_SELECTORS[:2] == (
        'form[data-type="unified-composer"] input[type="file"]',
        '[data-composer-surface] input[type="file"]',
    )


def test_selector_contract_has_structural_message_fallbacks() -> None:
    assert '[data-testid^="conversation-turn-"]' in TURN_SELECTORS
    assert ".agent-turn" in TURN_SELECTORS
    assert "article" in TURN_SELECTORS
    assert "[data-message-id]" not in TURN_SELECTORS
    assert "[data-message-uuid]" not in TURN_SELECTORS
    assert '[class*="markdown"]' in MARKDOWN_SELECTORS


def test_snapshot_has_page_level_react_fallback() -> None:
    assert "const pageReactRoot=document.querySelector('main')||document.body;" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "const pageReactMessages=pageReactRoot?reactMessages(pageReactRoot):[];" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "if(!entries.length&&pageReactMessages.length)" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "name.startsWith('__reactFiber$')" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "name.startsWith('__reactContainer$')" in CONVERSATION_SNAPSHOT_SCRIPT


def test_snapshot_keeps_javascript_newline_escapes_literal() -> None:
    assert "parts.join('\\n')" in CONVERSATION_SNAPSHOT_SCRIPT
    assert ".join('\\n\\n').trim()" in CONVERSATION_SNAPSHOT_SCRIPT


def test_snapshot_script_parses_as_javascript(tmp_path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    script_path = tmp_path / "conversation_snapshot.js"
    script_path.write_text(CONVERSATION_SNAPSHOT_SCRIPT)
    subprocess.run(
        [node, "--check", str(script_path)],
        check=True,
        capture_output=True,
        text=True,
    )
