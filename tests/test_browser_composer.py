from __future__ import annotations

import re
from pathlib import Path

import pytest
from _browser_fakes import offline_approval_default as offline_approval_default

import prompta.playwright_driver as playwright_driver
from prompta.playwright_driver import PlaywrightDriver


@pytest.mark.asyncio
async def test_first_usable_accepts_unique_visible_candidate_when_composed_guard_false(
    tmp_path: Path,
) -> None:
    class Candidate:
        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
            return False

    class Collection:
        def __init__(self, candidates: list[Candidate]) -> None:
            self.candidates = candidates

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Candidate:
            return self.candidates[index]

    candidate = Candidate()
    driver = PlaywrightDriver(profile=tmp_path / "profile")

    found = await driver._first_usable([Collection([candidate])])

    assert found is candidate


@pytest.mark.asyncio
async def test_first_usable_refuses_ambiguous_visible_candidates_when_guard_false(
    tmp_path: Path,
) -> None:
    class Candidate:
        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
            return False

    class Collection:
        def __init__(self, candidates: list[Candidate]) -> None:
            self.candidates = candidates

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Candidate:
            return self.candidates[index]

    driver = PlaywrightDriver(profile=tmp_path / "profile")

    found = await driver._first_usable([Collection([Candidate(), Candidate()])])

    assert found is None


@pytest.mark.asyncio
async def test_first_usable_refuses_two_composed_active_controls(tmp_path: Path) -> None:
    class Candidate:
        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
            return True

    class Collection:
        def __init__(self) -> None:
            self.candidates = [Candidate(), Candidate()]

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Candidate:
            return self.candidates[index]

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    assert await driver._first_usable([Collection()]) is None


@pytest.mark.asyncio
async def test_chat_surface_recognises_pressed_chat_without_click(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Control:
        def __init__(self) -> None:
            self.clicks = 0

        async def get_attribute(self, name: str) -> str | None:
            return "true" if name == "aria-pressed" else None

        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
            return True

        async def click(self) -> None:
            self.clicks += 1

    class Collection:
        def __init__(self, candidates: list[Control]) -> None:
            self.candidates = candidates

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Control:
            return self.candidates[index]

        def locator(self, _selector: str) -> Collection:
            return Collection([])

    class Page:
        def __init__(self, control: Control) -> None:
            self.control = control

        def locator(self, _selector: str) -> Collection:
            return Collection([])

        def get_by_role(
            self,
            role: str,
            *,
            name: re.Pattern[str] | None = None,
        ) -> Collection:
            if role == "button" and name is not None and name.search("Chat"):
                return Collection([self.control])
            return Collection([])

    control = Control()
    page = Page(control)
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: page)

    async def no_ready_composer(_page: object) -> object:
        return None

    monkeypatch.setattr(driver, "_composer", no_ready_composer)

    async def no_challenge(*, context: str | None = None) -> bool:
        return False

    monkeypatch.setattr(driver, "_cloudflare_challenge_present", no_challenge)
    await driver.ensure_chat_surface(timeout=0.1)

    assert control.clicks == 0


@pytest.mark.asyncio
async def test_chat_surface_skips_truncated_semantic_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Candidate:
        def __init__(self, label: str) -> None:
            self.label = label
            self.clicks = 0

        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, script: str, *, isolated_context: bool = True) -> bool | list[str]:
            if "semantic_control_labels" in script:
                return [self.label]
            return True

        async def click(self) -> None:
            self.clicks += 1

    class Collection:
        def __init__(self, items: list[Candidate]) -> None:
            self.items = items

        async def count(self) -> int:
            return len(self.items)

        def nth(self, index: int) -> Candidate:
            return self.items[index]

        def locator(self, _selector: str) -> Collection:
            return Collection(self.items)

    candidates = [Candidate("Other") for _ in range(41)]
    candidates[0].label = "Chat"
    candidates[40].label = "Chat"

    class Page:
        def get_by_role(self, role: str, *, name: re.Pattern[str] | None = None) -> Collection:
            if role == "main":
                return Collection(candidates)
            return Collection([])

        def locator(self, _selector: str) -> Collection:
            return Collection(candidates)

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: Page())

    async def no_composer(_page: object) -> None:
        return None

    async def no_challenge(*, context: str | None = None) -> bool:
        return False

    monkeypatch.setattr(driver, "_composer", no_composer)
    monkeypatch.setattr(driver, "_cloudflare_challenge_present", no_challenge)
    with pytest.raises(RuntimeError, match="ChatGPT Chat surface did not become active"):
        await driver.ensure_chat_surface(timeout=0.02)
    assert all(candidate.clicks == 0 for candidate in candidates)


@pytest.mark.asyncio
async def test_wait_for_composer_fails_closed_on_security_challenge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")

    async def challenge_present(*, context: str | None = None) -> bool:
        del context
        return True

    monkeypatch.setattr(driver, "_cloudflare_challenge_present", challenge_present)

    with pytest.raises(RuntimeError, match="security challenge"):
        await driver.wait_for_composer(timeout=0.1)


@pytest.mark.asyncio
async def test_wait_for_composer_rejects_logged_out_page_with_visible_composer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = object()
    login_checks = 0

    async def composer_ready(_page: object) -> object:
        return object()

    async def login_required() -> bool:
        nonlocal login_checks
        login_checks += 1
        return True

    async def no_challenge(*, context: str | None = None) -> bool:
        del context
        return False

    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    monkeypatch.setattr(driver, "_composer", composer_ready)
    monkeypatch.setattr(driver, "login_required", login_required)
    monkeypatch.setattr(driver, "_cloudflare_challenge_present", no_challenge)

    with pytest.raises(RuntimeError, match="login required; composer unavailable"):
        await driver.wait_for_composer(timeout=0.1)

    assert login_checks == 1


@pytest.mark.asyncio
async def test_wait_for_composer_reports_challenge_after_readiness_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = object()
    probes = 0

    async def challenge_present(*, context: str | None = None) -> bool:
        nonlocal probes
        del context
        probes += 1
        return probes > 1

    async def no_composer(_page: object) -> object | None:
        return None

    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    monkeypatch.setattr(driver, "_cloudflare_challenge_present", challenge_present)
    monkeypatch.setattr(driver, "_composer", no_composer)

    with pytest.raises(RuntimeError, match="security challenge"):
        await driver.wait_for_composer(timeout=0.01)

    assert probes == 2


@pytest.mark.asyncio
async def test_wait_for_composer_detects_challenge_during_hydration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = object()
    probes = 0
    composer_checks = 0

    async def challenge_present(*, context: str | None = None) -> bool:
        nonlocal probes
        del context
        probes += 1
        return probes == 2

    async def no_composer(_page: object) -> object | None:
        nonlocal composer_checks
        composer_checks += 1
        return None

    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    monkeypatch.setattr(driver, "_cloudflare_challenge_present", challenge_present)
    monkeypatch.setattr(driver, "_composer", no_composer)

    with pytest.raises(RuntimeError, match="security challenge"):
        await driver.wait_for_composer(timeout=1)

    assert probes == 2
    assert composer_checks == 1


@pytest.mark.asyncio
async def test_hydrated_composer_prefers_named_editor_when_multiple_are_active(
    tmp_path: Path,
) -> None:
    class Candidate:
        def __init__(self, labels: list[str]) -> None:
            self.labels = labels

        async def evaluate(self, script: str, *, isolated_context: bool = True) -> object:
            if "new Set(labels)" in script:
                return self.labels
            return True

        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

    class Collection:
        def __init__(self, candidates: list[Candidate]) -> None:
            self.candidates = candidates

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Candidate:
            return self.candidates[index]

    class Page:
        def __init__(self, candidates: list[Candidate]) -> None:
            self.candidates = candidates

        def locator(self, _selector: str) -> Collection:
            return Collection(self.candidates)

    unrelated = Candidate(["Scratch editor"])
    composer = Candidate(["Ask ChatGPT"])
    driver = PlaywrightDriver(profile=tmp_path / "profile")

    found = await driver._hydrated_composer(Page([unrelated, composer]))

    assert found is composer


@pytest.mark.asyncio
async def test_hydrated_composer_fails_closed_on_partial_inspection(tmp_path: Path) -> None:
    class Candidate:
        def __init__(self, broken: bool) -> None:
            self.broken = broken

        async def evaluate(self, script: str, *, isolated_context: bool = True) -> object:
            if self.broken:
                raise playwright_driver.PlaywrightError("detached editor")
            return ["Ask ChatGPT"] if "new Set(labels)" in script else True

        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

    class Collection:
        def __init__(self) -> None:
            self.candidates = [Candidate(False), Candidate(True)]

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Candidate:
            return self.candidates[index]

    class Page:
        def locator(self, _selector: str) -> Collection:
            return Collection()

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    assert await driver._hydrated_composer(Page()) is None


@pytest.mark.asyncio
async def test_hydrated_composer_refuses_truncated_editable_scan(tmp_path: Path) -> None:
    class Candidate:
        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> object:
            raise AssertionError("oversized set must not be scanned")

        async def is_visible(self) -> bool:
            raise AssertionError("oversized set must not be scanned")

        async def is_enabled(self) -> bool:
            raise AssertionError("oversized set must not be scanned")

    class Collection:
        async def count(self) -> int:
            return 25

        def nth(self, _index: int) -> Candidate:
            raise AssertionError("must fail closed before inspecting any candidate")

    class Page:
        def locator(self, _selector: str) -> Collection:
            return Collection()

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    assert await driver._hydrated_composer(Page()) is None


@pytest.mark.asyncio
async def test_hydrated_composer_rejects_ambiguous_unnamed_editors(tmp_path: Path) -> None:
    class Candidate:
        async def evaluate(self, script: str, *, isolated_context: bool = True) -> object:
            return [] if "new Set(labels)" in script else True

        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

    class Collection:
        def __init__(self, candidates: list[Candidate]) -> None:
            self.candidates = candidates

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Candidate:
            return self.candidates[index]

    class Page:
        def locator(self, _selector: str) -> Collection:
            return Collection([Candidate(), Candidate()])

    driver = PlaywrightDriver(profile=tmp_path / "profile")

    assert await driver._hydrated_composer(Page()) is None


@pytest.mark.asyncio
async def test_navigation_fails_closed_on_cloudflare_mitigation_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NavigationResponse:
        headers = {"cf-mitigated": "challenge"}

    class Page:
        async def goto(self, _url: str, *, wait_until: str, timeout: int) -> NavigationResponse:
            assert wait_until == "domcontentloaded"
            assert timeout > 0
            return NavigationResponse()

    page = Page()
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: page)

    with pytest.raises(RuntimeError, match="security challenge"):
        await driver.navigate("https://chatgpt.com/")


@pytest.mark.asyncio
async def test_new_tab_sets_actionable_viewport_before_navigation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Page:
        viewport: dict[str, int] | None = None

        async def set_viewport_size(self, size: dict[str, int]) -> None:
            self.viewport = size

        def set_default_timeout(self, _timeout: int) -> None:
            pass

        def on(self, _event: str, _callback: object) -> None:
            pass

    class Context:
        async def new_page(self) -> Page:
            return page

    page = Page()
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_browser_context", Context())

    async def navigate(_url: str, *, context: str | None = None) -> None:
        assert context is not None
        assert page.viewport == {"width": 1280, "height": 960}

    monkeypatch.setattr(driver, "navigate", navigate)
    context = await driver.new_tab()
    assert driver.context == context
    assert page.viewport == {"width": 1280, "height": 960}


@pytest.mark.asyncio
async def test_new_tab_closes_half_created_page_when_viewport_setup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Page:
        closed = False

        async def set_viewport_size(self, _size: dict[str, int]) -> None:
            raise RuntimeError("viewport unavailable")

        def set_default_timeout(self, _timeout: int) -> None:
            pass

        def on(self, _event: str, _callback: object) -> None:
            pass

        def is_closed(self) -> bool:
            return self.closed

        async def close(self) -> None:
            self.closed = True

    class Context:
        async def new_page(self) -> Page:
            return page

    page = Page()
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_browser_context", Context())

    with pytest.raises(RuntimeError, match="viewport unavailable"):
        await driver.new_tab()

    assert page.closed
    assert driver._pages == {}
    assert driver._page_contexts == {}
    assert driver._owned_contexts == set()


@pytest.mark.asyncio
async def test_effort_trigger_accepts_explicit_label_without_popup_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = object()
    page = object()
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: page)

    async def semantic_button(candidate_page: object, _name: object) -> object:
        assert candidate_page is page
        return marker

    monkeypatch.setattr(driver, "_semantic_button", semantic_button)

    assert await driver._effort_trigger_locator() is marker


@pytest.mark.parametrize(
    ("url", "required"),
    [
        ("https://auth.openai.com/mfa", True),
        ("https://auth.openai.com/mfa/", True),
        ("https://auth.openai.com/mfa-challenge?error=totp", True),
        ("https://auth.openai.com/api/mfa-challenge/verify", True),
        ("https://auth.openai.com/mfa-settings", False),
        ("https://chatgpt.com/?next=/mfa-challenge", False),
        ("https://auth.openai.com.evil.test/mfa-challenge", False),
        ("https://auth.openai.com/log-in", False),
    ],
)
def test_gateway_mfa_authentication_route_classification(url: str, required: bool) -> None:
    assert PlaywrightDriver._mfa_authentication_route(url) is required


@pytest.mark.asyncio
async def test_composer_timeout_classifies_mfa_without_inspecting_login_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PageStub:
        url = "https://auth.openai.com/mfa-challenge?error=totp"

    driver = PlaywrightDriver(profile=Path("/unused-test-profile"))

    async def no_security_challenge(*, context: str | None = None) -> bool:
        del context
        return False

    async def unexpected_login_check() -> bool:
        pytest.fail("MFA route classification must precede generic login inspection")

    monkeypatch.setattr(driver, "_page", lambda context=None: PageStub())
    monkeypatch.setattr(driver, "_composer", async_no_composer)
    monkeypatch.setattr(driver, "_cloudflare_challenge_present", no_security_challenge)
    monkeypatch.setattr(driver, "login_required", unexpected_login_check)

    with pytest.raises(
        RuntimeError, match="multi-factor authentication required; composer unavailable"
    ):
        await driver.wait_for_composer(timeout=0)


@pytest.mark.asyncio
async def test_composer_timeout_classifies_expired_login_without_submitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PageStub:
        url = "https://auth.openai.com/authorize"

    driver = PlaywrightDriver(profile=Path("/unused-test-profile"))

    async def no_security_challenge(*, context: str | None = None) -> bool:
        del context
        return False

    monkeypatch.setattr(driver, "_page", lambda context=None: PageStub())
    monkeypatch.setattr(driver, "_composer", async_no_composer)
    monkeypatch.setattr(driver, "_cloudflare_challenge_present", no_security_challenge)
    with pytest.raises(RuntimeError, match="login required"):
        await driver.wait_for_composer(timeout=0)


async def async_no_composer(_page: object) -> None:
    return None


@pytest.mark.asyncio
async def test_composer_text_fallback_targets_the_composer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from patchright.async_api import Error as PlaywrightError

    class Composer:
        def __init__(self) -> None:
            self.presses: list[str] = []

        async def is_visible(self) -> bool:
            return True

        async def fill(self, _text: str) -> None:
            raise PlaywrightError("contenteditable fill unsupported")

        async def press(self, key: str) -> None:
            self.presses.append(key)

        async def focus(self) -> None:
            self.presses.append("focus")

        async def evaluate(self, expression: str, *, isolated_context: bool = True) -> bool:
            assert "document.activeElement" in expression
            return True

    class Keyboard:
        def __init__(self) -> None:
            self.insertions: list[str] = []

        async def insert_text(self, text: str) -> None:
            self.insertions.append(text)

        async def press(self, _key: str) -> None:
            pytest.fail("Fallback must never select text in a different focused element")

    class Page:
        def __init__(self) -> None:
            self.keyboard = Keyboard()

    composer = Composer()
    page = Page()
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    await getattr(driver, "_replace_composer_text")(composer, "one-shot prompt")
    assert composer.presses == ["ControlOrMeta+A", "Backspace", "focus"]
    assert page.keyboard.insertions == ["one-shot prompt"]


@pytest.mark.asyncio
async def test_composer_fallback_rejects_stolen_focus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from patchright.async_api import Error as PlaywrightError

    class Composer:
        async def is_visible(self) -> bool:
            return True

        async def fill(self, _text: str) -> None:
            raise PlaywrightError("fill unavailable")

        async def press(self, _key: str) -> None:
            pass

        async def focus(self) -> None:
            pass

        async def evaluate(self, expression: str, *, isolated_context: bool = True) -> bool:
            assert "document.activeElement" in expression
            return False

    class Keyboard:
        async def insert_text(self, _text: str) -> None:
            pytest.fail("Must not insert into an unrelated focused field")

    class Page:
        keyboard = Keyboard()

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: Page())
    with pytest.raises(RuntimeError, match="lost focus before text insertion"):
        await getattr(driver, "_replace_composer_text")(Composer(), "one-shot prompt")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("challenge", "mfa", "login", "expected"),
    [
        (True, True, True, "security challenge is blocking model selection"),
        (False, True, True, "multi-factor authentication required; model selection unavailable"),
        (False, False, True, "login required; model selection unavailable"),
        (False, False, False, "model 'GPT-5.6 Sol' is unavailable"),
    ],
)
async def test_firstwari_picker_timeout_classifies_pre_dispatch_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    challenge: bool,
    mfa: bool,
    login: bool,
    expected: str,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    checks: list[str] = []

    class PageStub:
        url = "https://auth.openai.com/mfa-challenge" if mfa else "https://chatgpt.com/"

    async def security_challenge(*, context: str | None = None) -> bool:
        assert context is None
        checks.append("challenge")
        return challenge

    async def login_required() -> bool:
        checks.append("login")
        return login

    monkeypatch.setattr(driver, "_page", lambda _context=None: PageStub())
    monkeypatch.setattr(driver, "_cloudflare_challenge_present", security_challenge)
    monkeypatch.setattr(driver, "login_required", login_required)
    with pytest.raises(RuntimeError, match=re.escape(expected)):
        await driver._raise_model_selection_unavailable("GPT-5.6 Sol")
    assert checks == (["challenge"] if challenge or mfa else ["challenge", "login"])


@pytest.mark.asyncio
async def test_chat_surface_fails_closed_before_interacting_with_challenge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")

    class ChallengePage:
        def get_by_role(self, _role: str, *, name: object = None) -> object:
            raise AssertionError("Must not inspect chat controls during a challenge")

    monkeypatch.setattr(driver, "_page", lambda _context=None: ChallengePage())

    async def challenge(*, context: str | None = None) -> bool:
        return True

    monkeypatch.setattr(driver, "_cloudflare_challenge_present", challenge)
    with pytest.raises(RuntimeError, match="security challenge is blocking Chat surface"):
        await driver.ensure_chat_surface(timeout=0.1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("challenge", "mfa", "login", "expected", "login_calls"),
    [
        (True, True, True, "security challenge is blocking send readiness", 0),
        (False, True, True, "multi-factor authentication required; send control unavailable", 0),
        (False, False, True, "login required; send control unavailable", 1),
        (False, False, False, "send control remained disabled", 1),
    ],
)
async def test_firstwari_send_readiness_timeout_classifies_predispatch_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    challenge: bool,
    mfa: bool,
    login: bool,
    expected: str,
    login_calls: int,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    calls = 0

    class PageStub:
        url = "https://auth.openai.com/mfa-challenge" if mfa else "https://chatgpt.com/"

    async def challenge_present(*, context: str | None = None) -> bool:
        return challenge

    async def login_required() -> bool:
        nonlocal calls
        calls += 1
        return login

    monkeypatch.setattr(driver, "_page", lambda _context=None: PageStub())
    monkeypatch.setattr(driver, "_cloudflare_challenge_present", challenge_present)
    monkeypatch.setattr(driver, "login_required", login_required)
    with pytest.raises(RuntimeError, match=expected):
        await driver._raise_send_readiness_unavailable()
    assert calls == login_calls


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://chatgpt.com/backend-api/f/conversation", True),
        ("https://chatgpt.com/backend-api/conversation/", True),
        ("https://chat.openai.com/backend-api/conversation", True),
        ("https://example.org/backend-api/f/conversation", False),
        ("https://chatgpt.com.evil.test/backend-api/conversation", False),
        ("http://chatgpt.com/backend-api/conversation", False),
        ("https://auth.openai.com/backend-api/conversation", False),
        ("https://chatgpt.com/backend-api/conversation/extra", False),
    ],
)
def test_send_capture_requires_chatgpt_origin(url: str, expected: bool) -> None:
    assert PlaywrightDriver._is_send_endpoint(url) is expected


@pytest.mark.asyncio
async def test_first_usable_refuses_truncated_candidate_scan(tmp_path: Path) -> None:
    class Candidate:
        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
            return True

    class Collection:
        def __init__(self) -> None:
            self.candidates = [Candidate(), *[Candidate() for _ in range(12)]]

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Candidate:
            return self.candidates[index]

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    assert await driver._first_usable([Collection()]) is None
