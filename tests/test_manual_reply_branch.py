"""Real Chromium checks for exact DOM branch identity without external requests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import sync_playwright

from prompta.manual_reply_dispatch import (
    _branch_probe,
    _branch_wait_probe,
    _recovery_probe,
    _tip_recovery_probe,
)

CONVERSATION = "00000000-0000-4000-8000-000000000001"
PARENT = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000003"


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        (f"data-message-id='{PARENT}'", True),
        (f"data-chatgpt-search-message-ids='[\"{PARENT}\"]'", True),
        (f"data-chatgpt-search-message-ids='{PARENT} {PARENT}'", True),
        (f"data-chatgpt-search-message-ids='{PARENT} {OTHER}'", True),
        (f'data-chatgpt-search-message-ids=\'["{PARENT}","{OTHER}"]\'', True),
        ("data-chatgpt-search-message-ids='not-json'", False),
        (f"data-chatgpt-search-message-ids='[\"{OTHER}\"]'", False),
    ],
)
def test_exact_branch_probe_decodes_only_one_backend_id(attribute: str, expected: bool) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    html = (
        "<main><div data-message-author-role='assistant' data-chatgpt-search-unit-key='turn:assistant' "
        + attribute
        + ">Synthetic final assistant turn</div></main>"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page()
        routed: list[str] = []

        def fulfill(route: object) -> None:
            from patchright.sync_api import Route

            assert isinstance(route, Route)
            routed.append(route.request.url)
            route.fulfill(status=200, content_type="text/html", body=html)

        page.route("https://chatgpt.com/**", fulfill)
        page.goto(f"https://chatgpt.com/c/{CONVERSATION}")
        assert page.evaluate(_branch_probe(CONVERSATION, PARENT)) is expected
        assert routed == [f"https://chatgpt.com/c/{CONVERSATION}"]
        browser.close()


def test_exact_branch_rejects_later_user_turn() -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    html = (
        f"<main><div data-message-author-role='assistant' data-message-id='{PARENT}'>Answer</div>"
        "<div data-message-author-role='user'>External follow-up</div></main>"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page()
        page.route("https://chatgpt.com/**", lambda route: route.fulfill(
            status=200, content_type="text/html", body=html,
        ))
        page.goto(f"https://chatgpt.com/c/{CONVERSATION}")
        assert page.evaluate(_branch_probe(CONVERSATION, PARENT)) is False
        browser.close()


@pytest.mark.parametrize(
    ("ids", "answer", "extra", "expected"),
    [
        (f"{PARENT} {PARENT}", "Original answer", "", PARENT),
        (f"{PARENT} {OTHER}", "Original answer", "", None),
        (f"{PARENT} {PARENT}", "Changed answer", "", None),
        (
            f"{PARENT} {PARENT}",
            "Original answer",
            "<div data-chatgpt-search-unit-key='other:assistant' data-chatgpt-search-message-ids='"
            + OTHER
            + "'><div class='markdown'>Other answer</div></div>",
            None,
        ),
    ],
)
def test_explicit_recovery_verifies_only_the_one_original_branch(
    ids: str, answer: str, extra: str, expected: str | None
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    html = (
        "<main><div data-chatgpt-search-unit-key='first:user'>Original prompt</div>"
        "<div data-chatgpt-search-unit-key='first:assistant' "
        f"data-chatgpt-search-message-ids='{ids}'>"
        f"<div class='markdown'>{answer}</div></div>{extra}</main>"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page()
        page.route(
            "https://chatgpt.com/**",
            lambda route: route.fulfill(status=200, content_type="text/html", body=html),
        )
        page.goto(f"https://chatgpt.com/c/{CONVERSATION}")
        assert page.evaluate(_recovery_probe(CONVERSATION, "Original answer")) == expected
        assert page.evaluate(_recovery_probe(OTHER, "Original answer")) is None
        browser.close()


@pytest.mark.parametrize("hydration_delay_ms", [450, 12500])
def test_branch_wait_observes_delayed_assistant_hydration_without_polling(
    hydration_delay_ms: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page()
        routed: list[str] = []

        def serve(route: object) -> None:
            from patchright.sync_api import Route

            assert isinstance(route, Route)
            routed.append(route.request.url)
            route.fulfill(status=200, content_type="text/html", body="<main></main>")

        page.route("https://chatgpt.com/**", serve)
        page.goto(f"https://chatgpt.com/c/{CONVERSATION}")
        page.evaluate(
            """(payload) => setTimeout(() => {
                const assistant = document.createElement('div');
                assistant.setAttribute('data-message-author-role', 'assistant');
                assistant.setAttribute('data-message-id', payload.parent);
                assistant.innerText = 'Hydrated answer';
                document.querySelector('main').append(assistant);
            }, payload.delay)""",
            {"parent": PARENT, "delay": hydration_delay_ms},
        )
        assert page.evaluate(_branch_wait_probe(CONVERSATION, PARENT)) is True
        assert routed == [f"https://chatgpt.com/c/{CONVERSATION}"]
        browser.close()


def test_recover_manual_tip_requires_exact_preceding_parent_and_latest_user() -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    previous = PARENT
    recovered = OTHER
    html = (
        "<main>"
        "<div data-message-author-role='user'>Initial prompt</div>"
        f"<div data-message-author-role='assistant' data-message-id='{previous}'>"
        "<div class='markdown'>Original answer</div></div>"
        "<div data-message-author-role='user'>Follow-up</div>"
        f"<div data-message-author-role='assistant' data-message-id='{recovered}'>"
        "<div class='markdown'>Partial reply that grew longer</div></div></main>"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page()
        page.route("https://chatgpt.com/**", lambda route: route.fulfill(
            status=200, content_type="text/html", body=html,
        ))
        page.goto(f"https://chatgpt.com/c/{CONVERSATION}")

        def probe(user: str, parent: str, answer: str) -> str:
            return _tip_recovery_probe(CONVERSATION, parent, user, answer, 2)
        assert page.evaluate(probe("Follow-up", previous, "Partial reply")) == recovered
        assert page.evaluate(probe("Different", previous, "Partial reply")) is None
        assert page.evaluate(probe("Follow-up", recovered, "Partial reply")) is None
        assert page.evaluate(probe("Follow-up", previous, "Different")) is None
        browser.close()
