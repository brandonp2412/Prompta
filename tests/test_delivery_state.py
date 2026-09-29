from prompta.delivery_state import (
    CompletionAction,
    claimable_delivery,
    completion_action,
    renewable_delivery_lease,
)


def test_claimability_is_deterministic_at_retry_and_lease_boundaries() -> None:
    assert claimable_delivery({"status": "queued"}, now=10.0)
    assert not claimable_delivery({"status": "retrying", "retry_at": 10.1}, now=10.0)
    assert claimable_delivery({"status": "retrying", "retry_at": 10.0}, now=10.0)
    assert claimable_delivery({"status": "rate_limited", "retry_at": 10.0}, now=10.0)
    assert not claimable_delivery({"status": "running", "lease_expires_at": 10.1}, now=10.0)
    assert claimable_delivery({"status": "running", "lease_expires_at": 10.0}, now=10.0)
    assert not claimable_delivery({"status": "succeeded"}, now=10.0)


def test_renewal_requires_current_owner_and_unexpired_running_lease() -> None:
    record = {
        "status": "running",
        "lease_owner": "worker-a",
        "lease_expires_at": 20.0,
    }
    assert renewable_delivery_lease(record, owner="worker-a", now=19.9)
    assert not renewable_delivery_lease(record, owner="worker-b", now=19.9)
    assert not renewable_delivery_lease(record, owner="worker-a", now=20.0)


def test_completion_distinguishes_commit_duplicate_ack_and_rejection() -> None:
    assert (
        completion_action(
            {"status": "running", "lease_owner": "worker-a"},
            owner="worker-a",
        )
        is CompletionAction.COMPLETE
    )
    assert (
        completion_action(
            {"status": "succeeded", "lease_owner": ""},
            owner="stale-worker",
        )
        is CompletionAction.ACKNOWLEDGE
    )
    assert (
        completion_action(
            {"status": "running", "lease_owner": "worker-a"},
            owner="worker-b",
        )
        is CompletionAction.REJECT
    )
    assert (
        completion_action(
            {"status": "outcome_unknown", "lease_owner": ""},
            owner="worker-a",
        )
        is CompletionAction.REJECT
    )
