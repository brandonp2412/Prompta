from __future__ import annotations

import asyncio

import pytest

from prompta.browser_script_loader import load_browser_script
from prompta.connector_approval_supervisor import supervise_connector_approvals


@pytest.mark.asyncio
async def test_shared_supervisor_approves_successive_dialogs_immediately() -> None:
    observed: list[str] = []
    outcomes: list[object] = [True, True, False]

    async def evaluate(script: str) -> object:
        observed.append(script)
        if outcomes:
            return outcomes.pop(0)
        return False

    count = await supervise_connector_approvals(
        evaluate,
        deadline=asyncio.get_running_loop().time() + 0.03,
        source="live",
        poll_interval_seconds=0.01,
    )
    assert count == 2
    assert len(observed) >= 3
    assert all(script == load_browser_script("approve_connector.js") for script in observed)


@pytest.mark.asyncio
async def test_shared_supervisor_stops_if_original_tab_is_gone() -> None:
    calls = 0

    async def evaluate(_script: str) -> object:
        nonlocal calls
        calls += 1
        return True

    result = await supervise_connector_approvals(
        evaluate,
        deadline=asyncio.get_running_loop().time() + 5,
        source="backup",
        poll_interval_seconds=1.0,
        active=lambda: False,
    )
    assert result == 0
    assert calls == 0


@pytest.mark.asyncio
async def test_shared_supervisor_does_not_retry_stuck_dialog_tightly() -> None:
    calls = 0

    async def evaluate(_script: str) -> object:
        nonlocal calls
        calls += 1
        return "stuck"

    result = await supervise_connector_approvals(
        evaluate,
        deadline=asyncio.get_running_loop().time() + 0.025,
        source="live",
        poll_interval_seconds=0.02,
    )
    assert result == 0
    assert calls <= 2
