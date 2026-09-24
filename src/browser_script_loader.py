from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SCRIPT_ROOT = Path(__file__).resolve().parent / "browser_scripts"


@lru_cache
def load_browser_script(name: str) -> str:
    script_name = Path(name)
    if script_name.name != name or script_name.suffix != ".js":
        raise ValueError(f"Invalid browser script name: {name!r}")
    return (_SCRIPT_ROOT / script_name).read_text(encoding="utf-8").removesuffix("\n")


def render_browser_script(name: str, **values: Any) -> str:
    script = load_browser_script(name)
    for key, value in values.items():
        marker = f"__{key.upper()}__"
        if marker not in script:
            raise ValueError(f"Browser script {name!r} has no template marker {marker!r}")
        script = script.replace(marker, json.dumps(value))
    return script
