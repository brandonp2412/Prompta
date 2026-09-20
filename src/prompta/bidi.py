"""Small Firefox WebDriver BiDi client containing only what Prompta needs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import websockets
from websockets.exceptions import ConnectionClosed

_SEND_ENDPOINTS = ("/backend-api/f/conversation", "/backend-api/conversation")
_BIDI_CALL_TIMEOUT_SECONDS = 30.0


class FirefoxBiDiDriver:
    def __init__(self, url: str) -> None:
        self.url = url
        self.ws: Any = None
        self.context = ""
        self.request_id = 0
        self._network_subscribed = False
        self._send_capture: dict[str, Any] | None = None
        self.needs_browser_restart = False

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
            raise RuntimeError("Firefox BiDi session is poisoned; browser restart required")
        try:
            self.ws = await websockets.connect(
                self.url,
                max_size=16 * 1024 * 1024,
                ping_interval=None,
            )
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
            raise RuntimeError(f"Firefox BiDi session failed: {response}")
        tree = await self._call("browsingContext.getTree", {})
        contexts = tree.get("result", {}).get("contexts") or []
        if not contexts:
            raise RuntimeError("Firefox BiDi has no browsing context")
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
        deadline = asyncio.get_running_loop().time() + 15.0
        last_error: Exception | None = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                if await self.login_required():
                    raise RuntimeError("Prompta Firefox profile is not logged into ChatGPT")
                if await self.ensure_token():
                    return
            except Exception as exc:
                last_error = exc
            await asyncio.sleep(0.5)
        raise RuntimeError(
            "Prompta Firefox profile did not produce an authenticated ChatGPT session within 15s"
        ) from last_error

    async def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.ws is None:
            raise RuntimeError("Firefox BiDi is not connected")
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
                f"{method}: Firefox BiDi call timed out after {_BIDI_CALL_TIMEOUT_SECONDS:.0f}s"
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
                  req=new Request(input,init);
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
            raise RuntimeError("Firefox BiDi network capture is not subscribed")
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

    async def navigate(self, url: str) -> None:
        await self._call(
            "browsingContext.navigate",
            {"context": self.context, "url": url, "wait": "complete"},
        )

    async def activate_history_link(self, path: str) -> bool:
        target = json.dumps(path.rstrip("/"))
        return bool(
            await self.eval(
                f"""(()=>{{const target={target};const link=[...document.querySelectorAll('a[href]')].find(a=>{{try{{return new URL(a.href,location.origin).pathname.replace(/\\/$/,'')===target;}}catch{{return false;}}}});if(!link)return false;link.click();return true;}})()"""
            )
        )

    async def new_tab(self, url: str = "https://chatgpt.com/") -> str:
        response = await self._call("browsingContext.create", {"type": "tab"})
        context = str(response.get("result", {}).get("context") or "")
        if not context:
            raise RuntimeError(f"Firefox BiDi did not create a browsing context: {response}")
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
                """(()=>{const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};return visible(document.querySelector('button[data-testid="login-button"]'));})()"""
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
            raise RuntimeError("Prompta Firefox profile is not logged into ChatGPT")
        return token

    async def wait_for_composer(self, timeout: float = 20.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        expression = (
            "(()=>{const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),"
            "s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&"
            "s.visibility!=='hidden';};return [...document.querySelectorAll("
            "'#prompt-textarea,div[role=\\\"textbox\\\"].ProseMirror,textarea#prompt-textarea,textarea#mobile-composer-prompt'"
            ")].some(visible)})()"
        )
        while asyncio.get_running_loop().time() < deadline:
            if await self.eval(expression):
                return
            await asyncio.sleep(0.25)
        raise RuntimeError("ChatGPT composer did not become ready")

    async def _focus_composer(self) -> None:
        expression = (
            "(()=>{const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),"
            "s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&"
            "s.visibility!=='hidden';};const e=[...document.querySelectorAll("
            "'#prompt-textarea,div[role=\\\"textbox\\\"].ProseMirror,textarea#prompt-textarea,textarea#mobile-composer-prompt'"
            ")].find(visible);if(!e)return false;e.focus();return true})()"
        )
        if not await self.eval(expression):
            raise RuntimeError("ChatGPT composer could not be focused")

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
        await self._call(
            "input.performActions",
            {
                "context": self.context,
                "actions": [{"type": "key", "id": "keyboard", "actions": actions}],
            },
        )
        await self._call("input.releaseActions", {"context": self.context})

    async def attach_files(self, files: list[str]) -> None:
        paths = [str(Path(path).expanduser().resolve()) for path in files]
        if not paths:
            return
        for path in paths:
            if not Path(path).is_file():
                raise RuntimeError(f"Prompta attachment does not exist: {path}")

        async def file_input() -> dict[str, Any] | None:
            response = await self._call(
                "script.evaluate",
                {
                    "expression": "document.querySelector('input[type=file]')",
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
                """(()=>{const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};const buttons=[...document.querySelectorAll('button')].filter(visible);const b=buttons.find(e=>/attach|upload|add (?:file|photo)/i.test((e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'')));if(!b)return false;b.click();return true})()"""
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
        await self.eval(
            f"""(()=>{{
              const selector='#prompt-textarea,div[role="textbox"].ProseMirror,textarea#prompt-textarea,textarea#mobile-composer-prompt';
              const visible=e=>{{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
                return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';}};
              const e=[...document.querySelectorAll(selector)].find(visible);
              if(!e)return false;e.focus();
              const text={json.dumps(text)};
              if('value' in e){{
                const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')?.set;
                if(setter)setter.call(e,text);else e.value=text;
                e.dispatchEvent(new InputEvent('input',{{bubbles:true,inputType:'insertText',data:text}}));
              }}else{{
                document.execCommand('insertText',false,text);
              }}
              return true;
            }})()"""
        )
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
        cleared = await self.eval(
            """(()=>{
              const selector='#prompt-textarea,div[role="textbox"].ProseMirror,textarea#prompt-textarea,textarea#mobile-composer-prompt';
              const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
                return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
              const e=[...document.querySelectorAll(selector)].find(visible);
              if(!e)return false;e.focus();
              if('value' in e){
                const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')?.set;
                if(setter)setter.call(e,'');else e.value='';
              }else{
                const selection=window.getSelection(),range=document.createRange();
                range.selectNodeContents(e);selection?.removeAllRanges();selection?.addRange(range);
                document.execCommand('delete');
                if((e.innerText||e.textContent||'').trim())e.replaceChildren();
              }
              e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'deleteContentBackward'}));
              return true;
            })()"""
        )
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
        await self._call(
            "input.performActions",
            {
                "context": self.context,
                "actions": [
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
            },
        )
        await self._call("input.releaseActions", {"context": self.context})
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            state = await self.dom_state()
            if not str(state.get("composer_text") or "").strip():
                return
            await asyncio.sleep(0.1)
        raise RuntimeError("ChatGPT stale composer could not be cleared")

    async def click_send(self) -> None:
        # A WebDriver key action is trusted input just like a pointer action, but it does not
        # depend on DOM coordinates matching Firefox's action viewport. ChatGPT's composer
        # sends on Enter, so keep the trusted interaction anchored to the focused composer.
        await self._focus_composer()
        await self._key_text("", enter=True)

    async def click_send_button(self, timeout: float = 120.0) -> None:
        deadline = asyncio.get_running_loop().time() + max(1.0, timeout)
        point: dict[str, Any] | None = None
        while asyncio.get_running_loop().time() < deadline:
            raw = await self.eval(
                """JSON.stringify((()=>{const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};const composer=[...document.querySelectorAll('#prompt-textarea,div[role="textbox"].ProseMirror,textarea#prompt-textarea,textarea#mobile-composer-prompt')].find(visible);const scope=composer?.closest('form')||composer?.parentElement?.parentElement||document;const buttons=[...scope.querySelectorAll('button')].filter(visible);const enabled=e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true';const label=e=>(e.getAttribute('data-testid')||e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').trim();const button=buttons.find(e=>enabled(e)&&e.matches('button[type="submit"]'))||buttons.find(e=>enabled(e)&&/(?:^|[-_ ])send(?:$|[-_ ])/i.test(label(e)))||buttons.find(e=>enabled(e)&&/send/i.test(label(e)));if(!button)return null;const r=button.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2,label:label(button)};})())"""
            )
            candidate = json.loads(raw or "null")
            if isinstance(candidate, dict) and "x" in candidate and "y" in candidate:
                point = candidate
                break
            await asyncio.sleep(0.2)
        if point is None:
            raise RuntimeError("ChatGPT send button did not become enabled")
        try:
            x = float(point["x"])
            y = float(point["y"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("ChatGPT send button position was invalid") from exc
        await self._call(
            "input.performActions",
            {
                "context": self.context,
                "actions": [
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
            },
        )
        await self._call("input.releaseActions", {"context": self.context})

    async def dom_state(self) -> dict[str, Any]:
        raw = await self.eval(
            """JSON.stringify((()=>{
              const selector='#prompt-textarea,div[role="textbox"].ProseMirror,textarea#prompt-textarea,textarea#mobile-composer-prompt';
              const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
              const composer=[...document.querySelectorAll(selector)].find(visible);
              const messageText=root=>{
                if(!root)return '';
                const clone=root.cloneNode(true);
                clone.querySelectorAll('button,[role="button"]').forEach(node=>node.remove());
                return (clone.textContent||'').trim();
              };
              const messages=[...document.querySelectorAll('[data-message-author-role]')];
              const users=messages.filter(e=>e.getAttribute('data-message-author-role')==='user');
              const rateLimitText=[...document.querySelectorAll('[role="alert"],[aria-live="assertive"],[aria-live="polite"],[data-testid="conversation-fetch-error-toaster"],[data-testid*="rate-limit"]')]
                .filter(visible).map(e=>e.innerText||'').filter(Boolean).join('\\n');
              return {
                composer_text:(composer&&(composer.innerText||composer.value)||''),
                last_user_id:(users.at(-1)?.getAttribute('data-message-id')||''),
                last_user_text:messageText(users.at(-1)),
                rate_limit_text:rateLimitText
              };
            })())"""
        )
        return json.loads(raw or "{}")

    async def conversation_activity(self, context: str) -> dict[str, Any]:
        raw = await self.eval(
            """JSON.stringify((()=>{
              const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
              const stop=[...document.querySelectorAll('button[data-testid="stop-button"],button[aria-label="Stop answering"],button[aria-label="Stop generating"]')].some(visible);
              const streamActive=[...document.querySelectorAll('[data-streaming="active"],[data-is-streaming="true"]')].some(visible);
              const assistants=[...document.querySelectorAll('[data-message-author-role="assistant"]')];
              const assistant=assistants.at(-1);
              const turn=assistant?.closest('[data-testid^="conversation-turn-"]')||assistant?.closest('.agent-turn')||assistant?.parentElement;
              const turnText=(turn?.innerText||turn?.textContent||'').trim();
              const transientText=/(?:Connection interrupted|Waiting for the complete answer|Message delivery timed out\\.?\\s*Please try again)/i.test(turnText);
              const finalAction=Boolean(turn&&[...turn.querySelectorAll('button')].some(button=>{
                const testId=(button.getAttribute('data-testid')||'').trim();
                const label=(button.getAttribute('aria-label')||'').trim();
                return testId==='copy-turn-action-button'||/^Copy response$/i.test(label);
              }));
              const transient=transientText&&!finalAction;
              return {streaming:stop||streamActive,complete:finalAction&&!stop&&!streamActive,transient};
            })())""",
            context=context,
        )
        return json.loads(raw or "{}")

    async def conversation_snapshot(self, context: str) -> dict[str, Any]:
        raw = await self.eval(
            """JSON.stringify((()=>{
              const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
              const normalise=value=>(value||'').replace(/\\s+/g,' ').trim();
              const hash=value=>{let h=2166136261;for(const ch of value){h^=ch.charCodeAt(0);h=Math.imul(h,16777619);}return (h>>>0).toString(36);};
              const messageText=root=>{
                if(!root)return '';
                const clone=root.cloneNode(true);
                clone.querySelectorAll('button,[role="button"]').forEach(node=>node.remove());
                return (clone.textContent||'').trim();
              };
              const markdownText=root=>{
                const walk=node=>{
                  if(node.nodeType===Node.TEXT_NODE)return node.textContent||'';
                  if(node.nodeType!==Node.ELEMENT_NODE)return '';
                  const tag=node.tagName.toLowerCase();
                  const children=()=>[...node.childNodes].map(walk).join('');
                  if(tag==='br')return '\\n';
                  if(/^h[1-6]$/.test(tag))return '#'.repeat(Number(tag[1]))+' '+children().trim()+'\\n\\n';
                  if(tag==='p')return children().trim()+'\\n\\n';
                  if(tag==='strong'||tag==='b')return '**'+children()+'**';
                  if(tag==='em'||tag==='i')return '*'+children()+'*';
                  if(tag==='del'||tag==='s')return '~~'+children()+'~~';
                  if(tag==='code'&&node.parentElement?.tagName.toLowerCase()!=='pre')return '`'+children()+'`';
                  if(tag==='pre'){
                    const code=node.querySelector('code')||node;
                    const className=code.getAttribute('class')||'';
                    const language=className.match(/language-([\\w+-]+)/)?.[1]||'';
                    return '```'+language+'\\n'+(code.textContent||'').replace(/\\n$/,'')+'\\n```\\n\\n';
                  }
                  if(tag==='a'){
                    const href=node.getAttribute('href')||'';
                    const label=children().trim()||href;
                    return /^https?:\\/\\//i.test(href)?'['+label+']('+href+')':label;
                  }
                  if(tag==='ul'||tag==='ol'){
                    const ordered=tag==='ol';
                    return [...node.children].filter(child=>child.tagName.toLowerCase()==='li').map((child,index)=>{
                      const body=[...child.childNodes].filter(part=>!(part.nodeType===Node.ELEMENT_NODE&&['ul','ol'].includes(part.tagName.toLowerCase()))).map(walk).join('').trim();
                      const nested=[...child.children].filter(part=>['ul','ol'].includes(part.tagName.toLowerCase())).map(walk).join('').trimEnd();
                      const prefix=ordered?(index+1)+'. ':'- ';
                      return prefix+body+(nested?'\\n'+nested.split('\\n').map(line=>line?'  '+line:line).join('\\n'):'');
                    }).join('\\n')+'\\n\\n';
                  }
                  if(tag==='blockquote')return children().trim().split('\\n').map(line=>'> '+line).join('\\n')+'\\n\\n';
                  if(tag==='hr')return '---\\n\\n';
                  if(tag==='li')return children();
                  if(tag==='div'||tag==='section'||tag==='article')return children();
                  return children();
                };
                return walk(root).replace(/\\n{3,}/g,'\\n\\n').trim();
              };
              const toolSelector='[data-tool-call-id],[data-tool-name]';
              const toolBlocks=agent=>[...new Set([
                ...agent.querySelectorAll(toolSelector)
              ])].filter(node=>!node.querySelector(toolSelector)).map(node=>{
                const name=(node.getAttribute('data-tool-name')
                  ||node.querySelector('[data-tool-name]')?.getAttribute('data-tool-name')
                  ||'').trim();
                const noise=/^(?:Open tool call list|Close tool call list|cot-v5-tool-icon-pile|Tool call|Expand|Collapse)$/i;
                const detail=(node.innerText||node.textContent||'').split(/\\n+/)
                  .map(line=>line.trim())
                  .filter(line=>line&&!noise.test(line)&&!/^cot-v5-/i.test(line))
                  .join('\\n').trim().slice(0,16000);
                if(!detail&&!name)return '';
                const label=name||'tool';
                return '```tool:'+label+'\\n'+(detail||label)+'\\n```';
              }).filter(Boolean).filter((block,index,blocks)=>blocks.indexOf(block)===index);
              const roleNodes=[...document.querySelectorAll('[data-message-author-role]')];
              const entries=roleNodes.map(e=>{
                const role=e.getAttribute('data-message-author-role')||'';
                const rich=role==='assistant'
                  ? [...e.querySelectorAll('.markdown,.markdown-new-styling')].map(markdownText).filter(Boolean).join('\\n\\n').trim()
                  : '';
                return {
                  node:e,
                  id:e.getAttribute('data-message-id')||e.getAttribute('data-message-uuid')||'',
                  role,
                  content:role==='assistant'?rich:messageText(e)
                };
              }).filter(message=>message.role&&message.content&&!(
                message.role==='assistant'&&message.id.startsWith('request-placeholder-')
              ));
              const seenRoleKeys=new Set();
              for(let index=entries.length-1;index>=0;index-=1){
                const message=entries[index];
                const key=message.role+'|'+(message.id||normalise(message.content));
                if(seenRoleKeys.has(key))entries.splice(index,1);
                else seenRoleKeys.add(key);
              }
              const assistantNodes=roleNodes.filter(node=>node.getAttribute('data-message-author-role')==='assistant');
              const candidates=[...new Set([
                ...assistantNodes.map(node=>node.closest('[data-testid^="conversation-turn-"]')||node.closest('.agent-turn')||node.parentElement).filter(Boolean),
                ...document.querySelectorAll('.agent-turn')
              ])].filter(visible);
              for(const [agentIndex,agent] of candidates.entries()){
                const markdown=[...agent.querySelectorAll('.markdown,.markdown-new-styling')];
                const richText=markdown.map(markdownText).filter(Boolean);
                const richPlain=markdown.map(node=>(node.innerText||node.textContent||'').trim()).filter(Boolean);
                const tools=toolBlocks(agent);
                const rawVisible=(agent.innerText||agent.textContent||'').trim();
                const uiNoise=/^(?:copy|copy code|edit|good response|bad response|read aloud|regenerate|share|open tool call list|close tool call list|cot-v5-tool-icon-pile|connection interrupted\\.?|waiting for the complete answer|message delivery timed out\\.?\\s*please try again)$/i;
                const activityLines=[...new Set(rawVisible.split(/\\n+/).map(line=>line.trim()).filter(line=>(
                  line
                  && !uiNoise.test(line)
                  && !richPlain.some(text=>text===line||text.includes(line)||line.includes(text))
                  && !tools.some(block=>block.includes(line))
                )))].slice(0,200);
                const activity=!richText.length&&!tools.length&&activityLines.length
                  ? '**Tool activity**\\n\\n'+activityLines.join('\\n')
                  : '';
                const cleanVisible=rawVisible.split(/\\n+/).map(line=>line.trim())
                  .filter(line=>line&&!uiNoise.test(line)&&!/^cot-v5-/i.test(line))
                  .join('\\n').trim();
                const content=(richText.length||tools.length||activity
                  ? [...richText,...tools,...(activity?[activity]:[])].join('\\n\\n')
                  : cleanVisible
                ).trim();
                if(!content)continue;
                const nested=agent.querySelector('[data-message-author-role="assistant"]');
                const id=agent.getAttribute('data-message-id')
                  ||agent.getAttribute('data-message-uuid')
                  ||nested?.getAttribute('data-message-id')
                  ||nested?.getAttribute('data-message-uuid')
                  ||agent.closest('[data-message-id]')?.getAttribute('data-message-id')
                  ||agent.closest('[data-message-uuid]')?.getAttribute('data-message-uuid')
                  ||'';
                if(id.startsWith('request-placeholder-'))continue;
                let existing=id?entries.findIndex(message=>message.role==='assistant'&&message.id===id):-1;
                if(existing<0&&nested){
                  existing=entries.findIndex(message=>message.node===nested);
                }
                if(existing<0){
                  existing=entries.findIndex(message=>message.role==='assistant'&&message.content&&(
                    content.startsWith(message.content)||message.content.startsWith(content)
                  ));
                }
                if(existing>=0){
                  if(content.length>=entries[existing].content.length)entries[existing].content=content;
                  if(id&&!entries[existing].id)entries[existing].id=id;
                  continue;
                }
                const precedingUser=roleNodes
                  .filter(node=>node.getAttribute('data-message-author-role')==='user'
                    &&Boolean(node.compareDocumentPosition(agent)&Node.DOCUMENT_POSITION_FOLLOWING))
                  .at(-1);
                const turnSeed=precedingUser?.getAttribute('data-message-id')
                  ||precedingUser?.getAttribute('data-message-uuid')
                  ||normalise(messageText(precedingUser))
                  ||('agent-'+agentIndex);
                entries.push({
                  node:agent,
                  id:id||('__prompta_live_assistant_'+hash(turnSeed)+'__'),
                  role:'assistant',
                  content
                });
              }
              entries.sort((left,right)=>{
                if(left.node===right.node)return 0;
                return left.node.compareDocumentPosition(right.node)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1;
              });
              const messages=entries.map((message,index)=>({
                id:message.id,
                role:message.role,
                content:message.content,
                ordinal:index
              }));
              const stop=[...document.querySelectorAll('button[data-testid="stop-button"],button[aria-label="Stop answering"],button[aria-label="Stop generating"]')].some(visible);
              const streamActive=[...document.querySelectorAll('[data-streaming="active"],[data-is-streaming="true"]')].some(visible);
              return {
                path:location.pathname,
                title:document.title||'',
                messages,
                streaming:stop||streamActive
              };
            })())""",
            context=context,
        )
        return json.loads(raw or "{}")

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


async def wait_for_port(port: int, timeout: float = 20.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            del reader
            return
        except OSError:
            await asyncio.sleep(0.25)
    raise RuntimeError(f"Firefox BiDi port {port} did not open")
