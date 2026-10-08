from __future__ import annotations

import re
from pathlib import Path

import pytest

from prompta.delivery_browser import BrowserDeliverySender
from prompta.playwright_driver import PlaywrightDriver


class FakeDriver:
    def __init__(self) -> None:
        self.is_connected = True
        self.needs_browser_restart = False
        self.context = ""
        self.composer = ""
        self.closed_contexts: list[str] = []
        self.closed = False
        self.probe_armed = False
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

    async def arm_page_send_probe(self) -> None:
        self.probe_armed = True

    def arm_send_capture(self) -> dict[str, object]:
        return self.capture

    async def type_message(self, message: str) -> None:
        self.composer = message

    async def click_send(self) -> None:
        self.composer = ""

    async def page_send_probe(self) -> dict[str, object]:
        return {"committed": True, "response_status": 200}

    def captured_send_response(self, _capture: dict[str, object]) -> tuple[str, int]:
        return ("request-1", 200)

    def clear_send_capture(self, capture: dict[str, object]) -> None:
        assert capture is self.capture

    async def clear_page_send_probe(self) -> None:
        self.probe_armed = False

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
    assert driver.probe_armed is False
    assert driver.composer == ""


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

    await driver.ensure_chat_surface(timeout=0.1)

    assert control.clicks == 0


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
