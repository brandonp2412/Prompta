"""Periodic fresh-chat scheduler for Prompta."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from websockets.exceptions import ConnectionClosed

from .bidi import FirefoxBiDiDriver, wait_for_port

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30 * 60
DEFAULT_JOBS_PATH = Path.home() / ".config" / "prompta" / "jobs.json"
DEFAULT_STATE_PATH = Path.home() / ".local" / "state" / "prompta" / "state.json"
DEFAULT_FIREFOX_PROFILE = Path.home() / ".local" / "state" / "prompta" / "firefox-profile"
DEFAULT_FIREFOX_PORT = 9229
DEFAULT_RETRY_AFTER = 60
_SEND_CONFIRM_TIMEOUT_SECONDS = 20.0
_SEND_CONFIRM_POLL_SECONDS = 0.2
_EFFORT_CONTROL_TIMEOUT_SECONDS = 20.0
_IDLE_POLL_SECONDS = 1.0
_FAILURE_RETRY_SECONDS = 300.0
_RATE_LIMIT_BACKOFF_CAP_SECONDS = 15 * 60.0
_RATE_LIMIT_RESET_SECONDS = 15 * 60.0
_RATE_LIMIT_JITTER_FRACTION = 0.10
_RATE_LIMIT_JITTER_CAP_SECONDS = 30.0


class RateLimitError(RuntimeError):
    def __init__(self, message: str = "ChatGPT rate limit reached", retry_after: int = DEFAULT_RETRY_AFTER) -> None:
        super().__init__(message)
        self.retry_after = max(0, int(retry_after))

    @classmethod
    def from_text(cls, text: str) -> RateLimitError:
        return cls(retry_after=parse_retry_after(text))


def parse_retry_after(text: str) -> int:
    lowered = text.casefold()
    if re.search(r"\b(?:a\s+)?few\s+(?:minutes?|mins?)\b", lowered):
        return 5 * 60
    match = re.search(r"\b(\d+)\s*(seconds?|secs?|minutes?|mins?)\b", lowered)
    if match is None:
        return DEFAULT_RETRY_AFTER
    value = int(match.group(1))
    unit = match.group(2)
    return value * 60 if unit.startswith(("min", "minute")) else value


def is_rate_limited_text(text: str) -> bool:
    lowered = " ".join(text.casefold().split())
    return any(
        phrase in lowered
        for phrase in (
            "too many requests",
            "rate limit",
            "try again in",
            "wait a few minutes",
            "you've reached the current usage cap",
            "you have reached the current usage cap",
        )
    )


class RateLimitBackoff:
    def __init__(self) -> None:
        self.attempts = 0
        self.blocked_until = 0.0
        self.last_limited_at = 0.0

    def snapshot(
        self,
        *,
        now: float | None = None,
        wall_time: float | None = None,
    ) -> dict[str, float | int]:
        now = time.monotonic() if now is None else now
        wall_time = time.time() if wall_time is None else wall_time
        remaining = self.remaining(now=now)
        limited_age = max(0.0, now - self.last_limited_at) if self.attempts else 0.0
        return {
            "attempts": self.attempts,
            "blocked_until_epoch": wall_time + remaining,
            "last_limited_at_epoch": wall_time - limited_age,
        }

    def restore(
        self,
        snapshot: dict[str, Any],
        *,
        now: float | None = None,
        wall_time: float | None = None,
    ) -> None:
        now = time.monotonic() if now is None else now
        wall_time = time.time() if wall_time is None else wall_time
        attempts = max(0, int(snapshot.get("attempts") or 0))
        blocked_until_epoch = float(snapshot.get("blocked_until_epoch") or 0.0)
        last_limited_epoch = float(snapshot.get("last_limited_at_epoch") or 0.0)
        remaining = max(0.0, blocked_until_epoch - wall_time)
        limited_age = max(0.0, wall_time - last_limited_epoch) if last_limited_epoch else 0.0
        if not attempts or (remaining <= 0 and limited_age >= _RATE_LIMIT_RESET_SECONDS):
            self.reset()
            return
        self.attempts = attempts
        self.blocked_until = now + remaining
        self.last_limited_at = now - limited_age

    def record(self, retry_after: float = 0.0, *, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        self.attempts += 1
        exponential = min(
            _RATE_LIMIT_BACKOFF_CAP_SECONDS,
            float(DEFAULT_RETRY_AFTER) * (2 ** min(self.attempts - 1, 20)),
        )
        floor = max(exponential, max(0.0, float(retry_after)))
        jitter_cap = min(_RATE_LIMIT_JITTER_CAP_SECONDS, floor * _RATE_LIMIT_JITTER_FRACTION)
        delay = floor + random.uniform(0.0, jitter_cap)
        self.last_limited_at = now
        self.blocked_until = max(self.blocked_until, now + delay)
        return max(0.0, self.blocked_until - now)

    def remaining(self, *, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        return max(0.0, self.blocked_until - now)

    def reset(self) -> None:
        self.attempts = 0
        self.blocked_until = 0.0
        self.last_limited_at = 0.0


@dataclass(frozen=True)
class PromptJob:
    name: str
    prompt: str
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS


@dataclass(frozen=True)
class PromptaConfig:
    jobs_file: Path = DEFAULT_JOBS_PATH
    state_path: Path = DEFAULT_STATE_PATH
    send_timeout_seconds: float = _SEND_CONFIRM_TIMEOUT_SECONDS


class Prompta:
    def __init__(self, config: PromptaConfig, bidi_url: str) -> None:
        self.config = config
        self.bidi_url = bidi_url
        self.driver: FirefoxBiDiDriver | None = None
        self._backoffs: dict[str, RateLimitBackoff] = {}
        self._failure_retry_until: dict[str, float] = {}
        self._restore_backoffs()

    @staticmethod
    def _normalise(text: str) -> str:
        return " ".join(text.split()).strip()

    @staticmethod
    def _prompt_hash(prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()

    def _load_state(self) -> dict[str, Any]:
        path = self.config.state_path.expanduser()
        try:
            value = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write_state(self, state: dict[str, Any]) -> None:
        path = self.config.state_path.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        os.chmod(temporary, 0o600)
        temporary.replace(path)

    def _job_state(self, name: str) -> dict[str, Any]:
        jobs = self._load_state().get("jobs")
        if not isinstance(jobs, dict):
            return {}
        value = jobs.get(name)
        return value if isinstance(value, dict) else {}

    def _update_job_state(self, name: str, updates: dict[str, Any]) -> None:
        state = self._load_state()
        jobs = state.setdefault("jobs", {})
        if not isinstance(jobs, dict):
            jobs = {}
            state["jobs"] = jobs
        current = jobs.get(name)
        if not isinstance(current, dict):
            current = {}
            jobs[name] = current
        current.update(updates)
        self._write_state(state)

    def _restore_backoffs(self) -> None:
        jobs = self._load_state().get("jobs")
        if not isinstance(jobs, dict):
            return
        for name, job_state in jobs.items():
            if not isinstance(job_state, dict):
                continue
            snapshot = job_state.get("rate_limit_backoff")
            if not isinstance(snapshot, dict):
                continue
            backoff = RateLimitBackoff()
            backoff.restore(snapshot)
            if backoff.attempts:
                self._backoffs[str(name)] = backoff

    def _persist_backoff(self, name: str, backoff: RateLimitBackoff) -> None:
        self._update_job_state(name, {"rate_limit_backoff": backoff.snapshot()})

    def read_jobs(self) -> dict[str, PromptJob]:
        return load_jobs(self.config.jobs_file)

    def due_in(self, job: PromptJob, now: float | None = None) -> float:
        state = self._job_state(job.name)
        try:
            last_sent_at = float(state.get("last_sent_at") or 0.0)
        except (TypeError, ValueError):
            return 0.0
        if last_sent_at <= 0:
            return 0.0
        current = time.time() if now is None else now
        return max(0.0, last_sent_at + max(0.0, job.interval_seconds) - current)

    async def _ensure_driver(self) -> FirefoxBiDiDriver:
        if self.driver is None:
            self.driver = FirefoxBiDiDriver(self.bidi_url)
        if not self.driver.is_connected:
            await self.driver.connect()
        return self.driver

    async def _pointer_click(self, driver: FirefoxBiDiDriver, x: float, y: float) -> None:
        await driver._call(
            "input.performActions",
            {
                "context": driver.context,
                "actions": [
                    {
                        "type": "pointer",
                        "id": "mouse",
                        "parameters": {"pointerType": "mouse"},
                        "actions": [
                            {
                                "type": "pointerMove",
                                "x": int(x),
                                "y": int(y),
                                "duration": 0,
                                "origin": "viewport",
                            },
                            {"type": "pointerDown", "button": 0},
                            {"type": "pointerUp", "button": 0},
                        ],
                    }
                ],
            },
        )
        await driver._call("input.releaseActions", {"context": driver.context})

    async def _effort_trigger_info(
        self,
        driver: FirefoxBiDiDriver,
        *,
        timeout: float = _EFFORT_CONTROL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            raw = await driver.eval(
                """JSON.stringify((()=>{
                  const levels=['Instant','Medium','High','Extra high','Extra High'];
                  const normalise=value=>(value||'').replace(/\\s+/g,' ').trim();
                  const visible=el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);
                    return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
                  const composer=document.querySelector('main form[data-type="unified-composer"],main form,[data-composer-surface]');
                  const roots=composer?[composer,document]:[document];
                  let button=null;
                  for(const root of roots){
                    button=[...root.querySelectorAll('button[aria-haspopup="menu"]')]
                      .find(el=>visible(el)&&levels.includes(normalise(el.innerText||el.textContent||'')));
                    if(button)break;
                  }
                  if(!button)return null;
                  const r=button.getBoundingClientRect();
                  return {text:normalise(button.innerText||button.textContent||''),x:r.left+r.width/2,y:r.top+r.height/2};
                })())"""
            )
            if raw and raw != "null":
                payload = json.loads(raw)
                if isinstance(payload, dict) and payload.get("text"):
                    return payload
            await asyncio.sleep(0.15)
        raise RuntimeError("ChatGPT thinking-effort control did not become available")

    async def _high_effort_slider_point(self, driver: FirefoxBiDiDriver) -> dict[str, float]:
        deadline = asyncio.get_running_loop().time() + 3.0
        while asyncio.get_running_loop().time() < deadline:
            raw = await driver.eval(
                """JSON.stringify((()=>{
                  const slider=document.querySelector('[data-model-reasoning-effort-slider] [role="slider"]');
                  if(!slider)return null;
                  const root=slider.parentElement?.parentElement;
                  if(!root)return null;
                  const min=Number(slider.getAttribute('aria-valuemin')||0);
                  const max=Number(slider.getAttribute('aria-valuemax')||3);
                  const target=2;
                  if(target<min||target>max)return {error:'high-out-of-range'};
                  const ticks=[...root.querySelectorAll('[data-locked]')];
                  if(ticks[target]?.getAttribute('data-locked')==='true')return {error:'high-locked'};
                  const r=root.getBoundingClientRect(),pad=13;
                  return {x:r.left+pad+(r.width-pad*2)*(target-min)/(max-min),y:r.top+r.height/2};
                })())"""
            )
            if raw and raw != "null":
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    if payload.get("error"):
                        raise RuntimeError(f"ChatGPT High effort is unavailable: {payload['error']}")
                    if "x" in payload and "y" in payload:
                        return {"x": float(payload["x"]), "y": float(payload["y"])}
            await asyncio.sleep(0.1)
        raise RuntimeError("ChatGPT thinking-effort slider did not open")

    async def _ensure_high_effort(self, driver: FirefoxBiDiDriver) -> None:
        trigger = await self._effort_trigger_info(driver)
        if str(trigger.get("text") or "").strip().casefold() == "high":
            logger.info("Prompta verified thinking effort=High")
            return
        await self._pointer_click(driver, float(trigger["x"]), float(trigger["y"]))
        point = await self._high_effort_slider_point(driver)
        await self._pointer_click(driver, point["x"], point["y"])
        deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < deadline:
            value = str(
                await driver.eval(
                    "document.querySelector('[data-model-reasoning-effort-slider] [role=\"slider\"]')?.getAttribute('aria-valuenow')||''"
                )
                or ""
            )
            if value == "2":
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("ChatGPT thinking-effort slider did not reach High")
        await driver._call(
            "input.performActions",
            {
                "context": driver.context,
                "actions": [
                    {
                        "type": "key",
                        "id": "keyboard",
                        "actions": [
                            {"type": "keyDown", "value": "\ue00c"},
                            {"type": "keyUp", "value": "\ue00c"},
                        ],
                    }
                ],
            },
        )
        await driver._call("input.releaseActions", {"context": driver.context})
        await asyncio.sleep(0.2)
        verified = await self._effort_trigger_info(driver)
        if str(verified.get("text") or "").strip().casefold() != "high":
            raise RuntimeError(
                f"ChatGPT thinking effort verification failed: {verified.get('text')!r}"
            )
        logger.info("Prompta set and verified thinking effort=High")

    async def send_once(self, prompt: str) -> str:
        if not prompt.strip():
            raise ValueError("prompta prompt is empty")
        driver = await self._ensure_driver()
        await driver.navigate("https://chatgpt.com/")
        await driver.wait_for_composer()
        await self._ensure_high_effort(driver)
        baseline = await driver.dom_state()
        if self._normalise(str(baseline.get("composer_text") or "")):
            raise RuntimeError("ChatGPT new-chat composer was not empty")
        await driver.arm_page_send_probe()
        capture = driver.arm_send_capture()
        try:
            await driver.type_message(prompt)
            typed = await driver.dom_state()
            if self._normalise(str(typed.get("composer_text") or "")) != self._normalise(prompt):
                raise RuntimeError("ChatGPT composer did not contain the configured prompt")
            await driver.click_send()
            deadline = asyncio.get_running_loop().time() + max(
                1.0, self.config.send_timeout_seconds
            )
            while asyncio.get_running_loop().time() < deadline:
                state = await driver.dom_state()
                rate_limit_text = str(state.get("rate_limit_text") or "")
                if is_rate_limited_text(rate_limit_text):
                    raise RateLimitError.from_text(rate_limit_text)
                probe = await driver.page_send_probe()
                send_response = driver.captured_send_response(capture)
                path = str(await driver.eval("location.pathname") or "")
                user_text = self._normalise(str(state.get("last_user_text") or ""))
                message_id = str(probe.get("message_id") or state.get("last_user_id") or "")
                status = int(probe.get("response_status") or capture.get("status") or 0)
                if status == 429:
                    raise RateLimitError("prompta send rate limited")
                if status >= 400:
                    raise RuntimeError(f"prompta send failed with HTTP {status}")
                if capture.get("fetch_error"):
                    raise RuntimeError(f"prompta send failed: {capture['fetch_error']}")
                if (
                    path.startswith("/c/")
                    and user_text == self._normalise(prompt)
                    and message_id
                    and send_response is not None
                ):
                    conversation_id = path.removeprefix("/c/").split("/", 1)[0]
                    logger.info(
                        "Prompta sent prompt in new conversation=%s message_id=%s",
                        conversation_id,
                        message_id,
                    )
                    return conversation_id
                await asyncio.sleep(_SEND_CONFIRM_POLL_SECONDS)
        finally:
            driver.clear_send_capture(capture)
            try:
                await driver.clear_page_send_probe()
            except Exception:
                logger.debug("Could not clear page send probe", exc_info=True)
        raise RuntimeError("prompta could not prove the prompt was sent in a new conversation")

    async def _run_job(self, job: PromptJob, *, now: float) -> bool:
        if self.due_in(job, now) > 0:
            return False
        backoff = self._backoffs.setdefault(job.name, RateLimitBackoff())
        if backoff.remaining() > 0:
            return False
        if self._failure_retry_until.get(job.name, 0.0) > now:
            return False
        try:
            conversation_id = await self.send_once(job.prompt)
        except RateLimitError as exc:
            delay = backoff.record(float(exc.retry_after))
            self._persist_backoff(job.name, backoff)
            logger.warning(
                "Prompta job=%s rate limited; attempt=%d retrying in %.1fs",
                job.name,
                backoff.attempts,
                delay,
            )
            return False
        except (ConnectionClosed, OSError, RuntimeError) as exc:
            logger.exception("Prompta job=%s send failed: %s", job.name, exc)
            if self.driver is not None:
                await self.driver.close()
                self.driver = None
            self._failure_retry_until[job.name] = time.time() + _FAILURE_RETRY_SECONDS
            return False
        sent_at = time.time()
        backoff.reset()
        self._failure_retry_until.pop(job.name, None)
        self._update_job_state(
            job.name,
            {
                "prompt_sha256": self._prompt_hash(job.prompt),
                "last_sent_at": sent_at,
                "last_conversation_id": conversation_id,
                "rate_limit_backoff": backoff.snapshot(),
            },
        )
        logger.info(
            "Prompta job=%s completed; next send in %.0fs",
            job.name,
            job.interval_seconds,
        )
        return True

    async def run(self, *, once: bool = False) -> None:
        while True:
            jobs = self.read_jobs()
            if not jobs:
                if once:
                    return
                await asyncio.sleep(_IDLE_POLL_SECONDS)
                continue
            now = time.time()
            did_work = False
            for job in jobs.values():
                if await self._run_job(job, now=now):
                    did_work = True
            if once:
                return
            await asyncio.sleep(_IDLE_POLL_SECONDS if did_work else 1.0)

    async def close(self) -> None:
        if self.driver is not None:
            await self.driver.close()
            self.driver = None


def load_jobs(path: Path) -> dict[str, PromptJob]:
    target = path.expanduser()
    try:
        payload = json.loads(target.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    jobs_raw = payload.get("jobs", payload)
    if not isinstance(jobs_raw, dict):
        return {}
    jobs: dict[str, PromptJob] = {}
    for name, value in jobs_raw.items():
        if isinstance(value, str):
            prompt = value
            interval = DEFAULT_INTERVAL_SECONDS
        elif isinstance(value, dict):
            prompt = str(value.get("prompt") or "")
            try:
                interval = float(value.get("interval_seconds") or DEFAULT_INTERVAL_SECONDS)
            except (TypeError, ValueError):
                interval = DEFAULT_INTERVAL_SECONDS
        else:
            continue
        if str(name).strip() and prompt.strip():
            jobs[str(name)] = PromptJob(str(name), prompt, max(0.0, interval))
    return jobs


def _write_jobs(path: Path, jobs: dict[str, PromptJob]) -> None:
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "jobs": {
            name: {"prompt": job.prompt, "interval_seconds": job.interval_seconds}
            for name, job in sorted(jobs.items())
        }
    }
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(target)


def add_job(
    path: Path,
    name: str,
    prompt: str,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> None:
    if not name.strip():
        raise ValueError("prompta job name is empty")
    if not prompt.strip():
        raise ValueError("prompta prompt is empty")
    jobs = load_jobs(path)
    jobs[name] = PromptJob(name, prompt, max(0.0, interval_seconds))
    _write_jobs(path, jobs)


def remove_job(path: Path, name: str) -> None:
    jobs = load_jobs(path)
    jobs.pop(name, None)
    _write_jobs(path, jobs)


def clear_jobs(path: Path) -> None:
    try:
        path.expanduser().unlink()
    except FileNotFoundError:
        pass


async def _spawn_firefox(profile: Path, firefox_path: str, port: int) -> asyncio.subprocess.Process:
    resolved = profile.expanduser().resolve()
    if not resolved.is_dir():
        raise RuntimeError(f"Firefox profile does not exist: {resolved}")
    for name in ("lock", ".parentlock"):
        try:
            os.unlink(resolved / name)
        except FileNotFoundError:
            pass
    process = await asyncio.create_subprocess_exec(
        firefox_path,
        "--headless",
        "--profile",
        str(resolved),
        "--remote-debugging-port",
        str(port),
        "https://chatgpt.com/",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await wait_for_port(port)
    return process


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send named prompts into fresh ChatGPT chats on a cadence"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_parser = subparsers.add_parser("add", help="Add or replace a named job")
    add_parser.add_argument("name")
    add_parser.add_argument("prompt")
    add_parser.add_argument("--interval-minutes", type=float, default=30.0)
    add_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    remove_parser = subparsers.add_parser("remove", help="Remove a named job")
    remove_parser.add_argument("name")
    remove_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    show_parser = subparsers.add_parser("show", help="Show one named job")
    show_parser.add_argument("name")
    show_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    list_parser = subparsers.add_parser("list", help="List configured jobs")
    list_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    clear_parser = subparsers.add_parser("clear", help="Remove all jobs")
    clear_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    run_parser = subparsers.add_parser("run", help="Run the scheduler")
    run_parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    run_parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    run_parser.add_argument(
        "--send-timeout-seconds", type=float, default=_SEND_CONFIRM_TIMEOUT_SECONDS
    )
    run_parser.add_argument("--once", action="store_true")
    run_parser.add_argument("--bidi-url")
    run_parser.add_argument("--firefox-profile", type=Path, default=DEFAULT_FIREFOX_PROFILE)
    run_parser.add_argument("--firefox-path", default="/usr/bin/firefox")
    run_parser.add_argument("--firefox-port", type=int, default=DEFAULT_FIREFOX_PORT)
    return parser


async def _run(args: argparse.Namespace) -> None:
    firefox: asyncio.subprocess.Process | None = None
    if args.bidi_url:
        bidi_url = args.bidi_url
    else:
        firefox = await _spawn_firefox(args.firefox_profile, args.firefox_path, args.firefox_port)
        bidi_url = f"ws://127.0.0.1:{args.firefox_port}/session"
    prompta = Prompta(
        PromptaConfig(
            jobs_file=args.jobs_file,
            state_path=args.state,
            send_timeout_seconds=max(1.0, args.send_timeout_seconds),
        ),
        bidi_url,
    )
    try:
        await prompta.run(once=args.once)
    finally:
        await prompta.close()
        if firefox is not None and firefox.returncode is None:
            firefox.terminate()
            try:
                await asyncio.wait_for(firefox.wait(), timeout=5)
            except TimeoutError:
                firefox.kill()
                await firefox.wait()


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "add":
        add_job(
            args.jobs_file,
            args.name,
            args.prompt,
            max(0.0, args.interval_minutes * 60.0),
        )
        return
    if args.command == "remove":
        remove_job(args.jobs_file, args.name)
        return
    if args.command == "show":
        job = load_jobs(args.jobs_file).get(args.name)
        if job is None:
            raise SystemExit(f"No Prompta job named {args.name!r}")
        print(job.prompt)
        return
    if args.command == "list":
        for job in load_jobs(args.jobs_file).values():
            print(f"{job.name}\t{job.interval_seconds / 60:g}m\t{job.prompt}")
        return
    if args.command == "clear":
        clear_jobs(args.jobs_file)
        return
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
