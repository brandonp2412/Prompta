from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any


@lru_cache
def load_browser_script(name: str) -> str:
    return (
        files("prompta")
        .joinpath("browser_scripts", name)
        .read_text(encoding="utf-8")
        .removesuffix("\n")
    )


def render_browser_script(name: str, **values: Any) -> str:
    script = load_browser_script(name)
    for key, value in values.items():
        marker = f"__{key}__"
        if marker not in script:
            raise ValueError(f"Browser script {name!r} has no template marker {marker!r}")
        script = script.replace(marker, json.dumps(value))
    return script
