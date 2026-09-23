from __future__ import annotations

import json
from pathlib import Path

from prompta.image_previews import ImagePreviewStore
from prompta.metadata_store import UI_METADATA_DB, BrowserOwnershipStore
from prompta.pinned_chats import PinnedChatStore


def test_pinned_chat_store_imports_legacy_json_once(tmp_path: Path) -> None:
    legacy = tmp_path / "ui-pinned-chats.json"
    legacy.write_text(
        json.dumps({"ids": ["old-chat", "other-chat", "old-chat"]}),
        encoding="utf-8",
    )

    store = PinnedChatStore(tmp_path)

    assert store.snapshot() == {
        "initialized": True,
        "ids": ["old-chat", "other-chat"],
    }
    assert (tmp_path / UI_METADATA_DB).is_file()
    assert not legacy.exists()

    store.set_pinned("new-chat", True)
    legacy.write_text(json.dumps({"ids": ["should-not-reimport"]}), encoding="utf-8")

    assert PinnedChatStore(tmp_path).snapshot() == {
        "initialized": True,
        "ids": ["old-chat", "other-chat", "new-chat"],
    }
    assert not legacy.exists()


def test_image_preview_store_imports_legacy_metadata_and_keeps_image_file(
    tmp_path: Path,
) -> None:
    preview_id = "a" * 32
    preview_dir = tmp_path / "ui-image-previews"
    preview_dir.mkdir()
    preview_file = preview_dir / preview_id
    preview_file.write_bytes(b"png-data")
    legacy = tmp_path / "ui-image-previews.json"
    legacy.write_text(
        json.dumps(
            {
                "records": {
                    "client-1": {
                        "client_id": "client-1",
                        "conversation_id": "chat-1",
                        "message": "show image",
                        "created_at": 123.0,
                        "images": [
                            {
                                "id": preview_id,
                                "name": "photo.png",
                                "type": "image/png",
                            }
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    store = ImagePreviewStore(tmp_path)

    assert store.records["client-1"]["conversation_id"] == "chat-1"
    assert store.image_preview(preview_id) == (b"png-data", "image/png")
    assert preview_file.is_file()
    assert (tmp_path / UI_METADATA_DB).is_file()
    assert not legacy.exists()

    reloaded = ImagePreviewStore(tmp_path)
    assert reloaded.records == store.records
    assert reloaded.image_preview(preview_id) == (b"png-data", "image/png")


def test_browser_ownership_store_imports_legacy_targets_and_uses_sqlite(
    tmp_path: Path,
) -> None:
    profile = tmp_path / "chrome-profile"
    legacy = tmp_path / "chrome-profile.owned-contexts.json"
    legacy.write_text(json.dumps(["target-b", "target-a", "target-a"]), encoding="utf-8")

    store = BrowserOwnershipStore(profile)

    assert store.legacy_targets() == {"target-a", "target-b"}
    assert store.path.is_file()
    assert not legacy.exists()

    store.replace_legacy_targets({"target-b"})
    marker = "prompta:123:abc"
    store.remember_marker(marker)

    reloaded = BrowserOwnershipStore(profile)
    assert reloaded.legacy_targets() == {"target-b"}
    assert reloaded.markers() == {marker}

    reloaded.forget_marker(marker)
    assert reloaded.markers() == set()
