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
    for marker, dependency in (
        ("/* PROMPTA_MARKDOWN_FROM_DOM */", "markdown_from_dom.js"),
        ("/* PROMPTA_REPLY_TURN_SCAN */", "reply_turn_scan.js"),
    ):
        if marker in source:
            if name == dependency:
                raise ValueError("Recursive browser script include")
            source = source.replace(marker, load_browser_script(dependency))
    return source
