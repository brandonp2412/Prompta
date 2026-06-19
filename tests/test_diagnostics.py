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


# ── redaction + capture (Task 2) ──────────────────────────────

import json
from chatgpt_web2api.diagnostics import redact, DiagnosticsDir


def test_redact_strips_auth_tokens_and_emails():
    """Auth tokens, cookie values, and emails are replaced with <redacted>."""
    s = redact({
        "headers": {"Authorization": "Bearer eyJabc123.def"},
        "cookie": "__Secure-next-auth.session-token=longvalue",
        "email": "user@example.com",
        "url": "https://chatgpt.com/backend-api/conversation/abc-123",
    })
    dumped = json.dumps(s)
    assert "eyJabc123" not in dumped
    assert "<redacted>" in dumped
    # conversation IDs in URLs are NOT PII — keep them
    assert "abc-123" in s["url"]


def test_redact_truncates_long_bodies():
    """Captured response bodies are truncated to a safe size."""
    s = redact({"body": "x" * 10000})
    assert len(s["body"]) <= 2000


def test_capture_artifact_writes_redacted_json(tmp_path):
    """capture writes a redacted JSON file named <func>-<ts>.json."""
    diag = DiagnosticsDir(base=tmp_path)
    path = diag.capture(
        function="create_project",
        request={"expression": "fetch(...)", "data": {"token": "secret"}},
        response={"status": 422, "body": "validation error"},
        expected={"kind": "dict", "required_keys": ["id", "name"]},
        actual={"error": "HTTP 422"},
        mismatch="returned error shape: HTTP 422",
    )
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["function"] == "create_project"
    assert data["mismatch"] == "returned error shape: HTTP 422"
    assert data["request"]["data"]["token"] == "<redacted>"


def test_capture_volume_cap_keeps_newest(tmp_path):
    """Only the N most recent artifacts per function are kept."""
    import time as _time
    diag = DiagnosticsDir(base=tmp_path, max_per_function=3)
    for i in range(5):
        diag.capture(
            function="get_models", request={}, response={}, expected={},
            actual={}, mismatch=f"m{i}",
        )
        _time.sleep(0.01)  # ensure distinct timestamps in filenames
    files = sorted(tmp_path.glob("get_models-*.json"))
    assert len(files) == 3
    kept = [json.loads(f.read_text())["mismatch"] for f in files]
    assert "m4" in kept and "m0" not in kept  # newest kept, oldest evicted
