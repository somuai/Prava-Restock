import json

import pytest

from common import notification_store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        notification_store, "NOTIFICATION_STORE_PATH", tmp_path / "notifications.json"
    )
    notification_store.reset()


def notification_payload() -> dict:
    return {
        "item_id": "coffee-500g",
        "message": "Coffee will run out in two days.",
        "actions": ["approve", "adjust", "skip"],
    }


def test_create_then_get_pending_returns_notification() -> None:
    created = notification_store.create(notification_payload())

    assert created["status"] == "pending"
    assert created["notification_id"]
    assert notification_store.get_pending() == [created]


@pytest.mark.parametrize("status", ["approved", "adjusted", "skipped"])
def test_update_status_removes_terminal_notification_from_pending(status: str) -> None:
    created = notification_store.create(notification_payload())

    updated = notification_store.update_status(created["notification_id"], status)

    assert updated["status"] == status
    assert notification_store.get_pending() == []


def test_reset_clears_every_notification() -> None:
    notification_store.create(notification_payload())

    notification_store.reset()

    assert notification_store.get_pending() == []
    assert json.loads(notification_store.NOTIFICATION_STORE_PATH.read_text()) == []


@pytest.mark.parametrize(
    "unsafe_field",
    ["credential_reference", "raw_payment", "card_number", "cvv"],
)
def test_payment_or_credential_fields_are_never_persisted(unsafe_field: str) -> None:
    payload = notification_payload()
    payload[unsafe_field] = "must-not-be-stored"

    with pytest.raises(ValueError, match="unsupported fields"):
        notification_store.create(payload)

    contents = notification_store.NOTIFICATION_STORE_PATH.read_text()
    assert unsafe_field not in contents
    assert "must-not-be-stored" not in contents
