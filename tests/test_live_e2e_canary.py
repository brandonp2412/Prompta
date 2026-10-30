"""Offline proof that the live canary checks final content and exact branch IDs."""
from __future__ import annotations

from pathlib import Path

import pytest

from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from scripts.run_chatgpt_e2e import verify_passive_capture


def test_canary_requires_exact_final_answer_and_both_branch_ids(tmp_path: Path) -> None:
    results = ResponseStore(tmp_path / "chat-results.sqlite3")
    results.ensure_queued("canary", "Synthetic canary", now=10.0)
    assert results.accept("canary", "owner", deadline=30.0, now=11.0)
    capture = CaptureResult(
        "sse", "complete", "PROMPTA_E2E_ACCEPTED_TOKEN",
        "9d95e870-d0ad-43d0-a539-9282359ac7d6",
        "8dbdf809-9d89-47b3-8d40-8f6f4545f39b", None,
    )
    assert results.write("canary", "owner", capture, now=12.0)
    verify_passive_capture(
        results, "canary", "PROMPTA_E2E_ACCEPTED_TOKEN", timeout_seconds=1.0,
    )
    with pytest.raises(RuntimeError, match="failed exact-answer/branch validation"):
        verify_passive_capture(results, "canary", "WRONG_TOKEN", timeout_seconds=1.0)
