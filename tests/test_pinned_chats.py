from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

from prompta.pinned_chats import PinnedChatStore
from prompta.web import PromptaUIServer, ReadOnlyChatStore


def _post_json(url: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=2) as response:
        return response.status, json.loads(response.read())


def test_pinned_chat_store_persists_and_promotes(tmp_path: Path) -> None:
    store = PinnedChatStore(tmp_path)
    assert store.snapshot() == {"initialized": False, "ids": []}

    assert store.seed(["old-chat", "other-chat", "old-chat"]) == {
        "initialized": True,
        "ids": ["old-chat", "other-chat"],
    }

    reloaded = PinnedChatStore(tmp_path)
    assert reloaded.snapshot() == {
        "initialized": True,
        "ids": ["old-chat", "other-chat"],
    }

    reloaded.promote("old-chat", "real-chat")
    reloaded.set_pinned("other-chat", False)
    reloaded.set_pinned("new-chat", True)

    assert PinnedChatStore(tmp_path).snapshot() == {
        "initialized": True,
        "ids": ["real-chat", "new-chat"],
    }


def test_pin_http_routes_seed_and_update_server_state(tmp_path: Path) -> None:
    store = ReadOnlyChatStore(tmp_path / "missing.sqlite3")
    server = PromptaUIServer(("127.0.0.1", 0), store, tmp_path / "state.json")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with urlopen(f"{base_url}/api/pins", timeout=2) as response:
            assert response.status == HTTPStatus.OK
            assert json.loads(response.read()) == {"initialized": False, "ids": []}

        status, seeded = _post_json(
            f"{base_url}/api/pins/seed",
            {"ids": ["browser-pin"]},
        )
        assert status == HTTPStatus.OK
        assert seeded == {"initialized": True, "ids": ["browser-pin"]}

        status, pinned = _post_json(
            f"{base_url}/api/pins",
            {"id": "second-pin", "pinned": True},
        )
        assert status == HTTPStatus.OK
        assert pinned == {
            "initialized": True,
            "ids": ["browser-pin", "second-pin"],
        }

        status, promoted = _post_json(
            f"{base_url}/api/pins/promote",
            {"from": "browser-pin", "to": "resolved-chat"},
        )
        assert status == HTTPStatus.OK
        assert promoted == {
            "initialized": True,
            "ids": ["resolved-chat", "second-pin"],
        }

        with urlopen(f"{base_url}/api/pins", timeout=2) as response:
            assert json.loads(response.read()) == promoted
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
