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

CONVERSATION = "c" * 32
PARENT = "m" * 32
REPLY_ID = "r" * 32


class FakeDriver:
    def __init__(self, *, correct_branch: bool = True) -> None:
        self.correct_branch = correct_branch
        self.is_connected = True
        self.text = ""
        self.calls = 0
        self.type_calls = 0
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
        "send-1",
        "test-owner",
        CaptureResult("sse", "complete", "Original answer", CONVERSATION, PARENT, "p" * 32),
    )
    return store, tmp_path / "scheduler.sqlite3"


@pytest.mark.parametrize("correct", [True, False])
def test_explicit_reply_requires_exact_last_assistant_and_single_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    correct: bool,
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


def test_blank_rich_text_composer_newline_is_not_an_existing_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, state = completed_store(tmp_path)
    fake = FakeDriver(correct_branch=True)
    fake.text = "\n"
    monkeypatch.setattr(dispatch, "PlaywrightDriver", lambda **_kwargs: fake)
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


@pytest.mark.parametrize(
    ("existing_draft", "expected_send"),
    [("Synthetic explicit reply", 1), ("Unrelated human draft", 0)],
)
def test_prepared_reply_reuses_only_an_identical_existing_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    existing_draft: str, expected_send: int,
) -> None:
    store, state = completed_store(tmp_path)
    fake = FakeDriver(correct_branch=True)
    fake.text = existing_draft
    monkeypatch.setattr(dispatch, "PlaywrightDriver", lambda **_kwargs: fake)
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
    assert turns[-1]["status"] == ("completed" if expected_send else "prepared")


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failures: int, expected_sends: int,
) -> None:
    store, state = completed_store(tmp_path)
    fake = FlakyConnectDriver(failures)
    monkeypatch.setattr(dispatch, "PlaywrightDriver", lambda **_kwargs: fake)
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
    assert turns[-1]["status"] == ("completed" if expected_sends else "prepared")


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
    async def eval(self, script: str) -> object:
        if script.strip() == "location.pathname":
            return "/c/" + CONVERSATION
        return await super().eval(script)

    async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
        del timeout
        return CaptureResult(
            "dom", "complete", "DOM-only final answer",
            CONVERSATION, "a" * 32, None, "new:assistant",
        )

    def captured_assistant_response(
        self, _capture: dict[str, object]
    ) -> CaptureResult | None:
        return None


def test_accepted_post_with_exact_dom_final_completes_without_sse_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, state = completed_store(tmp_path)
    fake = DomOnlyDriver()
    monkeypatch.setattr(dispatch, "PlaywrightDriver", lambda **_kwargs: fake)
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


class MissingRouteSseDriver(DomOnlyDriver):
    async def wait_capture_update(self, *, timeout: float) -> None:
        del timeout

    def captured_assistant_response(self, _capture: dict[str, object]) -> CaptureResult:
        return CaptureResult(
            "sse", "complete", "SSE final without conversation field",
            None, "a" * 32, "u" * 32,
        )


def test_exact_owned_route_binds_sse_result_missing_conversation_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, state = completed_store(tmp_path)
    fake = MissingRouteSseDriver()
    monkeypatch.setattr(dispatch, "PlaywrightDriver", lambda **_kwargs: fake)
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
