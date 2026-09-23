"""Load JavaScript browser automation assets from standalone source files."""

from __future__ import annotations

from functools import cache
from importlib.resources import files


@cache
def browser_script(name: str) -> str:
    """Return a packaged browser script by its simple .js filename."""
    if not name.endswith(".js") or "/" in name or "\\" in name:
        raise ValueError(f"Invalid browser script name: {name!r}")
    return files("prompta").joinpath("browser_js", name).read_text(encoding="utf-8").strip()
