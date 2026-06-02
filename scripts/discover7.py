"""Autonomous Discovery v2 — uses BrowserFetch scratch-frame pattern.

Creates an about:blank target via CDP, routes all HTTP through it.
The browser's TLS stack + cookies handle auth and fingerprinting.

Usage:
    python scripts/discover7.py --cdp-port 9222

Prerequisite: Chrome with --remote-debugging-port=9222, ChatGPT logged in
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import sys
import time
import uuid
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("discover7")

try:
    import websockets
except ImportError:
    logger.error("pip install websockets")
    sys.exit(1)

import urllib.request


class BrowserFetchCDP:
    """Minimal BrowserFetch over raw CDP websockets.

    Creates an about:blank scratch frame, routes HTTP through it
    via Runtime.callFunctionOn with fetch().
    """

    def __init__(self, cdp_port: int):
        self.port = cdp_port
        self.ws = None
        self.msg_id = 0
        self.scratch_target_id = None
        self.scratch_session_id = None

    async def connect(self):
        """Connect to browser-level CDP and create scratch frame."""
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/version")
        with urllib.request.urlopen(req) as resp:
            info = json.loads(resp.read())
        ws_url = info["webSocketDebuggerUrl"]
        logger.info("Connecting to browser CDP: %s", ws_url[:60])
        self.ws = await websockets.connect(ws_url, max_size=100 * 1024 * 1024)

        # Create about:blank scratch target
        result = await self._send("Target.createTarget", {"url": "about:blank"})
        self.scratch_target_id = result["targetId"]
        logger.info("Created scratch target: %s", self.scratch_target_id[:20])

        # Attach to it
        result = await self._send("Target.attachToTarget", {
            "targetId": self.scratch_target_id, "flatten": True
        })
        self.scratch_session_id = result["sessionId"]
        logger.info("Attached to scratch frame")

        # Navigate to chatgpt.com so we get cookies
        await self._send("Page.navigate", {"url": "https://chatgpt.com"}, session=True)
        await asyncio.sleep(3)  # Wait for page load + cookies

    async def _send(self, method: str, params: dict = None, session: bool = False) -> dict:
        """Send CDP command and wait for response."""
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method, "params": params or {}}
        if session and self.scratch_session_id:
            msg["sessionId"] = self.scratch_session_id

        await self.ws.send(json.dumps(msg))

        # Read until we get our response
        while True:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=30)
            resp = json.loads(raw)
            if resp.get("id") == self.msg_id:
                if "error" in resp:
                    raise RuntimeError(f"CDP error: {resp['error']}")
                return resp.get("result", {})

    async def fetch(self, url: str, init: dict = None) -> dict:
        """Fetch URL through the scratch frame's fetch() API.

        Returns {status, ok, body, headers}.
        """
        # Get document objectId
        doc = await self._send("DOM.getDocument", {"depth": 0}, session=True)
        node_id = doc["root"]["nodeId"]
        resolved = await self._send("DOM.resolveNode", {"nodeId": node_id}, session=True)
        object_id = resolved["object"]["objectId"]

        if init is None:
            init = {}

        init_json = json.dumps(init).replace("</", "<\\/")

        fn_decl = (
            "async function(urlArg, initJson) {"
            "  try {"
            "    const init = JSON.parse(initJson);"
            "    const r = await fetch(urlArg, init);"
            "    const buf = await r.arrayBuffer();"
            "    let b64 = '';"
            "    const view = new Uint8Array(buf);"
            "    const CHUNK = 0x8000;"
            "    for (let i = 0; i < view.length; i += CHUNK) {"
            "      let s = '';"
            "      const end = Math.min(i + CHUNK, view.length);"
            "      for (let j = i; j < end; j++) s += String.fromCharCode(view[j]);"
            "      b64 += btoa(s);"
            "    }"
            "    const headers = {};"
            "    r.headers.forEach((v, k) => { headers[k] = v; });"
            "    return { status: r.status, headers, bodyB64: b64 };"
            "  } catch(e) {"
            "    return { status: 0, error: e.message, headers: {}, bodyB64: '' };"
            "  }"
            "}"
        )

        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": "Runtime.callFunctionOn",
            "params": {
                "functionDeclaration": fn_decl,
                "objectId": object_id,
                "arguments": [{"value": url}, {"value": init_json}],
                "returnByValue": True,
                "awaitPromise": True,
            },
            "sessionId": self.scratch_session_id,
        }
        await self.ws.send(json.dumps(msg))

        while True:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=60)
            resp = json.loads(raw)
            if resp.get("id") == self.msg_id:
                result = resp.get("result", {})
                exception = result.get("exceptionDetails")
                if exception:
                    desc = exception.get("exception", {}).get("description", str(exception))
                    return {"status": 0, "ok": False, "error": desc, "body": ""}

                val = result.get("result", {}).get("value", {})
                if not val:
                    return {"status": 0, "ok": False, "error": "no value", "body": ""}

                status = val.get("status", 0)
                body_b64 = val.get("bodyB64", "")
                body = base64.b64decode(body_b64).decode("utf-8", errors="replace") if body_b64 else ""
                return {
                    "status": status,
                    "ok": 200 <= status < 400,
                    "body": body,
                    "headers": val.get("headers", {}),
                }

    async def get(self, path: str) -> dict:
        return await self.fetch(f"https://chatgpt.com{path}")

    async def post(self, path: str, body: dict, token: str = "") -> dict:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return await self.fetch(f"https://chatgpt.com{path}", {
            "method": "POST",
            "headers": headers,
            "body": json.dumps(body),
        })

    async def close(self):
        if self.scratch_target_id and self.ws:
            try:
                await self._send("Target.closeTarget", {"targetId": self.scratch_target_id})
            except:
                pass
        if self.ws:
            await self.ws.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp-port", type=int, required=True)
    parser.add_argument("--output", default="captured_v2.json")
    args = parser.parse_args()

    bf = BrowserFetchCDP(args.cdp_port)
    results = {}

    try:
        await bf.connect()

        print("\n" + "=" * 70)
        print("DISCOVERY v2 (BrowserFetch scratch-frame pattern)")
        print("=" * 70)

        # 0. Auth
        logger.info("=== Getting access token ===")
        auth = await bf.get("/api/auth/session")
        results["auth_session_raw"] = auth
        token = ""
        if auth.get("ok"):
            sess = json.loads(auth["body"])
            token = sess.get("accessToken", "")
            user = sess.get("user", {})
            logger.info("  Token: %d chars, User: %s", len(token), user.get("name"))

        # 1. Models
        logger.info("=== Models ===")
        models = await bf.get("/backend-api/models?iim=false&is_gizmo=false")
        results["models"] = models
        if models.get("ok"):
            slugs = [m["slug"] for m in json.loads(models["body"]).get("models", [])]
            logger.info("  %s", slugs)

        # 2. Account
        logger.info("=== Account ===")
        acct = await bf.get("/backend-api/accounts/check/v4-2023-04-27?timezone_offset_min=-180")
        results["account"] = acct

        # 3. Me
        logger.info("=== Me ===")
        me = await bf.get("/backend-api/me")
        results["me"] = me

        # 4. Settings
        logger.info("=== Settings ===")
        settings = await bf.get("/backend-api/settings/user")
        results["settings"] = settings

        # 5. Conversations
        logger.info("=== Conversations ===")
        convs = await bf.get("/backend-api/conversations?offset=0&limit=5&order=updated")
        results["conversations"] = convs

        # 6. Gizmos
        logger.info("=== Gizmos ===")
        gizmos = await bf.get("/backend-api/gizmos/snorlax/sidebar?owned_only=true&conversations_per_gizmo=5&limit=20")
        results["gizmos_sidebar"] = gizmos

        # 7. Sentinel prepare
        logger.info("=== Sentinel prepare ===")
        sentinel = await bf.post("/backend-api/sentinel/chat-requirements/prepare", {}, token)
        results["sentinel_prepare"] = sentinel
        if sentinel.get("ok"):
            sp = json.loads(sentinel["body"])
            logger.info("  persona=%s turnstile=%s pow=%s so=%s",
                        sp.get("persona"),
                        sp.get("turnstile", {}).get("required"),
                        sp.get("proofofwork", {}).get("required"),
                        sp.get("so", {}).get("required"))

        # 8. Chat message attempt
        logger.info("=== Normal chat message ===")
        chat = await bf.post("/backend-api/f/conversation", {
            "action": "next",
            "messages": [{
                "id": str(uuid.uuid4()),
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": ["Hello, what model are you?"]},
            }],
            "conversation_id": str(uuid.uuid4()),
            "parent_message_id": str(uuid.uuid4()),
            "model": "auto",
            "timezone_offset_min": -180,
            "conversation_mode": {"kind": "primary_assistant"},
        }, token)
        results["normal_chat"] = chat
        status = chat.get("status", 0)
        logger.info("  Status: %s", status)
        if status == 200:
            logger.info("  SUCCESS! Body: %s", chat.get("body", "")[:300])
        else:
            logger.info("  Body: %s", chat.get("body", "")[:200])

        # 9. Memories
        logger.info("=== Memories ===")
        mem = await bf.get("/backend-api/memories?exclusive_to_gizmo=false")
        results["memories"] = mem

        # 10. Tasks
        logger.info("=== Tasks ===")
        tasks = await bf.get("/backend-api/tasks")
        results["tasks"] = tasks

    except Exception as e:
        logger.error("Fatal: %s", e, exc_info=True)
    finally:
        # Summary
        print("\n" + "=" * 70)
        print("RESULTS")
        ok = sum(1 for v in results.values() if isinstance(v, dict) and v.get("ok"))
        print(f"  {ok}/{len(results)} successful\n")
        for name, d in sorted(results.items()):
            if not isinstance(d, dict):
                continue
            s = d.get("status", "?")
            bl = len(d.get("body", ""))
            m = "OK" if d.get("ok") else "FAIL"
            print(f"  [{m:>4}] HTTP {s:>3}  {name:30s} ({bl:>7} bytes)")

        await save_results(bf, args.output, results)
        await bf.close()


async def save_results(bf, path, results):
    Path(path).write_text(json.dumps(results, indent=2, default=str))
    logger.info("\nSaved to %s", path)


if __name__ == "__main__":
    asyncio.run(main())
