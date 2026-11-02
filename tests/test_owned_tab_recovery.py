from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Self

import pytest

import prompta.history_recovery as history_recovery
import prompta.owned_tab_recovery as owned
from prompta.history_recovery import HistoryRecovery
from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from prompta.scheduler_runtime import SchedulerRuntime

CONV = "12345678-1234-4123-8123-123456789abc"
OTHER = "12345678-1234-4123-8123-123456789abd"


def _interrupted(store: ResponseStore, send_id: str, conversation: str = CONV) -> None:
    store.ensure_queued(send_id, "Original prompt", now=10)
    assert store.accept(send_id, "123:owner", deadline=100, now=11)
    assert store.bind_conversation_route(send_id, "123:owner", "/c/" + conversation, now=12)
    assert store.finish(send_id, "123:owner", "interrupted", now=100)


def _interrupted_reply(store: ResponseStore, *, send_id: str = "original") -> str:
    parent_id = "87654321-4321-4321-8321-123456789abc"
    store.ensure_queued(send_id, "Original prompt", now=10)
    assert store.accept(send_id, "123:owner", deadline=100, now=11)
    assert store.write(
        send_id, "123:owner",
        CaptureResult("sse", "complete", "Original answer", CONV, parent_id, None),
        now=12,
    )
    replies = ManualReplyStore(store.path)
    reply_id = "reply-for-" + send_id
    intent = ReplyIntent(reply_id, CONV, parent_id, "Follow up")
    assert replies.prepare(send_id, intent, now=13)["status"] == "prepared"
    assert replies.claim(reply_id, "123:reply", deadline=200, now=14)
    assert replies.finish(reply_id, "123:reply", uncertain=True, now=15)
    return reply_id


class _CDPResponse:
    def __init__(self, data: object) -> None:
        self.data = data

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def test_owned_discovery_requires_exact_loopback_targets_and_fresh_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets = [
        {"type": "page", "id": "owned", "url": "https://chatgpt.com/c/" + CONV},
        {"type": "page", "id": "unowned", "url": "https://chatgpt.com/c/" + OTHER},
        {"type": "page", "id": "fake-host", "url": "https://chatgpt.com.evil/c/" + OTHER},
        {"type": "page", "id": "stale", "url": "https://chatgpt.com/c/" + OTHER},
        {"type": "other", "id": "other-type", "url": "https://chatgpt.com/c/" + CONV},
    ]

    class Response(_CDPResponse):
        def read(self) -> bytes:
            return json.dumps(targets).encode()

    calls: list[str] = []

    def urlopen(url: str, timeout: float = 0) -> Response:
        calls.append(url)
        return Response(targets)

    monkeypatch.setattr(owned, "urlopen", urlopen)
    monkeypatch.setattr(
        owned,
        "owned_tab_records",
        lambda _: {
            "owned": 990,
            "stale": -2000,
            "fake-host": 990,
            "other-type": 990,
        },
    )
    matches = owned.surviving_owned_tabs("127.0.0.1:9222", now=1000)
    assert matches == (owned.SurvivingTab("owned", CONV),)
    assert calls == ["http://127.0.0.1:9222/json/list"]
    assert owned.surviving_owned_tabs("example.com:9222", now=1000) == ()
    assert len(calls) == 1
    assert owned._conversation_from_url("https://chatgpt.com/c/" + CONV + "?foo") is None


def test_owned_candidate_pinned_due_only_and_no_ambiguous_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _interrupted(store, "unpinned", OTHER)
    _interrupted(store, "pinned", CONV)
    assert store.set_local_pin("pinned", pinned=True)
    tabs = (
        owned.SurvivingTab("target1", CONV),
        owned.SurvivingTab("target2", OTHER),
    )
    monkeypatch.setattr(owned, "surviving_owned_tabs", lambda *a, **kw: tabs)
    candidate = owned.next_owned_recovery_candidate(store, "127.0.0.1:9222", now=150)
    assert candidate == owned.OwnedRecoveryCandidate("pinned", tabs[0])
    store.schedule_history_recovery("pinned", now=140, next_attempt_at=500)
    candidate = owned.next_owned_recovery_candidate(store, "127.0.0.1:9222", now=150)
    assert candidate == owned.OwnedRecoveryCandidate("pinned", tabs[0])
    # Only the pin itself—not a per-chat retry deadline—makes it outrank
    # an unpinned tab. Unpinning immediately exposes the untouched tab.
    assert store.set_local_pin("pinned", pinned=False)
    candidate = owned.next_owned_recovery_candidate(store, "127.0.0.1:9222", now=150)
    assert candidate == owned.OwnedRecoveryCandidate("unpinned", tabs[1])
    store.schedule_history_recovery("unpinned", now=140, next_attempt_at=500)
    assert owned.next_owned_recovery_candidate(store, "127.0.0.1:9222", now=150) is not None

    monkeypatch.setattr(
        owned,
        "surviving_owned_tabs",
        lambda *a, **kw: (tabs[0], owned.SurvivingTab("target3", CONV)),
    )
    assert owned.next_owned_recovery_candidate(store, "127.0.0.1:9222", now=600) is None


def test_surviving_tabs_round_robin_pinned_with_newest_tiebreak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _interrupted(store, "older", CONV)
    store.ensure_queued("newer", "Newer prompt", now=20)
    assert store.accept("newer", "123:owner", deadline=100, now=21)
    assert store.bind_conversation_route("newer", "123:owner", "/c/" + OTHER, now=22)
    assert store.finish("newer", "123:owner", "interrupted", now=100)
    assert store.set_local_pin("older", pinned=True)
    assert store.set_local_pin("newer", pinned=True)
    store.schedule_history_recovery("newer", now=110, next_attempt_at=125)
    monkeypatch.setattr(
        owned,
        "surviving_owned_tabs",
        lambda *a, **kw: (
            owned.SurvivingTab("old-target", CONV),
            owned.SurvivingTab("new-target", OTHER),
        ),
    )
    candidate = owned.next_owned_recovery_candidate(
        store,
        "127.0.0.1:9222",
        now=150,
    )
    assert candidate == owned.OwnedRecoveryCandidate(
        "older",
        owned.SurvivingTab("old-target", CONV),
    )
    store.schedule_history_recovery("older", now=120, next_attempt_at=9000)
    candidate = owned.next_owned_recovery_candidate(
        store, "127.0.0.1:9222", now=150,
    )
    assert candidate == owned.OwnedRecoveryCandidate(
        "newer", owned.SurvivingTab("new-target", OTHER),
    )


def test_due_owned_tabs_receive_first_attempt_before_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _interrupted(store, "already-tried", CONV)
    _interrupted(store, "never-tried", OTHER)
    assert store.set_local_pin("already-tried", pinned=True)
    assert store.set_local_pin("never-tried", pinned=True)
    store.schedule_history_recovery("already-tried", now=101, next_attempt_at=105)
    monkeypatch.setattr(
        owned,
        "surviving_owned_tabs",
        lambda *a, **kw: (
            owned.SurvivingTab("target1", CONV),
            owned.SurvivingTab("target2", OTHER),
        ),
    )
    candidate = owned.next_owned_recovery_candidate(
        store,
        "127.0.0.1:9222",
        now=150,
    )
    assert candidate is not None and candidate.send_id == "never-tried"


def test_owned_reply_candidate_requires_exact_parent_and_unique_tab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    reply_id = _interrupted_reply(store)
    assert store.set_local_pin("original", pinned=True)
    tab = owned.SurvivingTab("reply-tab", CONV)
    monkeypatch.setattr(owned, "surviving_owned_tabs", lambda *args, **kwargs: (tab,))
    candidate = owned.next_owned_reply_recovery_candidate(
        store, "127.0.0.1:9222", now=150,
    )
    assert candidate is not None
    assert candidate.send_id == "original"
    assert candidate.reply_id == reply_id
    assert candidate.tab == tab
    assert candidate.priority[0] == 1
    assert owned.best_owned_recovery_candidate(
        store, "127.0.0.1:9222", now=150,
    ) == candidate
    monkeypatch.setattr(
        owned, "surviving_owned_tabs",
        lambda *args, **kwargs: (tab, owned.SurvivingTab("second", CONV)),
    )
    assert owned.next_owned_reply_recovery_candidate(
        store, "127.0.0.1:9222", now=150,
    ) is None


def test_owned_reply_recovers_after_429_without_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    reply_id = _interrupted_reply(store)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    before: list[dict[str, object]] = [{"send_id": "original", "status": "completed"}]
    ManualReplyStore(store.path).annotate_response_markers(before)
    assert before[0]["status"] == "outcome_unknown"
    assert before[0]["needs_attention"] is True
    worker = HistoryRecovery(store, runtime, lambda: None, approval_enabled=True)
    monkeypatch.setattr(history_recovery, "_read_backoff_remaining", lambda _: 500.0)
    read_successes: list[bool] = []
    monkeypatch.setattr(runtime, "record_read_success", lambda: read_successes.append(True))
    calls: list[tuple[str, str, str, str, bool]] = []

    async def read(
        conversation: str, original: str, reply: str, parent: str,
        *, resume_approvals: bool,
    ) -> CaptureResult:
        calls.append((conversation, original, reply, parent, resume_approvals))
        return CaptureResult(
            "dom", "complete", "Verified recovered reply", CONV,
            "11111111-1111-4111-8111-111111111111", parent, "reply-unit",
        )

    monkeypatch.setattr(worker, "_read_reply_response", read)
    assert worker.recover_once(
        now=150, preferred_send_id="reply:" + reply_id, owned_tab_recovery=True,
    )
    assert calls == [(
        CONV, "Original prompt", "Follow up",
        "87654321-4321-4321-8321-123456789abc", True,
    )]
    assert read_successes == []
    turn = ManualReplyStore(store.path).get(reply_id)
    assert turn is not None and turn["status"] == "completed"
    assert turn["assistant_text"] == "Verified recovered reply"
    after: list[dict[str, object]] = [{"send_id": "original", "status": "completed"}]
    ManualReplyStore(store.path).annotate_response_markers(after)
    assert after[0]["status"] == "completed"
    assert after[0]["needs_attention"] is False
    assert not worker.recover_once(
        now=240, preferred_send_id="reply:" + reply_id, owned_tab_recovery=True,
    )


def test_targeted_owned_recovery_persists_exact_response_without_resending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _interrupted(store, "target", CONV)
    _interrupted(store, "other", OTHER)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(
        store,
        runtime,
        lambda: owned.ExistingOwnedTabDriver(
            "127.0.0.1:9222",
            owned.SurvivingTab("target-id", CONV),
        ),
        approval_enabled=True,
    )
    monkeypatch.setattr(history_recovery, "_read_backoff_remaining", lambda _: 500.0)
    read_successes: list[bool] = []
    monkeypatch.setattr(runtime, "record_read_success", lambda: read_successes.append(True))
    observed: list[tuple[str, str, bool]] = []

    async def probe(conversation: str, prompt: str, *, resume_approvals: bool) -> CaptureResult:
        observed.append((conversation, prompt, resume_approvals))
        return CaptureResult("dom", "complete", "Recovered answer", CONV, None, None, "turn")

    monkeypatch.setattr(worker, "_read_original_response", probe)
    assert worker.recover_once(now=150, preferred_send_id="target", owned_tab_recovery=True)
    assert observed == [(CONV, "Original prompt", True)]
    assert read_successes == []  # Local DOM success cannot clear the HTTP 429 gate.
    target = store.get("target")
    other = store.get("other")
    assert target is not None and target["status"] == "completed"
    assert other is not None and other["status"] == "interrupted"

    # No eligible target means no fallback to another run or implicit dispatch.
    assert not worker.recover_once(
        now=250, preferred_send_id="nonexistent", owned_tab_recovery=True
    )
    other = store.get("other")
    assert other is not None and other["status"] == "interrupted"


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [False, True])
async def test_attached_driver_proves_target_marker_owner_and_never_navigates_or_closes(
    monkeypatch: pytest.MonkeyPatch,
    reply: bool,
) -> None:
    marker = ("prompta:reply:" if reply else "prompta-delivery:") + "900:1234-dead:abcdef"
    actions: list[str] = []

    class Page:
        url = "https://chatgpt.com/c/" + CONV

        def is_closed(self) -> bool:
            return False

        async def evaluate(self, expression: str, **kwargs: object) -> object:
            actions.append("evaluate")
            return marker if expression == "window.name" else {"verified": True}

        async def close(self) -> None:
            raise AssertionError("No existing tab may be closed")

        async def goto(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("No historical navigation is permitted")

    class Session:
        async def send(self, method: str) -> object:
            return {"targetInfo": {"targetId": "target"}}

        async def detach(self) -> None:
            actions.append("detach")

    class Context:
        pages = [Page()]

        async def new_cdp_session(self, page: Page) -> Session:
            return Session()

    class Browser:
        contexts = [Context()]

    class Chromium:
        async def connect_over_cdp(self, endpoint: str, **kwargs: object) -> Browser:
            actions.append("attach")
            assert endpoint == "http://127.0.0.1:9222"
            return Browser()

    class Patchright:
        chromium = Chromium()

        async def stop(self) -> None:
            actions.append("stop")

    class Starter:
        async def start(self) -> Patchright:
            return Patchright()

    monkeypatch.setattr(owned, "async_playwright", Starter)
    monkeypatch.setattr(owned, "owned_tab_records", lambda _: {"target": 995.0})
    monkeypatch.setattr(owned, "touch_owned_tab", lambda *a: True)
    monkeypatch.setattr(owned, "owned_window_owner_alive", lambda owner: False)
    monkeypatch.setattr(owned.time, "time", lambda: 1000.0)
    driver = owned.ExistingOwnedTabDriver(
        "127.0.0.1:9222",
        owned.SurvivingTab("target", CONV),
        reply=reply,
    )
    await driver.connect()
    await driver.navigate("https://chatgpt.com/c/" + CONV, context=driver.context)
    assert await driver.eval("({verified:true})") == {"verified": True}
    with pytest.raises(RuntimeError, match="forbids navigation"):
        await driver.navigate("https://chatgpt.com/c/" + OTHER, context=driver.context)
    await driver.close()
    assert actions[0] == "attach"
    assert actions[-1] == "stop"


@pytest.mark.asyncio
async def test_tab_rejected_if_original_capture_owner_is_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Page:
        url = "https://chatgpt.com/c/" + CONV

        def is_closed(self) -> bool:
            return False

        async def evaluate(self, _: str, **kwargs: object) -> str:
            return "prompta-delivery:900:1234-active:abcdef"

    class Session:
        async def send(self, _: str) -> object:
            return {"targetInfo": {"targetId": "target"}}

        async def detach(self) -> None:
            pass

    class Context:
        pages = [Page()]

        async def new_cdp_session(self, _: Page) -> Session:
            return Session()

    class Chromium:
        async def connect_over_cdp(self, *args: object, **kwargs: object) -> object:
            return SimpleNamespace(contexts=[Context()])

    class Patchright:
        chromium = Chromium()

        async def stop(self) -> None:
            pass

    class Starter:
        async def start(self) -> Patchright:
            return Patchright()

    monkeypatch.setattr(owned, "async_playwright", Starter)
    monkeypatch.setattr(owned, "owned_tab_records", lambda _: {"target": 995.0})
    monkeypatch.setattr(owned, "owned_window_owner_alive", lambda owner: True)
    monkeypatch.setattr(owned.time, "time", lambda: 1000.0)
    driver = owned.ExistingOwnedTabDriver("127.0.0.1:9222", owned.SurvivingTab("target", CONV))
    try:
        with pytest.raises(RuntimeError, match="not an orphaned"):
            await driver.connect()
    finally:
        await driver.close()
