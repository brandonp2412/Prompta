"""Shared browser automation helpers used by the Chromium WebDriver."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import websockets
from websockets.exceptions import ConnectionClosed, InvalidMessage

from .chatgpt_dom import (
    ASSISTANT_MESSAGE_SELECTOR,
    COMPOSER_SELECTORS,
    FILE_INPUT_SELECTORS,
    MESSAGE_ROLE_SELECTOR,
    RATE_LIMIT_SELECTOR,
    SEND_BUTTON_SELECTORS,
    STOP_BUTTON_SELECTORS,
    STREAMING_SELECTOR,
    TURN_SELECTOR,
)
from .conversation_snapshot import CONVERSATION_SNAPSHOT_SCRIPT, parse_conversation_snapshot


class BrowsingContextUnavailableError(RuntimeError):
    """Raised when a tracked browser tab/context no longer exists."""


_SEND_ENDPOINTS = ("/backend-api/f/conversation", "/backend-api/conversation")
_BIDI_CALL_TIMEOUT_SECONDS = 30.0
_BIDI_CONNECT_RETRY_SECONDS = 5.0
_BIDI_CONNECT_RETRY_INTERVAL_SECONDS = 0.1
_BIDI_AUTH_TIMEOUT_SECONDS = 30.0


class WebDriverBase:
    def __init__(self, url: str) -> None:
        self.url = url
        self.ws: Any = None
        self.context = ""
        self.request_id = 0
        self._call_lock = asyncio.Lock()
        self._network_subscribed = False
        self._send_capture: dict[str, Any] | None = None
        self.needs_browser_restart = False
        self._call_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return (
            self.ws is not None
            and bool(self.context)
            and getattr(self.ws, "close_code", None) is None
        )

    @staticmethod
    def _is_chatgpt_url(url: str) -> bool:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        return parsed.scheme in {"http", "https"} and (
            host == "chatgpt.com" or host.endswith(".chatgpt.com")
        )

    async def connect(self) -> None:
        if self.is_connected:
            return
        if self.needs_browser_restart:
            raise RuntimeError("Browser session is poisoned; browser restart required")
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + _BIDI_CONNECT_RETRY_SECONDS
            while True:
                try:
                    self.ws = await websockets.connect(
                        self.url,
                        max_size=16 * 1024 * 1024,
                        ping_interval=None,
                        open_timeout=max(0.1, min(1.0, deadline - loop.time())),
                    )
                    break
                except (InvalidMessage, OSError) as exc:
                    if loop.time() >= deadline:
                        self.needs_browser_restart = True
                        raise RuntimeError(
                            "WebDriver BiDi endpoint did not become ready "
                            f"within {_BIDI_CONNECT_RETRY_SECONDS:.0f}s"
                        ) from exc
                    await asyncio.sleep(_BIDI_CONNECT_RETRY_INTERVAL_SECONDS)
            response = await self._call("session.new", {"capabilities": {}})
        except TimeoutError:
            self.needs_browser_restart = True
            raise
        except RuntimeError as exc:
            message = str(exc).casefold()
            if "session not created" in message or "maximum number of active sessions" in message:
                self.needs_browser_restart = True
            raise
        if response.get("type") != "success":
            raise RuntimeError(f"WebDriver BiDi session failed: {response}")
        tree = await self._call("browsingContext.getTree", {})
        contexts = tree.get("result", {}).get("contexts") or []
        if not contexts:
            raise RuntimeError("WebDriver BiDi has no browsing context")
        chatgpt_context = next(
            (
                context
                for context in contexts
                if self._is_chatgpt_url(str(context.get("url") or ""))
            ),
            None,
        )
        selected_context = chatgpt_context or contexts[0]
        self.context = str(selected_context["context"])
        await self._call(
            "session.subscribe",
            {
                "events": [
                    "network.beforeRequestSent",
                    "network.responseStarted",
                    "network.responseCompleted",
                    "network.fetchError",
                ],
            },
        )
        self._network_subscribed = True
        if chatgpt_context is None:
            await self.navigate("https://chatgpt.com/")
        deadline = asyncio.get_running_loop().time() + _BIDI_AUTH_TIMEOUT_SECONDS
        last_error: Exception | None = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                if await self.login_required():
                    raise RuntimeError("Prompta browser profile is not logged into ChatGPT")
                if await self.ensure_token():
                    return
            except Exception as exc:
                last_error = exc
            await asyncio.sleep(0.5)
        # A failed connect must not leave is_connected true. Otherwise the same
        # driver instance can bypass authentication on its next use just because
        # the BiDi websocket itself is still open.
        await self.close()
        raise RuntimeError(
            "Prompta browser profile did not produce an authenticated ChatGPT "
            f"session within {_BIDI_AUTH_TIMEOUT_SECONDS:.0f}s"
        ) from last_error

    async def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        # WebDriver BiDi uses one request/response stream. Concurrent recv() calls
        # are invalid, and a competing caller could otherwise consume this
        # request's response as if it were an event. Serialize complete
        # transactions while still dispatching unsolicited events in-band.
        async with self._call_lock:
            return await self._call_locked(method, params)

    async def _call_locked(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.ws is None:
            raise RuntimeError("WebDriver BiDi is not connected")
        self.request_id += 1
        request_id = self.request_id
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _BIDI_CALL_TIMEOUT_SECONDS
        try:
            await asyncio.wait_for(
                self.ws.send(json.dumps({"id": request_id, "method": method, "params": params})),
                timeout=max(0.001, deadline - loop.time()),
            )
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError
                message = json.loads(
                    await asyncio.wait_for(
                        self.ws.recv(),
                        timeout=remaining,
                    )
                )
                if message.get("id") != request_id:
                    self._handle_bidi_event(message)
                    continue
                if message.get("type") == "error":
                    raise RuntimeError(
                        f"{method}: {message.get('error')}: {message.get('message')}"
                    )
                return message
        except TimeoutError as exc:
            self.needs_browser_restart = True
            ws = self.ws
            self.ws = None
            self.context = ""
            self._network_subscribed = False
            self._send_capture = None
            if ws is not None:
                try:
                    await asyncio.wait_for(ws.close(), timeout=2.0)
                except Exception:
                    pass
            raise RuntimeError(
                f"{method}: WebDriver BiDi call timed out after {_BIDI_CALL_TIMEOUT_SECONDS:.0f}s"
            ) from exc
        except ConnectionClosed:
            self.needs_browser_restart = True
            self.ws = None
            self.context = ""
            self._network_subscribed = False
            self._send_capture = None
            raise

    @staticmethod
    def _is_send_endpoint(url: str) -> bool:
        return urlsplit(url).path.rstrip("/") in _SEND_ENDPOINTS

    def _handle_bidi_event(self, message: dict[str, Any]) -> None:
        capture = self._send_capture
        if capture is None:
            return
        method = str(message.get("method") or "")
        params = message.get("params") or {}
        request = params.get("request") or {}
        if method == "network.beforeRequestSent":
            if str(request.get("method") or "").upper() != "POST":
                return
            if not self._is_send_endpoint(str(request.get("url") or "")):
                return
            request_id = str(request.get("request") or "")
            if request_id:
                capture["request_id"] = request_id
            return
        if method == "network.fetchError":
            request_id = str(request.get("request") or "")
            if not request_id or request_id != str(capture.get("request_id") or ""):
                return
            capture["fetch_error"] = str(
                params.get("errorText")
                or params.get("error_text")
                or params.get("error")
                or "network.fetchError"
            )
            return
        if method not in {"network.responseStarted", "network.responseCompleted"}:
            return
        request_id = str(request.get("request") or "")
        if not request_id or request_id != str(capture.get("request_id") or ""):
            return
        response = params.get("response") or {}
        status = int(response.get("status") or 0)
        if status:
            capture["status"] = status
            capture["response_started"] = True
        if method == "network.responseCompleted":
            capture["completed"] = True

    async def arm_page_send_probe(self) -> None:
        await self.eval(
            """(()=>{
              const previous=window.__promptaSendProbeOriginalFetch||window.fetch;
              window.__promptaSendProbeOriginalFetch=previous;
              const probe={message_id:'',parent_message_id:'',conversation_id:'',response_status:0,committed:false,stream_error:''};
              window.__promptaSendProbe=probe;
              const captureBody=text=>{try{const body=JSON.parse(text||'{}');probe.message_id=body.messages?.[0]?.id||'';probe.parent_message_id=body.parent_message_id||'';}catch(_){}};
              window.fetch=function(input,init){
                let isSend=false,req=null;
                try{
                  req=new Request(input instanceof Request?input.clone():input,init);
                  const url=new URL(req.url,location.href);
                  isSend=req.method==='POST'&&(url.pathname==='/backend-api/f/conversation'||url.pathname==='/backend-api/conversation');
                  if(isSend){
                    if(typeof init?.body==='string')captureBody(init.body);
                    else req.clone().text().then(captureBody).catch(()=>{});
                  }
                }catch(_){}
                const result=previous.apply(this,arguments);
                if(!isSend)return result;
                return result.then(response=>{
                  probe.response_status=response.status;
                  try{
                    const reader=response.clone().body?.getReader();
                    if(reader){
                      const decoder=new TextDecoder(); let buffer=''; let chunks=0;
                      (async()=>{
                        try{
                          while(chunks<24&&buffer.length<65536){
                            const item=await reader.read(); if(item.done)break; chunks+=1;
                            buffer+=decoder.decode(item.value,{stream:true});
                            if(!probe.conversation_id){
                              const match=buffer.match(/["']conversation_id["'][ ]*:[ ]*["']([^"']+)["']/);
                              if(match)probe.conversation_id=match[1];
                            }
                            const id=probe.message_id;
                            if(id&&buffer.includes('\\"type\\":\\"input_message\\"')&&buffer.includes('\\"id\\":\\"'+id+'\\"')){
                              probe.committed=true;
                              try{await reader.cancel();}catch(_){}
                              break;
                            }
                          }
                        }catch(error){probe.stream_error=String(error||'stream probe failed');}
                      })();
                    }
                  }catch(error){probe.stream_error=String(error||'stream probe setup failed');}
                  return response;
                },error=>{probe.stream_error=String(error||'fetch failed');throw error;});
              };
              return true;
            })()"""
        )

    async def page_send_probe(self) -> dict[str, Any]:
        raw = await self.eval("JSON.stringify(window.__promptaSendProbe||{})")
        return json.loads(raw or "{}")

    async def clear_page_send_probe(self) -> dict[str, Any]:
        raw = await self.eval(
            """JSON.stringify((()=>{const probe=window.__promptaSendProbe||{};if(window.__promptaSendProbeOriginalFetch){window.fetch=window.__promptaSendProbeOriginalFetch;}delete window.__promptaSendProbe;delete window.__promptaSendProbeOriginalFetch;return probe})())"""
        )
        return json.loads(raw or "{}")

    def arm_send_capture(self) -> dict[str, Any]:
        if not self._network_subscribed:
            raise RuntimeError("WebDriver BiDi network capture is not subscribed")
        capture: dict[str, Any] = {
            "request_id": "",
            "status": 0,
            "response_started": False,
            "completed": False,
            "fetch_error": "",
        }
        self._send_capture = capture
        return capture

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
    ) -> Any:
        response = await self._call(
            "script.evaluate",
            {
                "expression": expression,
                "target": {"context": context or self.context},
                "awaitPromise": await_promise,
            },
        )
        payload = response.get("result")
        if not isinstance(payload, dict):
            raise RuntimeError(f"script.evaluate returned malformed response: {response}")
        if payload.get("type") == "exception":
            details = payload.get("exceptionDetails")
            raise RuntimeError(f"script.evaluate failed: {details}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"script.evaluate returned no result: {response}")
        return result.get("value")

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        await self._call(
            "browsingContext.navigate",
            {"context": context or self.context, "url": url, "wait": "complete"},
        )

    async def activate_history_link(self, path: str, *, context: str | None = None) -> bool:
        target = json.dumps(path.rstrip("/"))
        return bool(
            await self.eval(
                f"""(()=>{{const target={target};const link=[...document.querySelectorAll('a[href]')].find(a=>{{try{{return new URL(a.href,location.origin).pathname.replace(/\\/$/,'')===target;}}catch{{return false;}}}});if(!link)return false;link.click();return true;}})()""",
                context=context,
            )
        )

    async def find_context_for_path(self, expected_path: str) -> str | None:
        target_path = urlsplit(expected_path).path.rstrip("/") or "/"
        tree = await self._call("browsingContext.getTree", {})
        contexts = list(tree.get("result", {}).get("contexts") or [])
        while contexts:
            candidate = contexts.pop(0)
            contexts.extend(candidate.get("children") or [])
            url = str(candidate.get("url") or "")
            if (urlsplit(url).path.rstrip("/") or "/") != target_path:
                continue
            context = str(candidate.get("context") or "")
            if context:
                return context
        return None

    async def new_tab(self, url: str = "https://chatgpt.com/") -> str:
        response = await self._call("browsingContext.create", {"type": "tab"})
        context = str(response.get("result", {}).get("context") or "")
        if not context:
            raise RuntimeError(f"WebDriver BiDi did not create a browsing context: {response}")
        self.context = context
        await self.navigate(url)
        return context

    async def close_context(self, context: str) -> None:
        try:
            await self._call("browsingContext.close", {"context": context})
        except RuntimeError as exc:
            if "no such frame" not in str(exc).casefold():
                raise

    async def login_required(self) -> bool:
        return bool(
            await self.eval(
                r"""(()=>{
                  const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
                  const label=e=>(e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').replace(/\s+/g,' ').trim();
                  const direct=[
                    ...document.querySelectorAll('button[data-testid="login-button"],a[href*="/auth/login"],a[href*="/login"]')
                  ].find(visible);
                  if(direct)return true;
                  return [...document.querySelectorAll('header button,header a,nav button,nav a')]
                    .some(e=>visible(e)&&/^(?:log ?in|sign ?in)$/i.test(label(e)));
                })()"""
            )
        )

    async def ensure_token(self) -> str:
        raw = await self.eval(
            "(async()=>{try{const r=await fetch('/api/auth/session');const j=await r.json();"
            "return JSON.stringify({ok:r.ok,token:j.accessToken||j.access_token||''})}"
            "catch(e){return JSON.stringify({ok:false,token:''})}})()",
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
        conversation_id_json = json.dumps(conversation_id)
        raw = await self.eval(
            f"""(async()=>{{try{{
              const sessionResponse=await fetch('/api/auth/session');
              const session=await sessionResponse.json();
              const token=session.accessToken||session.access_token||'';
              if(!sessionResponse.ok||!token)return JSON.stringify({{ok:false,status:401}});
              const response=await fetch(
                '/backend-api/conversation/'+encodeURIComponent({conversation_id_json}),
                {{headers:{{Authorization:'Bearer '+token}}}}
              );
              if(!response.ok)return JSON.stringify({{ok:false,status:response.status}});
              const payload=await response.json();
              const mapping=payload&&typeof payload.mapping==='object'?payload.mapping:{{}};
              const branch=[];
              const seen=new Set();
              let nodeId=String(payload.current_node||'');
              while(nodeId&&!seen.has(nodeId)){{
                seen.add(nodeId);
                const node=mapping[nodeId];
                if(!node)break;
                if(node.message)branch.push({{message:node.message,parent:String(node.parent||'')}});
                nodeId=String(node.parent||'');
              }}
              branch.reverse();
              let lastUser=-1;
              for(let index=0;index<branch.length;index+=1){{
                const message=branch[index].message||{{}};
                if(String(message?.author?.role||message?.role||'')==='user')lastUser=index;
              }}
              let finalEvent=null;
              for(let index=lastUser+1;index<branch.length;index+=1){{
                const entry=branch[index];
                const message=entry.message||{{}};
                const role=String(message?.author?.role||message?.role||'');
                const recipient=String(message?.recipient||'');
                const content=message?.content||{{}};
                const contentType=String(content?.content_type||content?.type||'');
                if(
                  role!=='assistant'
                  ||(recipient&&recipient!=='all')
                  ||message?.end_turn!==true
                  ||(contentType!=='text'&&contentType!=='multimodal_text')
                )continue;
                const parts=Array.isArray(content?.parts)
                  ?content.parts.filter(part=>typeof part==='string'&&part.trim())
                  :[];
                const text=parts.length?parts.join('\n'):String(content?.text||'');
                if(!text.trim())continue;
                const metadata=message?.metadata||{{}};
                finalEvent={{
                  id:String(message?.id||''),
                  parent_id:entry.parent,
                  create_time:Number.isFinite(Number(message?.create_time))
                    ?Number(message.create_time):null,
                  update_time:Number.isFinite(Number(message?.update_time))
                    ?Number(message.update_time):null,
                  end_turn:true,
                  status:String(message?.status||''),
                  role:'assistant',
                  recipient:recipient||'all',
                  content_type:contentType,
                  text:typeof content?.text==='string'?content.text:'',
                  parts,
                  reasoning_title:'',
                  reasoning_titles:[],
                  invoked_resource:null,
                  connector_name:'',
                  model_slug:String(metadata?.model_slug||metadata?.default_model_slug||''),
                  request_id:String(metadata?.request_id||metadata?.requestId||''),
                  attachments:[],
                  citations:Array.isArray(metadata?.citations)?metadata.citations:[],
                  content_references:Array.isArray(metadata?.content_references)
                    ?metadata.content_references:[]
                }};
              }}
              return JSON.stringify({{
                ok:true,
                status:response.status,
                title:String(payload.title||''),
                final_event:finalEvent
              }});
            }}catch(error){{
              return JSON.stringify({{ok:false,status:0,error:String(error)}});
            }}}})()""",
            context=context,
            await_promise=True,
        )
        payload = json.loads(raw or "{}")
        return payload if isinstance(payload, dict) else {}

    async def wait_for_composer(
        self,
        timeout: float = 20.0,
        *,
        context: str | None = None,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        selectors = json.dumps(COMPOSER_SELECTORS)
        expression = (
            "(()=>{const selectors="
            + selectors
            + ";const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),"
            "s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&"
            "s.visibility!=='hidden'&&s.opacity!=='0';};"
            "for(const selector of selectors){for(const e of document.querySelectorAll(selector)){"
            "if(visible(e)&&!e.disabled&&e.getAttribute('aria-disabled')!=='true')return true;}}"
            "return false;})()"
        )
        while asyncio.get_running_loop().time() < deadline:
            ready = (
                await self.eval(expression)
                if context is None
                else await self.eval(expression, context=context)
            )
            if ready:
                return
            await asyncio.sleep(0.25)
        raise RuntimeError("ChatGPT composer did not become ready")

    async def _focus_composer(self) -> None:
        selectors = json.dumps(COMPOSER_SELECTORS)
        expression = (
            "(()=>{const selectors="
            + selectors
            + ";const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),"
            "s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&"
            "s.visibility!=='hidden'&&s.opacity!=='0';};"
            "for(const selector of selectors){for(const e of document.querySelectorAll(selector)){"
            "if(!visible(e)||e.disabled||e.getAttribute('aria-disabled')==='true')continue;"
            "e.focus();return document.activeElement===e||e.contains(document.activeElement);}}"
            "return false;})()"
        )
        if not await self.eval(expression):
            raise RuntimeError("ChatGPT composer could not be focused")

    async def _perform_actions(self, context: str, actions: list[dict[str, Any]]) -> None:
        try:
            await self._call(
                "input.performActions",
                {
                    "context": context,
                    "actions": actions,
                },
            )
        except BaseException:
            # The browser may create or partially apply an input source before an
            # action sequence fails. Best-effort release keeps that state from
            # leaking into the next trusted interaction.
            try:
                await self._call("input.releaseActions", {"context": context})
            except Exception:
                pass
            raise
        await self._call("input.releaseActions", {"context": context})

    async def _key_text(self, text: str, *, enter: bool = False) -> None:
        actions: list[dict[str, str]] = []
        for char in text:
            actions.extend(
                [
                    {"type": "keyDown", "value": char},
                    {"type": "keyUp", "value": char},
                ]
            )
        if enter:
            actions.extend(
                [
                    {"type": "keyDown", "value": "\ue007"},
                    {"type": "keyUp", "value": "\ue007"},
                ]
            )
        await self._perform_actions(
            self.context,
            [{"type": "key", "id": "keyboard", "actions": actions}],
        )

    async def attach_files(self, files: list[str]) -> None:
        paths = [str(Path(path).expanduser().resolve()) for path in files]
        if not paths:
            return
        for path in paths:
            if not Path(path).is_file():
                raise RuntimeError(f"Prompta attachment does not exist: {path}")

        async def file_input() -> dict[str, Any] | None:
            script = """(()=>{
              const selectors=__FILE_INPUT_SELECTORS__;
              for(const selector of selectors){
                for(const input of document.querySelectorAll(selector)){
                  if(input.disabled||input.getAttribute('aria-disabled')==='true')continue;
                  return input;
                }
              }
              return null;
            })()""".replace("__FILE_INPUT_SELECTORS__", json.dumps(FILE_INPUT_SELECTORS))
            response = await self._call(
                "script.evaluate",
                {
                    "expression": script,
                    "target": {"context": self.context},
                    "awaitPromise": False,
                    "resultOwnership": "root",
                },
            )
            payload = response.get("result")
            if not isinstance(payload, dict):
                return None
            result = payload.get("result")
            return result if isinstance(result, dict) and result.get("sharedId") else None

        remote = await file_input()
        if remote is None:
            opened = await self.eval(
                r"""(()=>{
                  const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
                  const enabled=e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true';
                  const label=e=>(e.getAttribute('data-testid')||e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').replace(/\s+/g,' ').trim();
                  const composer=document.querySelector('[data-composer-surface],form[data-type="unified-composer"]');
                  const roots=composer?[composer,document]:[document];
                  for(const root of roots){
                    const buttons=[...root.querySelectorAll('button')].filter(e=>visible(e)&&enabled(e));
                    const button=buttons.find(e=>e.getAttribute('data-testid')==='composer-plus-btn')
                      ||buttons.find(e=>/add files and more|attach|upload|add (?:file|photo)/i.test(label(e)));
                    if(button){button.click();return true;}
                  }
                  return false;
                })()"""
            )
            if opened:
                await asyncio.sleep(0.25)
                remote = await file_input()
        if remote is None:
            raise RuntimeError("ChatGPT attachment input could not be found")

        await self._call(
            "input.setFiles",
            {
                "context": self.context,
                "element": {"sharedId": str(remote["sharedId"])},
                "files": paths,
            },
        )

        file_names = [Path(path).name for path in paths]
        encoded_names = json.dumps(file_names)
        await asyncio.sleep(0.5)
        deadline = asyncio.get_running_loop().time() + 120.0
        stable_ready_polls = 0
        while asyncio.get_running_loop().time() < deadline:
            raw_state = await self.eval(
                f"""JSON.stringify((()=>{{const visible=e=>{{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';}};const names={encoded_names};const pageText=document.body?.innerText||'';const selected=[...document.querySelectorAll('input[type=file]')].flatMap(input=>[...(input.files||[])]).map(file=>file.name);const attached=names.every(name=>pageText.includes(name)||selected.includes(name));const progressBusy=[...document.querySelectorAll('[aria-busy="true"],progress,[role="progressbar"]')].some(visible);const labelledBusy=[...document.querySelectorAll('[data-testid*="upload" i],[aria-label*="upload" i],[title*="upload" i]')].some(e=>visible(e)&&/(?:uploading|processing|attaching|cancel upload)/i.test((e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'')));return {{attached,busy:progressBusy||labelledBusy}};}})())"""
            )
            try:
                state = json.loads(raw_state or "{}")
            except json.JSONDecodeError:
                state = {}
            if bool(state.get("attached")) and not bool(state.get("busy")):
                stable_ready_polls += 1
                if stable_ready_polls >= 3:
                    return
            else:
                stable_ready_polls = 0
            await asyncio.sleep(0.2)
        raise RuntimeError("ChatGPT attachment upload did not finish within 120s")

    async def type_message(self, text: str) -> None:
        await self.wait_for_composer()
        await self._focus_composer()
        script = """(()=>{
          const selectors=__COMPOSER_SELECTORS__;
          const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);
            return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
          let e=null;
          for(const selector of selectors){
            e=[...document.querySelectorAll(selector)].find(node=>visible(node)&&!node.disabled&&node.getAttribute('aria-disabled')!=='true');
            if(e)break;
          }
          if(!e)return false;e.focus();
          const text=__PROMPT_TEXT__;
          if('value' in e){
            const prototype=e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
            const setter=Object.getOwnPropertyDescriptor(prototype,'value')?.set;
            if(setter)setter.call(e,text);else e.value=text;
            e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:text}));
            e.dispatchEvent(new Event('change',{bubbles:true}));
          }else{
            const selection=window.getSelection(),range=document.createRange();
            range.selectNodeContents(e);selection?.removeAllRanges();selection?.addRange(range);
            document.execCommand('insertText',false,text);
            e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:text}));
          }
          return true;
        })()"""
        script = script.replace("__COMPOSER_SELECTORS__", json.dumps(COMPOSER_SELECTORS))
        script = script.replace("__PROMPT_TEXT__", json.dumps(text))
        await self.eval(script)
        state = await self.dom_state()
        actual = " ".join(str(state.get("composer_text") or "").split()).strip()
        expected = " ".join(text.split()).strip()
        if actual == expected:
            return
        # Some editor versions ignore synthetic input; retry through real key events.
        await self.clear_composer()
        await self._key_text(text)

    async def clear_composer(self, timeout: float = 3.0) -> None:
        await self.wait_for_composer()
        await self._focus_composer()
        script = """(()=>{
          const selectors=__COMPOSER_SELECTORS__;
          const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);
            return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
          let e=null;
          for(const selector of selectors){
            e=[...document.querySelectorAll(selector)].find(node=>visible(node)&&!node.disabled&&node.getAttribute('aria-disabled')!=='true');
            if(e)break;
          }
          if(!e)return false;e.focus();
          if('value' in e){
            const prototype=e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
            const setter=Object.getOwnPropertyDescriptor(prototype,'value')?.set;
            if(setter)setter.call(e,'');else e.value='';
          }else{
            const selection=window.getSelection(),range=document.createRange();
            range.selectNodeContents(e);selection?.removeAllRanges();selection?.addRange(range);
            document.execCommand('delete');
            if((e.innerText||e.textContent||'').trim())e.replaceChildren();
          }
          e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'deleteContentBackward'}));
          e.dispatchEvent(new Event('change',{bubbles:true}));
          return true;
        })()""".replace("__COMPOSER_SELECTORS__", json.dumps(COMPOSER_SELECTORS))
        cleared = await self.eval(script)
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            state = await self.dom_state()
            if not str(state.get("composer_text") or "").strip():
                return
            if cleared:
                await asyncio.sleep(0.1)
                continue
            break
        # Some editor versions ignore synthetic DOM input; use real key events as a fallback.
        await self._perform_actions(
            self.context,
            [
                {
                    "type": "key",
                    "id": "keyboard",
                    "actions": [
                        {"type": "keyDown", "value": "\ue009"},
                        {"type": "keyDown", "value": "a"},
                        {"type": "keyUp", "value": "a"},
                        {"type": "keyUp", "value": "\ue009"},
                        {"type": "keyDown", "value": "\ue003"},
                        {"type": "keyUp", "value": "\ue003"},
                    ],
                }
            ],
        )
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            state = await self.dom_state()
            if not str(state.get("composer_text") or "").strip():
                return
            await asyncio.sleep(0.1)
        raise RuntimeError("ChatGPT stale composer could not be cleared")

    async def click_send(self) -> None:
        # A WebDriver key action is trusted input just like a pointer action, but it does not
        # depend on DOM coordinates matching the browser's action viewport. ChatGPT's composer
        # sends on Enter, so keep the trusted interaction anchored to the focused composer.
        await self._focus_composer()
        await self._key_text("", enter=True)

    async def _click_viewport_point(self, context: str, x: float, y: float) -> None:
        await self._perform_actions(
            context,
            [
                {
                    "type": "pointer",
                    "id": "mouse",
                    "parameters": {"pointerType": "mouse"},
                    "actions": [
                        {
                            "type": "pointerMove",
                            "duration": 0,
                            "origin": "viewport",
                            "x": round(x),
                            "y": round(y),
                        },
                        {"type": "pointerDown", "button": 0},
                        {"type": "pointerUp", "button": 0},
                    ],
                }
            ],
        )

    async def click_send_button(self, timeout: float = 120.0) -> None:
        deadline = asyncio.get_running_loop().time() + max(1.0, timeout)
        while asyncio.get_running_loop().time() < deadline:
            script = r"""JSON.stringify((()=>{
              const composerSelectors=__COMPOSER_SELECTORS__;
              const sendSelectors=__SEND_SELECTORS__;
              const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
              const enabled=e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true';
              const label=e=>(e.getAttribute('data-testid')||e.id||e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').replace(/\s+/g,' ').trim();
              let composer=null;
              for(const selector of composerSelectors){
                composer=[...document.querySelectorAll(selector)].find(e=>visible(e)&&enabled(e));
                if(composer)break;
              }
              const scope=composer?.closest('form')||composer?.closest('[data-composer-surface]')||document;
              let button=null;
              for(const selector of sendSelectors){
                if(scope===document&&selector==='button[type="submit"]')continue;
                button=[...scope.querySelectorAll(selector)].find(e=>visible(e)&&enabled(e));
                if(button)break;
              }
              if(!button){
                button=[...scope.querySelectorAll('button')].find(e=>visible(e)&&enabled(e)&&/(?:^|[-_ ])send(?:$|[-_ ])/i.test(label(e)));
              }
              if(!button)return null;
              button.scrollIntoView({block:'center',inline:'center'});
              const r=button.getBoundingClientRect();
              const width=document.documentElement.clientWidth||window.innerWidth;
              const height=document.documentElement.clientHeight||window.innerHeight;
              const x=r.left+r.width/2,y=r.top+r.height/2;
              if(x<0||y<0||x>=width||y>=height)return null;
              return {x,y,label:label(button)};
            })())"""
            script = script.replace("__COMPOSER_SELECTORS__", json.dumps(COMPOSER_SELECTORS))
            script = script.replace("__SEND_SELECTORS__", json.dumps(SEND_BUTTON_SELECTORS))
            raw = await self.eval(script)
            candidate = json.loads(raw or "null")
            if isinstance(candidate, dict) and "x" in candidate and "y" in candidate:
                try:
                    x = float(candidate["x"])
                    y = float(candidate["y"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise RuntimeError("ChatGPT send button position was invalid") from exc
                try:
                    await self._click_viewport_point(self.context, x, y)
                except RuntimeError as exc:
                    if "out of bounds" not in str(exc).lower():
                        raise
                    await asyncio.sleep(0.1)
                    continue
                return
            await asyncio.sleep(0.2)
        raise RuntimeError("ChatGPT send button did not become enabled")

    async def click_delivery_retry(self, context: str, timeout: float = 3.0) -> bool:
        """Retry one ChatGPT response after its delivery timeout UI appears."""

        deadline = asyncio.get_running_loop().time() + max(0.1, timeout)
        while asyncio.get_running_loop().time() < deadline:
            script = r"""JSON.stringify((()=>{
              const assistantSelector=__ASSISTANT_SELECTOR__;
              const turnSelector=__TURN_SELECTOR__;
              const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
              const enabled=e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true';
              const label=e=>(e.getAttribute('data-testid')||e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').replace(/\s+/g,' ').trim();
              const assistants=[...document.querySelectorAll(assistantSelector)];
              const assistant=assistants.at(-1);
              let turn=assistant?.closest(turnSelector)||assistant?.parentElement||null;
              if(!turn){
                turn=[...document.querySelectorAll(turnSelector)].filter(visible).reverse().find(node=>/Message delivery timed out\.?\s*Please try again/i.test(node.innerText||node.textContent||''))||null;
              }
              const turnText=(turn?.innerText||turn?.textContent||'').trim();
              if(!turn||!/Message delivery timed out\.?\s*Please try again/i.test(turnText))return null;
              const scopes=[turn,turn.parentElement,turn.parentElement?.parentElement].filter(Boolean);
              const actionSelector='button,[role="button"]';
              const actions=scopes.flatMap(scope=>[...scope.querySelectorAll(actionSelector)]).filter((action,index,all)=>visible(action)&&enabled(action)&&all.indexOf(action)===index);
              const exactRetry=action=>/^(?:try again|retry|regenerate(?: response)?)$/i.test(label(action));
              const looseRetry=action=>/(?:try again|retry)/i.test(label(action));
              let button=actions.find(exactRetry)||actions.find(looseRetry);
              if(!button){
                const globalActions=[...document.querySelectorAll(actionSelector)].filter(action=>visible(action)&&enabled(action));
                button=globalActions.find(exactRetry)||globalActions.find(looseRetry);
              }
              if(!button)return null;
              button.scrollIntoView({block:'center',inline:'center'});
              const r=button.getBoundingClientRect();
              const width=document.documentElement.clientWidth||window.innerWidth;
              const height=document.documentElement.clientHeight||window.innerHeight;
              const x=r.left+r.width/2,y=r.top+r.height/2;
              if(x<0||y<0||x>=width||y>=height)return null;
              return {x,y,label:label(button)};
            })())"""
            script = script.replace(
                "__ASSISTANT_SELECTOR__", json.dumps(ASSISTANT_MESSAGE_SELECTOR)
            )
            script = script.replace("__TURN_SELECTOR__", json.dumps(TURN_SELECTOR))
            raw = await self.eval(script, context=context)
            candidate = json.loads(raw or "null")
            if isinstance(candidate, dict) and "x" in candidate and "y" in candidate:
                try:
                    x = float(candidate["x"])
                    y = float(candidate["y"])
                except (KeyError, TypeError, ValueError):
                    return False
                try:
                    await self._click_viewport_point(context, x, y)
                except RuntimeError as exc:
                    if "out of bounds" not in str(exc).lower():
                        raise
                    await asyncio.sleep(0.1)
                    continue
                return True
            await asyncio.sleep(0.2)
        return False

    async def click_stop(self, context: str, timeout: float = 5.0) -> bool:
        deadline = asyncio.get_running_loop().time() + max(0.2, timeout)
        point: dict[str, Any] | None = None
        while asyncio.get_running_loop().time() < deadline:
            script = r"""JSON.stringify((()=>{
              const selectors=__STOP_SELECTORS__;
              const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
              const enabled=e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true';
              const label=e=>(e.getAttribute('data-testid')||e.id||e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').replace(/\s+/g,' ').trim();
              let button=null;
              for(const selector of selectors){
                button=[...document.querySelectorAll(selector)].find(e=>visible(e)&&enabled(e));
                if(button)break;
              }
              if(!button){
                button=[...document.querySelectorAll('button')].find(e=>visible(e)&&enabled(e)&&/(?:^|[-_ ])stop(?:$|[-_ ])/i.test(label(e)));
              }
              if(!button)return null;
              const r=button.getBoundingClientRect();
              return {x:r.left+r.width/2,y:r.top+r.height/2,label:label(button)};
            })())""".replace("__STOP_SELECTORS__", json.dumps(STOP_BUTTON_SELECTORS))
            raw = await self.eval(script, context=context)
            candidate = json.loads(raw or "null")
            if isinstance(candidate, dict) and "x" in candidate and "y" in candidate:
                point = candidate
                break
            await asyncio.sleep(0.1)
        if point is None:
            return False
        try:
            x = float(point["x"])
            y = float(point["y"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("ChatGPT stop button position was invalid") from exc
        await self._click_viewport_point(context, x, y)
        return True

    async def dom_state(self) -> dict[str, Any]:
        script = r"""JSON.stringify((()=>{
          const composerSelectors=__COMPOSER_SELECTORS__;
          const messageSelector=__MESSAGE_SELECTOR__;
          const rateLimitSelector=__RATE_LIMIT_SELECTOR__;
          const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
          let composer=null;
          for(const selector of composerSelectors){
            composer=[...document.querySelectorAll(selector)].find(node=>visible(node)&&!node.disabled&&node.getAttribute('aria-disabled')!=='true');
            if(composer)break;
          }
          const messageText=root=>{
            if(!root)return '';
            const clone=root.cloneNode(true);
            clone.querySelectorAll('button,[role="button"]').forEach(node=>node.remove());
            const text=(clone.textContent||'').trim();
            const actionSuffix=['Show moreShow less','Show lessShow more'].find(suffix=>text.endsWith(suffix));
            return (actionSuffix?text.slice(0,-actionSuffix.length):text).trim();
          };
          const messages=[...document.querySelectorAll(messageSelector)];
          const users=messages.filter(e=>e.getAttribute('data-message-author-role')==='user');
          const rateLimitPattern=/(?:too many requests|temporarily limited access|requests too quickly|rate limit)/i;
          const rateLimitNodes=[...document.querySelectorAll(rateLimitSelector)]
            .filter(node=>visible(node)&&rateLimitPattern.test(node.innerText||node.textContent||''));
          const rateLimitModal=[...document.querySelectorAll('dialog,[role="dialog"],[data-testid*="rate-limit" i]')]
            .find(node=>visible(node)&&rateLimitPattern.test(node.innerText||node.textContent||''));
          const rateLimitText=[...new Set([
            ...rateLimitNodes.map(node=>node.innerText||node.textContent||''),
            rateLimitModal?.innerText||rateLimitModal?.textContent||''
          ].map(text=>text.trim()).filter(Boolean))].join('\n');
          if(rateLimitModal){
            const acknowledge=[...rateLimitModal.querySelectorAll('button')].find(button=>{
              const label=(button.innerText||button.textContent||button.getAttribute('aria-label')||'').trim();
              return visible(button)&&/^(?:got it|ok|okay|dismiss|close)$/i.test(label);
            });
            acknowledge?.click();
          }
          const lastUser=users.at(-1)||null;
          return {
            composer_text:(composer&&('value' in composer?composer.value:(composer.innerText||composer.textContent))||''),
            last_user_id:(lastUser?.getAttribute('data-message-id')||lastUser?.getAttribute('data-message-uuid')||''),
            last_user_text:messageText(lastUser),
            rate_limit_text:rateLimitText
          };
        })())"""
        script = script.replace("__COMPOSER_SELECTORS__", json.dumps(COMPOSER_SELECTORS))
        script = script.replace("__MESSAGE_SELECTOR__", json.dumps(MESSAGE_ROLE_SELECTOR))
        script = script.replace("__RATE_LIMIT_SELECTOR__", json.dumps(RATE_LIMIT_SELECTOR))
        raw = await self.eval(script)
        return json.loads(raw or "{}")

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

    async def close(self) -> None:
        if self.ws is not None:
            try:
                await self._call("session.end", {})
            except Exception:
                pass
            try:
                await self.ws.close()
            except Exception:
                pass
        self.ws = None
        self.context = ""
        self._network_subscribed = False
        self._send_capture = None
