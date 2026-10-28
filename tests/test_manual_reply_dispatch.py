"""Explicit manual reply cannot leave a verified branch or send twice."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from prompta import manual_reply_dispatch as dispatch
from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.response_capture import CaptureResult
from prompta.scheduler_runtime import SchedulerRuntime

CONVERSATION = "c" * 32
PARENT = "m" * 32
REPLY_ID = "r" * 32


class FakeDriver:
    def __init__(self, *, correct_branch: bool = True) -> None:
        self.correct_branch = correct_branch
        self.is_connected = True
        self.text = ""
        self.calls = 0
        self.capture: dict[str, object] = {}
        self.sent = threading.Event()

    async def connect(self) -> None:
        pass

    async def new_tab(self, _url: str) -> str:
        return "owned-test-tab"

    async def wait_for_composer(self) -> None:
        pass

    async def eval(self, script: str) -> object:
        if "const parent =" in script:
            return self.correct_branch
        return True

    async def dom_state(self) -> dict[str, object]:
        return {"composer_text": self.text, "send_in_progress": False}

    async def enable_passive_updates(self) -> None:
        pass

    async def type_message(self, text: str) -> None:
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
            "sse", "complete", "Synthetic final answer", CONVERSATION, "a" * 32, "u" * 32,
        )

    async def wait_capture_update(self, *, timeout: float) -> None:
        del timeout

    def record_verified_activity(self) -> bool:
        return True

    def clear_send_capture(self, _capture: dict[str, object]) -> None:
        pass

    async def close_context(self, _context: str) -> None:
        pass

    async def close(self) -> None:
        self.is_connected = False


class FakeSender:
    def __init__(self, state_path: Path, *, debugger_address: str) -> None:
        del state_path, debugger_address
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
        "send-1", "test-owner",
        CaptureResult("sse", "complete", "Original answer", CONVERSATION, PARENT, "p" * 32),
    )
    return store, tmp_path / "scheduler.sqlite3"


@pytest.mark.parametrize("correct", [True, False])
def test_explicit_reply_requires_exact_last_assistant_and_single_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, correct: bool,
) -> None:
    store, state = completed_store(tmp_path)
    fake = FakeDriver(correct_branch=correct)
    monkeypatch.setattr(dispatch, "PlaywrightDriver", lambda **_kwargs: fake)
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
        assert turns[-1]["status"] == "prepared"
        assert SchedulerRuntime(state, state).send_gap_remaining(time.time()) == 0


def test_atomic_send_reservation_serializes_manual_and_fresh(tmp_path: Path) -> None:
    state = tmp_path / "state.sqlite3"
    runtime = SchedulerRuntime(state, state)
    assert runtime.reserve_send_attempt(10000.0, manual=True) == 0
    assert runtime.reserve_send_attempt(10001.0) == 2699.0

    other = tmp_path / "concurrent.sqlite3"
    SchedulerRuntime(other, other)
    barrier = threading.Barrier(2)

    def reserve() -> float:
        item = SchedulerRuntime(other, other)
        barrier.wait()
        return item.reserve_send_attempt(20000.0, manual=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: reserve(), range(2)))
    assert sorted(outcomes) == [0, 2700.0]
