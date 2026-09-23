from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from prompta.chatgpt_dom import (
    MESSAGE_ROLE_SELECTOR,
    STREAMING_SELECTORS,
    TURN_SELECTORS,
)
from prompta.conversation_snapshot import (
    CONVERSATION_SNAPSHOT_SCRIPT,
    parse_conversation_snapshot,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "transcript_extraction"
CASES = json.loads((FIXTURE_DIR / "manifest.json").read_text())


@pytest.fixture(scope="module")
def chromium_browser():
    executable = shutil.which("chromium") or shutil.which("brave")
    if executable is None:
        pytest.skip("A Chromium-compatible browser is required for transcript fixture tests")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        try:
            yield browser
        finally:
            browser.close()


def test_primary_contract_prefers_role_and_stable_data_attributes() -> None:
    assert MESSAGE_ROLE_SELECTOR == "[data-message-author-role]"
    assert TURN_SELECTORS[0] == '[data-testid^="conversation-turn-"]'
    assert TURN_SELECTORS.index(".agent-turn") > 0
    assert TURN_SELECTORS.index("article") > 0
    assert STREAMING_SELECTORS[:2] == (
        '[data-streaming="active"]',
        '[data-is-streaming="true"]',
    )

    role_discovery = CONVERSATION_SNAPSHOT_SCRIPT.index(
        "const roleNodes=[...document.querySelectorAll(messageRoleSelector)]"
    )
    react_page_fallback = CONVERSATION_SNAPSHOT_SCRIPT.index(
        "const pageReactRoot=document.querySelector('main')||document.body;"
    )
    assert role_discovery < react_page_fallback
    assert "const toolSelector='[data-tool-call-id],[data-tool-name]';" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "reactOrdered&&reactHasVisibleText&&reactKeepsVisibleText" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_production_snapshot_matches_fixture_contract(chromium_browser, case: dict) -> None:
    html = (FIXTURE_DIR / case["file"]).read_text()
    if case["class_free"]:
        assert " class=" not in html

    page = chromium_browser.new_page()
    try:
        page.set_content(html)
        raw = page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT)
    finally:
        page.close()

    snapshot = parse_conversation_snapshot(raw)
    messages = snapshot["messages"]

    assert [message["role"] for message in messages] == case["roles"]
    assert [message["id"] for message in messages] == case["ids"]
    assert [message["ordinal"] for message in messages] == list(range(len(messages)))
    assert snapshot["streaming"] is case["streaming"]

    expected_contents = case.get("contents")
    if expected_contents is not None:
        assert [message["content"] for message in messages] == expected_contents

    content_contains = case.get("content_contains")
    if content_contains is not None:
        assert len(content_contains) == len(messages)
        for message, expected in zip(messages, content_contains, strict=True):
            assert expected in message["content"]

    ordered_fragments = case.get("contains_in_order") or []
    if ordered_fragments:
        assistant = next(
            message["content"] for message in reversed(messages) if message["role"] == "assistant"
        )
        positions = [assistant.index(fragment) for fragment in ordered_fragments]
        assert positions == sorted(positions)

    assert [event["id"] for event in snapshot["source_events"]] == case["source_event_ids"]


def test_fixture_baseline_labels_legacy_class_dependency() -> None:
    semantic = (FIXTURE_DIR / "semantic_data.html").read_text()
    react = (FIXTURE_DIR / "react_fallback.html").read_text()
    legacy = (FIXTURE_DIR / "legacy_tool_order.html").read_text()

    assert " class=" not in semantic
    assert " class=" not in react
    assert 'class="markdown"' in legacy
    assert "data-tool-call-id" in legacy
    assert "data-tool-name" in legacy
