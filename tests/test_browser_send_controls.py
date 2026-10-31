from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from _browser_fakes import offline_approval_default as offline_approval_default

from prompta.playwright_driver import PlaywrightDriver, _normalise_composer_text
from prompta.send_outcome import SendOutcomeUnknownError


@pytest.mark.asyncio
async def test_click_send_rechecks_composer_after_readiness_before_enter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Keyboard:
        def __init__(self) -> None:
            self.pressed: list[str] = []

        async def press(self, key: str) -> None:
            self.pressed.append(key)

    class Page:
        def __init__(self) -> None:
            self.keyboard = Keyboard()

    class Composer:
        pass

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = Page()
    composer = Composer()
    composer_text = "Scheduled work"
    focus_calls = 0

    async def focus_composer() -> Composer:
        nonlocal focus_calls
        focus_calls += 1
        return composer

    async def wait_for_send_ready(timeout: float = 3.0) -> None:
        nonlocal composer_text
        assert timeout == 3.0
        composer_text = "Different prompt"

    async def read_composer_text(_composer: object) -> str:
        return composer_text

    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    monkeypatch.setattr(driver, "_focus_composer", focus_composer)
    monkeypatch.setattr(driver, "wait_for_send_ready", wait_for_send_ready)
    monkeypatch.setattr(driver, "_composer_text", read_composer_text)

    with pytest.raises(RuntimeError, match="composer changed before submit"):
        await driver.click_send("Scheduled work")

    assert focus_calls == 2
    assert page.keyboard.pressed == []


@pytest.mark.asyncio
async def test_click_send_prefers_ready_send_control_over_enter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Keyboard:
        async def press(self, key: str) -> None:
            pytest.fail(f"Enter fallback must not run when send control is ready: {key}")

    class Page:
        def __init__(self) -> None:
            self.keyboard = Keyboard()

    class Composer:
        pass

    class Control:
        def __init__(self) -> None:
            self.clicks = 0

        async def click(self) -> None:
            self.clicks += 1

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = Page()
    composer = Composer()
    control = Control()

    async def focus_composer() -> Composer:
        return composer

    async def wait_for_send_ready(timeout: float = 3.0) -> Control:
        assert timeout == 3.0
        return control

    async def read_composer_text(_composer: object) -> str:
        return "Scheduled work"

    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    monkeypatch.setattr(driver, "_focus_composer", focus_composer)
    monkeypatch.setattr(driver, "wait_for_send_ready", wait_for_send_ready)
    monkeypatch.setattr(driver, "_composer_text", read_composer_text)

    await driver.click_send("Scheduled work")

    assert control.clicks == 1


@pytest.mark.asyncio
async def test_click_send_control_failure_keeps_outcome_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Keyboard:
        async def press(self, key: str) -> None:
            pytest.fail(
                f"Enter fallback must not run after a ready send control was selected: {key}"
            )

    class Page:
        def __init__(self) -> None:
            self.keyboard = Keyboard()

    class Composer:
        pass

    class Control:
        async def click(self) -> None:
            raise RuntimeError("detached while dispatching")

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = Page()
    composer = Composer()

    async def focus_composer() -> Composer:
        return composer

    async def wait_for_send_ready(timeout: float = 3.0) -> Control:
        assert timeout == 3.0
        return Control()

    async def read_composer_text(_composer: object) -> str:
        return "Scheduled work"

    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    monkeypatch.setattr(driver, "_focus_composer", focus_composer)
    monkeypatch.setattr(driver, "wait_for_send_ready", wait_for_send_ready)
    monkeypatch.setattr(driver, "_composer_text", read_composer_text)

    with pytest.raises(SendOutcomeUnknownError, match="clicking the send control"):
        await driver.click_send("Scheduled work")


@pytest.mark.asyncio
async def test_click_send_accepts_normalised_prompt_on_final_recheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Keyboard:
        def __init__(self) -> None:
            self.pressed: list[str] = []

        async def press(self, key: str) -> None:
            self.pressed.append(key)

    class Page:
        def __init__(self) -> None:
            self.keyboard = Keyboard()

    class Composer:
        pass

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = Page()
    composer = Composer()

    async def focus_composer() -> Composer:
        return composer

    async def wait_for_send_ready(timeout: float = 3.0) -> None:
        assert timeout == 3.0

    async def read_composer_text(_composer: object) -> str:
        return "Inspect upstream ( https://github.com/stufently/gpt-web-gateway)."

    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    monkeypatch.setattr(driver, "_focus_composer", focus_composer)
    monkeypatch.setattr(driver, "wait_for_send_ready", wait_for_send_ready)
    monkeypatch.setattr(driver, "_composer_text", read_composer_text)

    await driver.click_send("Inspect upstream (https://github.com/stufently/gpt-web-gateway).")

    assert page.keyboard.pressed == ["Enter"]


@pytest.mark.asyncio
async def test_send_readiness_fails_closed_when_known_control_stays_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Control:
        async def is_enabled(self) -> bool:
            return False

    control = Control()
    driver = PlaywrightDriver(profile=tmp_path / "profile")

    async def send_control(_page: object, *, enabled: bool = True) -> object:
        assert enabled is False
        return control

    class PageStub:
        url = "https://chatgpt.com/"

    monkeypatch.setattr(driver, "_page", lambda _context=None: PageStub())
    monkeypatch.setattr(driver, "_send_control", send_control)

    async def no_challenge(*, context: str | None = None) -> bool:
        return False

    async def no_login() -> bool:
        return False

    monkeypatch.setattr(driver, "_cloudflare_challenge_present", no_challenge)
    monkeypatch.setattr(driver, "login_required", no_login)

    with pytest.raises(RuntimeError, match="send control remained disabled"):
        await driver.wait_for_send_ready(timeout=0.1)


@pytest.mark.asyncio
async def test_send_readiness_preserves_keyboard_fallback_without_known_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    calls = 0

    async def send_control(_page: object, *, enabled: bool = True) -> None:
        nonlocal calls
        calls += 1
        assert enabled is False
        return None

    class PageStub:
        url = "https://chatgpt.com/"

    monkeypatch.setattr(driver, "_page", lambda _context=None: PageStub())
    monkeypatch.setattr(driver, "_send_control", send_control)

    async def no_challenge(*, context: str | None = None) -> bool:
        return False

    async def no_login() -> bool:
        return False

    monkeypatch.setattr(driver, "_cloudflare_challenge_present", no_challenge)
    monkeypatch.setattr(driver, "login_required", no_login)
    await driver.wait_for_send_ready(timeout=0.1)

    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("challenge", "mfa", "login", "expected", "login_calls"),
    [
        (True, True, True, "security challenge is blocking send readiness", 0),
        (False, True, True, "multi-factor authentication required; send control unavailable", 0),
        (False, False, True, "login required; send control unavailable", 1),
    ],
)
async def test_missing_send_control_rejects_session_interruptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    challenge: bool,
    mfa: bool,
    login: bool,
    expected: str,
    login_calls: int,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    calls: list[str] = []

    class PageStub:
        url = "https://auth.openai.com/mfa-challenge" if mfa else "https://chatgpt.com/"

    async def no_control(_page: object, *, enabled: bool = True) -> None:
        calls.append("control")
        return None

    async def security_challenge(*, context: str | None = None) -> bool:
        calls.append("challenge")
        return challenge

    async def login_required() -> bool:
        calls.append("login")
        return login

    monkeypatch.setattr(driver, "_page", lambda _context=None: PageStub())
    monkeypatch.setattr(driver, "_send_control", no_control)
    monkeypatch.setattr(driver, "_cloudflare_challenge_present", security_challenge)
    monkeypatch.setattr(driver, "login_required", login_required)

    with pytest.raises(RuntimeError, match=expected):
        await driver.wait_for_send_ready(timeout=0.1)
    assert calls.count("control") == 1
    assert calls.count("login") == login_calls


def test_composer_normalisation_accounts_for_chatgpt_autolink_spacing() -> None:
    # ChatGPT's ProseMirror editor inserts a space after the opening
    # parenthesis when linking URLs, even though Playwright filled the
    # original exact string. This must not strand the delivery queue.
    requested = "Inspect upstream (https://github.com/stufently/gpt-web-gateway)."
    editor_text = "Inspect upstream ( https://github.com/stufently/gpt-web-gateway)."

    assert _normalise_composer_text(requested) == _normalise_composer_text(editor_text)
    assert _normalise_composer_text("a=https://github.com/test") == _normalise_composer_text(
        "a= https://github.com/test"
    )
    assert _normalise_composer_text("a=https://github.com/good") != _normalise_composer_text(
        "a=https://github.com/bad"
    )
    assert _normalise_composer_text("preserve unrelated words") != _normalise_composer_text(
        "preserve altered words"
    )


@pytest.mark.parametrize(
    ("url", "required"),
    [
        ("https://auth.openai.com/authorize?state=secret", True),
        ("https://chatgpt.com/auth/login?next=/", True),
        ("https://chatgpt.com/login", True),
        ("https://chatgpt.com/", False),
        ("https://chatgpt.com/c/example", False),
        ("https://notchatgpt.com/auth/login", False),
        ("https://chatgpt.com.evil.test/login", False),
    ],
)
def test_firstwari_authentication_redirect_classification(url: str, required: bool) -> None:
    assert PlaywrightDriver._authentication_route(url) is required


@pytest.mark.asyncio
async def test_first_usable_refuses_truncated_single_candidate_scan(tmp_path: Path) -> None:
    class Candidate:
        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
            return True

    class Collection:
        async def count(self) -> int:
            return 25

        def nth(self, _index: int) -> Candidate:
            raise AssertionError("Oversized ambiguous collection must not be scanned")

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    assert await driver._first_usable([Collection()], limit=24) is None


@pytest.mark.asyncio
async def test_power_control_does_not_trust_truncated_slider_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Collection:
        def __init__(self, count: int) -> None:
            self.size = count

        async def count(self) -> int:
            return self.size

        def nth(self, index: int) -> Collection:
            raise AssertionError(f"partial scan selected index {index}")

    page = MagicMock()
    page.get_by_role.return_value = Collection(41)
    page.locator.return_value = Collection(13)
    driver = PlaywrightDriver(profile=tmp_path / "profile")

    async def no_named_control(candidates: object, *, enabled: bool) -> None:
        assert enabled
        assert candidates
        return None

    monkeypatch.setattr(driver, "_first_usable", no_named_control)
    assert await driver._power_control(page) is None
