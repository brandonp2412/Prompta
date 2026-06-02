"""ChatGPT-Web2API — CDP-driven reverse proxy.

Routes OpenAI API calls through a real Chrome browser via CDP.
The browser handles all anti-bot challenges automatically.

Usage:
    python -m chatgpt_web2api --cdp-port 9222
    python -m chatgpt_web2api --cdp-port 9222 --port 8080
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from .cdp_driver import CDPDriver
from .api_server import APIServer


def main():
    parser = argparse.ArgumentParser(
        description="ChatGPT-Web2API: OpenAI-compatible proxy via CDP"
    )
    parser.add_argument("--cdp-port", type=int, required=True,
                        help="Chrome remote debugging port")
    parser.add_argument("--port", type=int, default=8080,
                        help="API server port (default: 8080)")
    parser.add_argument("--host", default="0.0.0.0",
                        help="API server host (default: 0.0.0.0)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    asyncio.run(_run(args))


async def _run(args):
    driver = CDPDriver(args.cdp_port)
    server = APIServer(driver, host=args.host, port=args.port)

    print()
    print("=" * 60)
    print("  ChatGPT-Web2API — CDP-Driven Proxy")
    print("=" * 60)
    print(f"  CDP port:    {args.cdp_port}")
    print(f"  API server:  http://{args.host}:{args.port}")
    print()
    print("  Connecting to Chrome...")

    await driver.connect()

    print("  Connected! Starting API server...")
    print()
    print("  Endpoints:")
    print(f"    POST http://{args.host}:{args.port}/v1/chat/completions")
    print(f"    GET  http://{args.host}:{args.port}/v1/models")
    print(f"    GET  http://{args.host}:{args.port}/v1/projects")
    print(f"    GET  http://{args.host}:{args.port}/health")
    print()
    print("  Example:")
    print(f'    curl http://localhost:{args.port}/v1/chat/completions \\')
    print('      -H "Content-Type: application/json" \\')
    print('      -d \'{"model":"auto","messages":[{"role":"user","content":"Hello"}]}\'')
    print()

    try:
        await server.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await driver.close()


if __name__ == "__main__":
    main()
