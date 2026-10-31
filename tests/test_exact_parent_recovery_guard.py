"""Explicit exact-parent recovery remains bounded and account-rate-limit safe."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import prompta.manual_reply_dispatch as dispatch
from prompta.reply_contracts import ManualReplyStore, ReplyConflict

CONVERSATION = "00000000-0000-4000-8000-000000000001"


@pytest.mark.asyncio
@pytest.mark.parametrize("limited", [False, True])
async def test_parent_recovery_waits_only_on_its_owned_tab(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, limited: bool,
) -> None:
    seen: list[str] = []
    store = ManualReplyStore(tmp_path / "replies.sqlite3")
    monkeypatch.setattr(store, "turns", lambda _id: [{
        "status": "unavailable",
        "conversation_id": CONVERSATION,
        "user_text": "saved original prompt",
        "assistant_text": "",
        "message_id": "",
        "reply_id": "",
    }])
    monkeypatch.setattr(dispatch, "_RECOVER_PARENT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(dispatch, "_RECOVER_PARENT_POLL_SECONDS", 0.001)

    class Driver:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def connect(self) -> None:
            seen.append("connected")

        async def new_tab(self, url: str) -> str:
            assert url == f"https://chatgpt.com/c/{CONVERSATION}"
            seen.append("exact-tab")
            return "owned"

        async def wait_for_composer(self) -> None:
            pass

        def history_rate_limited(self) -> bool:
            return limited

        async def eval(self, _script: str) -> None:
            seen.append("probe")
            return None

        async def close_context(self, context: str) -> None:
            assert context == "owned"
            seen.append("close-tab")

        async def close(self) -> None:
            seen.append("close-browser")

    def record_rate_limit(_error: object) -> float:
        seen.append("429-backoff-persisted")
        return 300.0

    monkeypatch.setattr(dispatch, "PlaywrightDriver", Driver)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", lambda *_args, **_kwargs: SimpleNamespace(
        runtime=SimpleNamespace(
            read_backoff_remaining=lambda: 0.0,
            record_read_rate_limit=record_rate_limit,
        ),
        profile=None,
        chrome_path="",
        debugger_address="",
        auth_timeout_seconds=0,
    ))
    worker = dispatch.ManualReplyDispatcher(store, tmp_path / "state")
    with pytest.raises(ReplyConflict, match="cooldown" if limited else "could not be verified"):
        await worker._recover_exact_parent("saved-run")
    assert seen.count("exact-tab") == 1
    assert seen[-2:] == ["close-tab", "close-browser"]
    if limited:
        assert "429-backoff-persisted" in seen
        assert "probe" not in seen
    else:
        assert "429-backoff-persisted" not in seen
        assert "probe" in seen
