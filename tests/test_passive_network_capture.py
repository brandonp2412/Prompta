import asyncio
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from patchright.async_api import Page, Request, Response

from prompta.playwright_driver import PlaywrightDriver

SSE = (
    'data: {"message":{"id":"response-1","author":{"role":"assistant"},'
    '"recipient":"all","channel":"final","content":{"content_type":"text",'
    '"parts":["Private local answer"]},"status":"finished_successfully"}}\n\n'
    'data: [DONE]\n\n'
)


@pytest.mark.asyncio
async def test_capture_reads_only_existing_post_sse_and_preserves_send_confirmation(
    tmp_path: Path,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path)
    driver._connected = True
    driver.context = "owned-fresh-tab"
    driver._pages[driver.context] = Mock(spec=Page, **{"is_closed.return_value": False})
    capture = driver.arm_send_capture()

    request = Mock(spec=Request)
    request.method = "POST"
    request.url = "https://chatgpt.com/backend-api/conversation"
    response = Mock(spec=Response)
    response.request = request
    response.status = 200
    response.headers = {"content-type": "text/event-stream; charset=utf-8"}
    response.finished = Mock(side_effect=lambda: asyncio.sleep(0))
    response.text = Mock(side_effect=lambda: asyncio.sleep(0, result=SSE))

    driver._on_request(request)
    driver._on_response(response)
    assert driver.captured_send_response(capture) is not None
    await asyncio.gather(*driver._response_tasks)
    parsed = driver.captured_assistant_response(capture)
    assert parsed is not None
    assert parsed.status == "complete"
    assert parsed.text == "Private local answer"
    driver.clear_send_capture(capture)
    await driver.close()


@pytest.mark.asyncio
async def test_unrelated_or_duplicate_post_cannot_replace_owned_stream(tmp_path: Path) -> None:
    driver = PlaywrightDriver(profile=tmp_path)
    driver._connected = True
    driver.context = "owned-fresh-tab"
    driver._pages[driver.context] = Mock(spec=Page, **{"is_closed.return_value": False})
    capture = driver.arm_send_capture()
    get_request = Mock(spec=Request)
    get_request.method = "GET"
    get_request.url = "https://chatgpt.com/backend-api/conversation/some-id"
    driver._on_request(get_request)
    assert not capture.get("request_id")

    request = Mock(spec=Request)
    request.method = "POST"
    request.url = "https://chatgpt.com/backend-api/f/conversation"
    duplicate = Mock(spec=Request)
    duplicate.method = "POST"
    duplicate.url = request.url
    driver._on_request(request)
    bound = capture.get("request_id")
    driver._on_request(duplicate)
    assert capture.get("request_id") == bound
    assert capture["ambiguous_request"] is True
    await driver.close()


@pytest.mark.asyncio
async def test_non_sse_post_response_never_reads_body(tmp_path: Path) -> None:
    driver = PlaywrightDriver(profile=tmp_path)
    driver._connected = True
    driver.context = "owned-fresh-tab"
    driver._pages[driver.context] = Mock(spec=Page, **{"is_closed.return_value": False})
    capture = driver.arm_send_capture()
    request = Mock(spec=Request)
    request.method = "POST"
    request.url = "https://chatgpt.com/backend-api/conversation"
    response = Mock(spec=Response)
    response.request = request
    response.status = 429
    response.headers = {"content-type": "application/json"}
    driver._on_request(request)
    driver._on_response(response)
    assert capture["status"] == 429
    assert not driver._response_tasks
    assert driver.captured_assistant_response(capture) is None
    await driver.close()


@pytest.mark.asyncio
async def test_observer_binding_propagates_ambiguous_dom_rollover(tmp_path: Path) -> None:
    driver = PlaywrightDriver(profile=tmp_path)
    driver._connected = True
    driver.context = "owned-fresh-tab"
    page = Mock(spec=Page)
    page.is_closed.return_value = False
    callbacks: list[Callable[[object], None]] = []

    async def expose(_name: str, callback: Callable[[object], None]) -> None:
        callbacks.append(callback)

    page.expose_function = AsyncMock(side_effect=expose)
    driver._pages[driver.context] = page
    await driver.enable_passive_updates()
    assert len(callbacks) == 1
    callbacks[0]({"message_id": "", "text": "", "complete": False, "ambiguous": True})
    update = await driver.wait_capture_update(timeout=0.1)
    assert update is not None and update.source == "dom"
    assert update.status == "unknown" and update.message_id is None and not update.text
    await driver.close()


@pytest.mark.asyncio
async def test_patchright_driver_selects_main_world_for_passive_callbacks(tmp_path: Path) -> None:
    driver = PlaywrightDriver(profile=tmp_path)
    driver.context = "owned-fresh-tab"
    page = Mock(spec=Page)
    page.is_closed.return_value = False
    page.evaluate = AsyncMock(return_value=True)
    driver._pages[driver.context] = page

    assert await driver.eval("main-world observer", main_world=True) is True
    page.evaluate.assert_awaited_with("main-world observer", isolated_context=False)
    assert await driver.eval("scoped DOM check") is True
    page.evaluate.assert_awaited_with("scoped DOM check", isolated_context=True)
