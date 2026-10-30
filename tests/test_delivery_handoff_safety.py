"""Fail closed when a background fresh-chat handoff loses its receipt."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import prompta.delivery_browser as delivery_browser
from prompta.delivery_browser import (
    BrowserDeliverySender,
    DeliveryBackendUnavailableError,
    SendNotAcceptedError,
)
from prompta.rate_limit import RateLimitError
from prompta.send_outcome import SendOutcomeUnknownError


def _sender(tmp_path: Path) -> BrowserDeliverySender:
    return BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        connector_approval=False,
        delivery_hard_timeout_seconds=0.01,
    )


def test_background_handoff_has_a_bound_and_cannot_blindly_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = _sender(tmp_path)
    monkeypatch.setattr(delivery_browser, "_HANDOFF_GRACE_SECONDS", 0.01)

    async def stuck(_message: str, **kwargs: object) -> None:
        started = kwargs.get("dispatch_started")
        assert isinstance(started, delivery_browser.threading.Event)
        started.set()
        await asyncio.sleep(0.3)

    monkeypatch.setattr(sender, "_send_browser", stuck)
    with pytest.raises(SendOutcomeUnknownError) as caught:
        sender("One fresh chat", send_id="bounded-handoff")
    assert caught.value.stage == "delivery_handoff"


def test_unexpected_error_after_dispatch_is_never_retried_as_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = _sender(tmp_path)

    async def failed(_message: str, **kwargs: object) -> None:
        started = kwargs.get("dispatch_started")
        assert isinstance(started, delivery_browser.threading.Event)
        started.set()
        raise RuntimeError("CDP disconnected after clicking Send")

    monkeypatch.setattr(sender, "_send_browser", failed)
    with pytest.raises(SendOutcomeUnknownError) as caught:
        sender("One fresh chat", send_id="failed-after-dispatch")
    assert caught.value.stage == "post_dispatch"


def test_unexpected_error_before_dispatch_remains_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = _sender(tmp_path)

    async def failed(_message: str, **_kwargs: object) -> None:
        raise DeliveryBackendUnavailableError("Browser was unavailable")

    monkeypatch.setattr(sender, "_send_browser", failed)
    with pytest.raises(DeliveryBackendUnavailableError, match="unavailable"):
        sender("One fresh chat", send_id="failed-before-dispatch")


@pytest.mark.parametrize("exception", [
    RateLimitError("429 rejected"),
    SendNotAcceptedError("400 rejected"),
])
def test_explicit_rejection_stays_retryable_after_click(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exception: Exception,
) -> None:
    sender = _sender(tmp_path)

    async def rejected(_message: str, **kwargs: object) -> None:
        started = kwargs.get("dispatch_started")
        assert isinstance(started, delivery_browser.threading.Event)
        started.set()
        raise exception

    monkeypatch.setattr(sender, "_send_browser", rejected)
    with pytest.raises(type(exception)):
        sender("One fresh chat", send_id="explicit-rejection")
