from __future__ import annotations

import time
from pathlib import Path

import pytest

from prompta.delivery_browser import BrowserDeliverySender, DeliveryBackendUnavailableError
from prompta.delivery_worker import DeliveryAdmission
from prompta.playwright_driver import BrowserSecurityChallengeError
from prompta.scheduler_runtime import SchedulerRuntime


def test_security_challenge_cooldown_is_durable_and_blocks_all_delivery(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    first = SchedulerRuntime(path, path)
    assert first.record_security_challenge() >= 3590

    restarted = SchedulerRuntime(path, path)
    assert restarted.security_challenge_remaining() >= 3590
    status = restarted.account_admission_status()
    assert status["blocked"] is True
    assert status["kind"] == "security_challenge"
    allowed, reason, remaining = DeliveryAdmission(
        restarted, resource_admission=lambda: (True, "")
    )(manual=True)
    assert not allowed
    assert "security challenge" in reason
    assert remaining >= 3590

    sender = BrowserDeliverySender(
        path, connector_approval=False,
        driver_factory=lambda: pytest.fail("cooldown must block before browser creation"),
    )
    with pytest.raises(DeliveryBackendUnavailableError, match="security challenge cooldown"):
        sender("Never submit this prompt")


def test_security_challenge_cooldown_escalates_and_expires(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    runtime = SchedulerRuntime(path, path)
    assert runtime.record_security_challenge() >= 3590
    assert runtime.record_security_challenge() >= 7190
    assert runtime.record_security_challenge() >= 14390
    assert runtime.record_security_challenge() >= 21590
    assert runtime.record_security_challenge() <= 21600

    runtime.update_account_state({"security_challenge_backoff": {
        "attempts": 4, "last_seen_epoch": time.time() - 90000,
        "blocked_until_epoch": time.time() - 1,
    }})
    assert runtime.security_challenge_remaining() == 0
    assert 3590 <= runtime.record_security_challenge() <= 3600


@pytest.mark.asyncio
async def test_confirmed_challenge_records_cooldown_without_sending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    sender = BrowserDeliverySender(path, connector_approval=False)
    opened = 0
    closed = 0

    class ChallengedDriver:
        is_connected = True

        async def new_tab(self) -> str:
            nonlocal opened
            opened += 1
            raise BrowserSecurityChallengeError("ChatGPT security challenge blocked navigation")

        async def close(self) -> None:
            nonlocal closed
            closed += 1

    monkeypatch.setattr(sender, "_new_driver", ChallengedDriver)
    with pytest.raises(DeliveryBackendUnavailableError, match="new navigation paused"):
        await sender._send_browser("Never submit this prompt")
    assert (opened, closed) == (1, 1)
    assert sender.runtime.security_challenge_remaining() >= 3590
