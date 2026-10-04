from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .delivery_queue import DeliveryQueueStore
from .jobs import DEFAULT_INTERVAL_SECONDS, PromptJob, add_job, clear_jobs, load_jobs, remove_job
from .persistence import DEFAULT_RUNTIME_PATH
from .scheduler_runtime import SchedulerRuntime

DEFAULT_JOBS_PATH = DEFAULT_RUNTIME_PATH
DEFAULT_STATE_PATH = DEFAULT_RUNTIME_PATH
PROMPTA_HOST_ENV = "PROMPTA_HOST"
PROMPTA_REMOTE_CLI_ENV = "PROMPTA_REMOTE_CLI"
DEFAULT_REMOTE_CLI = "/home/brandon/.local/bin/prompta"
HOST_CONFIG_PATH = Path.home() / ".config" / "prompta" / "host"


def _configured_host() -> str:
    configured = os.environ.get(PROMPTA_HOST_ENV)
    if configured is not None:
        return configured.strip()
    try:
        return HOST_CONFIG_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _is_local_target(host: str) -> bool:
    normalized = host.strip().casefold()
    if normalized in {"", "local", "localhost", "127.0.0.1", "::1"}:
        return True
    hostname = socket.gethostname().casefold()
    return normalized in {hostname, hostname.split(".", 1)[0]}


def _dispatch_remote(argv: list[str]) -> int | None:
    if "--jobs-file" in argv or "--state" in argv:
        return None

    host = _configured_host()
    if _is_local_target(host):
        return None

    remote_cli = os.environ.get(PROMPTA_REMOTE_CLI_ENV, DEFAULT_REMOTE_CLI).strip()
    if not remote_cli:
        remote_cli = DEFAULT_REMOTE_CLI

    remote_command = shlex.join(
        ["env", f"{PROMPTA_HOST_ENV}=local", remote_cli, *argv]
    )
    try:
        completed = subprocess.run(["ssh", host, remote_command], check=False)
    except FileNotFoundError:
        print("prompta: ssh is required for remote job management", file=sys.stderr)
        return 127
    return completed.returncode



def set_job_paused(path: Path, state_path: Path, name: str, paused: bool) -> bool:
    return SchedulerRuntime(state_path, path).set_job_paused(name, paused)


def set_all_jobs_paused(path: Path, state_path: Path, paused: bool) -> int:
    return SchedulerRuntime(state_path, path).set_all_jobs_paused(paused)


def _cancel_pending_delivery(
    jobs_path: Path,
    state_path: Path,
    name: str,
    *,
    error: str,
) -> bool:
    state = SchedulerRuntime(state_path, jobs_path).job_state(name)
    send_id = str(state.get("last_delivery_send_id") or "")
    if not send_id:
        return False
    queue = DeliveryQueueStore(state_path.expanduser().parent / "ui-send-jobs.sqlite3")
    return queue.cancel_pending(send_id, error=error)


def _jobs_payload(path: Path, state_path: Path) -> list[dict[str, object]]:
    runtime = SchedulerRuntime(state_path, path)
    jobs = load_jobs(path)
    result: list[dict[str, object]] = []
    for job in jobs.values():
        state = runtime.job_state(job.name)
        result.append(
            {
                "name": job.name,
                "prompt": job.prompt,
                "interval_seconds": job.interval_seconds,
                "daily_at": job.daily_at,
                "exact_interval": job.exact_interval,
                "run_at_epoch": job.run_at_epoch,
                "paused": state.get("paused") is True,
                "status": state.get("status") or "pending",
            }
        )
    return result


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "now"
    total_minutes = max(1, int(seconds / 60 + 0.5))
    days, remainder = divmod(total_minutes, 60 * 24)
    hours, minutes = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h" if hours else f"{days}d"
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m"


def _parse_run_at(value: str, *, now: float | None = None) -> float:
    candidate = value.strip()
    current = (
        datetime.now().astimezone() if now is None else datetime.fromtimestamp(now).astimezone()
    )

    try:
        parsed_time = datetime.strptime(candidate, "%H:%M")
    except ValueError:
        parsed_time = None

    if parsed_time is not None:
        scheduled = current.replace(
            hour=parsed_time.hour,
            minute=parsed_time.minute,
            second=0,
            microsecond=0,
        )
        if scheduled <= current:
            scheduled += timedelta(days=1)
        return scheduled.timestamp()

    try:
        scheduled = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(
            "time must be HH:MM or an ISO local datetime like 2026-10-02T13:00"
        ) from exc

    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=current.tzinfo)
    if scheduled.timestamp() <= current.timestamp():
        raise ValueError("scheduled time must be in the future")
    return scheduled.timestamp()


def _format_next_due(runtime: SchedulerRuntime, job: PromptJob, now: float | None = None) -> str:
    current = time.time() if now is None else now
    remaining = runtime.due_in(job, current)
    when = datetime.fromtimestamp(current + remaining).astimezone().strftime("%Y-%m-%d %H:%M")
    return f"now ({when})" if remaining <= 0 else f"in {_format_duration(remaining)} ({when})"


def _job_status_from_state(state: Mapping[str, Any]) -> tuple[str, str]:
    if state.get("paused") is True:
        return "Ⅱ", "paused"
    status = str(state.get("status") or "pending")
    message = str(state.get("status_message") or "").casefold()
    if "rate limit" in message or "rate-limited" in message:
        return "⏳", "rate-limited"
    if status == "failing":
        return "✗", "failing"
    if status == "healthy":
        return "●", "healthy"
    backoff = state.get("rate_limit_backoff")
    try:
        backoff_attempts = int(backoff.get("attempts") or 0) if isinstance(backoff, dict) else 0
    except (TypeError, ValueError):
        backoff_attempts = 0
    if state.get("last_uncertain_send_at") or backoff_attempts > 0:
        return "✗", "failing"
    if state.get("last_sent_at"):
        return "●", "healthy"
    return "○", "pending"


def _prompt_preview(prompt: str, width: int = 52) -> str:
    single_line = " ".join(prompt.split())
    return single_line if len(single_line) <= width else single_line[: width - 1].rstrip() + "…"


def _uses_color(stream: Any = None) -> bool:
    stream = sys.stdout if stream is None else stream
    return bool(
        os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM") != "dumb"
        and getattr(stream, "isatty", lambda: False)()
    )


def _paint(text: str, code: str, *, stream: Any = None) -> str:
    return f"\033[{code}m{text}\033[0m" if _uses_color(stream) else text


def _status_text(status: str) -> str:
    code = {
        "healthy": "1;32",
        "failing": "1;31",
        "rate-limited": "1;33",
        "paused": "1;33",
        "pending": "2",
    }.get(status, "0")
    return _paint(status, code)


def _print_notice(icon: str, title: str, detail: str = "", *, tone: str = "36") -> None:
    marker = _paint(icon, f"1;{tone}")
    heading = _paint(title, "1")
    suffix = f"  {_paint(detail, '2')}" if detail else ""
    print(f"{marker} {heading}{suffix}")


def _print_job_table(runtime: SchedulerRuntime, jobs: dict[str, PromptJob]) -> None:
    if not jobs:
        _print_notice("○", "No jobs configured", "Add one with `prompta add …`", tone="33")
        return

    rows: list[tuple[str, str, str, str, str]] = []
    for job in jobs.values():
        icon, status = _job_status_from_state(runtime.job_state(job.name))
        rows.append(
            (icon, status, job.name, _format_next_due(runtime, job), _prompt_preview(job.prompt))
        )

    headers = ("", "STATUS", "NAME", "NEXT DUE", "PROMPT")
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    line = "┼".join("─" * (width + 2) for width in widths)
    print(
        f"{_paint('Prompta', '1;36')}  "
        f"{_paint(f'{len(rows)} job' + ('s' if len(rows) != 1 else ''), '2')}"
    )
    print("╭" + line.replace("┼", "┬") + "╮")
    print("│" + "│".join(f" {header.ljust(widths[i])} " for i, header in enumerate(headers)) + "│")
    print("├" + line + "┤")
    for icon, status, name, due, prompt in rows:
        values = (icon, status, name, due, prompt)
        rendered: list[str] = []
        for i, value in enumerate(values):
            shown = _status_text(value) if i == 1 else value
            rendered.append(f" {shown}{' ' * (widths[i] - len(value))} ")
        print("│" + "│".join(rendered) + "│")
    print("╰" + line.replace("┼", "┴") + "╯")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Prompta scheduled jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", aliases=["push"], help="Add or replace a named job")
    add.add_argument("name")
    add.add_argument("prompt")
    schedule = add.add_mutually_exclusive_group()
    schedule.add_argument("--interval-minutes", type=float)
    schedule.add_argument("--daily-at", metavar="HH:MM")
    add.add_argument("--exact-interval", action="store_true")
    add.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    add.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    at = subparsers.add_parser("at", help="Run a one-shot job at a specific local time")
    at.add_argument("when", metavar="TIME", help="HH:MM or ISO local datetime")
    at.add_argument("name")
    at.add_argument("prompt")
    at.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    at.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    remove = subparsers.add_parser("remove", aliases=["rm"], help="Remove a named job")
    remove.add_argument("name")
    remove.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    remove.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    show = subparsers.add_parser("show", help="Show one named job")
    show.add_argument("name")
    show.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    show.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    show.add_argument("--json", action="store_true")

    list_parser = subparsers.add_parser("list", aliases=["ls"], help="List configured jobs")
    list_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    list_parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    list_parser.add_argument("--json", action="store_true")

    clear = subparsers.add_parser("clear", aliases=["cls"], help="Remove all jobs")
    clear.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    clear.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    for command in ("pause", "resume"):
        verb = command.title()
        action = subparsers.add_parser(
            command,
            help=f"{verb} one named job, or all jobs when omitted",
        )
        action.add_argument(
            "name",
            nargs="?",
            help=f"Job name; omit to {command} all configured jobs",
        )
        action.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
        action.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    return parser


def main() -> None:
    remote_status = _dispatch_remote(sys.argv[1:])
    if remote_status is not None:
        raise SystemExit(remote_status)

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "at":
        try:
            run_at_epoch = _parse_run_at(args.when)
        except ValueError as exc:
            parser.error(str(exc))
        add_job(
            args.jobs_file,
            args.name,
            args.prompt,
            0.0,
            exact_interval=True,
            run_at_epoch=run_at_epoch,
        )
        SchedulerRuntime(args.state, args.jobs_file).clear_job_state(args.name)
        scheduled = datetime.fromtimestamp(run_at_epoch).astimezone().strftime("%Y-%m-%d %H:%M")
        _print_notice("✓", f"Scheduled {args.name}", f"once at {scheduled} local time", tone="32")
        return

    if args.command in {"add", "push"}:
        if args.daily_at is not None and args.exact_interval:
            parser.error("--exact-interval cannot be combined with --daily-at")
        interval_minutes = (
            DEFAULT_INTERVAL_SECONDS / 60.0
            if args.interval_minutes is None and args.daily_at is None
            else (args.interval_minutes or 0.0)
        )
        add_job(
            args.jobs_file,
            args.name,
            args.prompt,
            max(0.0, interval_minutes * 60.0),
            daily_at=args.daily_at,
            exact_interval=args.exact_interval,
        )
        SchedulerRuntime(args.state, args.jobs_file).clear_job_state(args.name)
        job = load_jobs(args.jobs_file)[args.name]
        if job.daily_at is not None:
            detail = f"daily at {job.daily_at} local time"
        else:
            detail = f"every {_format_duration(job.interval_seconds)}"
            if job.exact_interval:
                detail += " exactly"
        _print_notice("✓", f"Saved {args.name}", detail, tone="32")
        return

    if args.command in {"remove", "rm"}:
        existed = args.name in load_jobs(args.jobs_file)
        remove_job(args.jobs_file, args.name)
        _cancel_pending_delivery(
            args.jobs_file,
            args.state,
            args.name,
            error="scheduled job removed",
        )
        SchedulerRuntime(args.state, args.jobs_file).clear_job_state(args.name)
        if existed:
            _print_notice("✓", f"Removed {args.name}", tone="32")
        else:
            _print_notice("○", f"No job named {args.name}", tone="33")
        return

    if args.command == "show":
        jobs = load_jobs(args.jobs_file)
        job = jobs.get(args.name)
        if job is None:
            parser.error(f"unknown job: {args.name}")
        runtime = SchedulerRuntime(args.state, args.jobs_file)
        if args.json:
            payload = next(
                item
                for item in _jobs_payload(args.jobs_file, args.state)
                if item["name"] == args.name
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        icon, status = _job_status_from_state(runtime.job_state(job.name))
        state = runtime.job_state(job.name)
        print(f"{icon} {_paint(job.name, '1')}  {_status_text(status)}")
        print(_paint("─" * max(24, len(job.name) + len(status) + 4), "2"))
        if job.run_at_epoch is not None:
            scheduled = (
                datetime.fromtimestamp(job.run_at_epoch).astimezone().strftime("%Y-%m-%d %H:%M")
            )
            print(f"{_paint('Schedule', '2')}  once at {scheduled} local time")
        elif job.daily_at is not None:
            print(f"{_paint('Schedule', '2')}  daily at {job.daily_at} local time")
        else:
            interval = _format_duration(job.interval_seconds)
            if job.exact_interval:
                interval += " exactly"
            print(f"{_paint('Interval', '2')}  {interval}")
        print(f"{_paint('Next due', '2')}  {_format_next_due(runtime, job)}")
        if state.get("status_message"):
            print(f"{_paint('Issue', '2')}     {_paint(str(state['status_message']), '31')}")
        print(f"{_paint('Prompt', '2')}    {job.prompt}")
        return

    if args.command in {"list", "ls"}:
        if args.json:
            print(
                json.dumps(_jobs_payload(args.jobs_file, args.state), indent=2, ensure_ascii=False)
            )
            return
        runtime = SchedulerRuntime(args.state, args.jobs_file)
        _print_job_table(runtime, load_jobs(args.jobs_file))
        return

    if args.command in {"clear", "cls"}:
        names = list(load_jobs(args.jobs_file))
        count = len(names)
        clear_jobs(args.jobs_file)
        for name in names:
            _cancel_pending_delivery(
                args.jobs_file,
                args.state,
                name,
                error="scheduled job cleared",
            )
        SchedulerRuntime(args.state, args.jobs_file).clear_all_job_state()
        _print_notice("✓", f"Cleared {count} job{'s' if count != 1 else ''}", tone="32")
        return

    paused = args.command == "pause"
    if args.name is None:
        count = set_all_jobs_paused(args.jobs_file, args.state, paused)
        _print_notice(
            "Ⅱ" if paused else "▶",
            f"{'Paused' if paused else 'Resumed'} {count} job{'s' if count != 1 else ''}",
            tone="33" if paused else "32",
        )
        return

    if not set_job_paused(args.jobs_file, args.state, args.name, paused):
        parser.error(f"unknown job: {args.name}")
    _print_notice(
        "Ⅱ" if paused else "▶",
        f"{'Paused' if paused else 'Resumed'} {args.name}",
        tone="33" if paused else "32",
    )


if __name__ == "__main__":
    main()
