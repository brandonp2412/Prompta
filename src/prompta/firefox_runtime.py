from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

async def firefox_port_is_open(port: int) -> bool:
    try:
        _reader, writer = await asyncio.open_connection("127.0.0.1", port)
    except OSError:
        return False
    writer.close()
    await writer.wait_closed()
    return True
async def terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            return
        await process.wait()
def firefox_profile_owner_pid(profile: Path) -> int | None:
    try:
        target = os.readlink(profile / "lock")
    except (FileNotFoundError, OSError):
        return None
    match = re.search(r"\+(\d+)$", target)
    return int(match.group(1)) if match is not None else None
def firefox_process_uses_profile(pid: int, profile: Path) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    try:
        arguments = [
            value.decode("utf-8", errors="replace")
            for value in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            if value
        ]
    except OSError:
        return True
    if not arguments or Path(arguments[0]).name != "firefox":
        return False
    resolved = str(profile.resolve())
    return any(
        argument == resolved
        for index, argument in enumerate(arguments)
        if index > 0 and arguments[index - 1] == "--profile"
    )

async def spawn_firefox(
    profile: Path,
    firefox_path: str,
    port: int,
    *,
    port_is_open,
    process_uses_profile,
    wait_for_port_fn,
    terminate_process_fn,
    profile_release_timeout_seconds: float,
    reuse_poll_seconds: float,
    reuse_stability_checks: int,
) -> asyncio.subprocess.Process | None:
    resolved = profile.expanduser().resolve()
    if not resolved.is_dir():
        raise RuntimeError(f"Firefox profile does not exist: {resolved}")
    if await port_is_open(port):
        listener_stable = True
        for _ in range(reuse_stability_checks):
            await asyncio.sleep(reuse_poll_seconds)
            if not await port_is_open(port):
                listener_stable = False
                break
        if listener_stable:
            logger.info("Prompta reusing Firefox already listening on port %d", port)
            return None
        logger.info(
            "Prompta Firefox listener on port %d disappeared during reuse check",
            port,
        )

    owner_pid = firefox_profile_owner_pid(resolved)
    if owner_pid is not None and process_uses_profile(owner_pid, resolved):
        logger.info(
            "Prompta Firefox profile is still owned by pid=%d; waiting for it to exit",
            owner_pid,
        )
        deadline = (
            asyncio.get_running_loop().time()
            + profile_release_timeout_seconds
        )
        while process_uses_profile(owner_pid, resolved):
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError(
                    "Firefox profile is still in use after "
                    f"{profile_release_timeout_seconds:.0f}s "
                    f"(pid={owner_pid})"
                )
            await asyncio.sleep(reuse_poll_seconds)
            if await port_is_open(port):
                listener_stable = True
                for _ in range(reuse_stability_checks):
                    await asyncio.sleep(reuse_poll_seconds)
                    if not await port_is_open(port):
                        listener_stable = False
                        break
                if listener_stable:
                    logger.info(
                        "Prompta reusing Firefox already listening on port %d",
                        port,
                    )
                    return None
        logger.info(
            "Prompta previous Firefox pid=%d released the profile; starting a fresh browser",
            owner_pid,
        )

    for name in ("lock", ".parentlock"):
        try:
            os.unlink(resolved / name)
        except FileNotFoundError:
            pass
    firefox_tmp = resolved.parent / "firefox-tmp"
    firefox_tmp.mkdir(parents=True, exist_ok=True)
    os.chmod(firefox_tmp, 0o700)
    environment = os.environ.copy()
    environment["TMPDIR"] = str(firefox_tmp)
    process = await asyncio.create_subprocess_exec(
        firefox_path,
        "--headless",
        "--profile",
        str(resolved),
        "--remote-debugging-port",
        str(port),
        "-remote-allow-system-access",
        "https://chatgpt.com/",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env=environment,
    )
    try:
        await wait_for_port_fn(port)
    except BaseException:
        await terminate_process_fn(process)
        raise
    return process
