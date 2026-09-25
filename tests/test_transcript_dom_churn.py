from __future__ import annotations

import json
import re
import shutil

import pytest

from prompta.chatgpt_dom import (
    ASSISTANT_MESSAGE_SELECTOR,
    MESSAGE_ROLE_SELECTOR,
    PROSE_BLOCK_SELECTORS,
    SEMANTIC_TURN_SELECTORS,
    STREAMING_SELECTORS,
)
from prompta.conversation_snapshot import CONVERSATION_SNAPSHOT_SCRIPT


@pytest.fixture(scope="module")
def browser_page():
    executable = shutil.which("chromium") or shutil.which("brave")
    if executable is None:
        pytest.skip("A Chromium-compatible browser is unavailable")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        try:
            page = browser.new_page()
            yield page
        finally:
            browser.close()


def _snapshot(browser_page, html: str) -> dict:
    browser_page.set_content(html)
    return json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))


def _semantic_messages(snapshot: dict) -> list[tuple[str, str]]:
    return [
        (str(message.get("role", "")), str(message.get("content", "")))
        for message in snapshot.get("messages", [])
    ]


def _conversation(body: str) -> str:
    return f"<main>{body}</main>"


def test_current_search_unit_contract_preserves_user_and_assistant_turns(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-chatgpt-search-unit-key="fallback-turn-0:1:user"
                 data-chatgpt-search-message-ids="u-current">
              <div data-chatgpt-selection-message-id="u-current">
                Reply with exactly CURRENT_TOKEN and nothing else.
              </div>
            </div>
            <div data-chatgpt-search-unit-key="fallback-turn-0:2:assistant"
                 data-chatgpt-search-message-ids="a-current a-current">
              <div data-chatgpt-selection-message-id="a-current">
                <div data-markdown-text-style="assistant-message">
                  <p>CURRENT_TOKEN</p>
                </div>
              </div>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Reply with exactly CURRENT_TOKEN and nothing else."),
        ("assistant", "CURRENT_TOKEN"),
    ]
    assert [message["id"] for message in snapshot["messages"]] == ["u-current", "a-current"]


def test_wrapper_insertion_and_removal_preserve_semantic_transcript(browser_page) -> None:
    flat = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-u1">
              <div data-message-author-role="user" data-message-id="u1">Question</div>
            </section>
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Stable answer.</p>
              </div>
            </section>
            """
        ),
    )
    wrapped = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-u1">
              <div data-layout-shell="outer">
                <div data-layout-shell="inner">
                  <div data-message-author-role="user" data-message-id="u1">Question</div>
                </div>
              </div>
            </section>
            <section data-testid="conversation-turn-a1">
              <div data-layout-shell="outer">
                <div data-layout-shell="inner">
                  <div data-message-author-role="assistant" data-message-id="a1">
                    <div><p>Stable answer.</p></div>
                  </div>
                </div>
              </div>
            </section>
            """
        ),
    )

    assert _semantic_messages(wrapped) == _semantic_messages(flat)
    assert _semantic_messages(flat) == [
        ("user", "Question"),
        ("assistant", "Stable answer."),
    ]


@pytest.mark.parametrize(
    ("prose_class", "tool_class"),
    [
        ("old-copy-layout", "old-tool-layout"),
        ("new-copy-layout-x91", "new-tool-layout-z17"),
    ],
)
def test_class_renames_do_not_change_prose_or_tool_semantics(
    browser_page,
    prose_class: str,
    tool_class: str,
) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            f"""
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <div class="{prose_class}"><p>Before tool.</p></div>
                <div class="{tool_class}" data-tool-call-id="call-1" data-tool-name="Glass Serena">
                  <span>Read symbol</span>
                </div>
                <div class="{prose_class}"><p>After tool.</p></div>
              </div>
            </section>
            """
        ),
    )

    assert len(snapshot["messages"]) == 1
    content = snapshot["messages"][0]["content"]
    assert snapshot["messages"][0]["role"] == "assistant"
    assert content.index("Before tool.") < content.index(" ```tool:Glass Serena".strip())
    assert "Read symbol" in content
    assert content.index(" ```tool:Glass Serena".strip()) < content.index("After tool.")


@pytest.mark.parametrize("controls_first", [True, False])
def test_reordered_non_content_controls_do_not_change_message_text(
    browser_page,
    controls_first: bool,
) -> None:
    controls = """
      <div data-controls>
        <button aria-label="Copy">Copy</button>
        <button aria-label="Read aloud">Read aloud</button>
        <button aria-label="Share">Share</button>
      </div>
    """
    prose = "<div><p>Only this answer is content.</p></div>"
    body = controls + prose if controls_first else prose + controls
    snapshot = _snapshot(
        browser_page,
        _conversation(
            f"""
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                {body}
              </div>
            </section>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("assistant", "Only this answer is content."),
    ]


def test_hidden_duplicate_turn_does_not_replace_visible_message(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-u1">
              <div data-message-author-role="user" data-message-id="u1">Question</div>
            </section>
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Visible answer.</p>
              </div>
            </section>
            <section data-testid="conversation-turn-a1-shadow" style="display:none">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Hidden stale answer that must never win over the visible transcript copy.</p>
              </div>
            </section>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question"),
        ("assistant", "Visible answer."),
    ]


def test_missing_message_ids_do_not_drop_or_duplicate_turns(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-layout="turn">
              <div data-message-author-role="user">Question without id</div>
            </div>
            <div data-layout="turn">
              <div data-message-author-role="assistant">
                <p>Answer without id.</p>
              </div>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question without id"),
        ("assistant", "Answer without id."),
    ]


def test_streaming_transition_updates_content_and_completion_state(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1" data-is-streaming="true">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p id="answer">Partial answer</p>
              </div>
            </section>
            """
        )
    )

    partial = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))
    browser_page.evaluate(
        """() => {
          const turn = document.querySelector('[data-testid="conversation-turn-a1"]');
          turn.removeAttribute('data-is-streaming');
          document.querySelector('#answer').textContent = 'Complete answer.';
        }"""
    )
    complete = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))

    assert partial["streaming"] is True
    assert _semantic_messages(partial) == [("assistant", "Partial answer")]
    assert complete["streaming"] is False
    assert _semantic_messages(complete) == [("assistant", "Complete answer.")]


def test_semantic_tool_rows_survive_wrapper_and_class_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <div class="layout-before"><p>Inspecting.</p></div>
                <div class="arbitrary-wrapper">
                  <div class="arbitrary-tool-class" data-tool-call-id="tool-7" data-tool-name="Glass">
                    <span>execute_python</span>
                    <span>status completed</span>
                  </div>
                </div>
                <div class="layout-after"><p>Done.</p></div>
              </div>
            </section>
            """
        ),
    )

    content = snapshot["messages"][0]["content"]
    assert "```tool:Glass" in content
    assert "execute_python" in content
    assert "status completed" in content
    assert content.index("Inspecting.") < content.index("```tool:Glass") < content.index("Done.")


def test_partial_reasoning_activity_is_retained_without_private_dom_shape(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-phase="reasoning">Searching repository</div>
              <div data-phase="activity">Reading relevant tests</div>
            </section>
            """
        ),
    )

    assert len(snapshot["messages"]) == 1
    message = snapshot["messages"][0]
    assert message["role"] == "assistant"
    assert "Searching repository" in message["content"]
    assert "Reading relevant tests" in message["content"]


def _is_styling_class_selector(selector: str) -> bool:
    return "[class" in selector or bool(re.search(r"(^|[\s>+~,])\.[A-Za-z_-]", selector))


def test_primary_transcript_selectors_do_not_depend_on_styling_classes() -> None:
    primary_selectors = (
        MESSAGE_ROLE_SELECTOR,
        ASSISTANT_MESSAGE_SELECTOR,
        *SEMANTIC_TURN_SELECTORS,
        *PROSE_BLOCK_SELECTORS,
        *STREAMING_SELECTORS,
    )

    offenders = [selector for selector in primary_selectors if _is_styling_class_selector(selector)]

    assert offenders == []
