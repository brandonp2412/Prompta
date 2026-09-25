import json
import shutil
import subprocess

import pytest

from prompta.chatgpt_dom import (
    FILE_INPUT_SELECTORS,
    LEGACY_RICH_TEXT_SELECTORS,
    LEGACY_TURN_SELECTORS,
    PROSE_BLOCK_SELECTORS,
    SEMANTIC_TURN_SELECTORS,
    STOP_BUTTON_SELECTORS,
    TURN_SELECTORS,
)
from prompta.conversation_snapshot import CONVERSATION_SNAPSHOT_SCRIPT
from prompta.react_fallback import REACT_FALLBACK_ADAPTER_SCRIPT


def test_selector_contract_keeps_hidden_file_input_and_stop_state_signals() -> None:
    assert FILE_INPUT_SELECTORS[-1] == 'input[type="file"]'
    assert all("data-testid" not in selector for selector in STOP_BUTTON_SELECTORS)
    assert 'button[aria-label*="stop" i]' in STOP_BUTTON_SELECTORS


def test_selector_contract_separates_semantic_turns_from_legacy_fallbacks() -> None:
    assert SEMANTIC_TURN_SELECTORS == (
        '[data-testid^="conversation-turn-"]',
        '[data-chatgpt-search-unit-key$=":user"]',
        '[data-chatgpt-search-unit-key$=":assistant"]',
    )
    assert LEGACY_TURN_SELECTORS == (".agent-turn", "article")
    assert TURN_SELECTORS == SEMANTIC_TURN_SELECTORS + LEGACY_TURN_SELECTORS
    assert "[data-message-id]" not in TURN_SELECTORS
    assert "[data-message-uuid]" not in TURN_SELECTORS
    assert PROSE_BLOCK_SELECTORS[:4] == ("p", "pre", "blockquote", "ul")
    assert ".markdown" in LEGACY_RICH_TEXT_SELECTORS
    assert '[class*="markdown"]' in LEGACY_RICH_TEXT_SELECTORS


def test_snapshot_does_not_treat_explicit_user_turns_as_assistant_fallbacks() -> None:
    assert "const explicitUserTurns=new Set(userNodes.map(turnRoot).filter(Boolean));" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert ".filter(turn=>!explicitUserTurns.has(turn))" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const legacyAssistantTurns=" in CONVERSATION_SNAPSHOT_SCRIPT
    assert ".filter(turn=>!authorNode(turn,'user'))" in CONVERSATION_SNAPSHOT_SCRIPT


def test_snapshot_has_explicit_page_level_react_fallback_adapter() -> None:
    assert "reactFallback.inspect(root,{allow:true,reason" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "!entries.length&&pageReactRoot" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "reactMessages(pageReactRoot,'transcript-gap')" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const fallbackSummary=promptaTranscriptEngine.reactFallbackSummary();" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "react_fallback:fallbackSummary" in CONVERSATION_SNAPSHOT_SCRIPT


def test_react_fallback_orders_messages_by_parent_chain_before_timestamps() -> None:
    assert "const positionById=new Map();" in REACT_FALLBACK_ADAPTER_SCRIPT
    assert "const parentId=String(message?.parent_id||'').trim();" in (
        REACT_FALLBACK_ADAPTER_SCRIPT
    )
    assert "indegree[index]+=1;" in REACT_FALLBACK_ADAPTER_SCRIPT


def test_snapshot_anchors_each_dom_prose_block_to_surrounding_tool_calls() -> None:
    assert "const precedingToolCount=rows.filter" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const beforeTime=Number(toolCallEvents[precedingToolCount-1]?.create_time);" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "const afterTime=Number(toolCallEvents[precedingToolCount]?.create_time);" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "parts:[entry.text]" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "preceding_tool_count:precedingToolCount" in CONVERSATION_SNAPSHOT_SCRIPT


def test_snapshot_keeps_javascript_newline_escapes_literal() -> None:
    assert "parts.join('\\n')" in CONVERSATION_SNAPSHOT_SCRIPT
    assert ".join('\\n\\n').trim()" in CONVERSATION_SNAPSHOT_SCRIPT


def _snapshot_from_html(html: str) -> dict:
    executable = shutil.which("chromium") or shutil.which("brave")
    if executable is None:
        pytest.skip("A Chromium-compatible browser is unavailable")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        try:
            page = browser.new_page()
            page.set_content(html)
            raw = page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT)
        finally:
            browser.close()
    return json.loads(raw)


def _react_fallback_from_html(
    html: str,
    setup_script: str = "",
    *,
    options: dict[str, int] | None = None,
) -> dict:
    executable = shutil.which("chromium") or shutil.which("brave")
    if executable is None:
        pytest.skip("A Chromium-compatible browser is unavailable")
    from playwright.sync_api import sync_playwright

    extra_options = json.dumps(options or {})
    expression = (
        "JSON.stringify((()=>{"
        + REACT_FALLBACK_ADAPTER_SCRIPT
        + "const options={allow:true,reason:'transcript-gap',..."
        + extra_options
        + "};return reactFallback.inspect(document.body,options);})())"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        try:
            page = browser.new_page()
            page.set_content(html)
            if setup_script:
                page.evaluate(setup_script)
            raw = page.evaluate(expression)
        finally:
            browser.close()
    return json.loads(raw)


def test_react_fallback_without_private_properties_degrades_to_empty_result() -> None:
    result = _react_fallback_from_html("<main><p>DOM still works</p></main>")

    assert result["allowed"] is True
    assert result["used"] is True
    assert result["available"] is False
    assert result["provenance"] == "react-private-properties"
    assert result["messages"] == []
    assert result["error"] == ""


def test_react_fallback_accepts_changed_private_property_suffix() -> None:
    result = _react_fallback_from_html(
        "<main id='root'></main>",
        """() => {
          const root=document.querySelector('#root');
          root['__reactFiber$changed-build-key']={
            memoizedProps:{
              messages:[{
                id:'assistant-1',
                author:{role:'assistant'},
                content:{content_type:'text',parts:['Recovered from fallback']},
                create_time:1
              }]
            }
          };
        }""",
    )

    assert result["available"] is True
    assert "__reactFiber$changed-build-key" in result["property_names"]
    assert result["messages"][0]["id"] == "assistant-1"


def test_react_fallback_introspection_failure_returns_structured_error() -> None:
    result = _react_fallback_from_html(
        "<main></main>",
        """() => {
          document.body.querySelectorAll=()=>{throw new Error('private shape changed');};
        }""",
    )

    assert result["used"] is True
    assert result["messages"] == []
    assert result["error"] == "private shape changed"
    assert result["provenance"] == "react-private-properties"


def test_react_fallback_stops_at_explicit_scan_budget() -> None:
    result = _react_fallback_from_html(
        "<main><div id='first'></div><div id='late'></div></main>",
        """() => {
          const late=document.querySelector('#late');
          late['__reactFiber$late-message']={
            memoizedProps:{
              messages:[{
                id:'assistant-late',
                author:{role:'assistant'},
                content:{content_type:'text',parts:['Too late for bounded scan']},
                create_time:1
              }]
            }
          };
        }""",
        options={"maxNodes": 2, "maxMillis": 2000},
    )

    assert result["truncated"] is True
    assert result["scanned_nodes"] == 2
    assert result["messages"] == []
    assert result["error"] == "React fallback introspection budget exhausted"


def test_shared_transcript_engine_has_one_total_react_fallback_time_budget() -> None:
    assert "const fallbackDeadline=performance.now()+2500;" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const maxMillis=Math.max(1,fallbackDeadline-performance.now());" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )


def test_snapshot_discovers_semantic_and_structural_turns_without_styling_classes() -> None:
    snapshot = _snapshot_from_html(
        """
        <main>
          <section data-testid="conversation-turn-u1">
            <div data-message-author-role="user" data-message-id="u1">Question one</div>
          </section>
          <section data-testid="conversation-turn-a1">
            <div data-message-author-role="assistant" data-message-uuid="a1">Answer one</div>
          </section>
          <div data-layout-token="opaque-user">
            <div><div data-message-author-role="user" data-message-id="u2">Question two</div></div>
          </div>
          <div data-layout-token="opaque-assistant">
            <div><div data-message-author-role="assistant" data-message-id="a2">Answer two</div></div>
          </div>
        </main>
        """
    )

    assert [(message["role"], message["id"]) for message in snapshot["messages"]] == [
        ("user", "u1"),
        ("assistant", "a1"),
        ("user", "u2"),
        ("assistant", "a2"),
    ]
    contents = [message["content"] for message in snapshot["messages"]]
    assert contents[0] == "Question one"
    assert contents[1].endswith("Answer one")
    assert contents[2] == "Question two"
    assert contents[3].endswith("Answer two")
    assert snapshot["react_fallback"]["used"] is False
    diagnostics = snapshot["extraction_diagnostics"]
    assert "dom-role" in diagnostics["message_provenance"]
    assert diagnostics["fallback_used"] is False
    assert diagnostics["unreconciled_expected_content"] == []


def test_snapshot_preserves_role_nodes_visibility_and_streaming_semantics() -> None:
    snapshot = _snapshot_from_html(
        """
        <main>
          <div style="display:none">
            <div data-message-author-role="user" data-message-id="u-hidden">Hidden retained user</div>
          </div>
          <article style="display:none">
            <div class="markdown">Hidden legacy assistant must not leak</div>
          </article>
          <section data-testid="conversation-turn-stream" data-is-streaming="true">
            <div data-message-author-role="assistant" data-message-id="a-stream">Streaming answer</div>
          </section>
        </main>
        """
    )

    assert snapshot["streaming"] is True
    assert [(message["role"], message["id"]) for message in snapshot["messages"]] == [
        ("user", "u-hidden"),
        ("assistant", "a-stream"),
    ]
    assert all(
        "Hidden legacy assistant" not in message["content"] for message in snapshot["messages"]
    )


def test_snapshot_ignores_chatgpt_accessibility_heading_as_assistant_content() -> None:
    snapshot = _snapshot_from_html(
        """
        <main>
          <section data-testid="conversation-turn-u1">
            <div data-message-author-role="user" data-message-id="u1">Question one</div>
          </section>
          <section data-testid="conversation-turn-a1">
            <div data-message-author-role="assistant" data-message-id="a1">
              <h4>ChatGPT said:</h4>
            </div>
          </section>
          <section data-testid="conversation-turn-u2">
            <div data-message-author-role="user" data-message-id="u2">Question two</div>
          </section>
          <section data-testid="conversation-turn-a2">
            <div data-message-author-role="assistant" data-message-id="a2">
              <h4>ChatGPT said:</h4>
              <p>Actual answer</p>
            </div>
          </section>
        </main>
        """
    )

    assert [(message["role"], message["id"]) for message in snapshot["messages"]] == [
        ("user", "u1"),
        ("user", "u2"),
        ("assistant", "a2"),
    ]
    assert snapshot["messages"][-1]["content"] == "Actual answer"
    assert "ChatGPT said" not in snapshot["messages"][-1]["content"]


def test_snapshot_keeps_legacy_turn_selector_as_fallback_only() -> None:
    snapshot = _snapshot_from_html(
        """
        <main>
          <div data-message-author-role="user" data-message-id="u1">Question</div>
          <article>
            <div class="markdown">Legacy answer</div>
          </article>
        </main>
        """
    )

    assert snapshot["messages"][-1]["role"] == "assistant"
    assert snapshot["messages"][-1]["content"] == "Legacy answer"


@pytest.mark.parametrize(
    ("prose_class", "tool_class"),
    [
        ("opaque-rich-a91", "opaque-tool-b17"),
        ("rewritten-copy-z42", "rewritten-call-q08"),
    ],
)
def test_snapshot_preserves_prose_tool_order_across_class_name_churn(
    prose_class: str,
    tool_class: str,
) -> None:
    snapshot = _snapshot_from_html(
        f"""
        <main>
          <section data-testid="conversation-turn-a1">
            <div data-message-author-role="assistant" data-message-id="a1">
              <div class="{prose_class}"><p>Before <strong>tool</strong>.</p></div>
              <div class="{tool_class}">
                <button aria-label="Open tool call list">Tool</button>
                <span>Glass Serena</span>
              </div>
              <div class="{prose_class}"><p>After <code>tool</code>.</p></div>
            </div>
          </section>
        </main>
        """
    )

    content = snapshot["messages"][-1]["content"]
    assert content.index("Before **tool**.") < content.index("Glass Serena")
    assert content.index("Glass Serena") < content.index("After ")
    assert snapshot["extraction_diagnostics"]["unreconciled_expected_content"] == [
        "structured-tool-source-events"
    ]


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
