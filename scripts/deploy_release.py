"""Build the committed UI/backend release, upload both to Nox, and deploy it."""
from __future__ import annotations

import subprocess
import tarfile
import tempfile
from pathlib import Path


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        args, cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    revision = run("git", "rev-parse", "HEAD", cwd=repo)
    if revision != run("git", "rev-parse", "origin/main", cwd=repo):
        raise RuntimeError("Push the release to origin/main before deployment")
    with tempfile.TemporaryDirectory(prefix="prompta-release-") as temporary:
        root = Path(temporary)
        archive = root / "release.tar"
        run("git", "archive", "--format=tar", f"--output={archive}", revision, cwd=repo)
        source = root / "source"
        source.mkdir()
        with tarfile.open(archive) as contents:
            contents.extractall(source, filter="data")
        for command in (("bun", "install", "--frozen-lockfile"), ("bun", "run", "build")):
            subprocess.run(["buildq", "--wait", "--", *command], cwd=source, check=True)
        # Replace only the UI bundle in the tracked source archive.
        with tarfile.open(archive, "a") as contents:
            contents.add(source / "src/static/app.js", arcname="src/static/app.js")
        remote = run("ssh", "nox", "mktemp -d /tmp/prompta-release-XXXXXXXX")
        try:
            run("scp", str(archive), f"nox:{remote}/release.tar")
            subprocess.run([
                "ssh", "nox",
                f"mkdir {remote}/source && tar -xf {remote}/release.tar -C {remote}/source && "
                f"cd {remote}/source && PYTHONPATH={remote}/source "
                f"$HOME/prompta/.venv/bin/python -m scripts.deploy_guarded "
                f"--archive {remote}/release.tar --revision {revision}",
            ], check=True)
        finally:
            run("ssh", "nox", f"rm -rf {remote}")


if __name__ == "__main__":
    main()
