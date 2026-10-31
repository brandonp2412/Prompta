"""A repeated fresh-chat POST remains idempotent after attachment storage changes."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import patch

from web_results_support import post_json, server

from prompta.strict_types import string_object_dict

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZ0AAAAASUVORK5CYII="
)


def test_accepted_receipt_can_be_replayed_without_reopening_image(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        status, uploaded = post_json(
            port,
            "/api/images",
            {
                "name": "photo.png",
                "data": base64.b64encode(PNG).decode(),
            },
        )
        assert status == 200
        image = string_object_dict(uploaded["image"])
        assert image is not None
        ref = image["ref"]
        assert isinstance(ref, str)
        payload = {
            "request_id": "e" * 32,
            "prompt": "Describe this image",
            "images": [ref],
        }
        status, first = post_json(port, "/api/chats", payload)
        assert status == 202

        with patch.object(app.images, "path", side_effect=FileNotFoundError):
            status, replay = post_json(port, "/api/chats", payload)
        assert status == 202
        assert replay["send_id"] == first["send_id"]
        assert len(app.queue.records()) == 1
        assert app.queue.records()[0]["images"] == (ref,)

        changed = {**payload, "prompt": "Different prompt"}
        status, conflict = post_json(port, "/api/chats", changed)
        assert status == 409
        assert "conflicts" in str(conflict["error"])
        assert len(app.queue.records()) == 1


def test_new_chat_with_missing_image_is_definitely_rejected(tmp_path: Path) -> None:
    with server(tmp_path) as (app, port):
        status, uploaded = post_json(
            port,
            "/api/images",
            {
                "name": "photo.png",
                "data": base64.b64encode(PNG).decode(),
            },
        )
        assert status == 200
        image = string_object_dict(uploaded["image"])
        assert image is not None
        ref = image["ref"]
        assert isinstance(ref, str)
        with patch.object(app.images, "path", side_effect=ValueError("Image no longer exists")):
            status, response = post_json(
                port,
                "/api/chats",
                {
                    "request_id": "f" * 32,
                    "prompt": "Describe this image",
                    "images": [ref],
                },
            )
        assert status == 422
        assert response["error"] == "Image unavailable. Reattach it before sending."
        assert app.queue.records() == []
