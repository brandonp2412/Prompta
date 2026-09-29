from __future__ import annotations

import argparse
import json
from pathlib import Path

from .jobs import (
    DEFAULT_INTERVAL_SECONDS,
    add_job,
    clear_jobs,
    load_jobs,
    remove_job,
)
from .persistence import DEFAULT_RUNTIME_PATH
from .scheduler_runtime import SchedulerRuntime

DEFAULT_JOBS_PATH = DEFAULT_RUNTIME_PATH
DEFAULT_STATE_PATH = DEFAULT_RUNTIME_PATH


def set_job_paused(path: Path, state_path: Path, name: str, paused: bool) -> bool:
    return SchedulerRuntime(state_path, path).set_job_paused(name, paused)


def set_all_jobs_paused(path: Path, state_path: Path, paused: bool) -> int:
    return SchedulerRuntime(state_path, path).set_all_jobs_paused(paused)


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Prompta scheduled jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="Add or update a scheduled job")
    add.add_argument("name")
    add.add_argument("prompt")
    add.add_argument(
        "--interval-minutes",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS / 60.0,
    )
    add.add_argument("--daily-at")
    add.add_argument("--exact-interval", action="store_true")
    add.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    add.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    remove = subparsers.add_parser("remove", help="Remove a scheduled job")
    remove.add_argument("name")
    remove.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    remove.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    clear = subparsers.add_parser("clear", help="Remove all scheduled jobs")
    clear.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    clear.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    list_parser = subparsers.add_parser("list", help="List scheduled jobs")
    list_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    list_parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    for command in ("pause", "resume"):
        action = subparsers.add_parser(command, help=command.title() + " a scheduled job")
        action.add_argument("name")
        action.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
        action.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "add":
        if args.daily_at and args.exact_interval:
            parser.error("--exact-interval cannot be combined with --daily-at")
        interval_seconds = 0.0 if args.daily_at else max(0.0, args.interval_minutes * 60.0)
        add_job(
            args.jobs_file,
            args.name,
            args.prompt,
            interval_seconds,
            daily_at=args.daily_at,
            exact_interval=args.exact_interval,
        )
        SchedulerRuntime(args.state, args.jobs_file).clear_job_state(args.name)
        return

    if args.command == "remove":
        remove_job(args.jobs_file, args.name)
        SchedulerRuntime(args.state, args.jobs_file).clear_job_state(args.name)
        return

    if args.command == "clear":
        clear_jobs(args.jobs_file)
        SchedulerRuntime(args.state, args.jobs_file).clear_all_job_state()
        return

    if args.command == "list":
        print(json.dumps(_jobs_payload(args.jobs_file, args.state), indent=2, ensure_ascii=False))
        return

    paused = args.command == "pause"
    if not set_job_paused(args.jobs_file, args.state, args.name, paused):
        parser.error("unknown job: " + args.name)


if __name__ == "__main__":
    main()
