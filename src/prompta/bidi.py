"""Small Firefox WebDriver BiDi client containing only what Prompta needs."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urlsplit

import websockets
from websockets.exceptions import ConnectionClosed

_SEND_ENDPOINTS = ("/backend-api/f/conversation", "/backend-api/conversation")
_SEND_SELECTORS = (
    'button[aria-label*="Send" i]:not([data-testid="stop-button"])',
    'button[data-testid="send-button"]',
    'button[data-testid*="send" i]:not([data-testid="stop-button"])',
)


class FirefoxBiDiDriver:
    def __init__(self, url: str) -> None:
        self.url = url
        self.ws: Any = None
        self.context = ""
        self.request_id = 0
        self._network_subscribed = False
        self._send_capture: dict[str, Any] | None = None

    @property
    def is_connected(self) -> bool:
        return (
            self.ws is not None
            and bool(self.context)
            and getattr(self.ws, "close_code", None) is None
        )

    async def connect(self) -> None:
        if self.is_connected:
            return
        self.ws = await websockets.connect(
            self.url,
            max_size=16 * 1024 * 1024,
            ping_interval=None,
        )
        response = await self._call("session.new", {"capabilities": {}})
        if response.get("type") != "success":
            raise RuntimeError(f"Firefox BiDi session failed: {response}")
        tree = await self._call("browsingContext.getTree", {})
        contexts = tree.get("result", {}).get("contexts") or []
        if not contexts:
            raise RuntimeError("Firefox BiDi has no browsing context")
        self.context = str(contexts[0]["context"])
        await self._call(
            "session.subscribe",
            {
                "events": [
                    "network.beforeRequestSent",
                    "network.responseStarted",
                    "network.responseCompleted",
                    "network.fetchError",
                ],
                "contexts": [self.context],
            },
        )
        self._network_subscribed = True
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
        try:
            await self.ws.send(json.dumps({"id": request_id, "method": method, "params": params}))
            while True:
                message = json.loads(await self.ws.recv())
                if message.get("id") != request_id:
                    self._handle_bidi_event(message)
                    continue
                if message.get("type") == "error":
                    raise RuntimeError(
                        f"{method}: {message.get('error')}: {message.get('message')}"
                    )
                return message
        except ConnectionClosed:
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
              const probe={message_id:'',parent_message_id:'',response_status:0,committed:false,stream_error:''};
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

    async def eval(self, expression: str, *, await_promise: bool = False) -> Any:
        response = await self._call(
            "script.evaluate",
            {
                "expression": expression,
                "target": {"context": self.context},
                "awaitPromise": await_promise,
            },
        )
        result = response["result"]["result"]
        if result.get("type") == "exception":
            raise RuntimeError(str(result))
        return result.get("value")

    async def navigate(self, url: str) -> None:
        await self._call(
            "browsingContext.navigate",
            {"context": self.context, "url": url, "wait": "complete"},
        )

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
            "'#prompt-textarea,div[role=\\\"textbox\\\"].ProseMirror,textarea#prompt-textarea'"
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
            "'#prompt-textarea,div[role=\\\"textbox\\\"].ProseMirror,textarea#prompt-textarea'"
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

    async def type_message(self, text: str) -> None:
        await self.wait_for_composer()
        await self._focus_composer()
        await self.eval(
            f"""(()=>{{
              const selector='#prompt-textarea,div[role="textbox"].ProseMirror,textarea#prompt-textarea';
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
              const selector='#prompt-textarea,div[role="textbox"].ProseMirror,textarea#prompt-textarea';
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
        selectors = ",".join(_SEND_SELECTORS)
        deadline = asyncio.get_running_loop().time() + 10.0
        while asyncio.get_running_loop().time() < deadline:
            clicked = await self.eval(
                "(()=>{"
                f"const buttons=[...document.querySelectorAll({json.dumps(selectors)})];"
                "const b=buttons.find(e=>!e.disabled&&e.getClientRects().length>0);"
                "if(!b)return false;b.click();return true;})()"
            )
            if clicked:
                return
            await asyncio.sleep(0.25)
        await self._focus_composer()
        await self._key_text("", enter=True)

    async def dom_state(self) -> dict[str, Any]:
        raw = await self.eval(
            """JSON.stringify((()=>{
              const selector='#prompt-textarea,div[role="textbox"].ProseMirror,textarea#prompt-textarea';
              const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
              const composer=[...document.querySelectorAll(selector)].find(visible);
              const messages=[...document.querySelectorAll('[data-message-author-role]')];
              const users=messages.filter(e=>e.getAttribute('data-message-author-role')==='user');
              const rateLimitText=[...document.querySelectorAll('[role="alert"],[aria-live="assertive"],[aria-live="polite"],[data-testid="conversation-fetch-error-toaster"],[data-testid*="rate-limit"]')]
                .filter(visible).map(e=>e.innerText||'').filter(Boolean).join('\\n');
              return {
                composer_text:(composer&&(composer.innerText||composer.value)||''),
                last_user_id:(users.at(-1)?.getAttribute('data-message-id')||''),
                last_user_text:(users.at(-1)?.innerText||''),
                rate_limit_text:rateLimitText
              };
            })())"""
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
