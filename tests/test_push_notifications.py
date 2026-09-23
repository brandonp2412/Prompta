from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from prompta.push_notifications import CompletionPushMonitor, PushNotificationService


def _subscription(endpoint: str = "https://push.example.test/subscription") -> dict[str, object]:
    return {
        "endpoint": endpoint,
        "keys": {
            "p256dh": "browser-public-key",
            "auth": "browser-auth-secret",
        },
    }


def test_push_service_persists_subscription_and_stable_vapid_key(tmp_path: Path) -> None:
    service = PushNotificationService(tmp_path)

    assert service.has_subscriptions() is False
    assert service.register(_subscription()) == {"ok": True}
    assert service.has_subscriptions() is True
    assert service.subscriptions() == [_subscription()]

    first_key = service.public_key()
    second_key = PushNotificationService(tmp_path).public_key()
    raw = base64.urlsafe_b64decode(first_key + "=" * (-len(first_key) % 4))

    assert first_key == second_key
    assert len(raw) == 65
    assert raw[0] == 4
    assert service.key_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "subscription",
    [
        {},
        {"endpoint": "http://push.example.test", "keys": {"p256dh": "key", "auth": "auth"}},
        {"endpoint": "https://push.example.test", "keys": {"p256dh": "", "auth": "auth"}},
    ],
)
def test_push_service_rejects_invalid_subscriptions(
    tmp_path: Path,
    subscription: dict[str, object],
) -> None:
    service = PushNotificationService(tmp_path)

    with pytest.raises(ValueError, match="Invalid Web Push subscription"):
        service.register(subscription)


def test_push_service_sends_completion_payload(tmp_path: Path) -> None:
    sender = MagicMock()
    service = PushNotificationService(
        tmp_path, sender=sender, vapid_subject="mailto:test@example.test"
    )
    service.public_key()
    service.register(_subscription())

    service.send_completion(
        {
            "id": "chat/one",
            "title": "Mobile PWA",
            "status": "complete",
        },
        "Nox",
    )

    sender.assert_called_once()
    kwargs = sender.call_args.kwargs
    payload = json.loads(kwargs["data"])

    assert kwargs["subscription_info"] == _subscription()
    assert kwargs["vapid_private_key"] == str(service.key_path)
    assert kwargs["vapid_claims"] == {"sub": "mailto:test@example.test"}
    assert kwargs["ttl"] == 300
    assert payload == {
        "title": "Prompta · Nox",
        "body": "Mobile PWA finished",
        "tag": "prompta-finished-chat/one",
        "icon": "./icon.svg",
        "badge": "./icon.svg",
        "url": "./#/chat%2Fone",
    }


def test_completion_monitor_notifies_only_active_to_complete_transition(tmp_path: Path) -> None:
    notifications = MagicMock()
    store = MagicMock()
    store.notification_states.side_effect = [
        [{"id": "chat-1", "title": "Work", "status": "active"}],
        [
            {
                "id": "chat-1",
                "title": "Work",
                "status": "complete",
                "completed_at": 123,
            }
        ],
        [{"id": "chat-2", "title": "Already done", "status": "complete"}],
    ]
    monitor = CompletionPushMonitor(store, notifications, "Nox")

    monitor.poll_once()
    notifications.send_completion.assert_not_called()

    monitor.poll_once()
    notifications.send_completion.assert_called_once_with(
        {
            "id": "chat-1",
            "title": "Work",
            "status": "complete",
            "completed_at": 123,
        },
        "Nox",
    )

    notifications.send_completion.reset_mock()
    monitor.poll_once()
    notifications.send_completion.assert_not_called()
