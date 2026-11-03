from pathlib import Path

import pytest

from prompta.response_capture import (
    CaptureResult,
    CaptureStatus,
    SseResponseAccumulator,
    StopReason,
    normalize_dom_snapshot,
    parse_sse_body,
)

FIXTURES = Path(__file__).parent / "fixtures" / "passive_response"
CONVERSATION_ID = "d5c86e83-1f55-4ab5-ae50-7e2eed27c33e"


def test_legacy_snapshots_are_replacements_and_filter_private_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("prompta.tool_events.time.time", lambda: 123.0)
    result = parse_sse_body((FIXTURES / "legacy.sse").read_text())
    assert result == CaptureResult(
        source="sse",
        status="complete",
        text="Hello world",
        conversation_id=CONVERSATION_ID,
        message_id="final-1",
        parent_id=None,
        tool_calls=({
            "observed_at": 123.0,
            "id": "tool-1", "connector": "python", "action": "python",
            "status": "running", "arguments": "private tool code", "result": "", "error": "",
        },),
    )


@pytest.mark.parametrize("identities", [["not-an-id"], [123], [CONVERSATION_ID] * 257])
def test_dom_turn_message_id_proof_rejects_malformed_or_unbounded_lists(
    identities: list[object],
) -> None:
    capture = normalize_dom_snapshot({
        "message_id": "unit", "text": "Answer", "complete": True,
        "branch_message_id": CONVERSATION_ID, "turn_message_ids": identities,
        "pathname": "/c/" + CONVERSATION_ID,
    })
    assert capture.turn_message_ids == ()


def test_delta_append_and_patch_with_arbitrary_chunk_boundaries() -> None:
    body = (FIXTURES / "delta.sse").read_text()
    for step in (1, 3, 17, 10000):
        acc = SseResponseAccumulator()
        for start in range(0, len(body), step):
            acc.feed(body[start : start + step])
        acc.finish()
        result = acc.snapshot()
        assert result.status == "complete"
        assert result.text == "Hello world!"
        assert result.message_id == "answer-1"


def test_distinct_final_branches_are_not_concatenated_or_labeled_complete() -> None:
    result = parse_sse_body((FIXTURES / "branches.sse").read_text())
    assert result.status == "unknown"
    assert result.text == ""
    assert result.message_id is None


@pytest.mark.parametrize(
    ("stop_reason", "status"),
    [
        ("timeout", "timeout"),
        ("approval_wait", "approval_wait"),
        ("rate_limited", "rate_limited"),
        ("interrupted", "interrupted"),
        ("unknown", "partial"),
    ],
)
def test_incomplete_stream_reason_is_preserved(
    stop_reason: StopReason, status: CaptureStatus
) -> None:
    result = parse_sse_body((FIXTURES / "incomplete.sse").read_text(), stop_reason=stop_reason)
    assert result.text == "Work in progress"
    assert result.status == status


def test_empty_or_nonfinal_stream_never_claims_success() -> None:
    assert parse_sse_body("data: [DONE]\n\n").status == "unknown"
    only_tool = (
        'data: {"message":{"author":{"role":"assistant"},"recipient":"python",'
        '"content":{"content_type":"text","parts":["secret"]}}}\n\n'
        "data: [DONE]\n\n"
    )
    result = parse_sse_body(only_tool)
    assert result.status == "unknown"
    assert not result.text


def test_branch_parent_conflict_is_ambiguous() -> None:
    msg = (
        '{"conversation_id":"abc","parent_id":"other","message":{"id":"same",'
        '"author":{"role":"assistant"},"channel":"final","recipient":"all",'
        '"content":{"content_type":"text","parts":["new"]}}}'
    )
    body = (
        'data: {"conversation_id":"abc","parent_id":"original","message":{"id":"same",'
        '"author":{"role":"assistant"},"channel":"final","recipient":"all",'
        '"content":{"content_type":"text","parts":["old"]}}}\n\n'
        + "data: " + msg + "\n\n"
        + "data: [DONE]\n\n"
    )
    assert parse_sse_body(body).status == "unknown"


def test_nested_patch_targets_are_bounded_and_exact() -> None:
    body = (
        'data: {"o":"add","p":"/message","v":{"message":{"id":"m1",'
        '"author":{"role":"assistant"},"channel":"final","recipient":"all",'
        '"content":{"content_type":"text","parts":["A"]}}}}\n\n'
        'data: {"o":"patch","v":[{"o":"append","p":"/message/content/parts/0","v":"B"},'
        '{"o":"append","p":"/message/metadata/secret","v":"private"}]}\n\n'
        'data: {"type":"message_stream_complete"}\n\n'
    )
    assert parse_sse_body(body).text == "AB"


def test_dom_normalizer_requires_unique_fresh_assistant_and_completion_evidence() -> None:
    result = normalize_dom_snapshot(
        {"message_id": "new", "text": "Rendered answer", "complete": True, "ambiguous": False}
    )
    assert result.status == "complete"
    assert result.source == "dom"
    assert result.text == "Rendered answer"
    assert normalize_dom_snapshot(
        {"message_id": "new", "text": "Rendered answer", "complete": True, "ambiguous": True}
    ).status == "unknown"
    assert normalize_dom_snapshot({"message_id": "new", "text": "A"}).status == "partial"


def test_dom_normalizer_rejects_missing_identity_and_never_elevates_to_complete() -> None:
    result = normalize_dom_snapshot({"text": "unidentified", "complete": True})
    assert result.status == "unknown"
    assert result.text == ""


def test_completion_does_not_override_rate_limit_or_interruption() -> None:
    body = (FIXTURES / "legacy.sse").read_text()
    assert parse_sse_body(body, stop_reason="rate_limited").status == "rate_limited"
    assert parse_sse_body(body, stop_reason="interrupted").status == "interrupted"


def test_partial_sse_does_not_consume_get_history_mapping() -> None:
    # A GET history payload must never be an alternate parser input.
    body = '{"mapping":{"x":{"message":{"author":{"role":"assistant"},' \
        '"content":{"content_type":"text","parts":["private history"]}}}}}'
    assert parse_sse_body(body).status == "unknown"


def test_intermediate_tool_parents_do_not_poison_final_branch() -> None:
    body = (
        'data: {"conversation_id":"chat","parent_id":"think-parent",'
        '"message":{"id":"thought","author":{"role":"assistant"},'
        '"channel":"analysis","content":{"content_type":"text","parts":["hidden"]}}}\n\n'
        'data: {"conversation_id":"chat","parent_id":"tool-parent",'
        '"message":{"id":"tool","author":{"role":"tool"},'
        '"content":{"content_type":"text","parts":["secret"]}}}\n\n'
        'data: {"conversation_id":"chat","parent_id":"final-parent",'
        '"message":{"id":"answer","author":{"role":"assistant"},'
        '"channel":"final","recipient":"all",'
        '"content":{"content_type":"text","parts":["safe"]}}}\n\n'
        'data: [DONE]\n\n'
    )
    result = parse_sse_body(body)
    assert result.status == "complete"
    assert result.text == "safe"
    assert result.parent_id == "final-parent"


def test_metadata_hidden_analysis_is_never_captured() -> None:
    body = (
        'data: {"message":{"id":"hidden","author":{"role":"assistant"},'
        '"metadata":{"message_type":"analysis","is_visually_hidden_from_conversation":true},'
        '"recipient":"all","content":{"content_type":"text",'
        '"parts":["private reasoning"]}}}\n\n'
        'data: {"message":{"id":"visible","author":{"role":"assistant"},'
        '"recipient":"all","channel":"final","content":{"content_type":"text",'
        '"parts":["public answer"]}}}\n\n'
        'data: [DONE]\n\n'
    )
    result = parse_sse_body(body)
    assert result.status == "complete"
    assert result.text == "public answer"


def test_dom_completion_is_rejected_when_text_must_be_truncated() -> None:
    long_text = "z" * (2 * 1024 * 1024 + 1)
    result = normalize_dom_snapshot(
        {"message_id": "fresh", "text": long_text, "complete": True}
    )
    assert result.status == "partial"
    assert len(result.text) == 2 * 1024 * 1024


def test_adversarial_sse_overflow_does_not_fabricate_completion() -> None:
    accumulator = SseResponseAccumulator()
    accumulator.feed((FIXTURES / "legacy.sse").read_text().replace("data: [DONE]", "data: malformed"))
    accumulator.feed("x" * (4 * 1024 * 1024 + 1))
    accumulator.finish()
    result = accumulator.snapshot()
    assert result.status != "complete"
    assert len(result.text) <= 2 * 1024 * 1024


def test_nonfinal_message_followed_by_patch_cannot_leak_hidden_text() -> None:
    body = (
        'data: {"message":{"id":"a","author":{"role":"assistant"},'
        '"channel":"final","content":{"content_type":"text","parts":["Safe"]}}}\n\n'
        'data: {"message":{"id":"thought","author":{"role":"assistant"},'
        '"channel":"analysis","content":{"content_type":"text","parts":["Secret"]}}}\n\n'
        'data: {"o":"append","p":"/message/content/parts/0","v":"Secret patch"}\n\n'
        'data: [DONE]\n\n'
    )
    result = parse_sse_body(body)
    assert result.text == "Safe"
    assert result.status == "complete"


def test_stream_error_is_terminal_without_exposing_error_payload() -> None:
    accumulator = SseResponseAccumulator()
    accumulator.feed('data: {"type":"error","error":{"message":"internal secret"}}\n\n')
    assert accumulator.progress_events == 1
    result = accumulator.snapshot()
    assert result.stream_error is True
    assert result.status == "interrupted"
    assert "secret" not in result.text


def test_non_error_sse_events_are_activity_even_without_final_text() -> None:
    accumulator = SseResponseAccumulator()
    accumulator.feed('data: {"type":"message","message":{"author":{"role":"assistant"},"channel":"analysis","content":{"content_type":"thoughts"}}}\n\n')
    assert accumulator.progress_events == 1
    assert accumulator.snapshot().stream_error is False


def test_unchanged_generating_dom_does_not_renew_idle_lease() -> None:
    from prompta.response_capture import has_new_capture_activity

    spinner = CaptureResult(
        "dom", "partial", "Still working", CONVERSATION_ID,
        CONVERSATION_ID, None, verified_generating=True,
    )
    assert not has_new_capture_activity(spinner, previous_text="Still working", previous_tools=(), previous_blocks=())
    assert not has_new_capture_activity(spinner, previous_text="Still working", previous_tools=(), previous_blocks=())
    assert has_new_capture_activity(
        CaptureResult("dom", "partial", "New progress", CONVERSATION_ID, CONVERSATION_ID, None),
        previous_text="Still working", previous_tools=(), previous_blocks=(),
    )
    assert has_new_capture_activity(
        CaptureResult(
            "dom", "partial", "Still working", CONVERSATION_ID, CONVERSATION_ID, None,
            tool_calls=({"id": "new-tool"},),
        ),
        previous_text="Still working", previous_tools=(), previous_blocks=(),
    )
    assert has_new_capture_activity(
        CaptureResult(
            "dom", "partial", "Still working", CONVERSATION_ID, CONVERSATION_ID, None,
            display_blocks=({"id": "commentary", "kind": "text", "text": "New commentary"},),
        ),
        previous_text="Still working", previous_tools=(), previous_blocks=(),
    )


def test_owned_sse_progress_counts_even_before_text() -> None:
    from prompta.response_capture import has_new_capture_activity

    progress = CaptureResult(
        "sse", "unknown", "", CONVERSATION_ID, None, None,
        verified_generating=True,
    )
    assert has_new_capture_activity(
        progress, previous_text="", previous_tools=(), previous_blocks=(),
    )
    assert not has_new_capture_activity(
        None, previous_text="", previous_tools=(), previous_blocks=(),
    )


def test_dom_error_signal_requires_explicit_flag() -> None:
    result = normalize_dom_snapshot({
        "message_id": "unit", "text": "", "complete": False,
        "stream_error": True, "pathname": "/c/" + CONVERSATION_ID,
    })
    assert result.stream_error is True
    normal = normalize_dom_snapshot({
        "message_id": "unit", "text": "error in response stream",
        "complete": True, "pathname": "/c/" + CONVERSATION_ID,
    })
    assert normal.stream_error is False
