from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from .chrome import ChromeDriverDriver

logger = logging.getLogger(__name__)

BrowserDriver = ChromeDriverDriver
DriverFactory = Callable[[], BrowserDriver]

_EFFORT_CONTROL_TIMEOUT_SECONDS = 20.0


class BrowserSession:
    def __init__(self, browser_url: str, driver_factory: DriverFactory | None = None) -> None:
        self.browser_url = browser_url
        self.driver_factory = driver_factory
        self.driver: BrowserDriver | None = None

    async def ensure_driver(self) -> BrowserDriver:
        if self.driver is None:
            if self.driver_factory is None:
                raise RuntimeError("Chromium driver factory is not configured")
            self.driver = self.driver_factory()
        if not self.driver.is_connected:
            await self.driver.connect()
        return self.driver

    async def ensure_conversation_route(
        self,
        driver: BrowserDriver,
        expected_path: str,
        *,
        context: str | None = None,
    ) -> None:
        expected = expected_path.rstrip("/")
        deadline = asyncio.get_running_loop().time() + 10.0
        activated_history = False
        direct_navigation_attempted = False

        async def current_path() -> str:
            if context is None:
                return str(await driver.eval("location.pathname") or "").rstrip("/")
            return str(await driver.eval("location.pathname", context=context) or "").rstrip("/")

        path = await current_path()
        while path != expected and asyncio.get_running_loop().time() < deadline:
            if path in {"", "/"} and not activated_history:
                if context is None:
                    activated_history = await driver.activate_history_link(expected)
                else:
                    activated_history = await driver.activate_history_link(
                        expected,
                        context=context,
                    )
                if not activated_history and not direct_navigation_attempted:
                    target_url = f"https://chatgpt.com{expected}"
                    if context is None:
                        await driver.navigate(target_url)
                    else:
                        await driver.navigate(target_url, context=context)
                    direct_navigation_attempted = True
            await asyncio.sleep(0.25)
            path = await current_path()
        if path != expected:
            raise RuntimeError(
                f"ChatGPT opened unexpected conversation path {path!r}; expected {expected!r}"
            )

    async def pointer_click(self, driver: BrowserDriver, x: float, y: float) -> None:
        await driver._click_viewport_point(driver.context, x, y)

    async def effort_trigger_info(
        self,
        driver: BrowserDriver,
        *,
        timeout: float = _EFFORT_CONTROL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            raw = await driver.eval(
                r"""JSON.stringify((()=>{
                  const normalise=value=>(value||'').replace(/\s+/g,' ').trim();
                  const visible=el=>{if(!el)return false;const r=el.getBoundingClientRect(),s=getComputedStyle(el);
                    return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
                  const level=value=>{
                    const match=normalise(value).match(/\b(extra\s+high|instant|medium|high)\b/i);
                    if(!match)return '';
                    return match[1].replace(/\s+/g,' ').toLowerCase().replace(/^./,ch=>ch.toUpperCase());
                  };
                  const composer=document.querySelector('[data-composer-surface],form[data-type="unified-composer"],main form');
                  const roots=composer?[composer,document]:[document];
                  let button=null,selected='';
                  for(const root of roots){
                    const candidates=[...root.querySelectorAll('button[aria-haspopup="menu"],button[aria-haspopup="listbox"],[role="button"][aria-haspopup]')]
                      .filter(visible);
                    for(const candidate of candidates){
                      selected=level(
                        candidate.getAttribute('aria-label')
                        ||candidate.getAttribute('title')
                        ||candidate.innerText
                        ||candidate.textContent
                        ||''
                      );
                      if(selected){button=candidate;break;}
                    }
                    if(button)break;
                  }
                  if(!button)return null;
                  button.scrollIntoView({block:'center',inline:'center'});
                  const r=button.getBoundingClientRect();
                  const width=document.documentElement.clientWidth||window.innerWidth;
                  const height=document.documentElement.clientHeight||window.innerHeight;
                  const x=r.left+r.width/2,y=r.top+r.height/2;
                  if(x<0||y<0||x>=width||y>=height)return null;
                  return {text:selected,x,y};
                })())"""
            )
            if raw and raw != "null":
                payload = json.loads(raw)
                if isinstance(payload, dict) and payload.get("text"):
                    return payload
            await asyncio.sleep(0.15)
        raise RuntimeError("ChatGPT thinking-effort control did not become available")

    async def high_effort_slider_point(self, driver: BrowserDriver) -> dict[str, float]:
        deadline = asyncio.get_running_loop().time() + 3.0
        while asyncio.get_running_loop().time() < deadline:
            raw = await driver.eval(
                r"""JSON.stringify((()=>{
                  const visible=el=>{if(!el)return false;const r=el.getBoundingClientRect(),s=getComputedStyle(el);
                    return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
                  const candidates=[...document.querySelectorAll(
                    '[data-model-reasoning-effort-slider] [role="slider"],[role="slider"][aria-valuemin][aria-valuemax]'
                  )].filter(visible);
                  const slider=candidates.find(el=>el.closest('[data-model-reasoning-effort-slider]'))
                    ||candidates.find(el=>{
                      const popup=el.closest('[role="menu"],[role="dialog"],[role="listbox"],[data-radix-popper-content-wrapper]');
                      return /\b(?:instant|medium|high|extra\s+high)\b/i.test(popup?.innerText||popup?.textContent||'');
                    })
                    ||null;
                  if(!slider)return null;
                  const root=slider.closest('[data-model-reasoning-effort-slider]')
                    ||slider.parentElement?.parentElement
                    ||slider.parentElement;
                  if(!root)return null;
                  const min=Number(slider.getAttribute('aria-valuemin')||0);
                  const max=Number(slider.getAttribute('aria-valuemax')||3);
                  const target=2;
                  if(!Number.isFinite(min)||!Number.isFinite(max)||max<=min)return {error:'invalid-range'};
                  if(target<min||target>max)return {error:'high-out-of-range'};
                  const ticks=[...root.querySelectorAll('[data-locked]')];
                  if(ticks[target]?.getAttribute('data-locked')==='true')return {error:'high-locked'};
                  const r=root.getBoundingClientRect(),pad=13;
                  const width=document.documentElement.clientWidth||window.innerWidth;
                  const height=document.documentElement.clientHeight||window.innerHeight;
                  const x=r.left+pad+(r.width-pad*2)*(target-min)/(max-min),y=r.top+r.height/2;
                  if(x<0||y<0||x>=width||y>=height)return null;
                  return {x,y};
                })())"""
            )
            if raw and raw != "null":
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    if payload.get("error"):
                        raise RuntimeError(
                            f"ChatGPT High effort is unavailable: {payload['error']}"
                        )
                    if "x" in payload and "y" in payload:
                        return {"x": float(payload["x"]), "y": float(payload["y"])}
            await asyncio.sleep(0.1)
        raise RuntimeError("ChatGPT thinking-effort slider did not open")

    async def ensure_high_effort(
        self,
        driver: BrowserDriver,
        *,
        effort_trigger_info,
        high_effort_slider_point,
        pointer_click,
    ) -> None:
        trigger = await effort_trigger_info(driver)
        if str(trigger.get("text") or "").strip().casefold() == "high":
            logger.info("Prompta verified thinking effort=High")
            return
        for attempt in range(2):
            try:
                await pointer_click(driver, float(trigger["x"]), float(trigger["y"]))
                break
            except RuntimeError as exc:
                if "out of bounds" not in str(exc).casefold() or attempt > 0:
                    raise
                trigger = await effort_trigger_info(driver)
        for attempt in range(2):
            point = await high_effort_slider_point(driver)
            try:
                await pointer_click(driver, point["x"], point["y"])
                break
            except RuntimeError as exc:
                if "out of bounds" not in str(exc).casefold() or attempt > 0:
                    raise
        deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < deadline:
            value = str(
                await driver.eval(
                    r"""(()=>{
                      const visible=el=>{if(!el)return false;const r=el.getBoundingClientRect(),s=getComputedStyle(el);
                        return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
                      const sliders=[...document.querySelectorAll(
                        '[data-model-reasoning-effort-slider] [role="slider"],[role="slider"][aria-valuemin][aria-valuemax]'
                      )].filter(visible);
                      const slider=sliders.find(el=>el.closest('[data-model-reasoning-effort-slider]'))||sliders[0];
                      return slider?.getAttribute('aria-valuenow')||'';
                    })()"""
                )
                or ""
            )
            if value == "2":
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("ChatGPT thinking-effort slider did not reach High")
        await driver._perform_actions(
            driver.context,
            [
                {
                    "type": "key",
                    "id": "keyboard",
                    "actions": [
                        {"type": "keyDown", "value": "\ue00c"},
                        {"type": "keyUp", "value": "\ue00c"},
                    ],
                }
            ],
        )
        await asyncio.sleep(0.2)
        verified = await effort_trigger_info(driver)
        if str(verified.get("text") or "").strip().casefold() != "high":
            raise RuntimeError(
                f"ChatGPT thinking effort verification failed: {verified.get('text')!r}"
            )
        logger.info("Prompta set and verified thinking effort=High")
