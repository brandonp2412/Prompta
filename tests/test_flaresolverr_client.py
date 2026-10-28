from __future__ import annotations

import json
from pathlib import Path
from typing import Self
from unittest.mock import AsyncMock, MagicMock
from urllib.request import Request

import pytest

import prompta.flaresolverr_client as solver
from prompta.playwright_driver import BrowserSecurityChallengeError, PlaywrightDriver


def test_solver_rejects_nonlocal_endpoint() -> None:
    with pytest.raises(ValueError, match="local HTTP"):
        solver.solve_cloudflare("https://example.com/v1")


def test_solver_accepts_only_chatgpt_clearance(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[dict[str, object]] = []

    class Response:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def read(self, size: int) -> bytes:
            assert size <= 128 * 1024 + 1
            return json.dumps(self.payload).encode()

    def fake_open(request: Request, *, timeout: int) -> Response:
        assert timeout > 0
        assert isinstance(request.data, bytes)
        payload = json.loads(request.data)
        assert isinstance(payload, dict)
        posted.append(payload)
        if payload["cmd"] == "sessions.create":
            return Response({"status": "ok", "session": "prompta-chatgpt"})
        return Response(
            {
                "status": "ok",
                "solution": {
                    "status": 200,
                    "userAgent": "Mozilla/5.0 test-user-agent",
                    "cookies": [
                        {"name": "session", "domain": ".chatgpt.com", "value": "private"},
                        {"name": "cf_clearance", "domain": ".example.com", "value": "other"},
                        {"name": "cf_clearance", "domain": ".chatgpt.com", "value": "valid"},
                    ],
                },
            }
        )

    monkeypatch.setattr(solver, "urlopen", fake_open)
    assert solver.solve_cloudflare("http://127.0.0.1:8191") == (
        "valid", "Mozilla/5.0 test-user-agent"
    )
    assert posted == [
        {"cmd": "sessions.create", "session": "prompta-chatgpt"},
        {
            "cmd": "request.get",
            "session": "prompta-chatgpt",
            "url": "https://chatgpt.com/",
            "maxTimeout": 24000,
            "returnOnlyCookies": True,
        },
    ]


@pytest.mark.asyncio
async def test_navigation_uses_solver_only_after_challenge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __init__(self, challenged: bool) -> None:
            self.headers = {"cf-mitigated": "challenge"} if challenged else {}

    page = MagicMock()
    page.goto = AsyncMock(side_effect=[Response(True), Response(False)])
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    recover = AsyncMock(return_value=True)
    monkeypatch.setattr(driver, "_recover_security_challenge", recover)

    await driver.navigate("https://chatgpt.com/")
    assert page.goto.await_count == 2
    recover.assert_awaited_once_with(page)


@pytest.mark.asyncio
async def test_solver_clearance_applies_only_cf_cookie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROMPTA_FLARESOLVERR_URL", "http://127.0.0.1:8191")
    monkeypatch.setattr(
        "prompta.playwright_driver._claim_flaresolverr_attempt", lambda: True
    )
    monkeypatch.setattr(
        "prompta.playwright_driver.solve_cloudflare",
        lambda endpoint: ("clearance", "Mozilla/5.0 test-user-agent"),
    )
    page = MagicMock()
    page.evaluate = AsyncMock(return_value="different-agent")
    page.context.add_cookies = AsyncMock()
    session = MagicMock()
    session.send = AsyncMock()
    page.context.new_cdp_session = AsyncMock(return_value=session)
    driver = PlaywrightDriver(profile=tmp_path / "profile")

    assert await driver._recover_security_challenge(page)
    assert not await driver._recover_security_challenge(page)
    page.context.add_cookies.assert_awaited_once_with(
        [{"name": "cf_clearance", "value": "clearance", "url": "https://chatgpt.com/"}]
    )
    session.send.assert_awaited_once_with(
        "Network.setUserAgentOverride", {"userAgent": "Mozilla/5.0 test-user-agent"}
    )


@pytest.mark.asyncio
async def test_auth_endpoint_cloudflare_challenge_is_not_treated_as_logout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    probe = AsyncMock(return_value=json.dumps({
        "ok": False, "challenge": True, "token": "",
    }))
    monkeypatch.setattr(driver, "eval", probe)
    with pytest.raises(BrowserSecurityChallengeError, match="authentication endpoint"):
        await driver.ensure_token()
    probe.assert_awaited_once()
    assert "cf-mitigated" in (
        Path(__file__).parent.parent / "src/browser_scripts/ensure_token.js"
    ).read_text()


@pytest.mark.asyncio
async def test_auth_endpoint_nonchallenge_remains_login_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "eval", AsyncMock(return_value=json.dumps({
        "ok": False, "challenge": False, "token": "",
    })))
    with pytest.raises(RuntimeError, match="not logged into ChatGPT"):
        await driver.ensure_token()
