from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SCRIPT_ROOT = Path(__file__).resolve().parent / "browser_scripts"


@lru_cache
def load_browser_script(name: str) -> str:
    script_name = Path(name)
    if script_name.name != name or script_name.suffix != ".js":
        raise ValueError(f"Invalid browser script name: {name!r}")
    return (_SCRIPT_ROOT / script_name).read_text(encoding="utf-8").rstrip()
