"""Deployment-interrupted captures can continue scoped connector approvals without resending."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import prompta.history_recovery as recovery_module
from prompta.history_recovery import HistoryRecovery, _guarded_approval_script
from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from prompta.scheduler_runtime import SchedulerRuntime

CONVERSATION = "12345678-1234-4123-8123-123456789abc"


class ChainedApprovalDriver:
    context = "owned-recovery"

    def __init__(self) -> None:
        self.visited: list[str] = []
        self.grants = 0
        self.approval_checks = 0
        self.closed = False

    async def connect(self) -> None:
        self.visited.append("connect")

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        assert context == self.context
        assert url == "https://chatgpt.com/c/" + CONVERSATION
        self.visited.append(url)

    async def dom_state(self) -> dict[str, object]:
        return {"rate_limit_text": ""}

    async def eval(self, expression: str) -> object:
        assert "Original prompt" in expression
        assert CONVERSATION in expression
        if "return await " in expression:
            self.approval_checks += 1
            assert "proof?.verified !== true" in expression
            assert "users.length !== 1" in expression
            if self.grants < 2:
                self.grants += 1
                return True
            return False
        return {
            "verified": True,
            "ambiguous": False,
            "pathname": "/c/" + CONVERSATION,
            "message_id": "assistant-turn",
            "text": "Recovered final answer" if self.grants == 2 else "Partial",
            "complete": True,  # A copy-ready earlier chunk can precede another Allow prompt.
        }

    async def close(self) -> None:
        self.closed = True


def _interrupted(store: ResponseStore, send_id: str) -> None:
    store.ensure_queued(send_id, "Original prompt", now=10)
    assert store.accept(send_id, "old-worker", deadline=30, now=11)
    assert store.bind_conversation_route(send_id, "old-worker", "/c/" + CONVERSATION, now=12)
    assert store.finish(send_id, "old-worker", "interrupted", now=30)


def test_deploy_recovery_handles_two_sequential_approvals_without_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _interrupted(store, "deployment-capture")
    (tmp_path / "deployment-interrupted.json").write_text(json.dumps({
        "priority": {"job_responses": ["deployment-capture"], "manual_reply_turns": []},
    }))
    driver = ChainedApprovalDriver()
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")

    async def no_delay(_seconds: float) -> None:
        return None

    monkeypatch.setattr(recovery_module.asyncio, "sleep", no_delay)
    worker = HistoryRecovery(store, runtime, lambda: driver, approval_enabled=True)
    assert worker.recover_once(now=100)
    row = store.get("deployment-capture")
    assert row is not None and row["status"] == "completed"
    assert row["assistant_text"] == "Recovered final answer"
    assert driver.grants == 2 and driver.approval_checks == 3
    assert driver.closed
    assert driver.visited == ["connect", "https://chatgpt.com/c/" + CONVERSATION]


@pytest.mark.parametrize(
    ("is_priority", "enabled", "should_continue"),
    [(False, True, False), (True, False, False), (True, True, True)],
)
def test_only_explicitly_enabled_deployment_capture_can_resume_approvals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    is_priority: bool, enabled: bool, should_continue: bool,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _interrupted(store, "run")
    if is_priority:
        (tmp_path / "deployment-interrupted.json").write_text(json.dumps({
            "priority": {"job_responses": ["run"], "manual_reply_turns": []},
        }))
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(store, runtime, ChainedApprovalDriver, approval_enabled=enabled)
    modes: list[bool] = []

    async def fake_read(
        conversation_id: str, prompt: str, *, resume_approvals: bool = False,
    ) -> CaptureResult:
        assert conversation_id == CONVERSATION and prompt == "Original prompt"
        modes.append(resume_approvals)
        return CaptureResult("dom", "complete", "Recovered",
                             CONVERSATION, None, None, "turn")

    monkeypatch.setattr(worker, "_read_original_response", fake_read)
    assert worker.recover_once(now=100)
    assert modes == [should_continue]


def test_approval_script_checks_exact_live_turn_before_any_click() -> None:
    script = _guarded_approval_script(
        '(() => ({ verified: true, ambiguous: false, complete: false }))()',
        single_user_only=True,
    )
    assert "proof?.verified !== true" in script
    assert "proof?.ambiguous === true" in script
    assert "users.length !== 1" in script
    assert "return await " in script
    assert "always allow" in script.lower()
    assert "fetch(" not in script
    assert "click_send" not in script


@pytest.mark.asyncio
async def test_pending_approval_cannot_be_mistaken_for_a_completed_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PendingApproval(ChainedApprovalDriver):
        async def eval(self, expression: str) -> object:
            if "return await " in expression:
                self.approval_checks += 1
                return "pending"
            return {
                "verified": True, "ambiguous": False, "pathname": "/c/" + CONVERSATION,
                "message_id": "assistant-turn", "text": "Copy-ready earlier chunk",
                "complete": True,
            }

    async def no_delay(_seconds: float) -> None:
        return None

    monkeypatch.setattr(recovery_module, "_READ_PROBE_SECONDS", 0.02)
    monkeypatch.setattr(recovery_module.asyncio, "sleep", no_delay)
    driver = PendingApproval()
    worker = HistoryRecovery(
        ResponseStore(tmp_path / "chat-results.sqlite3"),
        SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json"),
        lambda: driver, approval_enabled=True,
    )
    result = await worker._read_original_response(
        CONVERSATION, "Original prompt", resume_approvals=True,
    )
    assert result is not None and result.status == "partial"
    assert driver.approval_checks > 0 and driver.grants == 0
    assert driver.closed


@pytest.mark.asyncio
async def test_trusted_fallback_requires_fresh_exact_branch_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ChangedBranch(ChainedApprovalDriver):
        async def eval(self, expression: str) -> object:
            if "return await " in expression:
                return "stuck"
            if expression.startswith("(async () => { const proof = "):
                return False  # The branch changed between the DOM and trusted click.
            return {
                "verified": True, "ambiguous": False, "pathname": "/c/" + CONVERSATION,
                "message_id": "assistant-turn", "text": "Incomplete answer",
                "complete": False,
            }

        async def click_stuck_connector_approval(self) -> object:
            raise AssertionError("No click after losing exact branch proof")

    async def no_delay(_seconds: float) -> None:
        return None

    monkeypatch.setattr(recovery_module, "_READ_PROBE_SECONDS", 0.02)
    monkeypatch.setattr(recovery_module.asyncio, "sleep", no_delay)
    driver = ChangedBranch()
    worker = HistoryRecovery(
        ResponseStore(tmp_path / "chat-results.sqlite3"),
        SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json"),
        lambda: driver, approval_enabled=True,
    )
    result = await worker._read_original_response(
        CONVERSATION, "Original prompt", resume_approvals=True,
    )
    assert result is not None and result.status == "partial"
    assert driver.closed
