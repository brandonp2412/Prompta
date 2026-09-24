from __future__ import annotations

from prompta.stream_order import (
    has_stream_order_inversion,
    observed_prose_blocks,
    recover_stream_order_from_observations,
    stabilize_streaming_content,
)


def _tool(
    *,
    created_at: float = 10.0,
    status: str = "running",
    result: str = "",
) -> str:
    fence = chr(96) * 3
    body = (
        '{"created_at": '
        + str(created_at)
        + ', "status": "'
        + status
        + '", "result": "'
        + result
        + '"}'
    )
    return f"{fence}tool:Test MCP · inspect\n{body}\n{fence}"


def test_streaming_content_keeps_first_seen_block_order() -> None:
    intro = "I will inspect the ordering."
    tool = _tool()
    first = stabilize_streaming_content(intro, f"{tool}\n\n{intro}")
    assert first == f"{intro}\n\n{tool}"

    follow_up = "The cache is reordering existing blocks."
    second = stabilize_streaming_content(
        first,
        f"{tool}\n\n{intro}\n\n{follow_up}",
    )
    assert second == f"{intro}\n\n{tool}\n\n{follow_up}"


def test_streaming_content_updates_matching_tool_in_place() -> None:
    intro = "Inspecting now."
    running = _tool()
    completed = _tool(status="completed", result="ok")

    content = stabilize_streaming_content(
        f"{intro}\n\n{running}",
        f"{completed}\n\n{intro}",
    )

    assert content == f"{intro}\n\n{completed}"
    assert content.count("tool:Test MCP · inspect") == 1


def test_streaming_content_extends_partial_prose_without_duplication() -> None:
    previous = "The first inspection exposed"
    incoming = "The first inspection exposed a tooling mismatch."

    assert stabilize_streaming_content(previous, incoming) == incoming


def test_streaming_content_appends_growth_after_already_visible_tool() -> None:
    intro = "I will inspect."
    tool = _tool()
    previous = f"{intro}\n\n{tool}"
    incoming = f"{tool}\n\n{intro} New streamed text."

    content = stabilize_streaming_content(previous, incoming)

    assert content == f"{intro}\n\n{tool}\n\nNew streamed text."


def test_observed_prose_blocks_preserve_disappearing_progress_updates() -> None:
    observations = [
        (10.0, "Inspecting the failing chat"),
        (20.0, "I found the persistence gap"),
        (30.0, "Fixed and deployed."),
    ]

    assert observed_prose_blocks(observations) == [
        (10.0, "Inspecting the failing chat"),
        (20.0, "I found the persistence gap"),
        (30.0, "Fixed and deployed."),
    ]


def test_observed_prose_blocks_coalesce_streaming_growth_across_observations() -> None:
    observations = [
        (10.0, "Inspecting"),
        (11.0, "Inspecting the failing chat"),
        (20.0, "Inspecting the failing chat\n\nI found the persistence gap"),
    ]

    assert observed_prose_blocks(observations) == [
        (10.0, "Inspecting the failing chat"),
        (20.0, "I found the persistence gap"),
    ]


def test_observation_history_repairs_tool_first_stream_order() -> None:
    intro = "I will inspect the ordering."
    tool = _tool(created_at=20.0)
    follow_up = "The cache is reordering existing blocks."
    content = "\n\n".join(["**Tool activity**", "Thinking", tool, intro, follow_up])
    observations = [
        (10.0, "I will inspect\n\nI will inspect the ordering."),
        (30.0, f"{intro}\n\n{follow_up}"),
    ]

    assert has_stream_order_inversion(content, observations)

    recovered = recover_stream_order_from_observations(content, observations)

    assert recovered == f"{intro}\n\n{tool}\n\n{follow_up}"
    assert not has_stream_order_inversion(recovered, observations)
