"""Tests for the diagnostic detector + capture."""
import pytest

from chatgpt_web2api.diagnostics import classify_result, EXPECTED_SHAPES


def test_classify_healthy_list():
    """A list[dict] result with the expected keys is healthy."""
    result = [{"slug": "gpt-5", "title": "GPT-5"}]
    healthy, mismatch = classify_result("get_models", result)
    assert healthy is True
    assert mismatch is None


def test_classify_broken_returns_error_shape():
    """A result that is an {'error': ...} dict is broken."""
    result = {"error": "HTTP 422", "body": "..."}
    healthy, mismatch = classify_result("create_project", result)
    assert healthy is False
    assert "error" in mismatch.lower()


def test_classify_broken_wrong_type():
    """A method promising list[dict] but returning a str is broken (the get_models bug)."""
    result = '{"models": [...]}'  # raw string, not parsed
    healthy, mismatch = classify_result("get_models", result)
    assert healthy is False
    assert "list" in mismatch.lower() or "type" in mismatch.lower()


def test_classify_broken_missing_required_key():
    """A dict result missing a required key is broken."""
    result = {"name": "Foo"}  # no id
    healthy, mismatch = classify_result("create_project", result)
    assert healthy is False
    assert "id" in mismatch


def test_expected_shapes_registry_covers_key_tools():
    """The registry must define shapes for the tools most likely to drift."""
    for fn in ("create_project", "get_models", "get_conversations", "get_memories"):
        assert fn in EXPECTED_SHAPES, f"{fn} missing from EXPECTED_SHAPES"
