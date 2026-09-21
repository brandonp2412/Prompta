"""Read-only Chromium/CDP enrichment for structured ChatGPT tool calls."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

import websockets

logger = logging.getLogger(__name__)

_DEFAULT_CDP_URL = "http://127.0.0.1:9222"
_FENCE = chr(96) * 3
_TOOL_BLOCK_RE = re.compile(
    r"^ {0,3}"
    + re.escape(_FENCE)
    + r"(?:tool|tool-call|function|function-call)(?::[^\n\x60]*)?\r?\n"
    + r"[\s\S]*?^ {0,3}"
    + re.escape(_FENCE)
    + r"[ \t]*\r?$",
    re.IGNORECASE | re.MULTILINE,
)
_REACT_TOOL_SCRIPT = r"""
(()=>{
  const assistants=[...document.querySelectorAll('[data-message-author-role="assistant"]')];
  const latestAssistant=assistants.at(-1);
  const root=latestAssistant?.closest('[data-testid^="conversation-turn-"]')
    ||latestAssistant?.closest('.agent-turn')
    ||document.querySelector('main')
    ||document.body;
  if(!root)return {ready:false,messages:[]};
  const found=[],seenObjects=new WeakSet(),seenArrays=new WeakSet();
  const add=messages=>{
    if(!Array.isArray(messages)||seenArrays.has(messages))return;
    seenArrays.add(messages);
    if(messages.some(message=>message&&typeof message==='object'&&message.content&&message.author)){
      found.push(...messages);
    }
  };
  const walk=(value,depth)=>{
    if(!value||depth>7||(typeof value!=='object'&&typeof value!=='function'))return;
    if(seenObjects.has(value))return;
    seenObjects.add(value);
    if(Array.isArray(value)){if(depth<=5)add(value);return;}
    let keys=[];
    try{keys=Object.keys(value);}catch{return;}
    for(const key of keys.slice(0,240)){
      if(['ref','_owner','return','child','sibling','stateNode','alternate'].includes(key))continue;
      let next;
      try{next=value[key];}catch{continue;}
      if(key==='messages')add(next);
      if(next&&depth<7&&(typeof next==='object'||typeof next==='function'))walk(next,depth+1);
    }
  };
  for(const node of [root,...root.querySelectorAll('*')]){
    const key=Object.keys(node).find(name=>name.startsWith('__reactProps$'));
    if(key)walk(node[key],0);
  }
  const seen=new Set(),messages=[];
  const trimString=value=>typeof value==='string'?value.slice(0,20000):value;
  for(const message of found){
    const id=String(message?.id||'');
    const dedupe=id||JSON.stringify([
      message?.author?.role,
      message?.recipient,
      message?.content?.content_type,
      message?.content?.text||''
    ]);
    if(seen.has(dedupe))continue;
    seen.add(dedupe);
    const metadata=message?.metadata||{};
    const invoked=metadata?.invoked_resource||null;
    const connectorName=metadata?.jit_plugin_data?.from_server?.body?.connector_name||null;
    const content=message?.content||{};
    messages.push({
      id,
      role:String(message?.author?.role||message?.role||''),
      recipient:String(message?.recipient||''),
      content_type:String(content?.content_type||content?.type||''),
      text:trimString(content?.text||''),
      parts:Array.isArray(content?.parts)
        ?content.parts.slice(0,8).map(part=>trimString(part))
        :[],
      connector_tool_payload:trimString(metadata?.connector_tool_payload||''),
      invoked_resource:invoked?{
        app_name:trimString(invoked?.app_name||''),
        resource_uri:trimString(invoked?.resource_uri||'')
      }:null,
      connector_name:trimString(connectorName||'')
    });
  }
  return {
    ready:Boolean(document.querySelector('[data-message-author-role]')),
    href:location.href,
    title:document.title||'',
    messages
  };
})()
"""


def _json_load(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _action_from_path(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    parts = [part for part in value.split("/") if part]
    return parts[-1] if parts else ""


def _connector_from_path(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    parts = [part for part in value.split("/") if part]
    if not parts:
        return ""
    first = parts[0]
    if first.startswith(("asdk_app_", "plugin_", "link_")):
        return ""
    return first


def _bounded(value: Any, limit: int = 6000) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        encoded = str(value)
    if len(encoded) <= limit:
        return value
    return encoded[: limit - 1] + "…"


def _result_value(message: dict[str, Any]) -> Any:
    text = message.get("text")
    parsed = _json_load(text)
    if isinstance(parsed, dict) and set(parsed) == {"text"}:
        nested = _json_load(parsed.get("text"))
        return nested if nested is not None else parsed.get("text")
    if parsed is not None:
        return parsed
    parts = message.get("parts")
    if isinstance(parts, list) and parts:
        first = parts[0]
        if isinstance(first, str):
            nested = _json_load(first)
            return nested if nested is not None else first
        return first
    if isinstance(text, str) and text.strip():
        return text
    return None


def tool_blocks_from_messages(messages: list[dict[str, Any]]) -> list[str]:
    """Convert sanitized ChatGPT React messages into Prompta tool fences."""

    calls: list[dict[str, Any]] = []
    completed_wrapper_count = 0
    connector_hint = ""

    for raw in messages:
        if not isinstance(raw, dict):
            continue
        connector_name = str(raw.get("connector_name") or "").strip()
        if connector_name:
            connector_hint = connector_name

        text = str(raw.get("text") or "")
        parsed = _json_load(text)
        if isinstance(parsed, dict) and (
            parsed.get("type") == "mcpToolCall" or parsed.get("appContext")
        ):
            app_context = parsed.get("appContext")
            if not isinstance(app_context, dict):
                app_context = {}
            tool_name = str(parsed.get("tool") or "")
            action = str(app_context.get("actionName") or "")
            if not action and tool_name:
                action = tool_name.rsplit(".", 1)[-1]
            invoked = raw.get("invoked_resource")
            if not isinstance(invoked, dict):
                invoked = {}
            connector = str(
                app_context.get("appName")
                or invoked.get("app_name")
                or connector_hint
            ).strip()
            calls.append(
                {
                    "connector": connector,
                    "action": action,
                    "arguments": parsed.get("arguments"),
                    "status": str(parsed.get("status") or "completed"),
                    "duration_ms": parsed.get("durationMs"),
                    "error": parsed.get("error"),
                    "result": parsed.get("result"),
                }
            )
            completed_wrapper_count += 1

    if completed_wrapper_count:
        return [_format_tool_block(call) for call in calls]

    invocations: list[dict[str, Any]] = []
    pending: list[int] = []
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        connector_name = str(raw.get("connector_name") or "").strip()
        if connector_name:
            connector_hint = connector_name

        recipient = str(raw.get("recipient") or "")
        text = str(raw.get("text") or "")
        if recipient == "api_tool.call_tool":
            parsed = _json_load(text)
            if not isinstance(parsed, dict):
                parsed = {}
            payload = _json_load(raw.get("connector_tool_payload"))
            path = parsed.get("path")
            args = parsed.get("args")
            if args is None and isinstance(payload, dict):
                if "args" in payload:
                    args = payload.get("args")
                elif "path" not in payload:
                    args = payload
            invocations.append(
                {
                    "connector": _connector_from_path(path) or connector_hint,
                    "action": _action_from_path(path),
                    "arguments": args,
                    "status": "running",
                    "duration_ms": None,
                    "error": None,
                    "result": None,
                    "path": path,
                }
            )
            pending.append(len(invocations) - 1)
            continue

        if str(raw.get("role") or "") != "tool":
            continue
        invoked = raw.get("invoked_resource")
        if not isinstance(invoked, dict):
            invoked = {}
        resource_uri = invoked.get("resource_uri")
        action = _action_from_path(resource_uri)
        connector = str(invoked.get("app_name") or connector_hint).strip()
        match_index: int | None = None
        for index in reversed(pending):
            candidate = invocations[index]
            if not action or not candidate.get("action") or candidate.get("action") == action:
                match_index = index
                break
        if match_index is None:
            continue
        pending.remove(match_index)
        call = invocations[match_index]
        if connector:
            call["connector"] = connector
        if action:
            call["action"] = action
        call["status"] = "completed"
        result = _result_value(raw)
        if result is not None:
            call["result"] = result

    return [_format_tool_block(call) for call in invocations]


def _format_tool_block(call: dict[str, Any]) -> str:
    connector = str(call.get("connector") or "").strip()
    action = str(call.get("action") or "").strip()
    label = " · ".join(part for part in (connector, action) if part) or "tool"
    detail: dict[str, Any] = {}
    if call.get("arguments") is not None:
        detail["arguments"] = _bounded(call["arguments"], 12000)
    status = str(call.get("status") or "").strip()
    if status:
        detail["status"] = status
    duration = call.get("duration_ms")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
        detail["duration_ms"] = duration
    if call.get("error"):
        detail["error"] = _bounded(call["error"])
    if call.get("result") is not None:
        detail["result"] = _bounded(call["result"])
    body = json.dumps(detail, indent=2, ensure_ascii=False) if detail else "Called tool"
    return _FENCE + "tool:" + label + chr(10) + body + chr(10) + _FENCE


def merge_tool_blocks(content: str, blocks: list[str]) -> str:
    if not blocks:
        return content
    source = str(content or "")
    matches = list(_TOOL_BLOCK_RE.finditer(source))
    if not matches:
        return (chr(10) * 2).join(part for part in [source.strip(), *blocks] if part).strip()

    parts: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        parts.append(source[cursor : match.start()])
        parts.append(blocks[index] if index < len(blocks) else match.group(0))
        cursor = match.end()
    parts.append(source[cursor:])
    merged = "".join(parts).strip()
    if len(blocks) > len(matches):
        merged = (chr(10) * 2).join([merged, *blocks[len(matches) :]]).strip()
    return merged


class ChromiumToolEnricher:
    """Use an authenticated local Chromium CDP endpoint for read-only enrichment."""

    def __init__(self, endpoint: str | None = None, *, timeout_seconds: float = 8.0) -> None:
        self.endpoint = (
            endpoint or os.getenv("PROMPTA_CHROMIUM_CDP_URL") or _DEFAULT_CDP_URL
        ).rstrip("/")
        self.timeout_seconds = max(1.0, timeout_seconds)

    async def tool_blocks(self, url: str) -> list[str]:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname != "chatgpt.com":
            return []
        created_target = False
        target: dict[str, Any] | None = None
        try:
            targets = await asyncio.to_thread(self._http_json, "/json/list")
            if isinstance(targets, list):
                target = next(
                    (
                        item
                        for item in targets
                        if isinstance(item, dict)
                        and item.get("type") == "page"
                        and str(item.get("url") or "").rstrip("/") == url.rstrip("/")
                    ),
                    None,
                )
            if target is None:
                target = await asyncio.to_thread(
                    self._http_json,
                    f"/json/new?{quote(url, safe='')}",
                    "PUT",
                )
                created_target = True
            if not isinstance(target, dict):
                return []
            websocket_url = str(target.get("webSocketDebuggerUrl") or "")
            if not websocket_url:
                return []
            messages = await self._react_messages(websocket_url)
            return tool_blocks_from_messages(messages)
        except Exception as exc:
            logger.debug("Chromium tool enrichment unavailable for %s: %s", url, exc)
            return []
        finally:
            if created_target and isinstance(target, dict) and target.get("id"):
                try:
                    await asyncio.to_thread(
                        self._http_json,
                        f"/json/close/{target['id']}",
                    )
                except Exception:
                    logger.debug("Could not close Chromium enrichment tab", exc_info=True)

    def _http_json(self, path: str, method: str = "GET") -> Any:
        request = Request(f"{self.endpoint}{path}", method=method)
        with urlopen(request, timeout=min(3.0, self.timeout_seconds)) as response:
            payload = response.read()
        return json.loads(payload) if payload else {}

    async def _react_messages(self, websocket_url: str) -> list[dict[str, Any]]:
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        async with websockets.connect(
            websocket_url,
            max_size=16 * 1024 * 1024,
            ping_interval=None,
            open_timeout=min(3.0, self.timeout_seconds),
        ) as websocket:
            request_id = 0

            async def call(
                method: str,
                params: dict[str, Any] | None = None,
            ) -> dict[str, Any]:
                nonlocal request_id
                request_id += 1
                current_id = request_id
                await websocket.send(
                    json.dumps(
                        {"id": current_id, "method": method, "params": params or {}}
                    )
                )
                while True:
                    remaining = max(
                        0.1,
                        deadline - asyncio.get_running_loop().time(),
                    )
                    message = json.loads(
                        await asyncio.wait_for(websocket.recv(), timeout=remaining)
                    )
                    if message.get("id") == current_id:
                        return message

            await call("Runtime.enable")
            latest: list[dict[str, Any]] = []
            while asyncio.get_running_loop().time() < deadline:
                response = await call(
                    "Runtime.evaluate",
                    {"expression": _REACT_TOOL_SCRIPT, "returnByValue": True},
                )
                value = response.get("result", {}).get("result", {}).get("value", {})
                if isinstance(value, dict):
                    messages = value.get("messages")
                    if isinstance(messages, list):
                        latest = [item for item in messages if isinstance(item, dict)]
                    if value.get("ready") and latest:
                        blocks = tool_blocks_from_messages(latest)
                        if blocks and not any(
                            '"status": "running"' in block for block in blocks
                        ):
                            return latest
                await asyncio.sleep(0.35)
            return latest
