"""Patchright proof that visible tool cards are scoped to the verified assistant turn."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import sync_playwright

from prompta.browser_script_loader import load_browser_script


def test_all_response_probes_include_the_shared_turn_root() -> None:
    for name in (
        "passive_response_observer.js",
        "historical_response_probe.js",
        "recover_manual_reply_tip.js",
        "verify_manual_reply_delivery.js",
        "historical_reply_probe.js",
    ):
        script = load_browser_script(name)
        assert "const responseTurnRoot =" in script
        assert script.count("responseTurnRoot") >= 2
        assert "/* PROMPTA_MARKDOWN_FROM_DOM */" not in script


def test_tool_cards_sibling_to_the_inner_answer_are_captured_without_crossing_turns() -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).is_file():
        pytest.skip("Headless Chromium unavailable")
    script = load_browser_script("markdown_from_dom.js")
    html = """
    <main>
      <div data-testid="conversation-turn-41">
        <button aria-label="Used Previous">Used Previous</button>
        <div class="group flex flex-col"><div class="markdown">Prior answer</div></div>
      </div>
      <div data-testid="conversation-turn-42">
        <button aria-label="Used Search">Used Search</button>
        <button aria-label="Used Hidden" style="display:none">Used Hidden</button>
        <div class="group flex flex-col">
          <div id="answer" data-message-author-role="assistant">
            <div class="markdown"><button aria-label="Used Markdown">Used Markdown</button>Answer</div>
          </div>
        </div>
      </div>
    </main>
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        try:
            page = browser.new_page()
            page.set_content(html)
            result = page.evaluate(
                "() => {" + script + """
                const answer = document.querySelector("#answer");
                const root = responseTurnRoot(answer);
                const visible = (node) => node.isConnected && node.getClientRects().length > 0;
                return {
                    root: root.getAttribute("data-testid"),
                    actions: toolCallsFromTurns([root], visible, ".markdown").map((call) => call.action)
                };
                }"""
            )
            assert result == {"root": "conversation-turn-42", "actions": ["Used Search"]}
        finally:
            browser.close()


def test_turn_root_prefers_exact_data_key_over_a_broad_article() -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).is_file():
        pytest.skip("Headless Chromium unavailable")
    script = load_browser_script("markdown_from_dom.js")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        try:
            page = browser.new_page()
            page.set_content("""
            <article>
              <button aria-label="Used Wrong">Used Wrong</button>
              <div data-turn-key="exact">
                <button aria-label="Used Right">Used Right</button>
                <div class="group flex flex-col"><div id="answer"></div></div>
              </div>
            </article>
            """)
            result = page.evaluate(
                "() => {" + script + """
                const root = responseTurnRoot(document.querySelector("#answer"));
                return toolCallsFromTurns([root], () => true, ".markdown")
                    .map((call) => call.action);
                }"""
            )
            assert result == ["Used Right"]
        finally:
            browser.close()
