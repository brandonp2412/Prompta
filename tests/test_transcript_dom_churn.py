from __future__ import annotations

import json
import re
import shutil

import pytest

from prompta.browser_script_loader import render_browser_script
from prompta.chatgpt_dom import (
    ASSISTANT_MESSAGE_SELECTOR,
    MESSAGE_ROLE_SELECTOR,
    PROSE_BLOCK_SELECTORS,
    SEMANTIC_TURN_SELECTORS,
    STREAMING_SELECTORS,
)
from prompta.conversation_snapshot import CONVERSATION_SNAPSHOT_SCRIPT
from prompta.transcript_browser_engine import TRANSCRIPT_BROWSER_ENGINE_SCRIPT


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
                 data-chatgpt-search-message-ids="a-current a-current" style="width:0;height:120px">
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


def test_content_search_unit_attribute_rename_preserves_turns(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-content-search-unit-key="fallback-turn-0:1:user"
                 data-chatgpt-search-message-ids="u-content">
              <div data-chatgpt-selection-message-id="u-content">Question after attribute rename</div>
            </div>
            <div data-content-search-unit-key="fallback-turn-0:2:assistant"
                 data-chatgpt-search-message-ids="a-content">
              <div data-chatgpt-selection-message-id="a-content">
                <p>Answer after attribute rename.</p>
              </div>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question after attribute rename"),
        ("assistant", "Answer after attribute rename."),
    ]


def test_unknown_semantic_attribute_namespace_preserves_turns_and_ids(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-transcript-search-unit-key="fallback-turn-0:1:user"
                 data-transcript-search-message-ids="u-future">
              <div data-transcript-selection-message-id="u-future">
                Question after namespace churn
              </div>
            </div>
            <div data-transcript-search-unit-key="fallback-turn-0:2:assistant"
                 data-transcript-search-message-ids="a-future">
              <div data-transcript-selection-message-id="a-future">
                <p>Answer after namespace churn.</p>
              </div>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question after namespace churn"),
        ("assistant", "Answer after namespace churn."),
    ]
    assert [message["id"] for message in snapshot["messages"]] == ["u-future", "a-future"]


def test_latest_assistant_root_uses_structural_role_discovery_after_namespace_churn(
    browser_page,
) -> None:
    browser_page.set_content(
        _conversation(
            """
            <div data-transcript-search-unit-key="fallback-turn-0:1:user">Question</div>
            <section data-turn-shell="future-wrapper">
              <div data-transcript-search-unit-key="fallback-turn-0:2:assistant">
                <p>Answer after namespace churn.</p>
              </div>
            </section>
            """
        )
    )
    latest = browser_page.evaluate(
        "() => {" + TRANSCRIPT_BROWSER_ENGINE_SCRIPT + ";"
        "const root=promptaTranscriptEngine.latestAssistantRoot();"
        "return root?.getAttribute('data-turn-shell')||'';"
        "}"
    )

    assert latest == "future-wrapper"


def test_accessible_turn_heading_recovers_role_when_author_attribute_disappears(
    browser_page,
) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-u1">
              <h5>You said:</h5>
              <div data-message-id="u-heading">Question without author attribute</div>
            </section>
            <section data-testid="conversation-turn-a1">
              <h5>ChatGPT said:</h5>
              <div data-message-id="a-heading"><p>Answer without author attribute.</p></div>
            </section>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question without author attribute"),
        ("assistant", "Answer without author attribute."),
    ]


def test_accessible_headings_recover_heading_only_legacy_articles(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <article>
              <h5>You said:</h5>
              <div>Question in heading-only legacy turn</div>
            </article>
            <article>
              <h5>ChatGPT said:</h5>
              <div><p>Answer in heading-only legacy turn.</p></div>
            </article>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question in heading-only legacy turn"),
        ("assistant", "Answer in heading-only legacy turn."),
    ]


def test_heading_only_turns_survive_semantic_wrapper_and_attribute_removal(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-layout-shell="outer-user">
              <div data-layout-shell="inner-user">
                <h5>You wrote:</h5>
                <div>Question after all turn attributes disappear</div>
              </div>
            </div>
            <div data-layout-shell="outer-assistant">
              <div data-layout-shell="inner-assistant">
                <h5>Assistant responded:</h5>
                <div><p>Answer after all turn attributes disappear.</p></div>
              </div>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question after all turn attributes disappear"),
        ("assistant", "Answer after all turn attributes disappear."),
    ]


def test_single_role_heading_does_not_create_false_turn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div>
              <h5>User</h5>
              <p>This is ordinary page content, not a transcript turn.</p>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == []


def test_heading_fallback_does_not_duplicate_partially_semantic_transcript(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-message-author-role="user" data-message-id="u1">
              <h5>You said:</h5>
              Question with surviving author metadata
            </div>
            <div data-layout-shell="assistant">
              <h5>ChatGPT answered:</h5>
              <p>Answer discovered only from accessible heading.</p>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question with surviving author metadata"),
        ("assistant", "Answer discovered only from accessible heading."),
    ]


def test_unknown_namespace_nested_inside_semantic_turn_wrapper_is_discovered(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-u1">
              <div data-layout-shell="outer">
                <div data-future-message-author-role="user" data-future-message-id="u1">
                  Question after nested namespace churn
                </div>
              </div>
            </section>
            <section data-testid="conversation-turn-a1">
              <div data-layout-shell="outer">
                <div data-future-message-author-role="assistant" data-future-message-id="a1">
                  <p>Answer after nested namespace churn.</p>
                </div>
              </div>
            </section>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question after nested namespace churn"),
        ("assistant", "Answer after nested namespace churn."),
    ]
    assert [message["id"] for message in snapshot["messages"]] == ["u1", "a1"]


def test_mixed_known_and_renamed_role_namespaces_preserve_all_turns(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-message-author-role="user" data-message-id="u-known">Known question</div>
            <div data-message-author-role="assistant" data-message-id="a-known">
              <p>Known answer.</p>
            </div>
            <div data-future-message-author-role="user" data-future-message-id="u-future">
              Question from renamed namespace
            </div>
            <div data-future-message-author-role="assistant" data-future-message-id="a-future">
              <p>Answer from renamed namespace.</p>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Known question"),
        ("assistant", "Known answer."),
        ("user", "Question from renamed namespace"),
        ("assistant", "Answer from renamed namespace."),
    ]
    assert [message["id"] for message in snapshot["messages"]] == [
        "u-known",
        "a-known",
        "u-future",
        "a-future",
    ]


def test_role_aliases_and_search_key_separator_churn_preserve_transcript(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-future-message-author-role="human" data-future-message-id="u-alias">
              Question after role vocabulary churn
            </div>
            <div data-future-search-unit-key="turn/2/model/content"
                 data-future-search-message-ids="a-alias">
              <p>Answer after separator and role vocabulary churn.</p>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question after role vocabulary churn"),
        ("assistant", "Answer after separator and role vocabulary churn."),
    ]
    assert [message["id"] for message in snapshot["messages"]] == ["u-alias", "a-alias"]


def test_aria_heading_roles_recover_transcript_after_heading_tag_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-layout-shell="user">
              <div role="heading" aria-level="5">You said:</div>
              <div>Question after heading tag churn</div>
            </div>
            <div data-layout-shell="assistant">
              <div role="heading" aria-level="5">ChatGPT replied:</div>
              <p>Answer after heading tag churn.</p>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question after heading tag churn"),
        ("assistant", "Answer after heading tag churn."),
    ]


def test_accessible_role_aliases_survive_heading_vocabulary_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-layout-shell="user">
              <h5>Human asked:</h5>
              <div>Question after heading vocabulary churn</div>
            </div>
            <div data-layout-shell="assistant">
              <h5>Model replied:</h5>
              <p>Answer after heading vocabulary churn.</p>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question after heading vocabulary churn"),
        ("assistant", "Answer after heading vocabulary churn."),
    ]


def test_search_unit_role_survives_added_key_segments(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-future-search-unit-key="turn:1:user:content" data-future-search-message-ids="u1">
              Question with extended semantic key
            </div>
            <div data-future-search-unit-key="turn:2:assistant:content" data-future-search-message-ids="a1">
              <p>Answer with extended semantic key.</p>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question with extended semantic key"),
        ("assistant", "Answer with extended semantic key."),
    ]


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


def test_display_contents_turn_wrapper_remains_visible(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-u1">
              <div data-message-author-role="user" data-message-id="u1">Question</div>
            </section>
            <section data-testid="conversation-turn-a1" data-runtime-streaming="active" style="display:contents">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Answer inside a boxless semantic wrapper.</p>
              </div>
            </section>
            """
        )
    )
    script = render_browser_script(
        "conversation_activity.js",
        stop_selector="button[aria-label*=stop i]",
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    snapshot = _snapshot(browser_page, browser_page.content())
    activity = json.loads(browser_page.evaluate(script))

    assert _semantic_messages(snapshot) == [
        ("user", "Question"),
        ("assistant", "Answer inside a boxless semantic wrapper."),
    ]
    assert snapshot["streaming"] is True
    assert activity["streaming"] is True
    assert activity["complete"] is False


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


def test_unknown_tool_attribute_namespace_preserves_tool_capture(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Before renamed tool metadata.</p>
                <div data-runtime-tool-call-id="tool-9" data-runtime-tool-name="Glass">
                  <span>execute_python</span>
                  <span>completed</span>
                </div>
                <p>After renamed tool metadata.</p>
              </div>
            </section>
            """
        ),
    )

    content = snapshot["messages"][0]["content"]
    assert "tool:Glass" in content
    assert "execute_python" in content
    assert content.index("Before renamed tool metadata.") < content.index("tool:Glass")
    assert content.index("tool:Glass") < content.index("After renamed tool metadata.")


def test_completion_action_discovery_survives_action_id_churn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Complete answer.</p>
                <div>
                  <button data-testid="feedback-turn-action-button" aria-label="Helpful">+</button>
                </div>
              </div>
            </section>
            """
        )
    )
    script = render_browser_script(
        "conversation_activity.js",
        stop_selector="button[aria-label*=stop i]",
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(script))

    assert activity["streaming"] is False
    assert activity["complete"] is True


def test_tool_trigger_discovery_survives_label_and_wrapper_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Before tool control.</p>
                <section class="totally-new-tool-layout">
                  <button aria-label="Show tool details">Glass</button>
                  <span>execute_python</span>
                  <span>completed</span>
                </section>
                <p>After tool control.</p>
              </div>
            </section>
            """
        ),
    )

    content = snapshot["messages"][0]["content"]
    assert "```tool:Glass" in content
    assert "execute_python" in content
    assert "completed" in content
    assert content.index("Before tool control.") < content.index("```tool:Glass")
    assert content.index("```tool:Glass") < content.index("After tool control.")


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


def test_streaming_detection_survives_semantic_attribute_namespace_churn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1" data-runtime-streaming="active">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Still generating.</p>
              </div>
            </section>
            """
        )
    )
    script = render_browser_script(
        "conversation_activity.js",
        stop_selector="button[aria-label*=stop i]",
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(script))
    snapshot = _snapshot(browser_page, browser_page.content())

    assert activity["streaming"] is True
    assert activity["complete"] is False
    assert snapshot["streaming"] is True


def test_streaming_detection_survives_aria_busy_markup_churn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1" aria-busy="true">
                <p>Still generating after markup churn.</p>
              </div>
            </section>
            """
        )
    )
    script = render_browser_script(
        "conversation_activity.js",
        stop_selector="button[aria-label*=stop i]",
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(script))
    snapshot = _snapshot(browser_page, browser_page.content())

    assert activity["streaming"] is True
    assert activity["complete"] is False
    assert snapshot["streaming"] is True


def test_mixed_tool_attribute_namespaces_preserve_all_tool_rows(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Before tools.</p>
                <div data-tool-call-id="known-1" data-tool-name="Known Tool">
                  <button aria-label="Show tool details">Known Tool</button>
                </div>
                <div data-transcript-tool-call-id="future-2" data-transcript-tool-name="Future Tool">
                  <button aria-label="Show tool details">Future Tool</button>
                </div>
                <p>After tools.</p>
              </div>
            </section>
            """
        ),
    )

    assistant = next(message for message in snapshot["messages"] if message["role"] == "assistant")
    content = assistant["content"]
    assert "```tool:Known Tool" in content
    assert "```tool:Future Tool" in content
    assert "Before tools." in content
    assert "After tools." in content


def test_tool_trigger_uses_renamed_semantic_tool_ancestor(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <section data-transcript-tool-call-id="future-3" data-transcript-tool-name="Glass">
                  <div>
                    <button aria-label="Show tool details">Glass</button>
                  </div>
                </section>
                <p>Done.</p>
              </div>
            </section>
            """
        ),
    )

    assistant = next(message for message in snapshot["messages"] if message["role"] == "assistant")
    assert "```tool:Glass" in assistant["content"]
    assert "Done." in assistant["content"]


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


def test_stop_control_detection_survives_semantic_markup_churn(browser_page) -> None:
    html = _conversation(
        """
        <section data-testid="conversation-turn-a1">
          <div data-message-author-role="assistant" data-message-id="a1">
            <p>Still generating after stop-control markup churn.</p>
          </div>
        </section>
        <div role="button" data-runtime-action="cancel-generation" style="width:32px;height:32px">
          <span>Cancel generation</span>
        </div>
        """
    )
    browser_page.set_content(html)
    activity_script = render_browser_script(
        "conversation_activity.js",
        stop_selector='button[aria-label="Stop answering"]',
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(activity_script))
    snapshot = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))

    assert activity["streaming"] is True
    assert activity["complete"] is False
    assert snapshot["streaming"] is True
