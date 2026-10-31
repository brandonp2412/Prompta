from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from _browser_fakes import FakeDriver
from _browser_fakes import offline_approval_default as offline_approval_default

import prompta.delivery_browser as delivery_browser
import prompta.playwright_driver as playwright_driver
from prompta.delivery_browser import (
    BrowserDeliverySender,
    DeliveryBackendUnavailableError,
)
from prompta.playwright_driver import PlaywrightDriver, _normalise_composer_text
from prompta.send_outcome import SendOutcomeUnknownError


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_path", ["/c/existing", "/g/g-p-example/c/existing"])
async def test_existing_conversation_route_is_rejected_before_dispatch(
    tmp_path: Path,
    existing_path: str,
) -> None:
    class ExistingConversationDriver(FakeDriver):
        async def eval(self, _script: str, *, main_world: bool = False) -> str:
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

        async def eval(self, _script: str, *, main_world: bool = False) -> str:
            return "/c/existing" if self.redirected else "/"

        async def click_send(self, expected_message: str) -> None:
            assert _normalise_composer_text(expected_message) == _normalise_composer_text(
                self.composer
            )
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
async def test_unconfirmed_send_diagnostic_never_logs_raw_path(tmp_path: Path) -> None:
    class UnconfirmedPathDriver(FakeDriver):
        async def eval(self, _script: str, *, main_world: bool = False) -> str:
            return "/temporary/opaque-sensitive-route-token"

        def captured_send_response(self, _capture: dict[str, object]) -> None:
            return None

    driver = UnconfirmedPathDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=lambda: driver, send_timeout_seconds=0.01
    )
    with pytest.raises(SendOutcomeUnknownError) as exc:
        await sender._send_browser("Scheduled work")
    assert "conversation_route=False" in str(exc.value)
    assert "opaque-sensitive-route-token" not in str(exc.value)
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed


@pytest.mark.asyncio
async def test_route_navigation_alone_does_not_prove_send_acceptance(tmp_path: Path) -> None:
    class RouteConfirmedSlowComposer(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.dispatched = False
            self.confirmation_dom_calls = 0

        async def click_send(self, expected_message: str) -> None:
            await super().click_send(expected_message)
            self.dispatched = True

        async def eval(self, _script: str, *, main_world: bool = False) -> str:
            return "/c/new-fresh-chat" if self.dispatched else "/"

        async def send_confirmation_state(self) -> dict[str, object]:
            self.confirmation_dom_calls += 1
            raise TimeoutError("composer blocked while UI hydrates")

        def captured_send_response(self, _capture: dict[str, object]) -> None:
            return None

    driver = RouteConfirmedSlowComposer()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=lambda: driver, send_timeout_seconds=0.01
    )
    with pytest.raises(SendOutcomeUnknownError) as error:
        await sender._send_browser("Do the scheduled work")
    assert error.value.stage == "send_confirmation"
    assert "conversation_route=True" in str(error.value)
    assert driver.dispatched
    assert driver.confirmation_dom_calls >= 1
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed


@pytest.mark.asyncio
async def test_route_navigation_waits_for_delayed_transport_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RouteThenTransportDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.dispatched = False
            self.state_probes = 0

        async def click_send(self, expected_message: str) -> None:
            await super().click_send(expected_message)
            self.dispatched = True

        async def eval(self, _script: str, *, main_world: bool = False) -> str:
            return "/c/new-fresh-chat" if self.dispatched else "/"

        async def send_confirmation_state(self) -> dict[str, object]:
            self.state_probes += 1
            return {"composer_text": self.composer, "send_in_progress": False}

        def captured_send_response(
            self,
            _capture: dict[str, object],
        ) -> tuple[str, int] | None:
            return ("request-1", 200) if self.state_probes else None

    monkeypatch.setattr(delivery_browser, "_SEND_CONFIRM_POLL_SECONDS", 0.001)
    driver = RouteThenTransportDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        send_timeout_seconds=0.2,
    )

    await sender._send_browser("Do the scheduled work")

    assert driver.dispatched
    assert driver.state_probes >= 1
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed


@pytest.mark.asyncio
async def test_transient_route_probe_timeout_falls_through_to_generation_signal(
    tmp_path: Path,
) -> None:
    class RouteProbeTimeoutDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.dispatched = False
            self.generation_active = False

        async def click_send(self, expected_message: str) -> None:
            await super().click_send(expected_message)
            self.dispatched = True
            self.generation_active = True

        async def eval(self, _script: str, *, main_world: bool = False) -> str:
            if self.dispatched:
                raise TimeoutError("transient route probe timeout")
            return "/"

        async def send_confirmation_state(self) -> dict[str, object]:
            return {
                "composer_text": self.composer,
                "send_in_progress": self.generation_active,
            }

        def captured_send_response(self, _capture: dict[str, object]) -> None:
            return None

    driver = RouteProbeTimeoutDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        send_timeout_seconds=0.05,
    )

    await sender._send_browser("Scheduled work")

    assert driver.dispatched
    assert driver.generation_active
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed


@pytest.mark.asyncio
async def test_generation_start_confirms_send_when_transport_and_route_are_unavailable(
    tmp_path: Path,
) -> None:
    class GenerationConfirmedDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.generation_active = False

        async def send_confirmation_state(self) -> dict[str, object]:
            return {
                "composer_text": self.composer,
                "send_in_progress": self.generation_active,
            }

        async def click_send(self, expected_message: str) -> None:
            assert _normalise_composer_text(expected_message) == _normalise_composer_text(
                self.composer
            )
            self.composer = ""
            self.generation_active = True

        def captured_send_response(self, _capture: dict[str, object]) -> None:
            return None

    driver = GenerationConfirmedDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        send_timeout_seconds=0.05,
    )

    await sender._send_browser("Scheduled work")

    assert driver.generation_active is True
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed is True


@pytest.mark.asyncio
async def test_preexisting_generation_control_does_not_confirm_send(tmp_path: Path) -> None:
    class StaleGenerationDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.generation_active = True

        async def dom_state(self) -> dict[str, object]:
            return {
                "composer_text": self.composer,
                "rate_limit_text": "",
                "send_in_progress": self.generation_active,
            }

        async def send_confirmation_state(self) -> dict[str, object]:
            return {
                "composer_text": self.composer,
                "send_in_progress": self.generation_active,
            }

        async def click_send(self, expected_message: str) -> None:
            assert _normalise_composer_text(expected_message) == _normalise_composer_text(
                self.composer
            )
            self.composer = ""

        def captured_send_response(self, _capture: dict[str, object]) -> None:
            return None

    driver = StaleGenerationDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        send_timeout_seconds=0.05,
    )

    with pytest.raises(SendOutcomeUnknownError):
        await sender._send_browser("Scheduled work")

    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed is True


@pytest.mark.asyncio
async def test_dom_state_uses_public_stop_generating_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = object()
    observed_patterns: list[re.Pattern[str]] = []
    observed_enabled: list[bool] = []

    async def no_composer(_page: object) -> None:
        return None

    async def no_rate_limit(_page: object) -> list[str]:
        return []

    async def semantic_button(
        _page: object,
        name: re.Pattern[str],
        *,
        enabled: bool = True,
    ) -> object:
        observed_patterns.append(name)
        observed_enabled.append(enabled)
        return object()

    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    monkeypatch.setattr(driver, "_composer", no_composer)
    monkeypatch.setattr(driver, "_rate_limit_texts", no_rate_limit)
    monkeypatch.setattr(driver, "_semantic_button", semantic_button)

    state = await driver.dom_state()

    assert len(observed_patterns) == 1
    assert len(observed_enabled) == 1
    pattern = observed_patterns[0]
    assert pattern.fullmatch("Stop generating")
    assert not pattern.fullmatch("Stop")
    assert observed_enabled[0] is False
    assert state["send_in_progress"] is True


@pytest.mark.asyncio
async def test_send_confirmation_state_never_scans_page_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = object()
    composer = object()
    observed: list[re.Pattern[str]] = []

    async def get_composer(_page: object) -> object:
        return composer

    async def composer_text(_composer: object) -> str:
        return "the submitted user prompt"

    async def semantic_button(
        _page: object,
        name: re.Pattern[str],
        *,
        enabled: bool = True,
    ) -> object:
        assert enabled is False
        observed.append(name)
        return object()

    async def forbidden_rate_limit_scan(_page: object) -> list[str]:
        pytest.fail("post-send confirmation must not scan page or response text")

    monkeypatch.setattr(driver, "_page", lambda _context=None: page)
    monkeypatch.setattr(driver, "_composer", get_composer)
    monkeypatch.setattr(driver, "_composer_text", composer_text)
    monkeypatch.setattr(driver, "_semantic_button", semantic_button)
    monkeypatch.setattr(driver, "_rate_limit_texts", forbidden_rate_limit_scan)

    state = await driver.send_confirmation_state()

    assert state == {"composer_text": "the submitted user prompt", "send_in_progress": True}
    assert len(observed) == 1
    assert observed[0].fullmatch("Stop generating")


@pytest.mark.asyncio
async def test_confirmation_uses_fast_composer_and_control_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")

    class Page:
        async def evaluate(
            self, script: str, *, isolated_context: bool = True
        ) -> dict[str, object]:
            assert "querySelector('main')" in script
            assert "send_in_progress" in script
            assert "querySelectorAll('button" in script
            assert "message" not in script.casefold()
            return {"composer_text": "", "send_in_progress": True}

    async def forbidden_semantic_fallback(*_args: object, **_kwargs: object) -> None:
        pytest.fail("fast confirmation must not scan hydrated accessibility tree")

    monkeypatch.setattr(driver, "_page", lambda _context=None: Page())
    monkeypatch.setattr(driver, "_composer", forbidden_semantic_fallback)
    monkeypatch.setattr(driver, "_semantic_button", forbidden_semantic_fallback)
    assert await driver.send_confirmation_state() == {"composer_text": "", "send_in_progress": True}


@pytest.mark.asyncio
async def test_model_picker_bounds_and_names_slow_option_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:

    class Candidate:
        def filter(self, **_kwargs: object) -> Candidate:
            return self

    class Page:
        def get_by_role(self, _role: str, **_kwargs: object) -> Candidate:
            return Candidate()

    driver = PlaywrightDriver(profile=tmp_path / "profile")
    monkeypatch.setattr(driver, "_page", lambda _context=None: Page())

    async def slow_scan(_candidates: object, *, enabled: bool = True) -> None:
        del enabled
        await asyncio.Event().wait()

    monkeypatch.setattr(driver, "_first_usable", slow_scan)
    monkeypatch.setattr(playwright_driver, "_MODEL_PICKER_STEP_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(TimeoutError):
        await driver.select_effort_model("GPT-5.6 Sol")

    assert "stage=option_discovery" in caplog.text
    assert "outcome=failed" in caplog.text
    assert "GPT-5.6 Sol" not in caplog.text


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

        async def evaluate(self, _script: str, *, isolated_context: bool = True) -> bool:
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
