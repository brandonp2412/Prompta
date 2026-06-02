"""Sentinel Flow Capture — intercept the full sentinel solve from the real ChatGPT page.

Strategy:
1. Connect to ChatGPT page via CDP
2. Enable Network monitoring
3. Monkey-patch fetch() to log sentinel/conversation requests
4. Navigate to new chat
5. Type + send a message via CDP
6. Capture the full sentinel flow (prepare → solve → finalize → message)

Usage:
    python scripts/capture_sentinel.py --cdp-port 9222
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("capture_sentinel")

try:
    import websockets
except ImportError:
    logger.error("pip install websockets")
    sys.exit(1)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp-port", type=int, required=True)
    args = parser.parse_args()

    req = urllib.request.Request(f"http://127.0.0.1:{args.cdp_port}/json/list")
    with urllib.request.urlopen(req) as resp:
        targets = json.loads(resp.read())
    page = [t for t in targets if "chatgpt.com" in t.get("url", "")]
    if not page:
        logger.error("No ChatGPT tab found")
        return
    page = page[0]
    ws = await websockets.connect(page["webSocketDebuggerUrl"], max_size=100 * 1024 * 1024)
    logger.info("Connected to: %s", page.get("title", "")[:60])

    msg_id = 0

    async def cdp(method, params=None, timeout=15):
        nonlocal msg_id
        msg_id += 1
        await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            resp = json.loads(raw)
            if resp.get("id") == msg_id:
                return resp

    async def js(expr, timeout=15):
        resp = await cdp("Runtime.evaluate", {
            "expression": expr, "awaitPromise": True, "returnByValue": True,
            "timeout": int(timeout * 1000)
        }, timeout=timeout)
        return resp.get("result", {}).get("result", {}).get("value")

    # Step 1: Navigate to new chat
    logger.info("Navigating to new chat...")
    await cdp("Page.navigate", {"url": "https://chatgpt.com/"})
    await asyncio.sleep(4)

    # Step 2: Monkey-patch fetch() to capture sentinel traffic
    logger.info("Patching fetch() to intercept sentinel flow...")
    patch_result = await js('''
    (async () => {
        if (window._sentinelCapture) return 'already patched';
        window._sentinelCapture = [];
        const origFetch = window.fetch;
        window.fetch = async function(...args) {
            const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
            const init = args[1] || {};
            const method = init.method || 'GET';
            
            // Capture sentinel + conversation requests
            const interesting = url.includes('sentinel') || url.includes('/f/conversation') || url.includes('/conversation/init');
            if (interesting) {
                let bodyStr = '';
                if (init.body) {
                    bodyStr = typeof init.body === 'string' ? init.body : JSON.stringify(init.body);
                }
                
                // Also capture headers
                const headers = {};
                if (init.headers) {
                    if (init.headers instanceof Headers) {
                        init.headers.forEach((v, k) => { headers[k] = v; });
                    } else if (typeof init.headers === 'object') {
                        for (const [k, v] of Object.entries(init.headers)) {
                            headers[k] = v;
                        }
                    }
                }
                
                const entry = {
                    url: url,
                    method: method,
                    headers: headers,
                    body: bodyStr.substring(0, 10000),
                    timestamp: Date.now(),
                    phase: 'request'
                };
                
                try {
                    const response = await origFetch.apply(this, args);
                    const clone = response.clone();
                    const respText = await clone.text();
                    entry.response_status = response.status;
                    entry.response_body = respText.substring(0, 50000);
                    entry.phase = 'complete';
                    window._sentinelCapture.push(entry);
                    return response;
                } catch(e) {
                    entry.error = e.message;
                    window._sentinelCapture.push(entry);
                    throw e;
                }
            }
            
            return origFetch.apply(this, args);
        };
        return 'patched';
    })()
    ''')
    logger.info("  Patch result: %s", patch_result)

    # Step 3: Find and fill the input
    logger.info("Finding input element...")
    input_result = await js('''
    (async () => {
        // Try multiple selectors for the input
        const selectors = [
            '#prompt-textarea',
            '[contenteditable="true"]',
            'textarea',
            'div.ProseMirror',
            '[data-placeholder]'
        ];
        
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
                el.focus();
                // Set the text
                if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                    el.value = 'Hello, what model are you? Reply briefly.';
                } else {
                    el.textContent = 'Hello, what model are you? Reply briefly.';
                    el.innerText = 'Hello, what model are you? Reply briefly.';
                }
                // Dispatch input event
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new InputEvent('beforeinput', {bubbles: true, inputType: 'insertText', data: 'Hello, what model are you? Reply briefly.'}));
                
                return 'filled: ' + sel + ' tag=' + el.tagName;
            }
        }
        return 'no input found';
    })()
    ''')
    logger.info("  Input: %s", input_result)

    await asyncio.sleep(1)

    # Step 4: Submit via keyboard (Enter)
    logger.info("Submitting message via Enter key...")
    # Use CDP Input.dispatchKeyEvent to send Enter
    await cdp("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
    await cdp("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})

    # Step 5: Wait for the full flow
    logger.info("Waiting 30s for sentinel + conversation flow...")
    await asyncio.sleep(30)

    # Step 6: Read captured requests
    captured = await js("JSON.stringify(window._sentinelCapture || [])")
    if captured:
        entries = json.loads(captured)
        logger.info("\nCaptured %d sentinel/conversation requests:", len(entries))
        for i, entry in enumerate(entries):
            url = entry.get("url", "")
            status = entry.get("response_status", "?")
            body_len = len(entry.get("body", ""))
            resp_len = len(entry.get("response_body", ""))
            logger.info("  [%d] %s %s → %s (req=%dB, resp=%dB)",
                        i, entry.get("method"), url.split("?")[0][-60:], status, body_len, resp_len)

            # Save key details
            if "sentinel" in url:
                logger.info("    Headers: %s", {k: v[:50] for k, v in entry.get("headers", {}).items()})
                if entry.get("body"):
                    logger.info("    Req body: %s", entry["body"][:500])
                if entry.get("response_body"):
                    try:
                        rb = json.loads(entry["response_body"])
                        if "turnstile" in rb:
                            logger.info("    Turnstile dx len: %d", len(rb.get("turnstile", {}).get("dx", "")))
                        if "proofofwork" in rb:
                            logger.info("    PoW: seed=%s diff=%s",
                                        rb.get("proofofwork", {}).get("seed"),
                                        rb.get("proofofwork", {}).get("difficulty"))
                    except:
                        pass

            if "/f/conversation" in url and "prepare" not in url:
                if entry.get("body"):
                    logger.info("    Conversation req body: %s", entry["body"][:800])
                if entry.get("response_body"):
                    # Show first few SSE events
                    body = entry["response_body"]
                    events = [l for l in body.split("\n") if l.startswith("data: ")]
                    logger.info("    SSE events: %d, first 3:", len(events))
                    for ev in events[:3]:
                        logger.info("      %s", ev[:200])

        # Save full capture
        output_path = "captured_sentinel_flow.json"
        with open(output_path, "w") as f:
            json.dump(entries, f, indent=2, default=str)
        logger.info("\nSaved to %s", output_path)
    else:
        logger.warning("No requests captured — message may not have been sent")

    await ws.close()


if __name__ == "__main__":
    asyncio.run(main())
