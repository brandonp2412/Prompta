import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from prompta.core import Prompta, PromptaConfig, PromptJob


@pytest.mark.asyncio
async def test_control_queue_waits_for_host_headroom(tmp_path: Path) -> None:
    healthy = False

    def admission() -> tuple[bool, str]:
        return (healthy, "" if healthy else "host is busy")

    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
        resource_admission=admission,
    )
    prompta.send_once = AsyncMock(return_value="new-chat")  # type: ignore[method-assign]
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    await prompta._once_requests.put(("Queued send", [], future))

    assert await prompta._drain_once_requests() is False
    assert prompta._once_requests.qsize() == 1
    assert prompta.send_once.await_count == 0
    assert not future.done()

    healthy = True
    prompta._update_scheduler_state({"last_attempt_at": 0.0})

    assert await prompta._drain_once_requests() is True
    assert await future == "new-chat"
    assert prompta._once_requests.empty()
    prompta.cache.close()


@pytest.mark.asyncio
async def test_scheduled_job_waits_for_host_headroom(tmp_path: Path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
        resource_admission=lambda: (False, "memory pressure"),
    )
    prompta.send_once = AsyncMock(return_value="new-chat")  # type: ignore[method-assign]

    assert await prompta._run_job(PromptJob("job", "work", 1800), now=1000.0) is False
    assert prompta.send_once.await_count == 0
    prompta.cache.close()
