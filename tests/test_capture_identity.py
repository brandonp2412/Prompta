from pathlib import Path

import pytest

from prompta.reply_contracts import ManualReplyStore, ReplyConflict, ReplyIntent
from prompta.response_capture import conversation_id_from_path, normalize_dom_snapshot
from prompta.response_store import ResponseStore

CHAT = "d5c86e83-1f55-4ab5-ae50-7e2eed27c33e"
ANSWER = "a0b7758e-fef9-47e3-933b-8ce91bd2c3c9"


@pytest.mark.parametrize("route", [f"/c/{CHAT}", f"/g/g-example/c/{CHAT}"])
def test_exact_owned_chat_route_extracts_uuid(route: str) -> None:
    assert conversation_id_from_path(route) == CHAT


@pytest.mark.parametrize(
    "route", ["/", "/c/not-a-uuid", f"/c/{CHAT}/edit", f"/other/c/{CHAT}", f"/c/{CHAT}?x=1", None]
)
def test_noncanonical_route_never_becomes_identity(route: object) -> None:
    assert conversation_id_from_path(route) is None


def test_dom_uses_real_backend_id_not_aggregate_display_key() -> None:
    result = normalize_dom_snapshot(
        {
            "pathname": f"/c/{CHAT}",
            "message_id": "unit:assistant",
            "branch_message_id": ANSWER,
            "text": "Finished",
            "complete": True,
        }
    )
    assert (result.conversation_id, result.message_id, result.observer_id) == (
        CHAT,
        ANSWER,
        "unit:assistant",
    )
    assert result.status == "complete"
    unknown = normalize_dom_snapshot(
        {
            "pathname": f"/c/{CHAT}",
            "message_id": "unit:assistant",
            "branch_message_id": "",
            "text": "Finished",
            "complete": True,
        }
    )
    assert unknown.status == "complete" and unknown.message_id is None
    assert unknown.observer_id == "unit:assistant"


def test_owned_lease_binds_route_once_and_preserves_terminal_identity(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "results.sqlite3")
    store.ensure_queued("send", "private", now=10)
    assert store.accept("send", "owner", deadline=30, now=11)
    assert not store.bind_conversation_route("send", "intruder", f"/c/{CHAT}", now=12)
    assert not store.bind_conversation_route("send", "owner", "/c/not-an-id", now=12)
    assert store.bind_conversation_route("send", "owner", f"/c/{CHAT}", now=12)
    assert store.bind_conversation_route("send", "owner", f"/c/{CHAT}", now=13)
    assert not store.bind_conversation_route("send", "owner", f"/c/{ANSWER}", now=13)
    assert not store.bind_conversation_route("send", "owner", f"/c/{CHAT}", now=31)
    row = store.get("send")
    assert row is not None and row["conversation_id"] == CHAT
    assert store.finish("send", "owner", "interrupted", now=14)
    assert not store.bind_conversation_route("send", "owner", f"/c/{CHAT}", now=15)


@pytest.mark.asyncio
async def test_real_browser_observer_binds_owned_route_without_network() -> None:
    import asyncio
    import shutil

    from playwright.async_api import async_playwright

    script = (
        Path(__file__).parents[1] / "src/browser_scripts/passive_response_observer.js"
    ).read_text()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, executable_path=shutil.which("chromium")
        )
        try:
            page = await browser.new_page()
            await page.route(
                "**/*",
                lambda route: route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="<html><body><main></main></body></html>",
                ),
            )
            await page.goto(f"https://chatgpt.com/c/{CHAT}")
            assert await page.evaluate(script) is True
            await page.evaluate(
                """(answer) => {
                const node = document.createElement('div');
                node.setAttribute('data-chatgpt-search-unit-key', 'new:assistant');
                node.setAttribute('data-chatgpt-search-message-ids', JSON.stringify([answer]));
                node.innerHTML = '<div class="markdown">Exact response</div><button data-testid="copy-turn-action-button">Copy</button>';
                document.querySelector('main').append(node);
            }""",
                ANSWER,
            )
            await asyncio.sleep(1.6)
            payload = await page.evaluate("window.__promptaPassiveResponseObserver.read()")
            result = normalize_dom_snapshot(payload)
            assert (result.status, result.conversation_id, result.message_id) == (
                "complete",
                CHAT,
                ANSWER,
            )
            assert result.text == "Exact response"
            # Real ChatGPT uses space-separated repeated IDs rather than JSON.
            await page.evaluate(
                """(answer) => document.querySelector('[data-chatgpt-search-unit-key="new:assistant"]')
                .setAttribute('data-chatgpt-search-message-ids', answer + ' ' + answer)""",
                ANSWER,
            )
            repeated = normalize_dom_snapshot(
                await page.evaluate("window.__promptaPassiveResponseObserver.read()")
            )
            assert repeated.message_id == ANSWER
            await page.evaluate(
                """([answer, other]) => document.querySelector('[data-chatgpt-search-unit-key="new:assistant"]')
                .setAttribute('data-chatgpt-search-message-ids', answer + ' ' + other)""",
                [ANSWER, CHAT],
            )
            conflicting = normalize_dom_snapshot(
                await page.evaluate("window.__promptaPassiveResponseObserver.read()")
            )
            assert conflicting.message_id is None
            # The observer must preserve rendered Markdown semantics rather
            # than flatten every table cell and list item into a paragraph.
            await page.evaluate("""
                () => {
                    document.querySelector('.markdown').innerHTML = `
                        <h2>Verification</h2>
                        <p><strong>Passed</strong> with <a href="https://example.com/report">report</a>.</p>
                        <ul><li>First check</li><li>Second check</li></ul>
                        <table><thead><tr><th>Check</th><th>Result</th></tr></thead>
                        <tbody><tr><td>Mobile</td><td>Passed</td></tr></tbody></table>
                        <pre><code class="language-ts">const ready = true;</code></pre>
                        <p><a href="javascript:alert(1)">unsafe label</a></p>
                    `;
                }
            """)
            semantic = await page.evaluate("window.__promptaPassiveResponseObserver.read()")
            assert "## Verification" in semantic["text"]
            assert "**Passed** with [report](https://example.com/report)." in semantic["text"]
            assert "- First check\n- Second check" in semantic["text"]
            assert "| Check | Result |" in semantic["text"]
            assert "| --- | --- |" in semantic["text"]
            assert "| Mobile | Passed |" in semantic["text"]
            assert "```ts\nconst ready = true;\n```" in semantic["text"]
            assert "unsafe label" in semantic["text"]
            assert "javascript:" not in semantic["text"]
        finally:
            await browser.close()


def test_unverified_dom_unit_cannot_be_used_as_reply_parent(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "results.sqlite3")
    store.ensure_queued("send", "private", now=10)
    assert store.accept("send", "owner", deadline=30, now=11)
    capture = normalize_dom_snapshot(
        {
            "pathname": f"/c/{CHAT}",
            "message_id": "unit:assistant",
            "branch_message_id": "",
            "text": "Visible answer",
            "complete": True,
        }
    )
    assert store.write("send", "owner", capture, now=12)
    row = store.get("send")
    assert row is not None and row["status"] == "completed"
    assert row["conversation_id"] == CHAT and row["message_id"] == ""
    with pytest.raises(ReplyConflict, match="incomplete"):
        ManualReplyStore(store.path).prepare(
            "send", ReplyIntent("reply-1234567890123", CHAT, "unit:assistant", "Follow-up")
        )
