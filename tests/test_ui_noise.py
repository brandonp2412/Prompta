from __future__ import annotations

from prompta.ui_noise import is_assistant_ui_noise, strip_assistant_ui_noise

NETWORK_ERROR = "A network error occurred. Please check your connection and try again. If this issue persists please contact us through our help center at help.openai.com."
LINKED_NETWORK_ERROR = NETWORK_ERROR.replace(
    "help.openai.com", "[help.openai.com](https://help.openai.com/)"
)


def test_network_error_banner_is_assistant_ui_noise() -> None:
    assert is_assistant_ui_noise(NETWORK_ERROR)
    assert is_assistant_ui_noise(LINKED_NETWORK_ERROR)
    assert is_assistant_ui_noise(NETWORK_ERROR.replace(". Please", ".\nPlease"))


def test_chatgpt_accessibility_heading_is_assistant_ui_noise() -> None:
    assert is_assistant_ui_noise("ChatGPT said:")
    assert is_assistant_ui_noise("#### ChatGPT said:")
    assert strip_assistant_ui_noise("#### ChatGPT said:") == ""


def test_strip_assistant_ui_noise_removes_network_error_between_transcript_text() -> None:
    content = f"Before tool\n\n{LINKED_NETWORK_ERROR}\n\nAfter tool"

    cleaned = strip_assistant_ui_noise(content)

    assert "A network error occurred" not in cleaned
    assert "Before tool" in cleaned
    assert "After tool" in cleaned


def test_strip_assistant_ui_noise_removes_multiline_network_error_banner() -> None:
    multiline = NETWORK_ERROR.replace(". Please", ".\nPlease").replace(". If this", ".\nIf this")

    assert strip_assistant_ui_noise(multiline) == ""


def test_similar_assistant_prose_is_not_filtered() -> None:
    prose = "A network error occurred while I was checking the local service logs."

    assert not is_assistant_ui_noise(prose)
    assert strip_assistant_ui_noise(prose) == prose


def test_partial_transport_status_variants_are_assistant_ui_noise() -> None:
    variants = (
        "Connection interrupted.",
        "Waiting for the complete answer",
        "Connection interrupted. Waiting for the complete answer",
        "A network error occurred.",
        "A network error occurred. Please check your connection and try again.",
    )

    for variant in variants:
        assert is_assistant_ui_noise(variant)
        assert strip_assistant_ui_noise(variant) == ""
