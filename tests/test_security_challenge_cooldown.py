from __future__ import annotations

import time
from pathlib import Path

import pytest

from prompta.delivery_browser import BrowserDeliverySender, DeliveryBackendUnavailableError
from prompta.delivery_worker import DeliveryAdmission
from prompta.playwright_driver import BrowserSecurityChallengeError
from prompta.scheduler_runtime import SchedulerRuntime


def test_legacy_challenge_cooldown_does_not_block_delivery(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    runtime = SchedulerRuntime(path, path)
    runtime.update_account_state({
        "security_challenge_backoff": {"blocked_until_epoch": time.time() + 7200},
    })

    allowed, reason, delay = DeliveryAdmission(
        runtime, resource_admission=lambda: (True, "")
    )(manual=True)

    assert allowed and not reason and delay == 0
    assert runtime.account_admission_status()["blocked"] is False


@pytest.mark.asyncio
async def test_confirmed_challenge_fails_closed_without_cooldown(
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
    with pytest.raises(DeliveryBackendUnavailableError, match="security challenge blocked navigation"):
        await sender._send_browser("Never submit this prompt")
    assert (opened, closed) == (1, 1)
    assert sender.runtime.account_admission_status()["blocked"] is False
    assert "security_challenge_backoff" not in sender.runtime.account_state()
