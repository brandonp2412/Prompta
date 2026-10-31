"""Deployment imports stay available while editable metadata is rebuilt."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_source_alias_imports_without_site_packages(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    alias = root / "prompta"
    assert alias.is_symlink()
    assert alias.resolve() == (root / "src").resolve()

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root)
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "from pathlib import Path; import prompta; print(Path(prompta.__file__).resolve())",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert Path(result.stdout.strip()) == (root / "src/__init__.py").resolve()


def test_systemd_python_services_use_stable_source_alias() -> None:
    root = Path(__file__).resolve().parents[1]
    for service in (
        "prompta-ui",
        "prompta-delivery-worker",
        "prompta-manual-reply-worker",
        "prompta-scheduler",
        "prompta-browser-watchdog",
    ):
        definition = (root / "systemd" / f"{service}.service").read_text()
        assert "Environment=PYTHONPATH=%h/prompta" in definition
