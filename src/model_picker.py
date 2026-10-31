from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Sequence
from typing import TYPE_CHECKING, Literal, Protocol, TypeVar

from patchright.async_api import Error as PatchrightError
from patchright.async_api import Locator, Page

from .browser_script_loader import load_browser_script
from .strict_types import int_value

logger = logging.getLogger("prompta.patchright_driver")

_MODEL_SELECTION_VERIFY_ATTEMPTS = 40
_MODEL_SELECTION_VERIFY_INTERVAL_SECONDS = 0.05
_MODEL_PICKER_STEP_TIMEOUT_SECONDS = 3.0


_PickerResult = TypeVar("_PickerResult")


async def _timed_model_picker_step(
    stage: str,
    operation: Awaitable[_PickerResult],
    *,
    timeout: float,
) -> _PickerResult:
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(operation, timeout=max(0.1, timeout))
    except BaseException as exc:
        logger.warning(
            "ChatGPT model picker stage finished stage=%s duration_ms=%d "
            "outcome=failed error_type=%s",
            stage,
            round((time.monotonic() - started) * 1000),
            type(exc).__name__,
        )
        raise
    logger.debug(
        "ChatGPT model picker stage finished stage=%s duration_ms=%d outcome=ok",
        stage,
        round((time.monotonic() - started) * 1000),
    )
    return result


class BrowserSecurityChallengeError(RuntimeError):
    """ChatGPT security challenge blocked an attempted navigation or UI action."""


_EFFORT_RE = re.compile(r"\b(max|extra\s+high|instant|medium|high)\b", re.IGNORECASE)
_EFFORT_TRIGGER_RE = re.compile(
    r"\b(?:thinking\s+effort|select\s+(?:chatgpt\s+)?model|model\s+selector)\b",
    re.IGNORECASE,
)


class _UsableCandidate(Protocol):
    async def is_visible(self) -> bool: ...
    async def is_enabled(self) -> bool: ...
    async def evaluate(self, expression: str, /) -> object: ...


_UsableT = TypeVar("_UsableT", bound=_UsableCandidate)
_UsableT_co = TypeVar("_UsableT_co", bound=_UsableCandidate, covariant=True)


class _UsableCollection(Protocol[_UsableT_co]):
    async def count(self) -> int: ...
    def nth(self, index: int, /) -> _UsableT_co: ...


class _LocatorPage(Protocol[_UsableT_co]):
    def locator(self, selector: str, /) -> _UsableCollection[_UsableT_co]: ...


class _AttributeControl(Protocol):
    async def get_attribute(self, name: str, /) -> str | None: ...


_ModelRole = Literal[
    "menuitem",
    "menuitemradio",
    "option",
    "radio",
    "tab",
    "combobox",
    "button",
    "main",
]


class _LocatorScope(Protocol[_UsableT_co]):
    def locator(self, selector: str, /) -> _UsableCollection[_UsableT_co]: ...


class _ModelCollection(
    _UsableCollection[_UsableT_co],
    _LocatorScope[_UsableT_co],
    Protocol[_UsableT_co],
):
    pass


class _ModelPage(_LocatorPage[_UsableT_co], Protocol[_UsableT_co]):
    def get_by_role(
        self,
        role: _ModelRole,
        /,
        *,
        name: re.Pattern[str] | None = None,
    ) -> _ModelCollection[_UsableT_co]: ...


class ModelPickerMixin:
    if TYPE_CHECKING:

        def _page(self) -> Page: ...
        async def _first_usable(
            self,
            locators: Sequence[_UsableCollection[_UsableT]],
            *,
            enabled: bool = True,
            limit: int = 12,
        ) -> _UsableT | None: ...
        async def _semantic_button(
            self, page: Page, name: re.Pattern[str], *, enabled: bool = True
        ) -> Locator | None: ...
        async def _selection_state(self, control: _AttributeControl) -> bool | None: ...
        async def _cloudflare_challenge_present(self) -> bool: ...
        def _mfa_authentication_route(self, url: str) -> bool: ...
        async def login_required(self) -> bool: ...

    async def _effort_trigger_locator(self) -> Locator | None:
        page = self._page()

        # A durable public label is sufficient for an explicit model/effort trigger.
        # Do not require aria-haspopup: popup metadata has changed independently of
        # the control label and _open_effort_menu verifies success structurally.
        direct = await self._semantic_button(page, _EFFORT_TRIGGER_RE)
        if direct is not None:
            return direct

        # Short state labels such as "High" are less specific, so retain popup
        # semantics for those to avoid matching unrelated controls.
        trigger_roles = (
            "button",
            "combobox",
            "menuitem",
            "menuitemradio",
            "option",
            "radio",
            "tab",
        )
        semantic_candidates = [page.get_by_role(role, name=_EFFORT_RE) for role in trigger_roles]
        for controls in semantic_candidates:
            try:
                count = min(await controls.count(), 12)
            except PatchrightError:
                continue
            for index in range(count):
                control = controls.nth(index)
                try:
                    if not await control.is_visible() or not await control.is_enabled():
                        continue
                    popup = (await control.get_attribute("aria-haspopup") or "").casefold()
                    if popup not in {"true", "menu", "listbox", "dialog", "tree", "grid"}:
                        continue
                    return control
                except PatchrightError:
                    continue

        # Accessible-role implementations can churn independently of the public
        # label. As a final semantic fallback, inspect popup owners directly and
        # accept one only when its accessible/visible text names the effort/model
        # control. This avoids coupling to styling classes or private test IDs.
        popup_controls = page.locator("[aria-haspopup]")
        try:
            count = min(await popup_controls.count(), 24)
        except PatchrightError:
            count = 0
        for index in range(count):
            control = popup_controls.nth(index)
            try:
                if not await control.is_visible() or not await control.is_enabled():
                    continue
                popup = (await control.get_attribute("aria-haspopup") or "").casefold()
                if popup not in {"true", "menu", "listbox", "dialog", "tree", "grid"}:
                    continue
                labels = await control.evaluate(load_browser_script("semantic_control_labels.js"))
                if not isinstance(labels, list):
                    continue
                label = " ".join(str(value) for value in labels if value)
                if _EFFORT_TRIGGER_RE.search(label) or _EFFORT_RE.search(label):
                    return control
            except PatchrightError:
                continue
        return None

    async def _power_control(self, page: Page) -> Locator | None:
        # The power row has changed accessible role before. The durable contract is
        # that it owns the reasoning slider, so discover that structure across
        # common selectable/container roles before falling back to its visible name.
        for role in ("menuitem", "menuitemradio", "radio", "option", "button", "group"):
            controls = page.get_by_role(role)
            try:
                count = await controls.count()
            except PatchrightError:
                continue
            # A partial scan cannot prove which control owns the effort slider.
            if count > 40:
                continue
            for index in range(count):
                item = controls.nth(index)
                try:
                    if not await item.is_visible():
                        continue
                    if (await item.get_attribute("aria-disabled") or "").casefold() == "true":
                        continue
                    if await item.locator(
                        '[role="slider"],[aria-valuenow][aria-valuemin][aria-valuemax]'
                    ).count():
                        return item
                except PatchrightError:
                    continue

        # Some UI builds drop the wrapper role entirely but keep a focusable owner
        # around the slider. Use the nearest focusable ancestor only when it is a
        # unique structural owner, avoiding assumptions about classes or test IDs.
        sliders = page.locator('[role="slider"],[aria-valuenow][aria-valuemin][aria-valuemax]')
        try:
            slider_count = await sliders.count()
        except PatchrightError:
            slider_count = 0
        if slider_count > 12:
            slider_count = 0  # Fall back to the explicitly named Power control.
        owners: list[Locator] = []
        for index in range(slider_count):
            slider = sliders.nth(index)
            try:
                owner = slider.locator("xpath=ancestor::*[@tabindex][1]")
                if await owner.count() != 1:
                    continue
                candidate = owner.first
                if not await candidate.is_visible():
                    continue
                if (await candidate.get_attribute("aria-disabled") or "").casefold() == "true":
                    continue
                if (
                    await candidate.locator(
                        '[role="slider"],[aria-valuenow][aria-valuemin][aria-valuemax]'
                    ).count()
                    != 1
                ):
                    continue
                owners.append(candidate)
            except PatchrightError:
                continue
        if len(owners) == 1:
            return owners[0]

        return await self._first_usable(
            [
                page.get_by_role(role, name=re.compile(r"\bpower\b", re.IGNORECASE))
                for role in ("menuitem", "option", "button", "group")
            ],
            enabled=True,
        )

    async def _open_effort_menu(self) -> None:
        page = self._page()
        power = await self._power_control(page)
        if power is not None:
            return

        for _ in range(2):
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.05)

        trigger = await self._effort_trigger_locator()
        if trigger is None:
            raise RuntimeError("ChatGPT thinking-effort control did not become available")
        try:
            await trigger.click()
        except PatchrightError as exc:
            raise RuntimeError("ChatGPT thinking-effort menu could not be opened") from exc

        deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < deadline:
            power = await self._power_control(page)
            if power is not None:
                return
            await asyncio.sleep(0.05)
        raise RuntimeError("ChatGPT Power control did not become available")

    async def _model_selector_control(self, page: _ModelPage[_UsableT]) -> _UsableT | None:
        # Require model meaning, not merely popup ownership. A lone unrelated popup
        # (for example Plugins) must never become the model selector just because
        # ChatGPT has not hydrated the real control yet.
        model_menu_name = re.compile(
            r" *(?:(?:select|choose|change) +)?(?:chatgpt +)?(?:model|engine) *",
            re.IGNORECASE,
        )
        selectable_roles = (
            "menuitem",
            "menuitemradio",
            "option",
            "radio",
            "tab",
            "combobox",
            "button",
        )
        named = await self._first_usable(
            [page.get_by_role(role, name=model_menu_name) for role in selectable_roles],
            enabled=True,
        )
        if named is not None:
            return named

        # Tolerate role/tag churn only when one interactive control has a public
        # semantic label that still means model selection. Do not fall back to
        # arbitrary aria-haspopup elements.
        scopes: tuple[_LocatorScope[_UsableT], ...] = (page.get_by_role("main"), page)
        for scope in scopes:
            controls = scope.locator(
                "button,input,select,summary,[role],[tabindex],[aria-label],"
                "[aria-labelledby],[title]"
            )
            try:
                count = await controls.count()
                if count > 60:
                    # Prefix scans cannot establish uniqueness across all controls.
                    continue
            except PatchrightError:
                continue

            matched: list[_UsableT] = []
            for index in range(count):
                item = controls.nth(index)
                try:
                    if not await item.is_visible() or not await item.is_enabled():
                        continue
                    labels = await item.evaluate(load_browser_script("semantic_control_labels.js"))
                    if not isinstance(labels, list):
                        continue
                    if any(
                        model_menu_name.fullmatch(str(label).strip())
                        for label in labels
                        if str(label).strip()
                    ):
                        matched.append(item)
                except PatchrightError:
                    continue
            if len(matched) == 1:
                return matched[0]

        return None

    async def _model_selection_verified(
        self,
        page: Page,
        option: Locator,
        model_name_re: re.Pattern[str],
    ) -> bool:
        # After a model click the menu option can disappear immediately.
        # Reading attributes from a missing Patchright locator waits for its
        # default timeout, starving the bounded post-click verification.
        if await option.is_visible():
            if await self._selection_state(option) is True:
                return True
        else:
            # Radix hides its submenu after a selection but retains the
            # checked option in the DOM. get_by_role() excludes hidden options;
            # a role/checked-state CSS query still sees the committed choice.
            # count() is immediate, unlike waiting on the hidden role locator.
            selected_options = page.locator(
                '[role="menuitemradio"][aria-checked="true"], '
                '[role="radio"][aria-checked="true"], '
                '[role="option"][aria-selected="true"], '
                '[role="tab"][aria-selected="true"]'
            ).filter(has_text=model_name_re)
            try:
                if await selected_options.count() == 1:
                    return True
            except PatchrightError:
                pass

        selector = await self._model_selector_control(page)
        if selector is None:
            return False
        try:
            labels = await selector.evaluate(load_browser_script("semantic_control_labels.js"))
        except PatchrightError:
            return False
        if not isinstance(labels, list):
            return False
        return any(model_name_re.search(label) for value in labels if (label := str(value).strip()))

    async def _verify_model_selection_after_click(
        self,
        page: Page,
        option: Locator,
        model_name_re: re.Pattern[str],
    ) -> bool:
        for _ in range(_MODEL_SELECTION_VERIFY_ATTEMPTS):
            if await self._model_selection_verified(page, option, model_name_re):
                return True
            await asyncio.sleep(_MODEL_SELECTION_VERIFY_INTERVAL_SECONDS)
        return False

    async def select_effort_model(self, model_name: str = "GPT-6") -> None:
        page = self._page()
        model_name_re = re.compile(
            rf"^ *{re.escape(model_name)}(?: |$)",
            re.IGNORECASE,
        )

        # The current High menu has a direct, stable three-control path.
        # Avoid the broad fallback discovery when its exact controls exist.
        if model_name.casefold() == "gpt-6":
            trigger = page.get_by_role("button", name=re.compile(r"^select chatgpt model$", re.I))
            try:
                if (
                    await trigger.count() == 1
                    and await trigger.first.get_attribute("data-selected-reasoning-effort")
                    == "high"
                ):
                    await trigger.first.dispatch_event("click")
                    row = page.get_by_role("menuitem", name=re.compile(r"^select model$", re.I))
                    if await row.count() == 1 and (await row.first.inner_text()).strip() == "High":
                        # This Radix view toggle requires keyboard activation;
                        # a synthetic click can dismiss the entire menu.
                        await row.first.focus()
                        await page.keyboard.press("Enter")
                        option = page.get_by_role("menuitemradio", name=model_name_re)
                        for _ in range(10):
                            if await option.count() == 1 and await option.first.is_visible():
                                if await option.first.get_attribute("aria-checked") != "true":
                                    await option.first.dispatch_event("click")
                                if await self._verify_model_selection_after_click(
                                    page, option.first, model_name_re
                                ):
                                    await page.keyboard.press("Escape")
                                    return
                            await asyncio.sleep(0.1)
            except PatchrightError:
                pass

        async def find_option() -> Locator | None:
            # Menus have changed role structure before. Prefer accessible role/name
            # semantics across common selectable roles, then an unambiguous semantic
            # control fallback if the role disappears entirely.
            option_roles = (
                "menuitemradio",
                "radio",
                "option",
                "menuitem",
                "button",
                "tab",
            )
            named_roles = [page.get_by_role(role, name=model_name_re) for role in option_roles]
            text_roles = [
                page.get_by_role(role).filter(has_text=model_name_re) for role in option_roles
            ]
            found = await self._first_usable(named_roles + text_roles, enabled=True)
            if found is not None:
                return found
            return await self._semantic_button(page, model_name_re)

        async def expanded(control: Locator) -> bool:
            try:
                return (
                    await control.get_attribute("aria-expanded") or ""
                ).strip().casefold() == "true"
            except PatchrightError:
                return False

        # Drive the menu as a semantic state machine. Never guess at unrelated popup
        # controls and never re-click an already-expanded trigger while waiting for
        # the next submenu to hydrate.
        deadline = asyncio.get_running_loop().time() + 15.0

        def step_timeout() -> float:
            remaining = deadline - asyncio.get_running_loop().time()
            return max(0.1, min(_MODEL_PICKER_STEP_TIMEOUT_SECONDS, remaining))

        option_seen = False
        selector_seen = False
        trigger_seen = False
        model_row_opened = False
        while asyncio.get_running_loop().time() < deadline:
            option = await _timed_model_picker_step(
                "option_discovery", find_option(), timeout=step_timeout()
            )
            option_seen = option_seen or option is not None
            if option is not None:
                # ChatGPT's High picker exposes a second High row labelled
                # "Select model" before its GPT model choices.
                if model_name.casefold() == "gpt-6" and not model_row_opened:
                    row = page.get_by_role("menuitem", name=re.compile(r"^select model$", re.I))
                    if await row.count() == 1:
                        item = row.first
                        if await item.is_visible() and (await item.inner_text()).strip() == "High":
                            await _timed_model_picker_step(
                                "high_model_row_open",
                                item.click(),
                                timeout=step_timeout(),
                            )
                            model_row_opened = True
                            continue
                try:
                    if await _timed_model_picker_step(
                        "selection_state_check",
                        self._model_selection_verified(page, option, model_name_re),
                        timeout=step_timeout(),
                    ):
                        await page.keyboard.press("Escape")
                        return

                    async def click_model_option() -> None:
                        try:
                            # ChatGPT's effort slider can overlap the centre of
                            # a model menu item and intercept pointer clicks.
                            await asyncio.wait_for(option.click(), timeout=1.25)
                        except (TimeoutError, PatchrightError):
                            # Never send a second click if the first one took.
                            if await self._model_selection_verified(page, option, model_name_re):
                                return
                            logger.info(
                                "ChatGPT model menu pointer click blocked; "
                                "trying the same semantic control's click event"
                            )
                            await option.dispatch_event("click")

                    await _timed_model_picker_step(
                        "model_option_click", click_model_option(), timeout=step_timeout()
                    )
                    if await _timed_model_picker_step(
                        "selection_verification",
                        self._verify_model_selection_after_click(page, option, model_name_re),
                        timeout=step_timeout(),
                    ):
                        await page.keyboard.press("Escape")
                        return
                    await self._raise_model_selection_unavailable(model_name)
                except PatchrightError:
                    await asyncio.sleep(0.1)
                    continue

            selector = await _timed_model_picker_step(
                "selector_discovery",
                self._model_selector_control(page),
                timeout=step_timeout(),
            )
            selector_seen = selector_seen or selector is not None
            if selector is not None:
                try:
                    if await _timed_model_picker_step(
                        "selector_expansion_state", expanded(selector), timeout=step_timeout()
                    ):
                        await asyncio.sleep(0.05)
                        continue
                    await _timed_model_picker_step(
                        "selector_open", selector.click(), timeout=step_timeout()
                    )
                    await asyncio.sleep(0.08)
                    continue
                except PatchrightError:
                    await asyncio.sleep(0.1)
                    continue

            trigger = await _timed_model_picker_step(
                "effort_trigger_discovery",
                self._effort_trigger_locator(),
                timeout=step_timeout(),
            )
            trigger_seen = trigger_seen or trigger is not None
            if trigger is not None:
                try:
                    if await _timed_model_picker_step(
                        "effort_trigger_expansion_state",
                        expanded(trigger),
                        timeout=step_timeout(),
                    ):
                        await asyncio.sleep(0.05)
                        continue
                    await _timed_model_picker_step(
                        "effort_trigger_open", trigger.click(), timeout=step_timeout()
                    )
                    await asyncio.sleep(0.08)
                    continue
                except PatchrightError:
                    await asyncio.sleep(0.1)
                    continue

            await asyncio.sleep(0.1)

        logger.warning(
            "ChatGPT model picker exhausted semantic search model_option_seen=%s "
            "selector_control_seen=%s effort_trigger_seen=%s",
            option_seen,
            selector_seen,
            trigger_seen,
        )
        await self._raise_model_selection_unavailable(model_name)

    async def _raise_model_selection_unavailable(self, model_name: str) -> None:
        # A session can expire or encounter a security challenge while the picker
        # is hydrating. Do not change selection or authentication ownership.
        if await self._cloudflare_challenge_present():
            raise BrowserSecurityChallengeError(
                "ChatGPT security challenge is blocking model selection"
            )
        page = self._page()
        if self._mfa_authentication_route(page.url):
            raise RuntimeError(
                "ChatGPT multi-factor authentication required; model selection unavailable"
            )
        if await self.login_required():
            raise RuntimeError("ChatGPT login required; model selection unavailable")
        raise RuntimeError(f"ChatGPT model {model_name!r} is unavailable")

    async def effort_power_info(self) -> dict[str, object]:
        page = self._page()
        power = await self._power_control(page)
        if power is None:
            return {}

        slider = power.get_by_role("slider", include_hidden=True)
        try:
            if await slider.count() < 1:
                slider = power.locator("[aria-valuenow][aria-valuemin][aria-valuemax]")
            if await slider.count() < 1:
                return {}
            current_value = int(await slider.first.get_attribute("aria-valuenow") or -1)
            min_value = int(await slider.first.get_attribute("aria-valuemin") or 0)
            max_value = int(await slider.first.get_attribute("aria-valuemax") or -1)
            described_by = str(await power.get_attribute("aria-describedby") or "").split()
            description_parts: list[str] = []
            id_nodes = page.locator("[id]")
            id_count = await id_nodes.count()
            for element_id in described_by:
                for index in range(id_count):
                    described = id_nodes.nth(index)
                    if await described.get_attribute("id") != element_id:
                        continue
                    text = (await described.inner_text()).strip()
                    if text:
                        description_parts.append(text)
                    break
        except (PatchrightError, ValueError):
            return {}

        if current_value < min_value or max_value < min_value:
            return {}
        description = " ".join(description_parts)
        label = description.split(",", 1)[0].strip() if description else ""
        return {
            "text": label,
            "position": current_value - min_value + 1,
            "total": max_value - min_value + 1,
            "value": current_value,
            "description": description,
        }

    async def set_effort_power_position(self, position: int) -> dict[str, object]:
        await self._open_effort_menu()
        page = self._page()
        power = await self._power_control(page)
        if power is None:
            raise RuntimeError("ChatGPT Power control did not become available")

        info = await self.effort_power_info()
        current = int_value(info.get("position"))
        total = int_value(info.get("total"))
        if current < 1 or total < 1 or position < 1 or position > total:
            raise RuntimeError(f"ChatGPT Power control has invalid state: {info!r}")

        try:
            await power.focus()
            key = "ArrowRight" if position > current else "ArrowLeft"
            for _ in range(abs(position - current)):
                await page.keyboard.press(key)
        except PatchrightError as exc:
            raise RuntimeError("ChatGPT Power control could not be adjusted") from exc

        deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < deadline:
            info = await self.effort_power_info()
            if int_value(info.get("position")) == position:
                return info
            await asyncio.sleep(0.05)
        raise RuntimeError(f"ChatGPT Power control did not reach position {position}")
