"""Real Chromium checks for exact DOM branch identity without external requests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from prompta.manual_reply_dispatch import _branch_probe

CONVERSATION = "00000000-0000-4000-8000-000000000001"
PARENT = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000003"


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        (f"data-message-id='{PARENT}'", True),
        (f"data-chatgpt-search-message-ids='[\"{PARENT}\"]'", True),
        (f"data-chatgpt-search-message-ids='{PARENT} {PARENT}'", True),
        (f"data-chatgpt-search-message-ids='{PARENT} {OTHER}'", False),
        (f"data-chatgpt-search-message-ids='[\"{PARENT}\",\"{OTHER}\"]'", False),
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
        + attribute + ">Synthetic final assistant turn</div></main>"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page()
        routed: list[str] = []

        def fulfill(route: object) -> None:
            from playwright.sync_api import Route

            assert isinstance(route, Route)
            routed.append(route.request.url)
            route.fulfill(status=200, content_type="text/html", body=html)

        page.route("https://chatgpt.com/**", fulfill)
        page.goto(f"https://chatgpt.com/c/{CONVERSATION}")
        assert page.evaluate(_branch_probe(CONVERSATION, PARENT)) is expected
        assert routed == [f"https://chatgpt.com/c/{CONVERSATION}"]
        browser.close()
