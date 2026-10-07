from __future__ import annotations

import argparse
import time
import uuid
from pathlib import Path

from prompta.delivery_queue import DeliveryQueueStore
from prompta.persistence import DEFAULT_RUNTIME_PATH

_PENDING_STATUSES = {"queued", "retrying", "rate_limited", "running"}
_TERMINAL_STATUSES = {"succeeded", "outcome_unknown", "dead_lettered", "cancelled"}


def run(state_path: Path, *, timeout_seconds: float) -> str:
    state_path = state_path.expanduser()
    queue = DeliveryQueueStore(state_path.parent / "ui-send-jobs.sqlite3")
    pending = [record for record in queue.records() if record["status"] in _PENDING_STATUSES]
    if pending:
        raise RuntimeError(
            "The delivery queue is busy; wait for existing work before running the ChatGPT E2E."
        )

    token = uuid.uuid4().hex[:12]
    send_id = "prompta-e2e-" + token
    prompt = (
        f"Prompta E2E verification {token}. Please reply with the exact phrase "
        '"PROMPTA_E2E_ACCEPTED".'
    )
    queue.enqueue_idempotent(
        {
            "send_id": send_id,
            "client_id": "prompta-e2e:" + token,
            "message": prompt,
            "created_at": time.time(),
        }
    )

    deadline = time.monotonic() + max(1.0, timeout_seconds)
    while time.monotonic() < deadline:
        record = queue.get(send_id)
        if record is not None and record["status"] in _TERMINAL_STATUSES:
            status = str(record["status"])
            if status == "succeeded":
                print(
                    f"PASS: ChatGPT accepted E2E prompt {token}; "
                    "Prompta discarded its fresh-chat tab. Assistant response was not read."
                )
                return send_id
            raise RuntimeError(
                f"ChatGPT E2E delivery ended with status {status!r}; "
                "the assistant response was not read."
            )
        time.sleep(0.5)

    record = queue.get(send_id)
    if record is not None and record["status"] in {"queued", "retrying", "rate_limited"}:
        queue.cancel_pending(
            send_id,
            error="ChatGPT E2E timed out before dispatch",
        )
    status = str(record["status"]) if record is not None else "missing"
    raise TimeoutError(
        f"ChatGPT E2E timed out with delivery status {status!r}; "
        "if dispatch had started, its tab was handled by Prompta's normal cleanup."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send one labeled prompt through Prompta's live ChatGPT delivery worker."
    )
    parser.add_argument("--state", type=Path, default=DEFAULT_RUNTIME_PATH)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    args = parser.parse_args()
    run(args.state, timeout_seconds=args.timeout_seconds)


if __name__ == "__main__":
    main()
