"""E2E: a real broken path triggers capture, and doctor auto-discovers + prints it.

Uses create_project (known-broken against the live API: 422 on the nested body)
as the trigger. With capture enabled, calling it writes a redacted artifact;
doctor then auto-discovers it (no human names the function) and prints evidence.

Run with: W2A_E2E_RUN=1 pytest tests/test_e2e_doctor.py -m e2e -v
"""

import json
from pathlib import Path

import pytest

import chatgpt_web2api.diagnostics as dmod
from chatgpt_web2api.cdp_driver import CDPDriver

pytestmark = pytest.mark.e2e


async def test_broken_function_triggers_capture(e2e_driver: CDPDriver, tmp_path, monkeypatch):
    """create_project (broken live) writes a diagnostic artifact when enabled."""
    monkeypatch.setattr(dmod, "_DIAG_DIR", dmod.DiagnosticsDir(base=tmp_path))
    monkeypatch.setattr(dmod, "_capture_enabled", True)

    result = await e2e_driver.create_project(name="W2A-DOCTOR-PROBE", instructions="")
    assert isinstance(result, dict) and "error" in result  # confirms it's broken

    files = list(tmp_path.glob("create_project-*.json"))
    assert len(files) == 1, "expected a capture artifact for the broken call"
    art = json.loads(files[0].read_text())
    assert art["function"] == "create_project"
    assert "422" in str(art["actual"]) or "error" in str(art["actual"]).lower()
    # redaction sanity: no raw auth token leaked into the artifact
    assert "Bearer eyJ" not in files[0].read_text()


async def test_doctor_auto_discovers_and_prints_broken_function(
    e2e_driver: CDPDriver, tmp_path, monkeypatch, capsys
):
    """After capture, doctor auto-discovers create_project + prints its evidence.

    No human names the function — doctor.list_broken_functions reads the dir.
    """
    monkeypatch.setattr(dmod, "_DIAG_DIR", dmod.DiagnosticsDir(base=tmp_path))
    monkeypatch.setattr(dmod, "_capture_enabled", True)
    await e2e_driver.create_project(name="W2A-DOCTOR-PROBE2", instructions="")

    from chatgpt_web2api.doctor import list_broken_functions, latest_artifact_for, print_evidence

    fns = list_broken_functions(tmp_path)
    assert "create_project" in fns

    art = latest_artifact_for(tmp_path, "create_project")
    assert art is not None
    print_evidence(art)
    out = capsys.readouterr().out
    assert "create_project" in out
    assert "MISMATCH" in out
