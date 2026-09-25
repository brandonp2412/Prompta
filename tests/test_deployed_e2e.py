from __future__ import annotations

import fcntl
import os
import shutil
import time
from pathlib import Path
from urllib.parse import urljoin

import pytest

deployed_e2e_only = pytest.mark.skipif(
    not os.environ.get("PROMPTA_E2E_BASE_URL"),
    reason="Set PROMPTA_E2E_BASE_URL to run the destructive deployed Prompta E2E test",
)


def _try_acquire_deployed_e2e_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = lock_path.open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        return None
    lock_handle.seek(0)
    lock_handle.truncate()
    lock_handle.write(f"pid={os.getpid()}\n")
    lock_handle.flush()
    return lock_handle


def _release_deployed_e2e_lock(lock_handle) -> None:
    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    lock_handle.close()


@pytest.fixture(scope="module", autouse=True)
def _serialize_deployed_e2e():
    if not os.environ.get("PROMPTA_E2E_BASE_URL"):
        yield
        return

    lock_path = Path(os.environ.get("PROMPTA_E2E_LOCK", "/tmp/prompta-deployed-e2e.lock"))
    lock_handle = _try_acquire_deployed_e2e_lock(lock_path)
    if lock_handle is None:
        pytest.skip(f"another deployed Prompta E2E run already holds {lock_path}")
    try:
        yield
    finally:
        _release_deployed_e2e_lock(lock_handle)


def test_deployed_e2e_lock_rejects_second_holder(tmp_path: Path) -> None:
    lock_path = tmp_path / "deployed-e2e.lock"
    first = _try_acquire_deployed_e2e_lock(lock_path)
    assert first is not None
    try:
        assert _try_acquire_deployed_e2e_lock(lock_path) is None
    finally:
        _release_deployed_e2e_lock(first)

    replacement = _try_acquire_deployed_e2e_lock(lock_path)
    assert replacement is not None
    _release_deployed_e2e_lock(replacement)


TOOL_PREVIEW_REGRESSION_CHAT = "6ab5951b-a778-83ec-8e70-a77c62cde6d7"
CANONICAL_ORDER_REGRESSION_CHAT = "6ab58fa4-714c-83ec-ac6b-3365d325a355"


def _base_url() -> str:
    value = os.environ["PROMPTA_E2E_BASE_URL"].strip()
    return value if value.endswith("/") else value + "/"


def _artifact_dir() -> Path:
    path = Path(os.environ.get("PROMPTA_E2E_ARTIFACTS", "/tmp/prompta-deployed-e2e"))
    path.mkdir(parents=True, exist_ok=True)
    for name in (
        "desktop-home.png",
        "historical-tool-preview.png",
        "historical-canonical-order.png",
        "new-chat-pending.png",
        "new-chat-complete.png",
        "reply-complete.png",
        "mobile-complete.png",
        "trace.zip",
    ):
        (path / name).unlink(missing_ok=True)
    return path


def _assert_viewport_layout(page) -> None:
    layout = page.evaluate(
        """() => {
          const sidebar = document.querySelector('#sidebar')?.getBoundingClientRect();
          const main = document.querySelector('.main-panel')?.getBoundingClientRect();
          const composer = document.querySelector('#composerFooter')?.getBoundingClientRect();
          return {
            width: innerWidth,
            height: innerHeight,
            bodyScrollWidth: document.documentElement.scrollWidth,
            sidebar: sidebar && {left: sidebar.left, right: sidebar.right, width: sidebar.width},
            main: main && {left: main.left, right: main.right, width: main.width},
            composer: composer && {top: composer.top, bottom: composer.bottom, height: composer.height},
          };
        }"""
    )
    assert layout["bodyScrollWidth"] <= layout["width"] + 1
    assert layout["main"]
    assert layout["composer"]
    assert layout["main"]["left"] >= -1
    assert layout["main"]["right"] <= layout["width"] + 1
    assert layout["composer"]["bottom"] <= layout["height"] + 1
    assert layout["composer"]["height"] > 0


def _wait_for_exact_reply(page, token: str, timeout_ms: int = 300_000) -> None:
    page.get_by_text(token, exact=True).last.wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_function(
        """expected => {
          const nodes = [...document.querySelectorAll('.message.assistant .message-content')];
          return nodes.some((node) => node.innerText.trim() === expected);
        }""",
        arg=token,
        timeout=timeout_ms,
    )


def _wait_for_send_delivery(request, base: str, send_id: str) -> None:
    timeout_ms = int(os.environ.get("PROMPTA_E2E_DELIVERY_TIMEOUT_MS", "900000"))
    deadline = time.monotonic() + timeout_ms / 1000
    last_job: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = request.get(urljoin(base, f"api/sends/{send_id}"))
        assert response.ok, f"send receipt {send_id} returned HTTP {response.status}"
        last_job = response.json()
        status = str(last_job.get("status") or "")
        if status == "succeeded":
            return
        if status in {"failed", "cancelled", "dead_lettered", "outcome_unknown"}:
            raise AssertionError(
                f"send {send_id} ended as {status}: "
                f"{last_job.get('error') or last_job.get('last_error') or 'no error detail'}"
            )
        time.sleep(0.5)
    raise AssertionError(
        f"send {send_id} did not complete delivery within {timeout_ms}ms: {last_job}"
    )


@deployed_e2e_only
def test_deployed_prompta_round_trip_and_historical_rendering() -> None:
    executable = shutil.which("chromium") or shutil.which("brave")
    if executable is None:
        pytest.skip("A Chromium-compatible browser is unavailable")

    from playwright.sync_api import sync_playwright

    base = _base_url()
    artifacts = _artifact_dir()
    existing_chat_id = os.environ.get("PROMPTA_E2E_EXISTING_CHAT_ID", "").strip()
    existing_token = os.environ.get("PROMPTA_E2E_EXISTING_TOKEN", "").strip()
    verify_only = os.environ.get("PROMPTA_E2E_VERIFY_ONLY", "").strip() == "1"
    run_token = existing_token or f"PROMPTA_E2E_{int(time.time())}"
    followup_token = f"{run_token}_FOLLOWUP"
    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            extra_http_headers={"X-Prompta-Track-Response": "1"},
        )
        context.tracing.start(screenshots=True, snapshots=True)
        page = context.new_page()
        page.on(
            "console",
            lambda message: (
                console_errors.append(message.text) if message.type == "error" else None
            ),
        )
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        try:
            page.goto(base, wait_until="domcontentloaded", timeout=30_000)
            page.get_by_role("button", name="Start a new chat").wait_for(
                state="visible", timeout=20_000
            )
            page.locator(".chat-item-select").first.wait_for(state="visible", timeout=20_000)
            _assert_viewport_layout(page)
            page.screenshot(path=artifacts / "desktop-home.png", full_page=True)

            page.goto(
                f"{base}#/{TOOL_PREVIEW_REGRESSION_CHAT}",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            page.locator(".tool-call-block").first.wait_for(state="visible", timeout=30_000)
            tool_api = context.request.get(
                urljoin(base, f"api/chats/{TOOL_PREVIEW_REGRESSION_CHAT}")
            )
            assert tool_api.ok
            tool_chat = tool_api.json()
            expected_tool_blocks = sum(
                1
                for message in tool_chat.get("messages", [])
                for part in message.get("parts") or []
                if part.get("kind") == "tool_call"
            )
            assert expected_tool_blocks > 0
            assert page.locator(".tool-call-block").count() == expected_tool_blocks
            page.screenshot(path=artifacts / "historical-tool-preview.png", full_page=True)

            page.goto(
                f"{base}#/{CANONICAL_ORDER_REGRESSION_CHAT}",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            try:
                page.locator(".message.assistant").first.wait_for(state="visible", timeout=60_000)
            except Exception as error:
                heading = page.locator("#chatHeading").inner_text()
                loading = page.locator('[aria-label="Loading conversation"]').count()
                raise AssertionError(
                    f"historical deep link did not render; heading={heading!r} "
                    f"loading={loading} console_errors={console_errors!r} "
                    f"page_errors={page_errors!r}"
                ) from error
            canonical_api = context.request.get(
                urljoin(base, f"api/chats/{CANONICAL_ORDER_REGRESSION_CHAT}")
            )
            assert canonical_api.ok
            canonical_chat = canonical_api.json()
            for message in canonical_chat.get("messages", []):
                parts = message.get("parts") or []
                final_ordinals = [
                    int(part["ordinal"])
                    for part in parts
                    if part.get("kind") == "final_text" and part.get("ordinal") is not None
                ]
                if final_ordinals:
                    assert final_ordinals == [max(int(part["ordinal"]) for part in parts)]
            page.screenshot(path=artifacts / "historical-canonical-order.png", full_page=True)

            if existing_chat_id:
                page.goto(
                    f"{base}#/{existing_chat_id}",
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
                _wait_for_exact_reply(page, run_token, timeout_ms=60_000)
                first_chat_url = page.url
            else:
                page.get_by_role("button", name="Start a new chat").click()
                composer = page.get_by_role("textbox", name="Message Prompta")
                composer.wait_for(state="visible", timeout=10_000)
                assert composer.is_enabled()
                prompt = f"Reply with exactly {run_token} and nothing else."
                composer.fill(prompt)
                with page.expect_response(
                    lambda response: (
                        response.request.method == "POST"
                        and response.url == urljoin(base, "api/chats")
                    ),
                    timeout=15_000,
                ) as send_response_info:
                    page.get_by_role("button", name="Send message").click()
                send_response = send_response_info.value
                assert send_response.ok
                send_id = str(send_response.json().get("send_id") or "")
                assert send_id, "new-chat response did not include send_id"
                page.locator(".message.user .message-content").get_by_text(
                    prompt, exact=True
                ).wait_for(state="visible", timeout=15_000)
                selected_status = page.locator(".chat-item.selected .item-status-dot")
                if selected_status.count():
                    assert selected_status.first.get_attribute("aria-label") != "Complete"
                page.screenshot(path=artifacts / "new-chat-pending.png", full_page=True)

                _wait_for_send_delivery(context.request, base, send_id)
                _wait_for_exact_reply(page, run_token)
                first_chat_url = page.url
                assert "#/" in first_chat_url
                page.screenshot(path=artifacts / "new-chat-complete.png", full_page=True)

            if verify_only:
                assert existing_chat_id, "verify-only mode requires an existing chat"
                _wait_for_exact_reply(page, followup_token, timeout_ms=60_000)
            else:
                composer = page.get_by_role("textbox", name="Message Prompta")
                composer.wait_for(state="visible", timeout=10_000)
                assert composer.is_enabled()
                followup_prompt = f"Reply with exactly {followup_token} and nothing else."
                composer.fill(followup_prompt)
                with page.expect_response(
                    lambda response: (
                        response.request.method == "POST" and response.url.endswith("/messages")
                    ),
                    timeout=15_000,
                ) as send_response_info:
                    page.get_by_role("button", name="Send message").click()
                send_response = send_response_info.value
                assert send_response.ok
                send_id = str(send_response.json().get("send_id") or "")
                assert send_id, "reply response did not include send_id"
                page.locator(".message.user .message-content").get_by_text(
                    followup_prompt, exact=True
                ).wait_for(state="visible", timeout=15_000)
                _wait_for_send_delivery(context.request, base, send_id)
                _wait_for_exact_reply(page, followup_token)
                page.screenshot(path=artifacts / "reply-complete.png", full_page=True)

            page.goto(base, wait_until="domcontentloaded", timeout=30_000)
            page.get_by_role("button", name="Start a new chat").wait_for(
                state="visible", timeout=20_000
            )
            page.goto(first_chat_url, wait_until="domcontentloaded", timeout=30_000)
            _wait_for_exact_reply(page, run_token, timeout_ms=30_000)
            _wait_for_exact_reply(page, followup_token, timeout_ms=30_000)
            _assert_viewport_layout(page)

            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(250)
            _assert_viewport_layout(page)
            page.screenshot(path=artifacts / "mobile-complete.png", full_page=True)

            assert not page_errors
            assert not [
                message
                for message in console_errors
                if "favicon" not in message.casefold() and "notification" not in message.casefold()
            ]
        finally:
            context.tracing.stop(path=artifacts / "trace.zip")
            browser.close()
