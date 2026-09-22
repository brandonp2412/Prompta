from __future__ import annotations

from prompta.stream_order import (
    has_stream_order_inversion,
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
