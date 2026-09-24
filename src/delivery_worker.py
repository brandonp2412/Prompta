from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

from .delivery_browser import BrowserDeliverySender
from .delivery_queue import DeliveryQueueStore
from .image_previews import ImagePreviewStore
from .persistence import DEFAULT_RUNTIME_PATH
from .send_jobs import SendJobRegistry

logger = logging.getLogger(__name__)

DEFAULT_STATE_PATH = DEFAULT_RUNTIME_PATH


def _reconcile_completed_previews(
    queue: DeliveryQueueStore,
    previews: ImagePreviewStore,
) -> None:
    for record in queue.records():
        if str(record.get("status") or "") != "succeeded":
            continue
        client_id = str(record.get("client_id") or "")
        conversation_id = str(record.get("conversation_id") or "")
        if not client_id or not conversation_id:
            continue
        previews.bind(
            client_id,
            conversation_id,
            str(record.get("message") or ""),
        )


def run(
    state_path: Path = DEFAULT_STATE_PATH,
    *,
    cache_path: Path | None = None,
    chrome_profile: Path | None = None,
    chrome_path: str = "/usr/bin/chromium",
    chrome_debugger_address: str | None = None,
    flaresolverr_url: str | None = None,
    chrome_auth_timeout_seconds: float = 30.0,
) -> None:
    state_path = state_path.expanduser()
    state_dir = state_path.parent
    queue_path = state_dir / "ui-send-jobs.sqlite3"
    previews = ImagePreviewStore(state_dir)
    queue = DeliveryQueueStore(queue_path)
    sender = BrowserDeliverySender(
        state_path,
        cache_path=cache_path,
        profile=chrome_profile,
        chrome_path=chrome_path,
        debugger_address=chrome_debugger_address,
        flaresolverr_url=flaresolverr_url,
        auth_timeout_seconds=chrome_auth_timeout_seconds,
    )
    registry = SendJobRegistry(
        sender,
        queue_path=queue_path,
        on_success=previews.bind,
        consume=True,
    )
    logger.info(
        "Prompta delivery worker consuming %s with direct browser delivery",
        queue_path,
    )
    try:
        while True:
            _reconcile_completed_previews(queue, previews)
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        registry.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Prompta durable delivery worker")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--cache", type=Path)
    parser.add_argument(
        "--chrome-profile",
        type=Path,
        default=(
            Path(os.environ["PROMPTA_CHROME_PROFILE"])
            if os.environ.get("PROMPTA_CHROME_PROFILE")
            else None
        ),
    )
    parser.add_argument(
        "--chrome-path",
        default=os.environ.get("PROMPTA_CHROME_PATH", "/usr/bin/chromium"),
    )
    parser.add_argument(
        "--chrome-debugger-address",
        default=os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9222"),
    )
    parser.add_argument(
        "--flaresolverr-url",
        default=os.environ.get("PROMPTA_FLARESOLVERR_URL"),
    )
    parser.add_argument(
        "--chrome-auth-timeout-seconds",
        type=float,
        default=float(os.environ.get("PROMPTA_CHROME_AUTH_TIMEOUT_SECONDS", "30")),
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(
        args.state,
        cache_path=args.cache,
        chrome_profile=args.chrome_profile,
        chrome_path=args.chrome_path,
        chrome_debugger_address=args.chrome_debugger_address,
        flaresolverr_url=args.flaresolverr_url,
        chrome_auth_timeout_seconds=args.chrome_auth_timeout_seconds,
    )


if __name__ == "__main__":
    main()
