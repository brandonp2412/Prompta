"""ChatGPT-Web2API — OpenAI-compatible proxy via CDP.

Usage:
    chatgpt-web2api                          # all defaults
    chatgpt-web2api --config config.json     # from config file
    chatgpt-web2api --port 9090              # override port
    chatgpt-web2api --cdp-port 9333          # override CDP port
    chatgpt-web2api --headless               # headless Chrome
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import Config
from .service import run_service


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chatgpt-web2api",
        description="OpenAI-compatible API proxy through ChatGPT web via CDP",
    )
    parser.add_argument("--config", "-c", help="Config file path (JSON)")
    parser.add_argument("--port", "-p", type=int, help="API server port (default: 8080)")
    parser.add_argument("--host", help="API server host (default: 127.0.0.1)")
    parser.add_argument("--cdp-port", type=int, help="Chrome CDP port (default: 9222)")
    parser.add_argument("--chrome-path", help="Path to Chrome binary")
    parser.add_argument("--user-data-dir", help="Chrome user data directory")
    parser.add_argument("--headless", action="store_true", help="Run Chrome headless")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    # Load config
    config = Config.load(args.config)

    # CLI overrides
    if args.port:
        config.server.port = args.port
    if args.host:
        config.server.host = args.host
    if args.cdp_port:
        config.chrome.cdp_port = args.cdp_port
    if args.chrome_path:
        config.chrome.chrome_path = args.chrome_path
    if args.user_data_dir:
        config.chrome.user_data_dir = args.user_data_dir
    if args.headless:
        config.chrome.headless = True
    if args.log_level:
        config.log.level = args.log_level

    # Logging
    logging.basicConfig(
        level=getattr(logging, config.log.level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Suppress noisy loggers
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

    # Run
    try:
        asyncio.run(run_service(config))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
