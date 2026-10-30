"""Bound the legacy connector-approved handoff without risking duplicate sends."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import prompta.delivery_browser as delivery_browser
from prompta.delivery_browser import BrowserDeliverySender, DeliveryBackendUnavailableError
from prompta.rate_limit import RateLimitError
from prompta.send_outcome import SendOutcomeUnknownError


def _sender(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BrowserDeliverySender:
    monkeypatch.setattr(delivery_browser, "_HANDOFF_GRACE_SECONDS", 0.01)
    return BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        connector_approval=True,
        delivery_hard_timeout_seconds=0.01,
    )


@pytest.mark.parametrize("after_dispatch", [False, True])
def test_stalled_connector_handoff_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, after_dispatch: bool,
) -> None:
    sender = _sender(tmp_path, monkeypatch)

    async def stuck(_message: str, **kwargs: object) -> None:
        started = kwargs.get("dispatch_started")
        assert isinstance(started, delivery_browser.threading.Event)
        if after_dispatch:
            started.set()
        await asyncio.sleep(0.3)

    monkeypatch.setattr(sender, "_send_browser", stuck)
    if after_dispatch:
        with pytest.raises(SendOutcomeUnknownError) as caught:
            sender("One connector-approved chat")
        assert caught.value.stage == "delivery_handoff"
    else:
        with pytest.raises(DeliveryBackendUnavailableError, match="before dispatch"):
            sender("One connector-approved chat")


def test_connector_failure_after_click_is_not_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = _sender(tmp_path, monkeypatch)

    async def failed(_message: str, **kwargs: object) -> None:
        started = kwargs.get("dispatch_started")
        assert isinstance(started, delivery_browser.threading.Event)
        started.set()
        raise RuntimeError("Browser lost the accepted send")

    monkeypatch.setattr(sender, "_send_browser", failed)
    with pytest.raises(SendOutcomeUnknownError) as caught:
        sender("One connector-approved chat")
    assert caught.value.stage == "post_dispatch"


def test_connector_explicit_rejection_remains_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = _sender(tmp_path, monkeypatch)

    async def rejected(_message: str, **kwargs: object) -> None:
        started = kwargs.get("dispatch_started")
        assert isinstance(started, delivery_browser.threading.Event)
        started.set()
        raise RateLimitError("429 rejected")

    monkeypatch.setattr(sender, "_send_browser", rejected)
    with pytest.raises(RateLimitError):
        sender("One connector-approved chat")
