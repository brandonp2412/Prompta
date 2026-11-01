from prompta.browser_watchdog import WatchdogState, decide_restart


def test_restarts_only_after_two_consecutive_failures() -> None:
    state = WatchdogState()
    assert not decide_restart(state, healthy=False, busy=False, now=1000)
    assert state.consecutive_failures == 1
    assert decide_restart(state, healthy=False, busy=False, now=1060)


def test_success_resets_failures() -> None:
    state = WatchdogState(consecutive_failures=1)
    assert not decide_restart(state, healthy=True, busy=False, now=1000)
    assert not decide_restart(state, healthy=False, busy=False, now=1060)


def test_inflight_dispatch_defers_restart() -> None:
    state = WatchdogState(consecutive_failures=1)
    assert not decide_restart(state, healthy=False, busy=True, now=1000)
    assert decide_restart(state, healthy=False, busy=False, now=1060)


def test_cooldown_prevents_repeated_restarts() -> None:
    state = WatchdogState(consecutive_failures=1, last_restart_at=900)
    assert not decide_restart(state, healthy=False, busy=False, now=1000)
    assert decide_restart(state, healthy=False, busy=False, now=1200)


def test_watchdog_recovers_after_sustained_unresponsiveness(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    import prompta.browser_watchdog as watchdog

    state_file = tmp_path / "watchdog.json"
    monkeypatch.setattr(watchdog, "STATE_DIR", tmp_path)
    monkeypatch.setattr(watchdog, "STATE_FILE", state_file)
    monkeypatch.setattr(watchdog, "debugger_responding", lambda address: False)
    monkeypatch.setattr(watchdog, "delivery_in_flight", lambda database, now: False)
    monkeypatch.setattr(watchdog.time, "time", lambda: 2000.0)
    commands: list[list[str]] = []

    def capture(args, **kwargs):
        commands.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(watchdog.subprocess, "run", capture)
    watchdog.main()
    assert commands == []
    watchdog.main()
    assert commands == [
        ["systemctl", "--user", "is-active", "--quiet", "prompta-browser.service"],
        ["systemctl", "--user", "restart", "prompta-browser.service"],
    ]
    state = watchdog.load_state(state_file)
    assert state.last_restart_at == 2000.0
    assert state.consecutive_failures == 0


def test_watchdog_does_not_revive_stopped_service(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    import prompta.browser_watchdog as watchdog

    monkeypatch.setattr(watchdog, "STATE_DIR", tmp_path)
    monkeypatch.setattr(watchdog, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(watchdog, "debugger_responding", lambda address: False)
    monkeypatch.setattr(watchdog, "delivery_in_flight", lambda database, now: False)
    monkeypatch.setattr(watchdog.time, "time", lambda: 2000.0)
    commands: list[list[str]] = []

    def capture(args, **kwargs):
        commands.append(args)
        return SimpleNamespace(returncode=3)

    monkeypatch.setattr(watchdog.subprocess, "run", capture)
    watchdog.main()
    watchdog.main()
    assert len(commands) == 1
    assert commands[0][3] == "--quiet"


def test_watchdog_uses_flaresolverr_browser_configuration(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    import prompta.browser_watchdog as watchdog

    monkeypatch.setenv("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9223")
    monkeypatch.setenv("PROMPTA_BROWSER_SERVICE", "prompta-flaresolverr.service")
    monkeypatch.setattr(watchdog, "STATE_DIR", tmp_path)
    monkeypatch.setattr(watchdog, "STATE_FILE", tmp_path / "state.json")
    addresses: list[str] = []
    commands: list[list[str]] = []

    def check(address: str) -> bool:
        addresses.append(address)
        return False

    def capture(args, **kwargs):
        commands.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(watchdog, "debugger_responding", check)
    monkeypatch.setattr(watchdog, "delivery_in_flight", lambda database, now: False)
    monkeypatch.setattr(watchdog.subprocess, "run", capture)
    monkeypatch.setattr(watchdog.time, "time", lambda: 2000.0)
    watchdog.main()
    watchdog.main()
    assert addresses == ["127.0.0.1:9223", "127.0.0.1:9223"]
    assert commands == [
        ["systemctl", "--user", "is-active", "--quiet", "prompta-flaresolverr.service"],
        ["systemctl", "--user", "restart", "prompta-flaresolverr.service"],
    ]


def test_tab_lease_records_earliest_timestamp_and_removes_only_targets(tmp_path) -> None:
    from prompta.browser_ownership import forget_owned_tabs, owned_tab_records, record_owned_tab

    path = tmp_path / "leases.sqlite3"
    record_owned_tab("expired", 100, path)
    record_owned_tab("expired", 200, path)
    record_owned_tab("recent", 250, path)
    assert owned_tab_records(path) == {"expired": 100, "recent": 250}
    forget_owned_tabs({"expired"}, path)
    assert owned_tab_records(path) == {"recent": 250}


def test_watchdog_uses_http_expiry_if_cdp_session_fails(monkeypatch, tmp_path) -> None:
    import prompta.browser_watchdog as watchdog

    monkeypatch.setattr(watchdog, "STATE_DIR", tmp_path)
    monkeypatch.setattr(watchdog, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(watchdog, "debugger_responding", lambda address: True)
    monkeypatch.setattr(watchdog, "delivery_in_flight", lambda database, now: False)

    async def healthy_renderer(address: str) -> bool:
        return True

    monkeypatch.setattr(watchdog, "bounded_renderer_probe", healthy_renderer)

    async def fail_cdp(address: str, *, now: float) -> None:
        raise RuntimeError("CDP websocket unavailable")

    attempts: list[float] = []
    monkeypatch.setattr(watchdog, "reap_expired_owned_tabs", fail_cdp)
    monkeypatch.setattr(
        watchdog, "reap_expired_leases_http", lambda address, *, now: attempts.append(now),
    )
    monkeypatch.setattr(watchdog.time, "time", lambda: 2000.0)
    watchdog.main()
    assert attempts == [2000.0]


def test_expired_tab_claim_serializes_close_against_activity_refresh(tmp_path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from prompta.browser_ownership import (
        claim_expired_tab,
        owned_tab_records,
        record_owned_tab,
        touch_owned_tab,
    )

    path = tmp_path / "owned.sqlite3"
    record_owned_tab("expired", 100, path)
    started = Event()

    def refresh() -> bool:
        started.set()
        return touch_owned_tab("expired", 200, path)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with claim_expired_tab("expired", 100, path) as mark_closed:
            assert mark_closed is not None
            future = pool.submit(refresh)
            assert started.wait(2)
            mark_closed()
        assert not future.result(timeout=6)
    assert owned_tab_records(path) == {}

    record_owned_tab("recent", 100, path)
    assert touch_owned_tab("recent", 200, path)
    with claim_expired_tab("recent", 100, path) as mark_closed:
        assert mark_closed is None
    assert owned_tab_records(path) == {"recent": 200}


def test_watchdog_crash_reaper_closes_only_expired_ledger_tabs(monkeypatch, tmp_path) -> None:
    import asyncio

    import prompta.browser_watchdog as watchdog
    from prompta.browser_ownership import (
        claim_expired_tab,
        forget_owned_tabs,
        owned_tab_records,
        record_owned_tab,
    )

    path = tmp_path / "owned.sqlite3"
    for index in range(6):
        record_owned_tab(f"expired-{index}", 100, path)
    record_owned_tab("recent", 2900, path)
    closed: list[str] = []

    class Session:
        async def send(self, method, args=None):
            if method == "Target.getTargets":
                return {"targetInfos": [
                    {"targetId": name, "type": "page"}
                    for name in [*owned_tab_records(path), "unowned-chat"]
                ]}
            assert method == "Target.closeTarget"
            assert isinstance(args, dict)
            target_id = args.get("targetId")
            assert isinstance(target_id, str)
            closed.append(target_id)
            return {"success": True}

        async def detach(self):
            return None

    class Browser:
        async def new_browser_cdp_session(self):
            return Session()

    class Chromium:
        async def connect_over_cdp(self, address, timeout):
            return Browser()

    class Patchright:
        chromium = Chromium()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(watchdog, "async_patchright", Patchright)
    monkeypatch.setattr(watchdog, "owned_tab_records", lambda: owned_tab_records(path))
    monkeypatch.setattr(watchdog, "forget_owned_tabs", lambda ids: forget_owned_tabs(ids, path))
    monkeypatch.setattr(
        watchdog, "claim_expired_tab", lambda target, cutoff: claim_expired_tab(target, cutoff, path),
    )

    assert asyncio.run(watchdog.reap_expired_owned_tabs(now=3000)) == 4
    assert closed == [f"expired-{index}" for index in range(4)]
    assert "recent" in owned_tab_records(path)
    assert "unowned-chat" not in closed
    assert asyncio.run(watchdog.reap_expired_owned_tabs(now=3000)) == 2
    assert owned_tab_records(path) == {"recent": 2900}


def test_healthy_watchdog_never_reaps_during_live_capture(monkeypatch, tmp_path) -> None:
    import prompta.browser_watchdog as watchdog

    monkeypatch.setattr(watchdog, "STATE_DIR", tmp_path)
    monkeypatch.setattr(watchdog, "STATE_FILE", tmp_path / "watchdog.json")
    monkeypatch.setattr(watchdog, "debugger_responding", lambda address: True)
    monkeypatch.setattr(watchdog, "delivery_in_flight", lambda database, now: True)
    monkeypatch.setattr(
        watchdog, "reap_expired_owned_tabs",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("live lease must prevent expiry")),
    )
    watchdog.main()


def test_failed_browser_close_leaves_expiry_claim_recoverable(tmp_path) -> None:
    import pytest

    from prompta.browser_ownership import claim_expired_tab, owned_tab_records, record_owned_tab

    path = tmp_path / "owned.sqlite3"
    record_owned_tab("orphan", 100, path)
    with pytest.raises(OSError):
        with claim_expired_tab("orphan", 100, path) as mark_closed:
            assert mark_closed is not None
            raise OSError("simulated target failure")
    assert owned_tab_records(path) == {"orphan": 100}


def test_http_fallback_never_closes_a_refreshed_or_unowned_page(monkeypatch, tmp_path) -> None:
    import json

    import prompta.browser_watchdog as watchdog
    from prompta.browser_ownership import (
        claim_expired_tab,
        forget_owned_tabs,
        owned_tab_records,
        record_owned_tab,
        touch_owned_tab,
    )

    path = tmp_path / "owned.sqlite3"
    record_owned_tab("owned", 100, path)
    closed: list[str] = []

    class Response:
        def __init__(self, payload: bytes):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return self.payload

    def open_url(url: str, timeout: float):
        if url.endswith("/json/list"):
            touch_owned_tab("owned", 150, path)
            return Response(json.dumps([
                {"id": "owned", "type": "page"},
                {"id": "unowned", "type": "page"},
            ]).encode())
        closed.append(url.rsplit("/", 1)[-1])
        return Response(b"Target is closing")

    monkeypatch.setattr(watchdog, "urlopen", open_url)
    monkeypatch.setattr(watchdog, "owned_tab_records", lambda: owned_tab_records(path))
    monkeypatch.setattr(watchdog, "forget_owned_tabs", lambda ids: forget_owned_tabs(ids, path))
    monkeypatch.setattr(
        watchdog, "claim_expired_tab", lambda target, cutoff: claim_expired_tab(target, cutoff, path),
    )

    assert watchdog.reap_expired_leases_http(now=2800) == 0
    assert closed == []
    assert owned_tab_records(path) == {"owned": 150}
    assert watchdog.reap_expired_leases_http(now=3000) == 1
    assert closed == ["owned"]
    assert owned_tab_records(path) == {}


def test_renderer_failure_restarts_browser_despite_healthy_http(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import prompta.browser_watchdog as watchdog

    monkeypatch.setattr(watchdog, "STATE_DIR", tmp_path)
    monkeypatch.setattr(watchdog, "STATE_FILE", tmp_path / "watchdog.json")
    monkeypatch.setattr(watchdog, "debugger_responding", lambda address: True)
    monkeypatch.setattr(watchdog, "delivery_in_flight", lambda database, now: False)
    monkeypatch.setattr(watchdog.time, "time", lambda: 2000.0)

    async def crashed_renderer(address):
        return False

    monkeypatch.setattr(watchdog, "bounded_renderer_probe", crashed_renderer)
    commands = []

    def run(args, **kwargs):
        commands.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(watchdog.subprocess, "run", run)
    watchdog.main()
    assert commands == []
    watchdog.main()
    assert commands[-1] == ["systemctl", "--user", "restart", "prompta-browser.service"]


def test_watchdog_skips_checks_while_browser_operation_holds_gate(monkeypatch, tmp_path):
    import prompta.browser_watchdog as watchdog
    from prompta.deployment_gate import DeploymentGate

    monkeypatch.setattr(watchdog, "STATE_DIR", tmp_path)
    gate = DeploymentGate(tmp_path / "runtime.sqlite3")

    def unexpected_check():
        raise AssertionError("Watchdog must not probe or restart during browser operations")

    monkeypatch.setattr(watchdog, "check_browser", unexpected_check)
    with gate.admission() as admitted:
        assert admitted
        watchdog.main()
    gate.pause_path.touch()
    watchdog.main()


async def test_renderer_probe_closes_tab_after_evaluation_failure(monkeypatch):
    from types import SimpleNamespace

    import prompta.browser_watchdog as watchdog

    closed = []

    class Page:
        async def evaluate(self, expression):
            raise RuntimeError("Target crashed")

        async def close(self):
            closed.append(True)

    class Context:
        async def new_page(self):
            return Page()

    class Chromium:
        async def connect_over_cdp(self, address, *, timeout):
            return SimpleNamespace(contexts=[Context()])

    class Patchright:
        async def __aenter__(self):
            return SimpleNamespace(chromium=Chromium())

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(watchdog, "async_patchright", Patchright)
    assert not await watchdog.bounded_renderer_probe("127.0.0.1:9222")
    assert closed == [True]
