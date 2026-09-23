from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from prompta.core import Prompta, PromptaConfig
from prompta.jobs import PromptJob, add_job, load_jobs


@pytest.mark.asyncio
async def test_restart_after_enqueue_does_not_duplicate_delivery_intent(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.sqlite3"
    state_path = tmp_path / "runtime.sqlite3"
    config = PromptaConfig(jobs_file=jobs_path, state_path=state_path)
    job = PromptJob("durable", "Do durable work", 1800, exact_interval=True)

    first = Prompta(config, "ws://unused")
    first.send_once = AsyncMock(return_value="should-not-run")  # type: ignore[method-assign]

    assert await first._enqueue_scheduled_job(job, now=1000.0) is True
    assert first.send_once.await_count == 0
    assert len(first.scheduler.delivery_intents("durable")) == 1

    restarted = Prompta(config, "ws://unused")
    restarted.send_once = AsyncMock(return_value="conversation-1")  # type: ignore[method-assign]

    assert await restarted._enqueue_scheduled_job(job, now=1001.0) is False
    assert len(restarted.scheduler.delivery_intents("durable")) == 1
    assert await restarted.scheduler_execution.drain_scheduled_deliveries(now=1001.0) is True

    restarted.send_once.assert_awaited_once_with("Do durable work", job_name="durable")
    intents = restarted.scheduler.delivery_intents("durable")
    assert len(intents) == 1
    assert intents[0]["status"] == "delivered"
    assert intents[0]["conversation_id"] == "conversation-1"


@pytest.mark.asyncio
async def test_one_time_job_survives_browser_failure_after_durable_enqueue(
    tmp_path: Path,
) -> None:
    jobs_path = tmp_path / "jobs.sqlite3"
    state_path = tmp_path / "runtime.sqlite3"
    add_job(
        jobs_path,
        "one-time",
        "Run exactly once",
        0,
        exact_interval=True,
        run_at_epoch=1000.0,
    )
    config = PromptaConfig(jobs_file=jobs_path, state_path=state_path)
    first = Prompta(config, "ws://unused")
    first.send_once = AsyncMock(side_effect=RuntimeError("browser unavailable"))  # type: ignore[method-assign]

    job = load_jobs(jobs_path)["one-time"]
    assert await first._enqueue_scheduled_job(job, now=1000.0) is True
    assert "one-time" not in load_jobs(jobs_path)
    assert await first.scheduler_execution.drain_scheduled_deliveries(now=1000.0) is False

    queued = first.scheduler.delivery_intents("one-time")
    assert len(queued) == 1
    assert queued[0]["status"] == "queued"
    assert queued[0]["available_at"] == pytest.approx(1300.0)

    restarted = Prompta(config, "ws://unused")
    restarted.send_once = AsyncMock(return_value="conversation-once")  # type: ignore[method-assign]

    assert await restarted.scheduler_execution.drain_scheduled_deliveries(now=1299.0) is False
    assert load_jobs(jobs_path) == {}

    await restarted.run(once=True)

    assert restarted.send_once.await_count == 1
    assert restarted.send_once.await_args is not None
    args, kwargs = restarted.send_once.await_args
    assert args[0].startswith("Run exactly once")
    assert kwargs == {"job_name": "one-time"}
    delivered = restarted.scheduler.delivery_intents("one-time")
    assert delivered[0]["status"] == "delivered"
    assert delivered[0]["conversation_id"] == "conversation-once"
