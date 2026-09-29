from __future__ import annotations

import json
import re
import shutil

import pytest

from prompta.browser_script_loader import load_browser_script, render_browser_script
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


def _shadow_snapshot(browser_page, html: str) -> dict:
    browser_page.set_content('<div id="shadow-host"></div>')
    browser_page.evaluate(
        """(html) => {
          const host = document.getElementById('shadow-host');
          const root = host.attachShadow({mode: 'open'});
          root.innerHTML = html;
        }""",
        html,
    )
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


def test_role_churned_controls_do_not_leak_into_transcript_text(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-u1">
              <div data-message-author-role="user" data-message-id="u1">
                <p>Prompt body.</p>
                <summary>Show more</summary>
                <div tabindex="0" aria-label="Edit message">Edit</div>
                <div role="switch">Temporary action</div>
                <input type="button" value="Retry">
              </div>
            </section>
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <div data-markdown-text-style="assistant-message">
                  <p>Answer body.</p>
                  <div role="menuitem">Copy response</div>
                  <div role="option">Read aloud</div>
                  <div role="combobox">Model picker</div>
                  <select><option>Internal UI choice</option></select>
                </div>
              </div>
            </section>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Prompt body."),
        ("assistant", "Answer body."),
    ]


def test_focusable_message_content_is_not_mistaken_for_ui_control(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-u1">
              <div data-message-author-role="user" data-message-id="u1">
                <div tabindex="0" aria-label="User message">
                  Question inside focusable message content
                </div>
              </div>
            </section>
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <div tabindex="0" aria-label="Assistant response">
                  Answer inside focusable message content.
                </div>
              </div>
            </section>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question inside focusable message content"),
        ("assistant", "Answer inside focusable message content."),
    ]


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


def test_generic_author_role_attribute_rename_preserves_turns(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-author-role="user" data-message-id="u-author">
              Question after author attribute rename
            </section>
            <section data-author-role="assistant" data-message-id="a-author">
              <p>Answer after author attribute rename.</p>
            </section>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question after author attribute rename"),
        ("assistant", "Answer after author attribute rename."),
    ]


def test_speaker_role_attribute_rename_preserves_turns(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-transcript-speaker-role="human" data-message-id="u-speaker">
              Question after speaker attribute rename
            </section>
            <section data-transcript-speaker-role="model" data-message-id="a-speaker">
              <p>Answer after speaker attribute rename.</p>
            </section>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question after speaker attribute rename"),
        ("assistant", "Answer after speaker attribute rename."),
    ]


def test_message_role_attribute_rename_preserves_turns(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-transcript-message-role="user-message" data-message-id="u-message-role">
              Question after message role attribute rename
            </section>
            <section data-transcript-message-role="assistant-response" data-message-id="a-message-role">
              <p>Answer after message role attribute rename.</p>
            </section>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question after message role attribute rename"),
        ("assistant", "Answer after message role attribute rename."),
    ]


def test_accessible_message_labels_preserve_turns_without_data_roles(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <article aria-label="User message" data-message-id="u-aria">
              Question discovered from accessible label
            </article>
            <article aria-label="Assistant response" data-message-id="a-aria">
              <p>Answer discovered from accessible label.</p>
            </article>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question discovered from accessible label"),
        ("assistant", "Answer discovered from accessible label."),
    ]


def test_aria_labelledby_preserves_turns_without_data_roles(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <span id="user-turn-label">User message</span>
            <article aria-labelledby="user-turn-label" data-message-id="u-labelled">
              Question discovered from labelled-by reference
            </article>
            <span id="assistant-turn-label">Assistant response</span>
            <article aria-labelledby="assistant-turn-label" data-message-id="a-labelled">
              <p>Answer discovered from labelled-by reference.</p>
            </article>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question discovered from labelled-by reference"),
        ("assistant", "Answer discovered from labelled-by reference."),
    ]


def test_aria_describedby_preserves_turns_without_data_roles(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <span id="user-turn-description">User message</span>
            <article aria-describedby="user-turn-description" data-message-id="u-described">
              Question discovered from described-by reference
            </article>
            <span id="assistant-turn-description">Assistant response</span>
            <article aria-describedby="assistant-turn-description" data-message-id="a-described">
              <p>Answer discovered from described-by reference.</p>
            </article>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question discovered from described-by reference"),
        ("assistant", "Answer discovered from described-by reference."),
    ]


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


def test_latest_assistant_root_ignores_hidden_duplicate_turn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-turn-shell="visible-turn">
              <div data-message-author-role="assistant" data-message-id="a-visible">
                <p>Visible answer.</p>
              </div>
            </section>
            <section data-turn-shell="hidden-turn" style="display:none">
              <div data-message-author-role="assistant" data-message-id="a-hidden">
                <p>Hidden stale answer.</p>
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

    assert latest == "visible-turn"


def test_latest_assistant_root_ignores_aria_hidden_duplicate_turn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-turn-shell="visible-turn">
              <div data-message-author-role="assistant" data-message-id="a-visible">
                <p>Visible answer.</p>
              </div>
            </section>
            <section data-turn-shell="hidden-turn" aria-hidden="true">
              <div data-message-author-role="assistant" data-message-id="a-hidden">
                <p>Accessibility-hidden stale answer.</p>
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

    assert latest == "visible-turn"


def test_latest_assistant_root_uses_semantic_transcript_landmark_when_assistant_is_not_in_dom(
    browser_page,
) -> None:
    browser_page.set_content(
        """
        <main><p>Unrelated shell content.</p></main>
        <div role="feed">
          <section data-sender="human" data-turn-id="u-pending">Pending question.</section>
        </div>
        """
    )
    latest = browser_page.evaluate(
        "() => {" + TRANSCRIPT_BROWSER_ENGINE_SCRIPT + ";"
        "const root=promptaTranscriptEngine.latestAssistantRoot();"
        "return root?.getAttribute('role')||root?.tagName||'';"
        "}"
    )

    assert latest == "feed"


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


def test_interleaved_known_and_renamed_role_namespaces_keep_dom_order(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-message-author-role="user" data-message-id="u1">First question</div>
            <div data-message-author-role="assistant" data-message-id="a1"><p>First answer.</p></div>
            <div data-future-message-author-role="user" data-future-message-id="u2">Second question</div>
            <div data-future-message-author-role="assistant" data-future-message-id="a2"><p>Second answer.</p></div>
            <div data-message-author-role="user" data-message-id="u3">Third question</div>
            <div data-message-author-role="assistant" data-message-id="a3"><p>Third answer.</p></div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "First question"),
        ("assistant", "First answer."),
        ("user", "Second question"),
        ("assistant", "Second answer."),
        ("user", "Third question"),
        ("assistant", "Third answer."),
    ]
    assert [message["id"] for message in snapshot["messages"]] == [
        "u1",
        "a1",
        "u2",
        "a2",
        "u3",
        "a3",
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


def test_aria_level_recovers_transcript_after_heading_role_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <div data-layout-shell="user">
              <div aria-level="5">You said:</div>
              <div>Question after heading role churn</div>
            </div>
            <div data-layout-shell="assistant">
              <div aria-level="5">ChatGPT replied:</div>
              <p>Answer after heading role churn.</p>
            </div>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("user", "Question after heading role churn"),
        ("assistant", "Answer after heading role churn."),
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


def test_nested_structural_wrapper_preserves_prose_around_tool(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <div data-layout-shell="new-wrapper-shape">
                  <div data-copy-row="before">Before <strong>tool</strong>.</div>
                  <section data-runtime-tool-call-id="tool-nested" data-runtime-tool-name="Glass">
                    <span>execute_python</span>
                    <span>completed</span>
                  </section>
                  <div data-copy-row="after">After tool.</div>
                </div>
              </div>
            </section>
            """
        ),
    )

    content = snapshot["messages"][0]["content"]
    assert content.index("Before **tool**.") < content.index("```tool:Glass")
    assert content.index("```tool:Glass") < content.index("After tool.")
    assert "execute_python" in content
    assert "completed" in content


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


def test_hidden_duplicate_turn_does_not_override_visible_completion_state(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-u1">
              <div data-message-author-role="user" data-message-id="u1">Question</div>
            </section>
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Visible completed answer.</p>
                <button aria-label="Copy">Copy</button>
              </div>
            </section>
            <section data-testid="conversation-turn-a1-shadow" style="display:none" aria-busy="true">
              <div data-message-author-role="assistant" data-message-id="a1-shadow">
                <p>Hidden stale streaming answer.</p>
              </div>
            </section>
            """
        )
    )
    activity_script = render_browser_script(
        "conversation_activity.js",
        stop_selector='button[aria-label="Stop answering"]',
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(activity_script))
    snapshot = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))

    assert activity["streaming"] is False
    assert activity["complete"] is True
    assert snapshot["streaming"] is False


def test_hidden_streaming_marker_inside_visible_turn_is_ignored(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Visible completed answer.</p>
                <span aria-busy="true" style="display:none">Hidden stale progress marker</span>
                <button aria-label="Copy">Copy</button>
              </div>
            </section>
            """
        )
    )
    activity_script = render_browser_script(
        "conversation_activity.js",
        stop_selector='button[aria-label="Stop answering"]',
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(activity_script))
    snapshot = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))

    assert activity["streaming"] is False
    assert activity["complete"] is True
    assert snapshot["streaming"] is False


def test_aria_hidden_streaming_marker_inside_visible_turn_is_ignored(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Visible completed answer.</p>
                <span aria-busy="true" aria-hidden="true">Accessibility-hidden stale progress</span>
                <button aria-label="Copy">Copy</button>
              </div>
            </section>
            """
        )
    )
    activity_script = render_browser_script(
        "conversation_activity.js",
        stop_selector='button[aria-label="Stop answering"]',
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(activity_script))
    snapshot = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))

    assert activity["streaming"] is False
    assert activity["complete"] is True
    assert snapshot["streaming"] is False


def test_hidden_completion_action_does_not_finish_active_turn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Answer still lacks an observable completion signal.</p>
                <button aria-label="Copy" style="display:none">Copy</button>
              </div>
            </section>
            """
        )
    )
    activity_script = render_browser_script(
        "conversation_activity.js",
        stop_selector='button[aria-label="Stop answering"]',
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(activity_script))

    assert activity["streaming"] is False
    assert activity["complete"] is False


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


def test_code_language_metadata_survives_css_class_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <pre data-syntax-language="python"><code class="syntax-tokenized">print('ok')</code></pre>
              </div>
            </section>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        ("assistant", "```python\nprint('ok')\n```"),
    ]


def test_code_language_metadata_survives_attribute_separator_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <pre data.code.language="python"><code>print('dot')</code></pre>
              </div>
            </section>
            """
        ),
    )

    assert _semantic_messages(snapshot) == [
        (
            "assistant",
            chr(96) * 3 + "python" + chr(10) + "print('dot')" + chr(10) + chr(96) * 3,
        ),
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


def test_completion_action_discovery_uses_turn_key_container_for_actions(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <div data-turn-key="turn-a1">
              <div data-content-search-turn-key="fallback-turn-1">
                <div data-chatgpt-search-unit-key="fallback-turn-1:0:user"
                     data-chatgpt-search-message-ids="u1">
                  <h4>You said:</h4>
                  <p>Question.</p>
                </div>
                <div>
                  <div data-content-search-unit-key="fallback-turn-1:2:assistant"
                       data-chatgpt-search-unit-key="fallback-turn-1:2:assistant"
                       data-chatgpt-search-message-ids="a1 a1">
                    <h4>ChatGPT said:</h4>
                    <p>Complete answer.</p>
                  </div>
                </div>
                <div>
                  <button aria-label="Copy">Copy</button>
                  <button aria-label="Regenerate response">Regenerate</button>
                </div>
              </div>
            </div>
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
    assert activity["turn_ended"] is None


def test_completion_action_discovery_survives_attribute_namespace_churn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Complete answer.</p>
                <div>
                  <button data-transcript-turn-action="feedback" aria-label="Helpful">+</button>
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


def test_control_discovery_survives_interactive_element_churn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Complete answer.</p>
                <div role="menuitem" tabindex="0" aria-label="Copy response">Copy</div>
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


def test_completion_action_discovery_survives_link_semantics_churn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Complete answer.</p>
                <a href="#" aria-label="Copy response">Copy</a>
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


def test_navigational_link_named_copy_is_not_completion_action(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Answer with <a href="https://example.com" aria-label="Copy response">docs</a>.</p>
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
    assert activity["complete"] is False


def test_stop_control_discovery_survives_focusable_control_churn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Still answering.</p>
              </div>
            </section>
            <div tabindex="0" aria-label="Stop responding">Stop</div>
            """
        )
    )
    script = render_browser_script(
        "conversation_activity.js",
        stop_selector="button[aria-label*=stop i]",
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(script))

    assert activity["streaming"] is True
    assert activity["complete"] is False


def test_stop_control_discovery_uses_native_control_value(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Still answering.</p>
              </div>
            </section>
            <input type="button" value="Stop responding">
            """
        )
    )
    script = render_browser_script(
        "conversation_activity.js",
        stop_selector="button[aria-label*=stop i]",
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(script))

    assert activity["streaming"] is True
    assert activity["complete"] is False


def test_stop_control_discovery_uses_native_associated_label(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Still answering.</p>
              </div>
            </section>
            <label for="stop-control">Stop responding</label>
            <input id="stop-control" type="button" value="">
            """
        )
    )
    script = render_browser_script(
        "conversation_activity.js",
        stop_selector="button[aria-label*=stop i]",
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(script))

    assert activity["streaming"] is True
    assert activity["complete"] is False


def test_stop_control_discovery_survives_link_semantics_churn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Still answering.</p>
              </div>
            </section>
            <a href="#" aria-label="Stop responding">Stop</a>
            """
        )
    )
    script = render_browser_script(
        "conversation_activity.js",
        stop_selector="button[aria-label*=stop i]",
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(script))
    snapshot = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))

    assert activity["streaming"] is True
    assert activity["complete"] is False
    assert snapshot["streaming"] is True


def test_tool_trigger_discovery_survives_non_button_control_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Before tool control.</p>
                <section class="totally-new-tool-layout">
                  <summary aria-label="Show tool details">Glass</summary>
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
    assert "tool:Glass" in content
    assert "execute_python" in content
    assert "completed" in content


def test_tool_trigger_discovery_survives_link_semantics_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Before tool control.</p>
                <section class="future-tool-layout">
                  <a href="#" aria-label="Show tool details">Glass</a>
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
    assert "tool:Glass" in content
    assert "execute_python" in content
    assert "completed" in content
    assert content.index("Before tool control.") < content.index("tool:Glass")
    assert content.index("tool:Glass") < content.index("After tool control.")


def test_accessible_content_link_named_tool_details_is_not_promoted_to_tool_block(
    browser_page,
) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Read <a href="https://example.com" aria-label="Show tool details">the docs</a>.</p>
              </div>
            </section>
            """
        ),
    )

    content = snapshot["messages"][0]["content"]
    assert "tool:" not in content
    assert "[the docs](https://example.com)" in content


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


def test_tool_trigger_discovery_survives_nested_semantic_icon_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Before nested tool control.</p>
                <section class="unrelated-wrapper-name">
                  <button><svg data-icon="tool-call"></svg><span>Glass</span></button>
                  <span>execute_python</span>
                  <span>completed</span>
                </section>
                <p>After nested tool control.</p>
              </div>
            </section>
            """
        ),
    )

    content = snapshot["messages"][0]["content"]
    assert "```tool:Glass" in content
    assert "execute_python" in content
    assert "completed" in content
    assert content.index("Before nested tool control.") < content.index("```tool:Glass")
    assert content.index("```tool:Glass") < content.index("After nested tool control.")


def test_tool_trigger_discovery_survives_renamed_descendant_metadata(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Before renamed nested tool control.</p>
                <section class="unrelated-wrapper-name">
                  <button><svg data.icon.kind="tool-call"></svg><span>Glass</span></button>
                  <span>execute_python</span>
                  <span>completed</span>
                </section>
                <p>After renamed nested tool control.</p>
              </div>
            </section>
            """
        ),
    )

    content = snapshot["messages"][0]["content"]
    assert chr(96) * 3 + "tool:Glass" in content
    assert "execute_python" in content
    assert "completed" in content


def test_tool_trigger_discovery_uses_aria_labelledby(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Before labelled tool control.</p>
                <span id="tool-trigger-label">Show tool details</span>
                <section class="new-tool-layout">
                  <button aria-labelledby="tool-trigger-label">Glass</button>
                  <span>execute_python</span>
                  <span>completed</span>
                </section>
                <p>After labelled tool control.</p>
              </div>
            </section>
            """
        ),
    )

    content = snapshot["messages"][0]["content"]
    assert "tool:Glass" in content
    assert "execute_python" in content
    assert content.index("Before labelled tool control.") < content.index("tool:Glass")
    assert content.index("tool:Glass") < content.index("After labelled tool control.")


def test_tool_trigger_discovery_uses_aria_describedby(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Before described tool control.</p>
                <span id="tool-trigger-description">Show tool details</span>
                <section class="future-tool-layout">
                  <button aria-describedby="tool-trigger-description">Glass</button>
                  <span>execute_python</span>
                  <span>completed</span>
                </section>
                <p>After described tool control.</p>
              </div>
            </section>
            """
        ),
    )

    content = snapshot["messages"][0]["content"]
    assert "tool:Glass" in content
    assert "execute_python" in content


def test_completion_action_discovery_uses_aria_labelledby(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Complete answer.</p>
                <span id="copy-action-label">Copy response</span>
                <button aria-labelledby="copy-action-label">+</button>
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


def test_completion_action_discovery_uses_aria_describedby(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Complete answer.</p>
                <span id="copy-action-description">Copy response</span>
                <button aria-describedby="copy-action-description">+</button>
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


def test_completion_action_discovery_tolerates_copy_wording_churn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Complete answer.</p>
                <button aria-label="Copy message">+</button>
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


def test_completion_action_discovery_uses_descendant_semantics(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Complete answer.</p>
                <button><span data-icon="copy-message"></span></button>
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


def test_completion_action_discovery_survives_renamed_descendant_metadata(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Complete answer.</p>
                <button><span data.action.icon="copy-message"></span></button>
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


def test_role_discovery_survives_author_attribute_without_role_token(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-turn-author="user" data-message-id="u-future">
              <p>Future user markup.</p>
            </section>
            <section data-message-author="assistant" data-message-id="a-future">
              <p>Future assistant markup.</p>
            </section>
            """
        ),
    )

    roles = [(message["role"], message["content"]) for message in snapshot["messages"]]

    assert ("user", "Future user markup.") in roles
    assert ("assistant", "Future assistant markup.") in roles


def test_role_discovery_survives_sender_attribute_without_role_token(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-sender="human" data-message-id="u-sender">
              <p>Sender user markup.</p>
            </section>
            <section data-sender="model" data-message-id="a-sender">
              <p>Sender assistant markup.</p>
            </section>
            """
        ),
    )

    roles = [(message["role"], message["content"]) for message in snapshot["messages"]]

    assert ("user", "Sender user markup.") in roles
    assert ("assistant", "Sender assistant markup.") in roles


def test_role_discovery_survives_actor_and_participant_attribute_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-turn-actor="human" data-message-id="u-actor">
              <p>Actor user markup.</p>
            </section>
            <section data-message-participant-role="model" data-message-id="a-participant">
              <p>Participant assistant markup.</p>
            </section>
            """
        ),
    )

    roles = [(message["role"], message["content"]) for message in snapshot["messages"]]

    assert ("user", "Actor user markup.") in roles
    assert ("assistant", "Participant assistant markup.") in roles


def test_streaming_detection_survives_semantic_attribute_namespace_churn(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-a1" data-runtime-streaming-state-v2="active">
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


def test_mixed_known_and_unknown_prose_markup_preserves_all_text(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Known semantic paragraph.</p>
                <div data-future-copy-block="true">Text inside a future prose wrapper.</div>
                <p>Known semantic tail.</p>
              </div>
            </section>
            """
        ),
    )

    assistant = next(message for message in snapshot["messages"] if message["role"] == "assistant")
    content = assistant["content"]
    assert "Known semantic paragraph." in content
    assert "Text inside a future prose wrapper." in content
    assert "Known semantic tail." in content
    assert content.index("Known semantic paragraph.") < content.index(
        "Text inside a future prose wrapper."
    )
    assert content.index("Text inside a future prose wrapper.") < content.index(
        "Known semantic tail."
    )


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


def test_tool_metadata_survives_token_reordering_and_separator_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Before reordered tool metadata.</p>
                <section data.call.tool.id="future-4" data.name.tool="Glass Serena">
                  <button aria-label="Show tool details">Inspect result</button>
                </section>
                <p>After reordered tool metadata.</p>
              </div>
            </section>
            """
        ),
    )

    assistant = next(message for message in snapshot["messages"] if message["role"] == "assistant")
    content = assistant["content"]
    assert chr(96) * 3 + "tool:Glass Serena" in content
    assert "Before reordered tool metadata." in content
    assert "After reordered tool metadata." in content


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


def test_legacy_tool_row_discovery_survives_class_token_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-testid="conversation-turn-a1">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Before legacy tool.</p>
                <span class="layout/tool-call-message">
                  <span>Legacy Tool</span>
                  <span>completed</span>
                </span>
                <p>After legacy tool.</p>
              </div>
            </section>
            """
        ),
    )

    assistant = next(message for message in snapshot["messages"] if message["role"] == "assistant")
    content = assistant["content"]
    assert "```tool:Legacy Tool" in content
    assert "Before legacy tool." in content
    assert "After legacy tool." in content


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


def test_stop_control_detection_survives_label_and_wrapper_churn(browser_page) -> None:
    html = _conversation(
        """
        <section data-testid="conversation-turn-a1">
          <div data-message-author-role="assistant" data-message-id="a1">
            <p>Still generating without a stable stop label.</p>
          </div>
        </section>
        <button style="width:32px;height:32px">
          <svg data-icon="stop" viewBox="0 0 16 16"><rect width="8" height="8" /></svg>
        </button>
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


def test_stop_control_detection_survives_renamed_descendant_metadata(browser_page) -> None:
    html = _conversation(
        """
        <section data-testid="conversation-turn-a1">
          <div data-message-author-role="assistant" data-message-id="a1">
            <p>Still generating after descendant metadata churn.</p>
          </div>
        </section>
        <button style="width:32px;height:32px">
          <svg data.control.icon="stop-response" viewBox="0 0 16 16"></svg>
        </button>
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


def test_streaming_marker_outside_selected_transcript_does_not_keep_chat_active(
    browser_page,
) -> None:
    browser_page.set_content(
        """
        <main>
          <section data-testid="conversation-turn-a1">
            <div data-message-author-role="assistant" data-message-id="a1">
              <p>Completed answer.</p>
              <button aria-label="Copy">Copy</button>
            </div>
          </section>
        </main>
        <aside>
          <section data-testid="conversation-turn-decoy" aria-busy="true" style="width:100px;height:40px">
            Background panel activity.
          </section>
        </aside>
        """
    )
    activity_script = render_browser_script(
        "conversation_activity.js",
        stop_selector='button[aria-label="Stop answering"]',
        streaming_selector='[aria-busy="true"][data-testid*="turn" i]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(activity_script))
    snapshot = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))

    assert activity["streaming"] is False
    assert activity["complete"] is True
    assert snapshot["streaming"] is False


def test_stale_streaming_marker_on_older_turn_does_not_keep_chat_active(browser_page) -> None:
    browser_page.set_content(
        _conversation(
            """
            <section data-testid="conversation-turn-u1">
              <div data-message-author-role="user" data-message-id="u1">First question</div>
            </section>
            <section data-testid="conversation-turn-a1" data-streaming="active">
              <div data-message-author-role="assistant" data-message-id="a1">
                <p>Older answer with stale streaming state.</p>
                <button aria-label="Copy">Copy</button>
              </div>
            </section>
            <section data-testid="conversation-turn-u2">
              <div data-message-author-role="user" data-message-id="u2">Latest question</div>
            </section>
            <section data-testid="conversation-turn-a2">
              <div data-message-author-role="assistant" data-message-id="a2">
                <p>Latest completed answer.</p>
                <button aria-label="Copy">Copy</button>
              </div>
            </section>
            """
        )
    )
    activity_script = render_browser_script(
        "conversation_activity.js",
        stop_selector='button[aria-label="Stop answering"]',
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    activity = json.loads(browser_page.evaluate(activity_script))
    snapshot = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))

    assert activity["streaming"] is False
    assert activity["complete"] is True
    assert snapshot["streaming"] is False


def test_transcript_wrapper_streaming_marker_still_applies_to_latest_turn(browser_page) -> None:
    browser_page.set_content(
        """
        <main data-streaming="active">
          <section data-testid="conversation-turn-u1">
            <div data-message-author-role="user" data-message-id="u1">Question</div>
          </section>
          <section data-testid="conversation-turn-a1">
            <div data-message-author-role="assistant" data-message-id="a1">
              <p>Current answer.</p>
            </div>
          </section>
        </main>
        """
    )
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


def test_accessible_heading_names_survive_visible_heading_copy_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section>
              <div role="heading" aria-level="2" aria-label="You said">Message</div>
              <p>Question survives heading copy churn.</p>
            </section>
            <section>
              <div role="heading" aria-level="2" aria-label="Assistant response">Message</div>
              <p>Answer survives heading copy churn.</p>
            </section>
            """
        ),
    )

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "Question survives heading copy churn."),
        ("assistant", "Answer survives heading copy churn."),
    ]


def test_aria_labelledby_heading_names_survive_heading_text_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <span id="user-role-label" hidden>You wrote</span>
            <section>
              <div role="heading" aria-level="2" aria-labelledby="user-role-label">Message</div>
              <p>Labelled user turn.</p>
            </section>
            <span id="assistant-role-label" hidden>ChatGPT replied</span>
            <section>
              <div role="heading" aria-level="2" aria-labelledby="assistant-role-label">Message</div>
              <p>Labelled assistant turn.</p>
            </section>
            """
        ),
    )

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "Labelled user turn."),
        ("assistant", "Labelled assistant turn."),
    ]


def test_accessible_role_metadata_survives_label_and_heading_copy_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section role="group" aria-roledescription="Message from user">
              <div>Question recovered from role description.</div>
            </section>
            <section role="group" title="Response by assistant">
              <p>Answer recovered from title metadata.</p>
            </section>
            """
        ),
    )

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "Question recovered from role description."),
        ("assistant", "Answer recovered from title metadata."),
    ]


def test_message_identity_survives_turn_id_attribute_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data-turn-id="u-turn-future" data-sender="human">
              <p>Future user identity.</p>
            </section>
            <section data-conversation-turn-uuid="a-turn-future" data-sender="model">
              <p>Future assistant identity.</p>
            </section>
            """
        ),
    )

    assert [(message["role"], message["id"]) for message in snapshot["messages"]] == [
        ("user", "u-turn-future"),
        ("assistant", "a-turn-future"),
    ]


def test_semantic_message_attributes_survive_separator_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        _conversation(
            """
            <section data.turn.uuid="u-dot" data.message.sender.role="human">
              <p>Dotted user metadata.</p>
            </section>
            <section data.turn.uuid="a-dot" data.message.sender.role="model">
              <p>Dotted assistant metadata.</p>
            </section>
            """
        ),
    )

    assert [
        (message["role"], message["id"], message["content"]) for message in snapshot["messages"]
    ] == [
        ("user", "u-dot", "Dotted user metadata."),
        ("assistant", "a-dot", "Dotted assistant metadata."),
    ]


def test_structural_discovery_uses_chat_landmark_when_first_main_is_unrelated(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        """
        <main>
          <section data-sender="model" data-message-id="decoy">Unrelated main content.</section>
        </main>
        <div role="main">
          <section data-sender="human" data-turn-id="u-chat"><p>Actual question.</p></section>
          <section data-sender="model" data-turn-id="a-chat"><p>Actual answer.</p></section>
        </div>
        """,
    )

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "Actual question."),
        ("assistant", "Actual answer."),
    ]


def test_unrelated_main_does_not_block_inferred_transcript_after_landmark_churn(
    browser_page,
) -> None:
    snapshot = _snapshot(
        browser_page,
        """
        <main>
          <section data-sender="model" data-message-id="decoy">Unrelated main content.</section>
        </main>
        <div class="future-chat-shell">
          <section data-sender="human" data-turn-id="u1"><p>First question.</p></section>
          <section data-sender="model" data-turn-id="a1"><p>First answer.</p></section>
          <section data-sender="human" data-turn-id="u2"><p>Second question.</p></section>
          <section data-sender="model" data-turn-id="a2"><p>Second answer.</p></section>
        </div>
        """,
    )

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "First question."),
        ("assistant", "First answer."),
        ("user", "Second question."),
        ("assistant", "Second answer."),
    ]


def test_feed_landmark_outranks_unrelated_main_after_landmark_churn(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        """
        <main>
          <section data-sender="model" data-message-id="decoy">Unrelated main content.</section>
        </main>
        <div role="feed">
          <section data-sender="human" data-turn-id="u-feed"><p>Feed question.</p></section>
          <section data-sender="model" data-turn-id="a-feed"><p>Feed answer.</p></section>
        </div>
        """,
    )

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "Feed question."),
        ("assistant", "Feed answer."),
    ]


def test_role_main_landmark_bounds_structural_message_discovery(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        """
        <aside data-sender="model" data-message-id="sidebar-noise">Sidebar noise.</aside>
        <div role="main">
          <section data-sender="human" data-turn-id="u-main"><p>Main user.</p></section>
          <section data-sender="model" data-turn-id="a-main"><p>Main assistant.</p></section>
        </div>
        """,
    )

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "Main user."),
        ("assistant", "Main assistant."),
    ]


def test_inferred_transcript_excludes_role_noise_inside_chat_landmark(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        """
        <main>
          <aside data-sender="model" data-message-id="status-noise">Sidebar status.</aside>
          <div class="future-chat-shell">
            <section data-sender="human" data-turn-id="u1"><p>First question.</p></section>
            <section data-sender="model" data-turn-id="a1"><p>First answer.</p></section>
            <section data-sender="human" data-turn-id="u2"><p>Second question.</p></section>
            <section data-sender="model" data-turn-id="a2"><p>Second answer.</p></section>
          </div>
        </main>
        """,
    )

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "First question."),
        ("assistant", "First answer."),
        ("user", "Second question."),
        ("assistant", "Second answer."),
    ]


def test_legacy_turn_fallback_stays_within_selected_chat_landmark(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        """
        <main>
          <section data-sender="human" data-turn-id="u-chat"><p>Actual question.</p></section>
          <section data-sender="model" data-turn-id="a-chat"><p>Actual answer.</p></section>
        </main>
        <aside>
          <article aria-label="User message"><p>Sidebar legacy question.</p></article>
          <article aria-label="Assistant response"><p>Sidebar legacy answer.</p></article>
        </aside>
        """,
    )

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "Actual question."),
        ("assistant", "Actual answer."),
    ]


def test_missing_main_landmark_infers_transcript_around_structural_role_noise(browser_page) -> None:
    snapshot = _snapshot(
        browser_page,
        """
        <aside data-sender="model" data-message-id="sidebar-noise">Sidebar noise.</aside>
        <div class="future-chat-shell">
          <section data-sender="human" data-turn-id="u-chat"><p>Actual question.</p></section>
          <section data-sender="model" data-turn-id="a-chat"><p>Actual answer.</p></section>
        </div>
        """,
    )

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "Actual question."),
        ("assistant", "Actual answer."),
    ]


def test_missing_main_landmark_scopes_primary_semantic_nodes_to_inferred_transcript(
    browser_page,
) -> None:
    snapshot = _snapshot(
        browser_page,
        """
        <aside data-message-author-role="assistant" data-message-id="sidebar-noise">
          Sidebar assistant noise.
        </aside>
        <div class="future-chat-shell">
          <section data-message-author-role="user" data-message-id="u1"><p>First question.</p></section>
          <section data-message-author-role="assistant" data-message-id="a1"><p>First answer.</p></section>
          <section data-message-author-role="user" data-message-id="u2"><p>Second question.</p></section>
          <section data-message-author-role="assistant" data-message-id="a2"><p>Second answer.</p></section>
        </div>
        """,
    )

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "First question."),
        ("assistant", "First answer."),
        ("user", "Second question."),
        ("assistant", "Second answer."),
    ]


def test_open_shadow_root_transcript_and_aria_references_survive_componentization(
    browser_page,
) -> None:
    snapshot = _shadow_snapshot(
        browser_page,
        """
        <main>
          <span id="shadow-user-role" hidden>You wrote</span>
          <section role="group" aria-labelledby="shadow-user-role" data-turn-id="u-shadow">
            <p>Shadow question.</p>
          </section>
          <span id="shadow-assistant-role" hidden>ChatGPT replied</span>
          <section role="group" aria-labelledby="shadow-assistant-role" data-turn-id="a-shadow">
            <p>Shadow answer.</p>
          </section>
        </main>
        """,
    )

    assert [
        (message["role"], message["id"], message["content"]) for message in snapshot["messages"]
    ] == [
        ("user", "u-shadow", "Shadow question."),
        ("assistant", "a-shadow", "Shadow answer."),
    ]


def test_mixed_light_and_shadow_turns_keep_composed_document_order(browser_page) -> None:
    browser_page.set_content(
        """
        <main>
          <section data-sender="human" data-turn-id="u1"><p>First question.</p></section>
          <div id="assistant-shadow-host"></div>
          <section data-sender="human" data-turn-id="u2"><p>Second question.</p></section>
          <section data-sender="model" data-turn-id="a2"><p>Second answer.</p></section>
        </main>
        """
    )
    browser_page.evaluate(
        """() => {
          const host = document.getElementById('assistant-shadow-host');
          const root = host.attachShadow({mode: 'open'});
          root.innerHTML = '<section data-sender="model" data-turn-id="a1"><p>First answer.</p></section>';
        }"""
    )

    snapshot = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))

    assert [(message["role"], message["content"]) for message in snapshot["messages"]] == [
        ("user", "First question."),
        ("assistant", "First answer."),
        ("user", "Second question."),
        ("assistant", "Second answer."),
    ]


def test_shadow_root_streaming_and_completion_controls_are_discovered(browser_page) -> None:
    browser_page.set_content('<div id="shadow-host"></div>')
    browser_page.evaluate(
        """() => {
          const host = document.getElementById('shadow-host');
          const root = host.attachShadow({mode: 'open'});
          root.innerHTML = '<main><section data-sender="human" data-turn-id="u-shadow"><p>Question.</p></section><section data-sender="model" data-turn-id="a-shadow" data-streaming="active"><p>Answer in progress.</p><button aria-label="Stop generating">Stop</button></section></main>';
        }"""
    )
    activity_script = render_browser_script(
        "conversation_activity.js",
        stop_selector='button[aria-label*="stop" i]',
        streaming_selector='[data-streaming="active"]',
    ).replace("/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT)

    streaming = json.loads(browser_page.evaluate(activity_script))
    assert streaming["streaming"] is True
    assert streaming["complete"] is False

    browser_page.evaluate(
        """() => {
          const root = document.getElementById('shadow-host').shadowRoot;
          const turn = root.querySelector('[data-turn-id="a-shadow"]');
          turn.removeAttribute('data-streaming');
          turn.querySelector('button').remove();
          turn.insertAdjacentHTML('beforeend', '<button aria-label="Copy">Copy</button>');
        }"""
    )

    complete = json.loads(browser_page.evaluate(activity_script))
    assert complete["streaming"] is False
    assert complete["complete"] is True


def test_shadow_root_control_labels_resolve_local_aria_references(browser_page) -> None:
    browser_page.set_content('<div id="shadow-host"></div>')
    browser_page.evaluate(
        """() => {
          const root = document.getElementById('shadow-host').attachShadow({mode: 'open'});
          root.innerHTML = '<span id="action-label">Retry response</span><button aria-labelledby="action-label">↻</button>';
        }"""
    )

    labels = browser_page.locator("button").evaluate(
        load_browser_script("semantic_control_labels.js")
    )

    assert "Retry response" in labels


def test_shadow_root_ancestor_matching_crosses_component_boundary(browser_page) -> None:
    browser_page.set_content(
        '<section data-testid="modal-conversation-history-rate-limit"><div id="shadow-host"></div></section>'
    )
    browser_page.evaluate(
        """() => {
          const root = document.getElementById('shadow-host').attachShadow({mode: 'open'});
          root.innerHTML = '<button>Dismiss</button>';
        }"""
    )

    matched = browser_page.locator("button").evaluate(
        load_browser_script("matches_or_closest.js"),
        '[data-testid="modal-conversation-history-rate-limit"]',
    )

    assert matched is True


def test_shadow_message_hosts_and_slots_preserve_rendered_content(browser_page) -> None:
    browser_page.set_content(
        """
        <main>
          <div id="shadow-user" data-sender="human" data-turn-id="u-host"></div>
          <div id="shadow-assistant" data-sender="model" data-turn-id="a-host">
            <p>Slotted answer.</p>
          </div>
        </main>
        """
    )
    browser_page.evaluate(
        """() => {
          const user = document.getElementById('shadow-user');
          user.attachShadow({mode: 'open'}).innerHTML = '<span>Shadow-host question.</span>';
          const assistant = document.getElementById('shadow-assistant');
          assistant.attachShadow({mode: 'open'}).innerHTML = '<slot></slot>';
        }"""
    )

    snapshot = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))

    assert [
        (message["role"], message["id"], message["content"]) for message in snapshot["messages"]
    ] == [
        ("user", "u-host", "Shadow-host question."),
        ("assistant", "a-host", "Slotted answer."),
    ]


def test_nested_shadow_role_references_use_composed_label_text(browser_page) -> None:
    browser_page.set_content('<div id="outer-host"></div>')
    browser_page.evaluate(
        """() => {
          const outer = document.getElementById('outer-host').attachShadow({mode: 'open'});
          outer.innerHTML = `
            <main>
              <span id="user-role-label"><span id="user-role-text"></span></span>
              <div id="user-turn-host"></div>
              <span id="assistant-role-label"><span id="assistant-role-text"></span></span>
              <div id="assistant-turn-host"></div>
            </main>
          `;
          outer.getElementById('user-role-text').attachShadow({mode: 'open'}).innerHTML = 'You wrote';
          outer.getElementById('assistant-role-text').attachShadow({mode: 'open'}).innerHTML = 'ChatGPT replied';
          outer.getElementById('user-turn-host').attachShadow({mode: 'open'}).innerHTML =
            '<section aria-labelledby="user-role-label" data-turn-id="u-nested"><p>Nested question.</p></section>';
          outer.getElementById('assistant-turn-host').attachShadow({mode: 'open'}).innerHTML =
            '<section aria-labelledby="assistant-role-label" data-turn-id="a-nested"><p>Nested answer.</p></section>';
        }"""
    )

    snapshot = json.loads(browser_page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))

    assert [
        (message["role"], message["id"], message["content"]) for message in snapshot["messages"]
    ] == [
        ("user", "u-nested", "Nested question."),
        ("assistant", "a-nested", "Nested answer."),
    ]


def test_nested_shadow_control_label_resolves_through_ancestor_root(browser_page) -> None:
    browser_page.set_content('<div id="outer-host"></div>')
    browser_page.evaluate(
        """() => {
          const outer = document.getElementById('outer-host').attachShadow({mode: 'open'});
          outer.innerHTML =
            '<span id="action-label"><span id="action-text"></span></span><div id="control-host"></div>';
          outer.getElementById('action-text').attachShadow({mode: 'open'}).innerHTML =
            'Retry response';
          outer.getElementById('control-host').attachShadow({mode: 'open'}).innerHTML =
            '<button aria-labelledby="action-label">↻</button>';
        }"""
    )

    button = browser_page.locator("#outer-host").evaluate_handle(
        "host => host.shadowRoot.getElementById('control-host').shadowRoot.querySelector('button')"
    )
    labels = button.evaluate(load_browser_script("semantic_control_labels.js"))

    assert "Retry response" in labels


def test_control_labels_include_native_label_description_and_placeholder(browser_page) -> None:
    browser_page.set_content(
        """
        <label for="retry-control">Retry response</label>
        <input
          id="retry-control"
          aria-description="Runs the response again"
          placeholder="Fallback retry"
          value=""
        >
        """
    )

    labels = browser_page.locator("#retry-control").evaluate(
        load_browser_script("semantic_control_labels.js")
    )

    assert "Retry response" in labels
    assert "Runs the response again" in labels
    assert "Fallback retry" in labels
