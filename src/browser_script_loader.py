from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SCRIPT_ROOT = Path(__file__).resolve().parent / "browser_scripts"


@lru_cache(maxsize=64)
def _read_versioned_script(path: Path, inode: int, mtime_ns: int, size: int) -> str:
    """Reuse unchanged scripts, but never inject a pre-deployment observer."""
    return path.read_text(encoding="utf-8").rstrip()


def load_browser_script(name: str) -> str:
    script_name = Path(name)
    if script_name.name != name or script_name.suffix != ".js":
        raise ValueError(f"Invalid browser script name: {name!r}")
    path = _SCRIPT_ROOT / script_name
    stat = path.stat()
    source = _read_versioned_script(path, stat.st_ino, stat.st_mtime_ns, stat.st_size)
    # Keep live and historical ChatGPT DOM response serialization identical.
    # The shared source is also cached against its own file version.
    marker = "/* PROMPTA_MARKDOWN_FROM_DOM */"
    if marker in source:
        if name == "markdown_from_dom.js":
            raise ValueError("Recursive Markdown serializer include")
        return source.replace(marker, load_browser_script("markdown_from_dom.js"))
    return source
