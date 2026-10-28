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
