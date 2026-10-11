from __future__ import annotations

import re
from pathlib import Path

import pytest

from prompta.delivery_browser import (
    BrowserDeliverySender,
    DeliveryBackendUnavailableError,
    _is_conversation_path,
)
from prompta.playwright_driver import PlaywrightDriver, _normalise_composer_text
from prompta.send_outcome import SendOutcomeUnknownError


class FakeDriver:
    def __init__(self) -> None:
        self.is_connected = True
        self.needs_browser_restart = False
        self.context = ""
        self.composer = ""
        self.closed_contexts: list[str] = []
        self.closed = False
        self.capture: dict[str, object] = {
            "status": 200,
            "response_started": True,
            "request_id": "request-1",
        }

    async def connect(self) -> None:
        self.is_connected = True

    async def new_tab(self) -> str:
        self.context = "fresh-tab"
        return self.context

    async def wait_for_composer(self) -> None:
        return None

    async def ensure_chat_surface(self) -> None:
        return None

    async def select_effort_model(self, _model: str) -> None:
        return None

    async def set_effort_power_position(self, _position: int) -> dict[str, object]:
        return {"text": "High", "description": ""}

    async def dismiss_transient_controls(self) -> None:
        return None

    async def dom_state(self) -> dict[str, object]:
        return {"composer_text": self.composer, "rate_limit_text": ""}

    async def eval(self, _script: str) -> str:
        return "/"

    async def clear_composer(self) -> None:
        self.composer = ""

    def arm_send_capture(self) -> dict[str, object]:
        return self.capture

    async def type_message(self, message: str) -> None:
        self.composer = message

    async def click_send(self) -> None:
        self.composer = ""

    def captured_send_response(self, _capture: dict[str, object]) -> tuple[str, int] | None:
        return ("request-1", 200)

    def clear_send_capture(self, capture: dict[str, object]) -> None:
        assert capture is self.capture

    async def close_context(self, context: str) -> None:
        self.closed_contexts.append(context)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_fresh_chat_is_discarded_immediately_after_dispatch_confirmation(
    tmp_path: Path,
) -> None:
    driver = FakeDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
    )

    await sender._send_browser("Do the scheduled work")

    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed is True
    assert driver.composer == ""


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/", False),
        ("/?model=gpt", False),
        ("/c/example", True),
        ("/g/g-p-example/c/example", True),
    ],
)
def test_conversation_route_detection_does_not_parse_identifiers(path: str, expected: bool) -> None:
    assert _is_conversation_path(path) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_path", ["/c/existing", "/g/g-p-example/c/existing"])
async def test_existing_conversation_route_is_rejected_before_dispatch(
    tmp_path: Path,
    existing_path: str,
) -> None:
    class ExistingConversationDriver(FakeDriver):
        async def eval(self, _script: str) -> str:
            return existing_path

        async def select_effort_model(self, _model: str) -> None:
            pytest.fail("model selection must not run on an existing conversation")

        def arm_send_capture(self) -> dict[str, object]:
            pytest.fail("send capture must not arm on an existing conversation")

        async def type_message(self, message: str) -> None:
            pytest.fail(f"must not type into an existing conversation: {message}")

    driver = ExistingConversationDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
    )

    with pytest.raises(
        DeliveryBackendUnavailableError,
        match="fresh-chat navigation landed on an existing conversation",
    ):
        await sender._send_browser("Do the scheduled work")

    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed is True


@pytest.mark.asyncio
async def test_conversation_redirect_after_typing_prevents_send(tmp_path: Path) -> None:
    class RedirectOnTypingDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.redirected = False
            self.send_clicked = False

        async def type_message(self, message: str) -> None:
            await super().type_message(message)
            self.redirected = True

        async def eval(self, _script: str) -> str:
            return "/c/existing" if self.redirected else "/"

        async def click_send(self) -> None:
            self.send_clicked = True
            pytest.fail("must not submit into a redirected existing chat")

    driver = RedirectOnTypingDriver()
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", driver_factory=lambda: driver)
    with pytest.raises(
        DeliveryBackendUnavailableError,
        match="existing conversation before dispatch",
    ):
        await sender._send_browser("Do the scheduled work")
    assert not driver.send_clicked
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed


@pytest.mark.asyncio
async def test_unconfirmed_send_fails_closed_without_stream_probe(tmp_path: Path) -> None:
    class UnconfirmedDriver(FakeDriver):
        def captured_send_response(self, _capture: dict[str, object]) -> None:
            return None

    driver = UnconfirmedDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        send_timeout_seconds=0.01,
    )
    with pytest.raises(SendOutcomeUnknownError):
        await sender._send_browser("Scheduled work")
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed is True


@pytest.mark.asyncio
async def test_url_autolink_spacing_does_not_block_real_send(tmp_path: Path) -> None:
    class AutolinkingEditorDriver(FakeDriver):
        async def type_message(self, message: str) -> None:
            # Reproduced on ChatGPT's current live ProseMirror composer.
            self.composer = message.replace("(https://", "( https://")

    driver = AutolinkingEditorDriver()
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", driver_factory=lambda: driver)

    await sender._send_browser("Inspect upstream (https://github.com/stufently/gpt-web-gateway).")

    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.composer == ""


@pytest.mark.asyncio
async def test_stale_fresh_chat_composer_is_cleared_before_dispatch(tmp_path: Path) -> None:
    class StaleDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.composer = "stale draft"
            self.clear_calls = 0

        async def clear_composer(self) -> None:
            self.clear_calls += 1
            await super().clear_composer()

    driver = StaleDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
    )

    await sender._send_browser("Do the scheduled work")

    assert driver.clear_calls == 1
    assert driver.composer == ""
    assert driver.closed_contexts == ["fresh-tab"]


@pytest.mark.asyncio
async def test_rate_limit_detection_uses_semantic_active_surfaces(tmp_path: Path) -> None:
    class Candidate:
        def __init__(self, text: str, *, visible: bool = True, active: bool = True) -> None:
            self.text = text
            self.visible = visible
            self.active = active

        async def is_visible(self) -> bool:
            return self.visible

        async def evaluate(self, _script: str) -> bool:
            return self.active

        async def inner_text(self) -> str:
            return self.text

    class Collection:
        def __init__(self, candidates: list[Candidate]) -> None:
            self.candidates = candidates

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Candidate:
            return self.candidates[index]

        def get_by_text(self, pattern: re.Pattern[str]) -> Collection:
            return Collection(
                [candidate for candidate in self.candidates if pattern.search(candidate.text)]
            )

    class Page:
        def __init__(self) -> None:
            self.roles = {
                "alert": Collection(
                    [
                        Candidate("You've reached your usage limit"),
                        Candidate("Rate limit", active=False),
                    ]
                ),
                "status": Collection([]),
                "dialog": Collection([]),
                "main": Collection([Candidate("Normal fresh chat")]),
            }

        def get_by_role(self, role: str) -> Collection:
            return self.roles.get(role, Collection([]))

        def locator(self, _selector: str) -> Collection:
            return Collection([Candidate("Too many requests", visible=False)])

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    texts = await driver._rate_limit_texts(Page())

    assert texts == ["You've reached your usage limit"]


def test_active_delivery_driver_avoids_private_chatgpt_dom_hooks() -> None:
    source = Path("src/playwright_driver.py").read_text()
    assert "data-testid" not in source
    assert "data-composer-markdown" not in source


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attributes", "expected"),
    [
        ({"aria-pressed": "true"}, True),
        ({"aria-selected": "true"}, True),
        ({"aria-current": "page"}, True),
        ({"data-state": "selected"}, True),
        ({"aria-checked": "false"}, False),
        ({}, None),
    ],
)
async def test_selection_state_accepts_accessibility_role_churn(
    tmp_path: Path,
    attributes: dict[str, str],
    expected: bool | None,
) -> None:
    class Control:
        async def get_attribute(self, name: str) -> str | None:
            return attributes.get(name)

    driver = PlaywrightDriver(profile=tmp_path / "profile")

    assert await driver._selection_state(Control()) is expected


@pytest.mark.asyncio
async def test_first_usable_accepts_unique_visible_candidate_when_composed_guard_false(
    tmp_path: Path,
) -> None:
    class Candidate:
        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str) -> bool:
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

        async def evaluate(self, _script: str) -> bool:
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

        async def evaluate(self, _script: str) -> bool:
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

        async def evaluate(self, script: str) -> object:
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
async def test_hydrated_composer_rejects_ambiguous_unnamed_editors(tmp_path: Path) -> None:
    class Candidate:
        async def evaluate(self, script: str) -> object:
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


@pytest.mark.asyncio
async def test_model_selector_matches_current_public_label(tmp_path: Path) -> None:
    class Control:
        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str) -> bool:
            return True

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
            if role == "button" and name is not None and name.search("Select ChatGPT model"):
                return Collection([self.control])
            return Collection([])

    control = Control()
    driver = PlaywrightDriver(profile=tmp_path / "profile")

    found = await driver._model_selector_control(Page(control))

    assert found is control


@pytest.mark.asyncio
async def test_model_selector_prefers_visible_submenu_when_composed_guard_false(
    tmp_path: Path,
) -> None:
    class Control:
        def __init__(self, label: str) -> None:
            self.label = label

        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str) -> bool:
            return False

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
        def __init__(self, inner: Control, outer: Control) -> None:
            self.inner = inner
            self.outer = outer

        def locator(self, _selector: str) -> Collection:
            return Collection([])

        def get_by_role(
            self,
            role: str,
            *,
            name: re.Pattern[str] | None = None,
        ) -> Collection:
            if role == "menuitem" and name is not None and name.search(self.inner.label):
                return Collection([self.inner])
            if role == "button" and name is not None and name.search(self.outer.label):
                return Collection([self.outer])
            return Collection([])

    inner = Control("Select model")
    outer = Control("Select ChatGPT model")
    driver = PlaywrightDriver(profile=tmp_path / "profile")

    found = await driver._model_selector_control(Page(inner, outer))

    assert found is inner


@pytest.mark.asyncio
async def test_model_selector_ignores_unrelated_visible_popup(tmp_path: Path) -> None:
    class Control:
        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str) -> list[str]:
            return ["Plugins"]

    class Collection:
        def __init__(self, candidates: list[Control]) -> None:
            self.candidates = candidates

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Control:
            return self.candidates[index]

        def locator(self, _selector: str) -> Collection:
            return Collection([])

    class Scope:
        def __init__(self, control: Control) -> None:
            self.control = control

        async def count(self) -> int:
            return 0

        def nth(self, index: int) -> Control:
            raise IndexError(index)

        def locator(self, _selector: str) -> Collection:
            return Collection([self.control])

    class Page(Scope):
        def get_by_role(
            self,
            role: str,
            *,
            name: re.Pattern[str] | None = None,
        ) -> Scope | Collection:
            if role == "main" and name is None:
                return Scope(self.control)
            if role == "button" and name is not None and name.search("Plugins"):
                return Collection([self.control])
            return Collection([])

    driver = PlaywrightDriver(profile=tmp_path / "profile")

    found = await driver._model_selector_control(Page(Control()))

    assert found is None


@pytest.mark.asyncio
async def test_model_selection_walks_outer_and_submenu_before_option(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class State:
        stage = 0

    class Control:
        def __init__(self, state: State) -> None:
            self.state = state

        async def get_attribute(self, name: str) -> str | None:
            return "false" if name == "aria-expanded" else None

        async def click(self) -> None:
            self.state.stage += 1

    class Option:
        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str) -> bool:
            return False

        async def get_attribute(self, name: str) -> str | None:
            return "true" if name == "aria-checked" else None

    class Collection:
        def __init__(self, candidates: list[Option]) -> None:
            self.candidates = candidates

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Option:
            return self.candidates[index]

        def filter(self, **_kwargs: object) -> Collection:
            return self

        def get_by_role(self, _role: str, **_kwargs: object) -> Collection:
            return Collection([])

        def locator(self, _selector: str) -> Collection:
            return Collection([])

    class Keyboard:
        def __init__(self) -> None:
            self.pressed: list[str] = []

        async def press(self, key: str) -> None:
            self.pressed.append(key)

    class Page:
        def __init__(self, state: State, option: Option) -> None:
            self.state = state
            self.option = option
            self.keyboard = Keyboard()

        def get_by_role(
            self,
            role: str,
            *,
            name: re.Pattern[str] | None = None,
        ) -> Collection:
            if (
                self.state.stage >= 2
                and role == "menuitemradio"
                and name is not None
                and name.search("GPT-5.6 Sol")
            ):
                return Collection([self.option])
            return Collection([])

        def locator(self, _selector: str) -> Collection:
            return Collection([])

    state = State()
    outer = Control(state)
    inner = Control(state)
    option = Option()
    page = Page(state, option)
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: page)

    async def selector(_page: object) -> object:
        if state.stage == 0:
            return outer
        if state.stage == 1:
            return inner
        return None

    async def unexpected_trigger() -> object:
        raise AssertionError("semantic model selectors should be sufficient")

    monkeypatch.setattr(driver, "_model_selector_control", selector)
    monkeypatch.setattr(driver, "_effort_trigger_locator", unexpected_trigger)

    await driver.select_effort_model("GPT-5.6 Sol")

    assert state.stage == 2
    assert page.keyboard.pressed == ["Escape"]


@pytest.mark.asyncio
async def test_model_selection_accepts_menuitem_and_aria_selected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Option:
        def __init__(self) -> None:
            self.clicks = 0

        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str) -> bool:
            return False

        async def get_attribute(self, name: str) -> str | None:
            return "true" if name == "aria-selected" else None

        async def click(self) -> None:
            self.clicks += 1

    class Collection:
        def __init__(self, candidates: list[Option]) -> None:
            self.candidates = candidates

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Option:
            return self.candidates[index]

        def filter(self, **_kwargs: object) -> Collection:
            return self

    class Keyboard:
        def __init__(self) -> None:
            self.pressed: list[str] = []

        async def press(self, key: str) -> None:
            self.pressed.append(key)

    class Page:
        def __init__(self, option: Option) -> None:
            self.option = option
            self.keyboard = Keyboard()

        def get_by_role(
            self,
            role: str,
            *,
            name: re.Pattern[str] | None = None,
        ) -> Collection:
            if role == "menuitem" and name is not None and name.search("GPT-5.6 Sol"):
                return Collection([self.option])
            return Collection([])

    option = Option()
    page = Page(option)
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: page)

    await driver.select_effort_model("GPT-5.6 Sol")

    assert option.clicks == 0
    assert page.keyboard.pressed == ["Escape"]


@pytest.mark.parametrize(
    ("current_label", "should_fail"),
    [
        ("GPT-5.6 Sol", False),
        (None, True),
    ],
)
@pytest.mark.asyncio
async def test_model_selection_verifies_click_before_reporting_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    current_label: str | None,
    should_fail: bool,
) -> None:
    class Option:
        def __init__(self) -> None:
            self.clicks = 0

        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str) -> bool:
            return False

        async def get_attribute(self, name: str) -> str | None:
            return "false" if name == "aria-selected" else None

        async def click(self) -> None:
            self.clicks += 1

    class Selector:
        async def evaluate(self, _script: str) -> list[str]:
            return ["Select ChatGPT model", current_label or "GPT-5.6 Luna"]

    class Collection:
        def __init__(self, candidates: list[Option]) -> None:
            self.candidates = candidates

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Option:
            return self.candidates[index]

        def filter(self, **_kwargs: object) -> Collection:
            return self

    class Keyboard:
        def __init__(self) -> None:
            self.pressed: list[str] = []

        async def press(self, key: str) -> None:
            self.pressed.append(key)

    class Page:
        def __init__(self, option: Option) -> None:
            self.option = option
            self.keyboard = Keyboard()

        def get_by_role(
            self,
            role: str,
            *,
            name: re.Pattern[str] | None = None,
        ) -> Collection:
            if role == "menuitem" and name is not None and name.search("GPT-5.6 Sol"):
                return Collection([self.option])
            return Collection([])

    option = Option()
    page = Page(option)
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    monkeypatch.setattr("prompta.playwright_driver._MODEL_SELECTION_VERIFY_ATTEMPTS", 1)
    monkeypatch.setattr("prompta.playwright_driver._MODEL_SELECTION_VERIFY_INTERVAL_SECONDS", 0.0)

    selector_calls = 0

    async def selector(_page: object) -> Selector | None:
        nonlocal selector_calls
        selector_calls += 1
        if selector_calls == 1 or current_label is None:
            return None
        return Selector()

    async def unavailable(model_name: str) -> None:
        raise RuntimeError(f"selection for {model_name} was not verified")

    monkeypatch.setattr(driver, "_model_selector_control", selector)
    monkeypatch.setattr(driver, "_raise_model_selection_unavailable", unavailable)

    if should_fail:
        with pytest.raises(RuntimeError, match="was not verified"):
            await driver.select_effort_model("GPT-5.6 Sol")
    else:
        await driver.select_effort_model("GPT-5.6 Sol")

    assert option.clicks == 1
    assert page.keyboard.pressed == ([] if should_fail else ["Escape"])


@pytest.mark.asyncio
async def test_send_readiness_recovers_when_disabled_control_is_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Control:
        def __init__(self, ready: bool) -> None:
            self.ready = ready
            self.checks = 0

        async def is_enabled(self) -> bool:
            self.checks += 1
            return self.ready

    stale = Control(False)
    replacement = Control(True)
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    discoveries = 0

    async def send_control(_page: object, *, enabled: bool = True) -> object:
        nonlocal discoveries
        discoveries += 1
        assert enabled is False
        return stale if discoveries == 1 else replacement

    class PageStub:
        url = "https://chatgpt.com/"

    monkeypatch.setattr(driver, "_page", lambda _context=None: PageStub())
    monkeypatch.setattr(driver, "_send_control", send_control)

    await driver.wait_for_send_ready(timeout=0.5)

    assert stale.checks == 1
    assert replacement.checks == 1
    assert discoveries >= 2


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

    with pytest.raises(RuntimeError, match="multi-factor authentication required; composer unavailable"):
        await driver.wait_for_composer(timeout=0)


@pytest.mark.asyncio
async def test_composer_timeout_classifies_expired_login_without_submitting(monkeypatch: pytest.MonkeyPatch) -> None:
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
async def test_composer_text_fallback_targets_the_composer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from playwright.async_api import Error as PlaywrightError

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

        async def evaluate(self, expression: str) -> bool:
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
    from playwright.async_api import Error as PlaywrightError

    class Composer:
        async def is_visible(self) -> bool:
            return True

        async def fill(self, _text: str) -> None:
            raise PlaywrightError("fill unavailable")

        async def press(self, _key: str) -> None:
            pass

        async def focus(self) -> None:
            pass

        async def evaluate(self, expression: str) -> bool:
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
