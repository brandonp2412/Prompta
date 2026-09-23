"""Shared browser-independent helpers for Prompta browser automation."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from .chatgpt_dom import (
    ASSISTANT_MESSAGE_SELECTOR,
    STOP_BUTTON_SELECTORS,
    STREAMING_SELECTOR,
    TURN_SELECTOR,
)
from .conversation_snapshot import CONVERSATION_SNAPSHOT_SCRIPT, parse_conversation_snapshot
from .script_assets import browser_script


class BrowsingContextUnavailableError(RuntimeError):
    """Raised when a tracked browser tab/context no longer exists."""


_SEND_ENDPOINTS = ("/backend-api/f/conversation", "/backend-api/conversation")


class BrowserDriverBase:
    # Shared browser-independent helpers used by the Playwright driver.

    def __init__(self, url: str = "") -> None:
        self.url = url
        self.context = ""
        self._network_subscribed = False
        self._send_capture: dict[str, Any] | None = None
        self.needs_browser_restart = False

    @staticmethod
    def _is_send_endpoint(url: str) -> bool:
        return urlsplit(url).path.rstrip("/") in _SEND_ENDPOINTS

    async def arm_page_send_probe(self) -> None:
        await self.eval(browser_script("send_probe_arm.js"))

    async def page_send_probe(self) -> dict[str, Any]:
        raw = await self.eval(browser_script("send_probe_read.js"))
        return json.loads(raw or "{}")

    async def clear_page_send_probe(self) -> dict[str, Any]:
        raw = await self.eval(browser_script("send_probe_clear.js"))
        return json.loads(raw or "{}")

    @staticmethod
    def captured_send_response(capture: dict[str, Any]) -> tuple[str, int] | None:
        request_id = str(capture.get("request_id") or "")
        status = int(capture.get("status") or 0)
        if request_id and bool(capture.get("response_started")) and 200 <= status < 400:
            return request_id, status
        return None

    def clear_send_capture(self, capture: dict[str, Any]) -> None:
        if self._send_capture is capture:
            self._send_capture = None

    async def eval(
        self,
        expression: str,
        *,
        await_promise: bool = False,
        context: str | None = None,
        argument: Any = None,
    ) -> Any:
        raise NotImplementedError

    async def ensure_token(self) -> str:
        raw = await self.eval(
            browser_script("auth_session_token.js"),
            await_promise=True,
        )
        payload = json.loads(raw or "{}")
        token = str(payload.get("token") or "")
        if not payload.get("ok") or not token:
            raise RuntimeError("Prompta browser profile is not logged into ChatGPT")
        return token

    async def conversation_final_event(
        self,
        conversation_id: str,
        *,
        context: str | None = None,
    ) -> dict[str, Any]:
        raw = await self.eval(
            browser_script("conversation_final_event.js"),
            context=context,
            await_promise=True,
            argument=conversation_id,
        )
        payload = json.loads(raw or "{}")
        return payload if isinstance(payload, dict) else {}

    async def conversation_activity(self, context: str) -> dict[str, Any]:
        script = r"""JSON.stringify((()=>{
          const assistantSelector=__ASSISTANT_SELECTOR__;
          const turnSelector=__TURN_SELECTOR__;
          const stopSelector=__STOP_SELECTOR__;
          const streamingSelector=__STREAMING_SELECTOR__;
          const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
          const stop=[...document.querySelectorAll(stopSelector)].some(visible);
          const streamActive=[...document.querySelectorAll(streamingSelector)].some(visible);
          const assistants=[...document.querySelectorAll(assistantSelector)];
          const assistant=assistants.at(-1);
          const candidateTurns=[...document.querySelectorAll(turnSelector)].filter(visible);
          const turn=assistant?.closest(turnSelector)||assistant?.parentElement||candidateTurns.at(-1)||null;
          const visibleMessageId=assistant?.getAttribute('data-message-id')
            ||assistant?.getAttribute('data-message-uuid')
            ||turn?.getAttribute('data-message-id')
            ||turn?.getAttribute('data-message-uuid')
            ||turn?.querySelector('[data-message-id]')?.getAttribute('data-message-id')
            ||turn?.querySelector('[data-message-uuid]')?.getAttribute('data-message-uuid')
            ||'';
          const reactTurnEnd=()=>{
            const root=turn||document.querySelector('main')||document.body;
            if(!root)return null;
            const found=[],seenObjects=new WeakSet(),seenArrays=new WeakSet();
            const add=messages=>{
              if(!Array.isArray(messages)||seenArrays.has(messages))return;
              seenArrays.add(messages);
              found.push(...messages.filter(message=>message&&typeof message==='object'&&message.content&&message.author));
            };
            const walk=(value,depth)=>{
              if(!value||depth>7||(typeof value!=='object'&&typeof value!=='function'))return;
              if(seenObjects.has(value))return;
              seenObjects.add(value);
              if(Array.isArray(value)){if(depth<=5)add(value);return;}
              let keys=[];
              try{keys=Object.keys(value);}catch{return;}
              for(const key of keys.slice(0,260)){
                if(['ref','_owner','return','child','sibling','stateNode','alternate'].includes(key))continue;
                let next;
                try{next=value[key];}catch{continue;}
                if(key==='messages')add(next);
                if(next&&depth<7&&(typeof next==='object'||typeof next==='function'))walk(next,depth+1);
              }
            };
            for(const node of [root,...root.querySelectorAll('*')]){
              let keys=[];
              try{keys=Object.getOwnPropertyNames(node).filter(name=>name.startsWith('__reactProps$')||name.startsWith('__reactFiber$')||name.startsWith('__reactContainer$'));}catch{}
              for(const key of keys)walk(node[key],0);
            }
            const assistantMessages=found.filter(message=>String(message?.author?.role||message?.role||'')==='assistant');
            const target=visibleMessageId
              ?assistantMessages.filter(message=>String(message?.id||'')===visibleMessageId)
              :assistantMessages.slice(-8);
            const states=target.map(message=>message?.end_turn).filter(value=>typeof value==='boolean');
            if(states.includes(true))return true;
            if(states.includes(false))return false;
            return null;
          };
          const turnEnded=reactTurnEnd();
          const turnText=(turn?.innerText||turn?.textContent||'').trim();
          const transientText=/(?:Connection interrupted|Waiting for the complete answer|A network error occurred\.?\s*Please check your connection and try again\.?\s*If this issue persists please contact us through our help center at help\.openai\.com\.?)/i.test(turnText);
          const deliveryFailed=/Message delivery timed out\.?\s*Please try again/i.test(turnText);
          const finalAction=Boolean(turn&&[...turn.querySelectorAll('button')].some(button=>{
            const testId=(button.getAttribute('data-testid')||'').trim();
            const label=(button.getAttribute('aria-label')||button.getAttribute('title')||button.textContent||'').trim();
            return testId==='copy-turn-action-button'||/^Copy(?: response)?$/i.test(label);
          }));
          const streaming=stop||streamActive||turnEnded===false;
          const complete=!streaming&&(turnEnded===true||(turnEnded===null&&finalAction));
          const transient=transientText&&!complete;
          const failed=deliveryFailed&&!complete&&!streaming;
          return {streaming,complete,transient,failed,turn_ended:turnEnded};
        })())"""
        script = script.replace("__ASSISTANT_SELECTOR__", json.dumps(ASSISTANT_MESSAGE_SELECTOR))
        script = script.replace("__TURN_SELECTOR__", json.dumps(TURN_SELECTOR))
        script = script.replace("__STOP_SELECTOR__", json.dumps(",".join(STOP_BUTTON_SELECTORS)))
        script = script.replace("__STREAMING_SELECTOR__", json.dumps(STREAMING_SELECTOR))
        raw = await self.eval(script, context=context)
        return json.loads(raw or "{}")

    async def conversation_snapshot(self, context: str) -> dict[str, Any]:
        raw = await self.eval(CONVERSATION_SNAPSHOT_SCRIPT, context=context)
        return parse_conversation_snapshot(raw)


# Compatibility alias for older imports; there is no WebDriver transport.
WebDriverBase = BrowserDriverBase
