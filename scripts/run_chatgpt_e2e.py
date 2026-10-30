from __future__ import annotations

import argparse
import time
import uuid
from pathlib import Path

from prompta.delivery_queue import DeliveryQueueStore
from prompta.persistence import DEFAULT_RUNTIME_PATH
from prompta.response_store import ResponseStore

_TERMINAL_STATUSES = {"succeeded", "outcome_unknown", "dead_lettered", "cancelled"}


def verify_passive_capture(
    results: ResponseStore, send_id: str, expected: str, *, timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + max(1.0, timeout_seconds)
    while time.monotonic() < deadline:
        row = results.get(send_id)
        if row is not None and row["status"] == "completed":
            if (
                str(row["assistant_text"]).strip() == expected
                and row["conversation_id"]
                and row["message_id"]
            ):
                print(f"PASS: Passive final answer and exact branch identity persisted for {send_id}")
                return
            raise RuntimeError(
                f"Passive capture was completed but failed exact-answer/branch validation "
                f"for {send_id}; no response contents were logged."
            )
        time.sleep(1.0)
    row = results.get(send_id)
    status = str(row["status"]) if row is not None else "missing"
    raise TimeoutError(
        f"Passive capture did not complete within the deadline send_id={send_id} "
        f"status={status}. No ChatGPT resend was attempted."
    )


def run(
    state_path: Path, *, timeout_seconds: float, verify_capture: bool = False,
    capture_timeout_seconds: float = 300.0,
) -> str:
    state_path = state_path.expanduser()
    queue = DeliveryQueueStore(state_path.parent / "ui-send-jobs.sqlite3")
    token = uuid.uuid4().hex[:12]
    send_id = "manual-e2e-" + token
    expected = "PROMPTA_E2E_ACCEPTED_" + token.upper()
    prompt = (
        f"Prompta E2E verification {token}. Reply with exactly {expected} "
        "and nothing else."
    )
    queue.enqueue_idempotent(
        {
            "send_id": send_id,
            # A user-requested E2E may run outside scheduled working hours.
            "client_id": "manual:prompta-e2e:" + token,
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
                print(f"PASS: ChatGPT accepted fresh-chat E2E prompt {token}")
                if verify_capture:
                    results = ResponseStore(state_path.parent / "chat-results.sqlite3")
                    verify_passive_capture(
                        results, send_id, expected, timeout_seconds=capture_timeout_seconds,
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
    parser.add_argument("--verify-capture", action="store_true",
                        help="Wait for an exact final answer and durable branch identity")
    parser.add_argument("--capture-timeout-seconds", type=float, default=300.0)
    args = parser.parse_args()
    run(args.state, timeout_seconds=args.timeout_seconds,
        verify_capture=args.verify_capture,
        capture_timeout_seconds=args.capture_timeout_seconds)


if __name__ == "__main__":
    main()
