"""Shared browser-independent helpers for Prompta browser automation."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from .chatgpt_dom import (
    MESSAGE_DISCOVERY_SCRIPT,
    STOP_BUTTON_SELECTORS,
    STREAMING_SELECTOR,
)
from .conversation_snapshot import CONVERSATION_SNAPSHOT_SCRIPT, parse_conversation_snapshot
from .react_fallback import REACT_FALLBACK_ADAPTER_SCRIPT


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
        raise NotImplementedError

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
                const text=parts.length?parts.join(String.fromCharCode(10)):String(content?.text||'');
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

    async def conversation_activity(self, context: str) -> dict[str, Any]:
        script = r"""JSON.stringify((()=>{
__MESSAGE_DISCOVERY__
__REACT_FALLBACK_ADAPTER__
          const stopSelector=__STOP_SELECTOR__;
          const streamingSelector=__STREAMING_SELECTOR__;
          const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
          const stop=[...document.querySelectorAll(stopSelector)].some(visible);
          const streamActive=[...document.querySelectorAll(streamingSelector)].some(visible);
          const assistant=authorNodes('assistant').at(-1)||null;
          const semanticTurns=[...document.querySelectorAll(semanticTurnSelector)].filter(visible);
          const legacyTurns=[...document.querySelectorAll(legacyTurnSelector)].filter(visible);
          const turn=turnRoot(assistant)||semanticTurns.at(-1)||legacyTurns.at(-1)||null;
          const visibleMessageId=messageId(assistant)||turnMessageId(turn,'assistant');
          let activityReactFallback=null;
          const reactTurnEnd=()=>{
            const root=turn||document.querySelector('main')||document.body;
            if(!root)return null;
            activityReactFallback=reactFallback.inspect(root,{
              allow:true,
              reason:'activity-end-state',
              maxDepth:7,
              maxKeys:260
            });
            const found=activityReactFallback.messages;
            const assistantMessages=found.filter(message=>String(message?.author?.role||message?.role||'')==='assistant');
            const target=visibleMessageId
              ?assistantMessages.filter(message=>String(message?.id||'')===visibleMessageId)
              :assistantMessages.slice(-8);
            const states=target.map(message=>message?.end_turn).filter(value=>typeof value==='boolean');
            if(states.includes(true))return true;
            if(states.includes(false))return false;
            return null;
          };
          const turnText=(turn?.innerText||turn?.textContent||'').trim();
          const transientText=/(?:Connection interrupted|Waiting for the complete answer|A network error occurred\.?\s*Please check your connection and try again\.?\s*If this issue persists please contact us through our help center at help\.openai\.com\.?)/i.test(turnText);
          const deliveryFailed=/Message delivery timed out\.?\s*Please try again/i.test(turnText);
          const finalAction=Boolean(turn&&[...turn.querySelectorAll('button')].some(button=>{
            const testId=(button.getAttribute('data-testid')||'').trim();
            const label=(button.getAttribute('aria-label')||button.getAttribute('title')||button.textContent||'').trim();
            return testId==='copy-turn-action-button'||/^Copy(?: response)?$/i.test(label);
          }));
          const needsReactEndState=Boolean(turn&&!stop&&!streamActive&&!finalAction);
          const turnEnded=needsReactEndState?reactTurnEnd():null;
          const streaming=stop||streamActive||turnEnded===false;
          const complete=!streaming&&(turnEnded===true||(turnEnded===null&&finalAction));
          const transient=transientText&&!complete;
          const failed=deliveryFailed&&!complete&&!streaming;
          return {
            streaming,complete,transient,failed,turn_ended:turnEnded,
            react_fallback:activityReactFallback
          };
        })())"""
        script = script.replace("__MESSAGE_DISCOVERY__", MESSAGE_DISCOVERY_SCRIPT)
        script = script.replace("__REACT_FALLBACK_ADAPTER__", REACT_FALLBACK_ADAPTER_SCRIPT)
        script = script.replace("__STOP_SELECTOR__", json.dumps(",".join(STOP_BUTTON_SELECTORS)))
        script = script.replace("__STREAMING_SELECTOR__", json.dumps(STREAMING_SELECTOR))
        raw = await self.eval(script, context=context)
        return json.loads(raw or "{}")

    async def conversation_snapshot(self, context: str) -> dict[str, Any]:
        raw = await self.eval(CONVERSATION_SNAPSHOT_SCRIPT, context=context)
        return parse_conversation_snapshot(raw)


# Compatibility alias for older imports; there is no WebDriver transport.
WebDriverBase = BrowserDriverBase
