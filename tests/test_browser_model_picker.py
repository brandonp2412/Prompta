from __future__ import annotations

import asyncio
import re
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from _browser_fakes import FakeDriver
from _browser_fakes import offline_approval_default as offline_approval_default

import prompta.delivery_browser as delivery_browser
import prompta.playwright_driver as playwright_driver
from prompta.delivery_browser import (
    BrowserDeliverySender,
)
from prompta.playwright_driver import PlaywrightDriver


@pytest.mark.asyncio
async def test_model_selector_matches_current_public_label(tmp_path: Path) -> None:
    class Control:
        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
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

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
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

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> list[str]:
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

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
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
async def test_gpt6_uses_live_high_menu_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clicks: list[str] = []

    class Control:
        def __init__(self, name: str) -> None:
            self.name = name

        async def get_attribute(self, attr: str) -> str | None:
            if attr == "data-selected-reasoning-effort":
                return "high"
            if attr == "aria-checked":
                return "true" if "GPT-6" in clicks else "false"
            return None

        async def inner_text(self) -> str:
            return self.name

        async def is_visible(self) -> bool:
            return True

        async def focus(self) -> None:
            assert self.name == "High"

        async def dispatch_event(self, event: str) -> None:
            assert event == "click"
            clicks.append(self.name)

    class Collection:
        def __init__(self, items: list[Control]) -> None:
            self.items = items

        async def count(self) -> int:
            return len(self.items)

        @property
        def first(self) -> Control:
            return self.items[0]

    class Keyboard:
        async def press(self, key: str) -> None:
            assert key in {"Enter", "Escape"}
            if key == "Enter":
                clicks.append("High")

    class Page:
        keyboard = Keyboard()

        def get_by_role(self, role: str, *, name: re.Pattern[str]) -> Collection:
            if role == "button" and name.search("Select ChatGPT model"):
                return Collection([Control("High")])
            if clicks and role == "menuitem" and name.search("Select model"):
                return Collection([Control("High")])
            if len(clicks) >= 2 and role == "menuitemradio" and name.search("GPT-6"):
                return Collection([Control("GPT-6")])
            return Collection([])

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: Page())
    await driver.select_effort_model("GPT-6")
    assert clicks == ["High", "High", "GPT-6"]


@pytest.mark.asyncio
async def test_model_picker_opens_high_row_before_gpt6(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clicks: list[str] = []

    class Control:
        def __init__(self, label: str) -> None:
            self.label = label

        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def inner_text(self) -> str:
            return self.label

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
            return True

        async def get_attribute(self, name: str) -> str | None:
            if name == "aria-expanded":
                return "false"
            if name == "aria-checked" and self.label == "GPT-6":
                return "true" if len(clicks) == 3 else "false"
            return None

        async def click(self) -> None:
            clicks.append(self.label)

    class Collection:
        def __init__(self, items: list[Control]) -> None:
            self.items = items

        async def count(self) -> int:
            return len(self.items)

        @property
        def first(self) -> Control:
            return self.items[0]

        def nth(self, index: int) -> Control:
            return self.items[index]

        def filter(self, **_kwargs: object) -> Collection:
            return self

    class Keyboard:
        async def press(self, _key: str) -> None:
            pass

    class Page:
        keyboard = Keyboard()

        def get_by_role(self, role: str, *, name: re.Pattern[str] | None = None) -> Collection:
            if not clicks or name is None:
                return Collection([])
            if role == "menuitem" and name.search("Select model"):
                return Collection([Control("High")])
            if role == "menuitemradio" and name.search("GPT-6"):
                return Collection([Control("GPT-6")])
            return Collection([])

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: Page())

    async def selector(_page: object) -> Control | None:
        return Control("High") if not clicks else None

    monkeypatch.setattr(driver, "_model_selector_control", selector)

    async def missing_button(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(driver, "_semantic_button", missing_button)
    await driver.select_effort_model("GPT-6")
    assert clicks == ["High", "High", "GPT-6"]


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

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
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

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
            return False

        async def get_attribute(self, name: str) -> str | None:
            return "false" if name == "aria-selected" else None

        async def click(self) -> None:
            self.clicks += 1

    class Selector:
        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> list[str]:
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
async def test_model_selector_does_not_trust_truncated_control_scan(tmp_path: Path) -> None:
    class Control:
        def __init__(self, label: str) -> None:
            self.label = label

        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> list[str]:
            return [self.label]

    class Collection:
        def __init__(self, controls: list[Control]) -> None:
            self.controls = controls

        async def count(self) -> int:
            return len(self.controls)

        def nth(self, index: int) -> Control:
            return self.controls[index]

        def locator(self, _selector: str) -> Collection:
            return self

    class Page:
        def __init__(self) -> None:
            self.controls = (
                [Control("Select model")]
                + [Control("Other") for _ in range(59)]
                + [Control("Select model")]
            )

        def get_by_role(self, role: str, *, name: re.Pattern[str] | None = None) -> Collection:
            if role == "main" and name is None:
                return Collection(self.controls)
            return Collection([])

        def locator(self, _selector: str) -> Collection:
            return Collection(self.controls)

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    assert await driver._model_selector_control(Page()) is None


@pytest.mark.asyncio
async def test_semantic_button_does_not_select_from_truncated_candidate_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")

    class Candidates:
        async def count(self) -> int:
            return 81

        def nth(self, _index: int) -> object:
            raise AssertionError("an oversized candidate set must not be scanned")

    class Scope:
        def get_by_role(self, _role: str, *, name: re.Pattern[str] | None = None) -> object:
            return self

        def locator(self, _selector: str) -> Candidates:
            return Candidates()

    class Page(Scope):
        pass

    async def no_role_matches(_candidates: object, *, enabled: bool = True) -> None:
        return None

    monkeypatch.setattr(driver, "_first_usable", no_role_matches)
    monkeypatch.setattr(driver, "_page", lambda _context=None: Page())
    monkeypatch.setattr(driver, "_composer", no_role_matches)
    state = await driver.send_confirmation_state()
    assert state == {"composer_text": "", "send_in_progress": False}


@pytest.mark.asyncio
async def test_model_selection_uses_semantic_event_when_slider_obscures_click(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Option:
        def __init__(self) -> None:
            self.selected = False
            self.events = 0

        async def is_visible(self) -> bool:
            return True

        async def is_enabled(self) -> bool:
            return True

        async def get_attribute(self, name: str) -> str | None:
            return ("true" if self.selected else "false") if name == "aria-checked" else None

        async def click(self) -> None:
            # Simulate Playwright waiting for a pointer-intercepting overlay.
            await asyncio.sleep(5)

        async def dispatch_event(self, name: str) -> None:
            assert name == "click"
            self.events += 1
            self.selected = True

    class Collection:
        def filter(self, **_kwargs: object) -> Collection:
            return self

    class Keyboard:
        async def press(self, _key: str) -> None:
            return None

    class Page:
        keyboard = Keyboard()

        def get_by_role(self, _role: str, **_kwargs: object) -> Collection:
            return Collection()

    option = Option()
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: Page())

    async def usable(_candidates: object, *, enabled: bool = False) -> Option:
        return option

    async def no_selector(_page: object) -> None:
        return None

    monkeypatch.setattr(driver, "_first_usable", usable)
    monkeypatch.setattr(driver, "_model_selector_control", no_selector)
    await driver.select_effort_model("GPT-5.6 Sol")
    assert option.selected is True
    assert option.events == 1


@pytest.mark.asyncio
async def test_model_selection_verifies_selector_after_option_unmount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Selector:
        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> list[str]:
            return ["Select ChatGPT model", "GPT-5.6 Sol"]

    driver = PlaywrightDriver(profile=tmp_path / "profile")

    async def selector(_page: object) -> Selector:
        return Selector()

    monkeypatch.setattr(driver, "_model_selector_control", selector)

    class NoSelectedItems:
        def filter(self, **_kwargs: object) -> NoSelectedItems:
            return self

        async def count(self) -> int:
            return 0

    page = MagicMock(spec=playwright_driver.Page)
    page.locator.return_value = NoSelectedItems()
    option = MagicMock(spec=playwright_driver.Locator)
    option.is_visible = AsyncMock(return_value=False)
    option.get_attribute = AsyncMock(
        side_effect=AssertionError("unmounted locator must not be read")
    )
    assert await driver._model_selection_verified(page, option, re.compile(r"GPT-5\.6 Sol"))


@pytest.mark.asyncio
@pytest.mark.parametrize("checked", [True, False])
async def test_model_selection_verifies_hidden_checked_menu_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, checked: bool
) -> None:
    class SelectedCandidates:
        def filter(self, *, has_text: re.Pattern[str]) -> SelectedCandidates:
            assert has_text.search("GPT-5.6 Sol")
            return self

        async def count(self) -> int:
            return 1 if checked else 0

    def selected_candidates(selector: str) -> SelectedCandidates:
        assert '[role="menuitemradio"][aria-checked="true"]' in selector
        return SelectedCandidates()

    driver = PlaywrightDriver(profile=tmp_path / "profile")

    async def no_selector(_page: object) -> None:
        return None

    monkeypatch.setattr(driver, "_model_selector_control", no_selector)
    page = MagicMock(spec=playwright_driver.Page)
    page.locator.side_effect = selected_candidates
    option = MagicMock(spec=playwright_driver.Locator)
    option.is_visible = AsyncMock(return_value=False)
    option.get_attribute = AsyncMock(
        side_effect=AssertionError("hidden inaccessible role locator must not be read")
    )
    result = await driver._model_selection_verified(page, option, re.compile(r"^GPT-5\.6 Sol"))
    assert result is checked


@pytest.mark.asyncio
async def test_connector_grace_keeps_tab_until_deadline_and_signals_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.setattr(delivery_browser, "_CONNECTOR_APPROVAL_SECONDS", 0.03)
    accepted = threading.Event()

    class PermissionDriver(FakeDriver):
        checks = 0

        async def eval(self, _script: str, *, main_world: bool = False) -> str:
            if "always allow" in _script:
                assert accepted.is_set()
                assert not self.closed_contexts
                self.checks += 1
            return "/"

    driver = PermissionDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        connector_approval=True,
        delivery_hard_timeout_seconds=0.02,
    )
    await sender._send_browser("Work", accepted=accepted)
    assert driver.checks > 0
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed
