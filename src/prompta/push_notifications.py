from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush

logger = logging.getLogger(__name__)

_DEFAULT_VAPID_SUBJECT = "mailto:prompta@localhost"
_PUSH_POLL_SECONDS = 0.5


class PushNotificationService:
    """Persist browser push subscriptions and deliver completion notifications."""

    def __init__(
        self,
        state_dir: Path,
        *,
        sender: Callable[..., Any] = webpush,
        vapid_subject: str | None = None,
    ) -> None:
        self.state_dir = state_dir.expanduser()
        self.path = self.state_dir / "push-subscriptions.sqlite3"
        self.key_path = self.state_dir / "push-vapid-private.pem"
        self.sender = sender
        self.vapid_subject = (
            vapid_subject or os.environ.get("PROMPTA_VAPID_SUBJECT") or _DEFAULT_VAPID_SUBJECT
        )

    def _connect(self) -> sqlite3.Connection:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=2.0)
        connection.execute("PRAGMA busy_timeout=2000")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                endpoint TEXT PRIMARY KEY,
                subscription_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        return connection

    @staticmethod
    def _validated_subscription(subscription: dict[str, Any]) -> dict[str, Any]:
        endpoint = str(subscription.get("endpoint") or "").strip()
        keys = subscription.get("keys")
        p256dh = str(keys.get("p256dh") or "").strip() if isinstance(keys, dict) else ""
        auth = str(keys.get("auth") or "").strip() if isinstance(keys, dict) else ""

        if not endpoint.startswith("https://") or not p256dh or not auth:
            raise ValueError("Invalid Web Push subscription")

        return {
            "endpoint": endpoint,
            "keys": {
                "p256dh": p256dh,
                "auth": auth,
            },
        }

    def register(self, subscription: dict[str, Any]) -> dict[str, Any]:
        normalized = self._validated_subscription(subscription)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO push_subscriptions(endpoint, subscription_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET
                    subscription_json = excluded.subscription_json,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized["endpoint"],
                    json.dumps(normalized, separators=(",", ":"), sort_keys=True),
                    time.time(),
                ),
            )
        return {"ok": True}

    def remove(self, endpoint: str) -> None:
        if not self.path.exists():
            return
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        except sqlite3.DatabaseError:
            logger.exception("Could not remove Web Push subscription endpoint=%s", endpoint)

    def subscriptions(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT subscription_json FROM push_subscriptions ORDER BY updated_at"
                ).fetchall()
        except sqlite3.DatabaseError:
            logger.exception("Could not read Web Push subscriptions")
            return []

        subscriptions: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(str(row[0]))
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                subscriptions.append(payload)
        return subscriptions

    def has_subscriptions(self) -> bool:
        if not self.path.exists():
            return False
        try:
            with self._connect() as connection:
                row = connection.execute("SELECT 1 FROM push_subscriptions LIMIT 1").fetchone()
        except sqlite3.DatabaseError:
            return False
        return row is not None

    def public_key(self) -> str:
        key = self._private_key()
        raw = key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    def _private_key(self) -> ec.EllipticCurvePrivateKey:
        if self.key_path.exists():
            key = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
            if not isinstance(key, ec.EllipticCurvePrivateKey):
                raise ValueError("Stored VAPID key is not an EC private key")
            return key

        self.state_dir.mkdir(parents=True, exist_ok=True)
        key = ec.generate_private_key(ec.SECP256R1())
        encoded = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        temporary = self.key_path.with_suffix(".tmp")
        temporary.write_bytes(encoded)
        os.chmod(temporary, 0o600)
        temporary.replace(self.key_path)
        return key

    @staticmethod
    def _chat_title(chat: dict[str, Any]) -> str:
        return str(
            chat.get("title")
            or chat.get("job_name")
            or chat.get("prompt")
            or chat.get("id")
            or "Chat"
        ).strip()

    def send_completion(self, chat: dict[str, Any], display_name: str) -> None:
        conversation_id = str(chat.get("id") or "").strip()
        if not conversation_id:
            return

        payload = json.dumps(
            {
                "title": f"Prompta · {display_name}",
                "body": f"{self._chat_title(chat)} finished",
                "tag": f"prompta-finished-{conversation_id}",
                "icon": "./icon.svg",
                "badge": "./icon.svg",
                "url": f"./#/{quote(conversation_id, safe='')}",
            },
            separators=(",", ":"),
        )

        for subscription in self.subscriptions():
            endpoint = str(subscription.get("endpoint") or "")
            try:
                self.sender(
                    subscription_info=subscription,
                    data=payload,
                    vapid_private_key=str(self.key_path),
                    vapid_claims={"sub": self.vapid_subject},
                    ttl=300,
                    timeout=10,
                )
            except WebPushException as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in {404, 410}:
                    self.remove(endpoint)
                else:
                    logger.warning(
                        "Web Push delivery failed endpoint=%s status=%s: %s",
                        endpoint,
                        status,
                        exc,
                    )
            except Exception:
                logger.exception("Unexpected Web Push delivery failure endpoint=%s", endpoint)


class CompletionPushMonitor:
    """Track active conversations so completions can wake background PWAs."""

    def __init__(
        self,
        store: Any,
        notifications: PushNotificationService,
        display_name: str,
        *,
        poll_seconds: float = _PUSH_POLL_SECONDS,
    ) -> None:
        self.store = store
        self.notifications = notifications
        self.display_name = display_name
        self.poll_seconds = poll_seconds
        self._active: dict[str, dict[str, Any]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="prompta-push-monitor",
                daemon=True,
            )
            self._thread.start()

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=max(1.0, self.poll_seconds * 3))

    def poll_once(self) -> None:
        rows = self.store.notification_states(tuple(self._active))
        seen: set[str] = set()

        for chat in rows:
            conversation_id = str(chat.get("id") or "").strip()
            if not conversation_id:
                continue
            seen.add(conversation_id)
            status = str(chat.get("status") or "")

            if status == "active":
                self._active[conversation_id] = chat
                continue

            if conversation_id not in self._active:
                continue

            self._active.pop(conversation_id, None)
            if status == "complete":
                self.notifications.send_completion(chat, self.display_name)

        for conversation_id in tuple(self._active):
            if conversation_id not in seen:
                self._active.pop(conversation_id, None)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                logger.exception("Prompta completion push monitor failed")
            self._stop.wait(self.poll_seconds)
