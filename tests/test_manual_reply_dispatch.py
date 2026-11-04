"""Explicit manual reply cannot leave a verified branch or send twice."""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import update

from prompta import manual_reply_dispatch as dispatch
from prompta.deployment_gate import DeploymentGate
from prompta.reply_contracts import ManualReplyStore, ReplyConflict, ReplyIntent
from prompta.response_capture import CaptureResult
from prompta.response_tables import history_recovery_attempts
from prompta.scheduler_runtime import SchedulerRuntime

CONVERSATION = "c" * 32
PARENT = "m" * 32
REPLY_ID = "r" * 32


def test_exact_parent_recovery_refuses_deploy_pause(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime.sqlite3"
    gate = DeploymentGate(state_path)
    gate.pause_path.touch()
    dispatcher = dispatch.ManualReplyDispatcher(
        ManualReplyStore(tmp_path / "chat-results.sqlite3"), state_path,
    )
    with pytest.raises(ReplyConflict, match="paused for deployment"):
        dispatcher.recover("any-send-id")
    assert dispatcher.inflight_count() == 0


def test_shutdown_inflight_count_includes_read_only_recovery(tmp_path: Path) -> None:
    dispatcher = dispatch.ManualReplyDispatcher(
        ManualReplyStore(tmp_path / "chat-results.sqlite3"),
        tmp_path / "runtime.sqlite3",
    )
    with dispatcher._lock:
        dispatcher._recovering.add("read-only-parent")
    assert dispatcher.active_count() == 0
    assert dispatcher.inflight_count() == 1


class FakeDriver:
    def __init__(self, *, correct_branch: bool = True) -> None:
        self.correct_branch = correct_branch
        self.is_connected = True
        self.text = ""
        self.calls = 0
        self.type_calls = 0
        self.capture: dict[str, object] = {}
        self.sent = threading.Event()

    def history_rate_limited(self) -> bool:
        return False

    async def connect(self) -> None:
        self.is_connected = True

    async def new_tab(self, _url: str) -> str:
        return "owned-test-tab"

    async def wait_for_composer(self) -> None:
        pass

    async def eval(self, script: str, *, main_world: bool = False) -> object:
        if "const parent =" in script:
            return self.correct_branch
        return True

    async def dom_state(self) -> dict[str, object]:
        return {"composer_text": self.text, "send_in_progress": False}

    async def enable_passive_updates(self) -> None:
        pass

    async def type_message(self, text: str) -> None:
        self.type_calls += 1
        self.text = text

    def arm_send_capture(self) -> dict[str, object]:
        self.capture = {"status": 0}
        return self.capture

    async def click_send(self, _text: str) -> None:
        self.calls += 1
        self.capture["status"] = 200
        self.sent.set()

    def captured_send_response(self, _capture: dict[str, object]) -> tuple[str, int] | None:
        return ("synthetic-POST", 200) if self.calls else None

    def captured_assistant_response(self, _capture: dict[str, object]) -> CaptureResult | None:
        if not self.calls:
            return None
        return CaptureResult(
            "sse",
            "complete",
            "Synthetic final answer",
            CONVERSATION,
            "a" * 32,
            "u" * 32,
        )

    async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
        del timeout

    def record_verified_activity(self) -> bool:
        return True

    def clear_send_capture(self, _capture: dict[str, object]) -> None:
        pass

    async def close_context(self, _context: str) -> None:
        pass

    async def close(self) -> None:
        self.is_connected = False


class ErrorSurfaceDriver(FakeDriver):
    def __init__(self, failure: str) -> None:
        super().__init__()
        self.failure = failure

    async def eval(self, script: str, *, main_world: bool = False) -> object:
        if "return 'route_lost'" in script:
            return self.failure
        return await super().eval(script, main_world=main_world)

    def captured_assistant_response(self, _capture: dict[str, object]) -> CaptureResult | None:
        return None

    async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
        await asyncio.sleep(min(timeout, 0.01))
        return None


class MissedFinalDriver(ErrorSurfaceDriver):
    def __init__(self) -> None:
        super().__init__("")

    async def eval(self, script: str, *, main_world: bool = False) -> object:
        if "scanExactReplyTurn" in script:
            return {
                "verified": True, "complete": True,
                "message_id": "a" * 32, "text": "Recovered final answer",
            }
        return await super().eval(script, main_world=main_world)


class MissingAnswerDriver(ErrorSurfaceDriver):
    def __init__(self, *, error_visible: bool = False) -> None:
        super().__init__("")
        self.error_visible = error_visible
        self.probes = 0

    async def eval(self, script: str, *, main_world: bool = False) -> object:
        if "scanExactReplyTurn" in script:
            self.probes += 1
            return {
                "verified": True, "complete": False, "message_id": "",
                "text": "", "has_assistant": False, "generating": False,
                "error_visible": self.error_visible,
            }
        return await super().eval(script, main_world=main_world)


class FakeSender:
    def __init__(self, state_path: Path, *, debugger_address: str) -> None:
        del debugger_address
        self.runtime = SchedulerRuntime(state_path, state_path)
        self.profile = Path("/tmp/not-used")
        self.chrome_path = ""
        self.debugger_address = ""
        self.auth_timeout_seconds = 1.0
        self.connector_approval = False


def completed_store(tmp_path: Path) -> tuple[ManualReplyStore, Path]:
    path = tmp_path / "chat-results.sqlite3"
    store = ManualReplyStore(path)
    now = time.time()
    store.responses.ensure_queued("send-1", "Synthetic original", now=now)
    assert store.responses.accept("send-1", "test-owner", deadline=now + 4000)
    assert store.responses.write(
        "send-1",
        "test-owner",
        CaptureResult("sse", "complete", "Original answer", CONVERSATION, PARENT, "p" * 32),
    )
    return store, tmp_path / "scheduler.sqlite3"


def expire_read_pacing(store: ManualReplyStore) -> None:
    with store.responses.engine.begin() as connection:
        connection.execute(update(history_recovery_attempts).where(
            history_recovery_attempts.c.send_id == "__global_pacing__",
        ).values(next_attempt_at=0))


def test_ready_reply_precedes_missing_parent_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, state = completed_store(tmp_path)
    service = dispatch.ManualReplyDispatcher(store, state)
    turn = store.queue_explicit_send(
        "send-1", ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Saved explicit question"),
    )
    submitted: list[str] = []

    def submit(send_id: str, intent: ReplyIntent) -> dict[str, object]:
        submitted.append(intent.reply_id)
        return turn

    def recover() -> None:
        pytest.fail("Parent recovery must not take a ready reply's read slot")

    monkeypatch.setattr(service, "submit", submit)
    monkeypatch.setattr(service, "_schedule_queued_parent_recovery", recover)
    service.pump_queued()
    assert submitted == [REPLY_ID]


def test_ready_reply_waits_for_global_capacity_without_consuming_a_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, state = completed_store(tmp_path)
    config = tmp_path / "config.toml"
    config.write_text("[concurrency]\nenabled = true\nmax_workers = 1\n")
    service = dispatch.ManualReplyDispatcher(store, state, concurrency_config_path=config)
    store.queue_explicit_send(
        "send-1", ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Saved reply"),
    )
    service.queue.upsert({
        "send_id": "fresh-busy", "message": "Another chat", "status": "queued", "created_at": 100,
    })
    assert service.queue.claim_next("fresh-owner", now=time.time(), lease_seconds=60)
    dispatched: list[str] = []

    def submit(_send_id: str, intent: ReplyIntent) -> dict[str, object]:
        dispatched.append(intent.reply_id)
        saved = store.get(intent.reply_id)
        assert saved is not None
        return saved

    monkeypatch.setattr(service, "submit", submit)
    service.pump_queued()
    assert dispatched == []

    assert service.queue.complete_claim("fresh-busy", "fresh-owner")
    service.pump_queued()
    assert dispatched == [REPLY_ID]


def test_reply_losing_last_slot_remains_prepared_for_later_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, state = completed_store(tmp_path)
    config = tmp_path / "config.toml"
    config.write_text("[concurrency]\nenabled = true\nmax_workers = 1\n")
    fake = FakeDriver()
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state, concurrency_config_path=config)
    turn = store.queue_explicit_send(
        "send-1", ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Saved explicit reply"),
    )
    service.queue.upsert({
        "send_id": "fresh-busy", "message": "Another chat", "status": "queued", "created_at": 100,
    })
    assert service.queue.claim_next("fresh-owner", now=time.time(), lease_seconds=60)

    asyncio.run(service._dispatch(turn))

    saved = store.get(REPLY_ID)
    assert saved is not None and saved["status"] == "prepared"
    assert saved["queued_by_user"] is True
    assert fake.calls == 0
    assert service.queue.complete_claim("fresh-busy", "fresh-owner")
    assert store.next_queued_intent() is not None


def test_ready_reply_shares_history_read_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, state = completed_store(tmp_path)
    fake = FakeDriver()
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    turn = store.queue_explicit_send(
        "send-1", ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Saved explicit question"),
    )
    # A read reserved by another worker must also block a known-parent reply.
    assert store.responses.reserve_history_recovery_global_slot(
        now=time.time(), interval=dispatch.HISTORY_READ_INTERVAL_SECONDS,
    )
    asyncio.run(service._dispatch(turn))
    saved = store.get(REPLY_ID)
    assert saved is not None and saved["status"] == "prepared"
    assert fake.calls == fake.type_calls == 0
    assert fake.is_connected
    expire_read_pacing(store)
    asyncio.run(service._dispatch(saved))
    saved = store.get(REPLY_ID)
    assert saved is not None and saved["status"] == "completed"
    assert fake.calls == 1
    assert store.responses.history_recovery_global_pace_remaining() > 0


@pytest.mark.parametrize("correct", [True, False])
def test_explicit_reply_requires_exact_last_assistant_and_single_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    correct: bool,
) -> None:
    store, state = completed_store(tmp_path)
    fake = FakeDriver(correct_branch=correct)
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    end = time.monotonic() + 3.0
    while time.monotonic() < end:
        last = store.turns("send-1")
        assert last is not None
        if (last[-1]["status"] == "completed") == correct and REPLY_ID not in service._active:
            break
        time.sleep(0.02)
    turns = store.turns("send-1")
    assert turns is not None
    if correct:
        assert fake.calls == 1
        assert turns[-1]["status"] == "completed"
        assert turns[-1]["assistant_text"] == "Synthetic final answer"
        assert service.submit("send-1", intent)["status"] == "completed"
        assert fake.calls == 1
    else:
        assert fake.calls == 0
        assert turns[-1]["status"] == "preflight_failed"
        # The first attempt never claimed a send. A second explicit click with
        # the same immutable intent may verify again, but never auto-retries.
        fake.correct_branch = True
        expire_read_pacing(store)
        assert service.submit("send-1", intent)["status"] == "prepared"
        until = time.monotonic() + 3.0
        while time.monotonic() < until and REPLY_ID in service._active:
            time.sleep(0.02)
        assert fake.calls == 1
        saved = store.get(REPLY_ID)
        assert saved is not None and saved["status"] == "completed"


def test_explicit_reply_respects_shared_resource_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, state = completed_store(tmp_path)
    SchedulerRuntime(state, state).set_resource_admission(False, "synthetic pressure")
    fake = FakeDriver()
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")

    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)

    turns = store.turns("send-1")
    assert turns is not None
    assert turns[-1]["status"] == "preflight_failed"
    assert fake.calls == 0
    assert fake.type_calls == 0
    saved = store.get(REPLY_ID)
    assert saved is not None and saved["user_text"] == intent.text
    assert saved["conversation_id"] == CONVERSATION
    assert saved["parent_id"] == PARENT

    # Resource admission can recover, but only another explicit click with
    # the exact immutable intent may rearm this definitely-unsent request.
    SchedulerRuntime(state, state).set_resource_admission(True, "")
    unsent = store.get(REPLY_ID)
    assert unsent is not None and unsent["status"] == "preflight_failed"
    with pytest.raises(ReplyConflict, match="Idempotency key"):
        service.submit("send-1", ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Changed text"))
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    assert fake.calls == 1
    assert fake.type_calls == 1
    saved = store.get(REPLY_ID)
    assert saved is not None and saved["status"] == "completed"
    assert saved["user_text"] == intent.text
    assert service.submit("send-1", intent)["status"] == "completed"
    assert fake.calls == 1


def test_blank_rich_text_composer_newline_is_not_an_existing_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, state = completed_store(tmp_path)
    fake = FakeDriver(correct_branch=True)
    fake.text = "\n"
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    assert fake.calls == 1
    turns = store.turns("send-1")
    assert turns is not None and turns[-1]["status"] == "completed"


def test_native_mention_reply_verifies_rendered_chip_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, state = completed_store(tmp_path)

    class MentionDriver(FakeDriver):
        async def type_message(self, text: str) -> None:
            assert text == "Synthetic explicit reply @Glass"
            self.text = "Synthetic explicit reply Glass "

    fake = MentionDriver(correct_branch=True)
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply @Glass")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    assert fake.calls == 1
    turns = store.turns("send-1")
    assert turns is not None and turns[-1]["status"] == "completed"


@pytest.mark.parametrize(
    ("existing_draft", "expected_send"),
    [("Synthetic explicit reply", 1), ("Unrelated human draft", 0)],
)
def test_prepared_reply_reuses_only_an_identical_existing_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    existing_draft: str,
    expected_send: int,
) -> None:
    store, state = completed_store(tmp_path)
    fake = FakeDriver(correct_branch=True)
    fake.text = existing_draft
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    assert fake.calls == expected_send
    assert fake.type_calls == 0
    turns = store.turns("send-1")
    assert turns is not None
    assert turns[-1]["status"] == ("completed" if expected_send else "preflight_failed")


class FlakyConnectDriver(FakeDriver):
    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures
        self.connect_attempts = 0

    async def connect(self) -> None:
        self.connect_attempts += 1
        if self.connect_attempts <= self.failures:
            raise RuntimeError("Synthetic authentication connection failure")
        self.is_connected = True


@pytest.mark.parametrize(("failures", "expected_sends"), [(1, 1), (2, 0)])
def test_manual_reply_retries_only_preclaim_browser_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failures: int,
    expected_sends: int,
) -> None:
    store, state = completed_store(tmp_path)
    fake = FlakyConnectDriver(failures)
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 4.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    turns = store.turns("send-1")
    assert turns is not None
    assert fake.connect_attempts == 2
    assert fake.calls == expected_sends
    assert turns[-1]["status"] == ("completed" if expected_sends else "preflight_failed")


def test_atomic_manual_claim_is_exactly_once_across_workers(tmp_path: Path) -> None:
    store, _state = completed_store(tmp_path)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert store.prepare("send-1", intent)["status"] == "prepared"
    barrier = threading.Barrier(2)

    def claim(worker_number: int) -> bool:
        independent = ManualReplyStore(tmp_path / "chat-results.sqlite3")
        barrier.wait()
        return independent.claim(
            REPLY_ID,
            f"worker-{worker_number}",
            deadline=time.time() + 100,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(claim, range(2)))
    assert sorted(outcomes) == [False, True]
    turns = store.turns("send-1")
    assert turns is not None
    assert turns[-1]["status"] == "dispatching"


class DomOnlyDriver(FakeDriver):
    async def eval(self, script: str, *, main_world: bool = False) -> object:
        if script.strip() == "location.pathname":
            return "/c/" + CONVERSATION
        return await super().eval(script)

    async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
        del timeout
        return CaptureResult(
            "dom",
            "complete",
            "DOM-only final answer",
            CONVERSATION,
            "a" * 32,
            None,
            "new:assistant",
        )

    def captured_assistant_response(self, _capture: dict[str, object]) -> CaptureResult | None:
        return None


def test_accepted_post_with_exact_dom_final_completes_without_sse_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, state = completed_store(tmp_path)
    fake = DomOnlyDriver()
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    turns = store.turns("send-1")
    assert turns is not None and turns[-1]["status"] == "completed"
    assert turns[-1]["assistant_text"] == "DOM-only final answer"
    assert turns[-1]["parent_id"] == PARENT
    assert fake.calls == 1


def test_unchanged_dom_generating_does_not_extend_manual_reply_idle_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnchangedGeneratingDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.activity_calls = 0
            self.observations = 0

        def record_verified_activity(self) -> bool:
            self.activity_calls += 1
            return True

        def captured_assistant_response(self, _capture: dict[str, object]) -> CaptureResult | None:
            return None

        async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
            await asyncio.sleep(min(timeout, 0.01))
            self.observations += 1
            if self.observations == 30:
                self.is_connected = False  # Bound the broken implementation too.
            return CaptureResult(
                "dom", "unknown", "", CONVERSATION, "a" * 32, None,
                verified_generating=True,
            )

    store, state = completed_store(tmp_path)
    fake = UnchangedGeneratingDriver()
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    monkeypatch.setattr(dispatch, "MAX_OWNED_TAB_AGE_SECONDS", 0.12)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.01)
    assert REPLY_ID not in service._active
    turns = store.turns("send-1")
    assert turns is not None and turns[-1]["status"] == "interrupted"
    assert fake.activity_calls == 1  # Accepted POST only; unchanged DOM isn't activity.
    assert fake.observations < 30  # The idle deadline, not disconnect, ended capture.


@pytest.mark.parametrize("failure", ["error_surface", "route_lost"])
def test_accepted_reply_releases_broken_owned_page_for_read_only_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    store, state = completed_store(tmp_path)
    fake = ErrorSurfaceDriver(failure)
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    monkeypatch.setattr(dispatch, "_CAPTURE_SURFACE_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(dispatch, "_CAPTURE_SURFACE_RECHECK_SECONDS", 0.01)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    turns = store.turns("send-1")
    assert turns is not None and turns[-1]["status"] == "interrupted"
    assert turns[-1]["message_id"] == ""
    assert fake.calls == 1
    recovered = store.next_history_reply_recovery(priority_ids={REPLY_ID})
    assert recovered is not None and recovered["reply_id"] == REPLY_ID


def test_accepted_reply_reconciles_missed_dom_completion_without_resending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, state = completed_store(tmp_path)
    fake = MissedFinalDriver()
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    monkeypatch.setattr(dispatch, "_CAPTURE_SURFACE_GRACE_SECONDS", 0.0)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    turns = store.turns("send-1")
    assert turns is not None and turns[-1]["status"] == "completed"
    assert turns[-1]["assistant_text"] == "Recovered final answer"
    assert turns[-1]["message_id"] == "a" * 32
    assert fake.calls == 1


@pytest.mark.parametrize("error_visible", [False, True])
def test_accepted_reply_without_answer_releases_after_verified_idle_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_visible: bool,
) -> None:
    store, state = completed_store(tmp_path)
    fake = MissingAnswerDriver(error_visible=error_visible)
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    monkeypatch.setattr(dispatch, "_CAPTURE_SURFACE_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(dispatch, "_CAPTURE_SURFACE_RECHECK_SECONDS", 0.01)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    turns = store.turns("send-1")
    assert turns is not None and turns[-1]["status"] == "interrupted"
    assert fake.probes == (1 if error_visible else 2)
    assert fake.calls == 1
    recovery = store.next_history_reply_recovery(priority_ids={REPLY_ID})
    assert recovery is not None and recovery["reply_id"] == REPLY_ID


class AmbiguousThenCompleteDriver(DomOnlyDriver):
    def __init__(self) -> None:
        super().__init__()
        self.observations = 0

    async def wait_capture_update(self, *, timeout: float) -> CaptureResult:
        del timeout
        self.observations += 1
        if self.observations == 1:
            return CaptureResult("dom", "unknown", "", None, None, None)
        return CaptureResult(
            "dom", "complete", "Recovered final after ambiguous hydration",
            CONVERSATION, "a" * 32, None, "new:assistant",
        )


def test_transient_ambiguous_dom_does_not_interrupt_accepted_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, state = completed_store(tmp_path)
    fake = AmbiguousThenCompleteDriver()
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    turns = store.turns("send-1")
    assert turns is not None
    assert fake.calls == 1
    assert fake.observations >= 2
    assert turns[-1]["status"] == "completed"
    assert turns[-1]["assistant_text"] == "Recovered final after ambiguous hydration"


class AmbiguousWrongRouteDriver(AmbiguousThenCompleteDriver):
    async def eval(self, script: str, *, main_world: bool = False) -> object:
        if script.strip() == "location.pathname":
            return "/c/unrelated"
        return await super().eval(script)


def test_ambiguous_dom_after_leaving_owned_branch_interrupts_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, state = completed_store(tmp_path)
    fake = AmbiguousWrongRouteDriver()
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    turns = store.turns("send-1")
    assert turns is not None
    assert fake.calls == 1
    assert fake.observations == 1
    assert turns[-1]["status"] == "interrupted"
    assert not turns[-1]["assistant_text"]


class MissedPostDriver(FakeDriver):
    def __init__(self, *, verified: bool) -> None:
        super().__init__()
        self.verified = verified

    async def eval(self, script: str, *, main_world: bool = False) -> object:
        if "const targetReply =" in script:
            return {
                "verified": self.verified,
                "complete": self.verified,
                "message_id": "a" * 32 if self.verified else "",
                "text": "Verified DOM final" if self.verified else "",
            }
        return await super().eval(script)

    def captured_send_response(self, _capture: dict[str, object]) -> None:
        return None

    def captured_assistant_response(self, _capture: dict[str, object]) -> None:
        return None


@pytest.mark.parametrize("verified", [True, False])
def test_exact_dom_reply_confirmation_survives_missed_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verified: bool,
) -> None:
    store, state = completed_store(tmp_path)
    fake = MissedPostDriver(verified=verified)
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    monkeypatch.setattr(dispatch, "_CONFIRM_SECONDS", 0.02)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    turns = store.turns("send-1")
    assert turns is not None
    assert turns[-1]["status"] == ("completed" if verified else "outcome_unknown")
    assert turns[-1]["assistant_text"] == ("Verified DOM final" if verified else "")
    assert fake.calls == 1


class MissingRouteSseDriver(DomOnlyDriver):
    async def wait_capture_update(self, *, timeout: float) -> None:
        del timeout

    def captured_assistant_response(self, _capture: dict[str, object]) -> CaptureResult:
        return CaptureResult(
            "sse",
            "complete",
            "SSE final without conversation field",
            None,
            "a" * 32,
            "u" * 32,
        )


def test_exact_owned_route_binds_sse_result_missing_conversation_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, state = completed_store(tmp_path)
    fake = MissingRouteSseDriver()
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Synthetic explicit reply")
    assert service.submit("send-1", intent)["status"] == "prepared"
    until = time.monotonic() + 3.0
    while time.monotonic() < until and REPLY_ID in service._active:
        time.sleep(0.02)
    turns = store.turns("send-1")
    assert turns is not None and turns[-1]["status"] == "completed"
    assert turns[-1]["assistant_text"] == "SSE final without conversation field"


@pytest.mark.parametrize("already_blocked", [False, True])
@pytest.mark.parametrize("composer_fails", [False, True])
def test_unsent_reply_waits_for_read_cooldown_then_sends_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, already_blocked: bool,
    composer_fails: bool,
) -> None:
    store, state = completed_store(tmp_path)

    class LimitedDriver(FakeDriver):
        limited = not already_blocked
        opened = 0

        async def new_tab(self, _url: str) -> str:
            self.opened += 1
            return await super().new_tab(_url)

        async def wait_for_composer(self) -> None:
            if self.limited and composer_fails:
                raise TimeoutError("Conversation read rejected")

        def history_rate_limited(self) -> bool:
            return self.limited

        async def eval(self, script: str, *, main_world: bool = False) -> object:
            if "const parent =" in script and self.limited:
                return False
            return await super().eval(script, main_world=main_world)

    fake = LimitedDriver()
    monkeypatch.setattr(dispatch, "PatchrightDriver", lambda **_kwargs: fake)
    monkeypatch.setattr(dispatch, "BrowserDeliverySender", FakeSender)
    service = dispatch.ManualReplyDispatcher(store, state)
    intent = ReplyIntent(REPLY_ID, CONVERSATION, PARENT, "Saved explicit question")
    turn = store.queue_explicit_send("send-1", intent)
    if already_blocked:
        service.runtime.record_read_rate_limit(dispatch.RateLimitError())
    asyncio.run(service._dispatch(turn))
    saved = store.get(REPLY_ID)
    assert saved is not None and saved["status"] == "prepared"
    assert fake.calls == fake.type_calls == 0
    assert fake.opened == (0 if already_blocked else 1)
    assert service.runtime.read_backoff_remaining() > 0
    service.pump_queued()
    assert not service._active

    # Expire the durable cooldown without waiting or changing the intent.
    service.runtime.update_account_state({"read_rate_limit_backoff": {}})
    service.runtime.update_scheduler_state({"read_rate_limit_backoff": {}})
    expire_read_pacing(store)
    fake.limited = False
    asyncio.run(service._dispatch(saved))
    saved = store.get(REPLY_ID)
    assert saved is not None and saved["status"] == "completed"
    assert fake.calls == 1
    assert fake.type_calls == 1
