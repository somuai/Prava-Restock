"""Atomic JSON-backed persistence for user-facing Restock notifications."""

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
NOTIFICATION_STORE_PATH = ROOT / "logs" / "notifications.json"

_LOCK = threading.RLock()
_INPUT_FIELDS = frozenset({"item_id", "message", "actions"})
_TERMINAL_STATUSES = frozenset({"approved", "adjusted", "skipped"})


def _read_unlocked() -> list[dict[str, Any]]:
    if not NOTIFICATION_STORE_PATH.exists():
        return []
    data = json.loads(NOTIFICATION_STORE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("notification store must contain a JSON array of objects")
    return data


def _write_unlocked(notifications: list[dict[str, Any]]) -> None:
    """Replace the store atomically so readers never observe partial JSON."""
    path = NOTIFICATION_STORE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(notifications, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def create(notification: Mapping[str, Any]) -> dict[str, Any]:
    """Create a pending notification from the deliberately narrow public payload."""
    unexpected_fields = set(notification) - _INPUT_FIELDS
    missing_fields = _INPUT_FIELDS - set(notification)
    if unexpected_fields or missing_fields:
        details = []
        if missing_fields:
            details.append(f"missing fields: {sorted(missing_fields)}")
        if unexpected_fields:
            details.append(f"unsupported fields: {sorted(unexpected_fields)}")
        raise ValueError("; ".join(details))

    item_id = str(notification["item_id"])
    message = notification["message"]
    actions = notification["actions"]
    if not item_id or not isinstance(message, str) or not message.strip():
        raise ValueError("item_id and message must be non-empty")
    if not isinstance(actions, list) or not actions or not all(
        isinstance(action, str) for action in actions
    ):
        raise ValueError("actions must be a non-empty list of strings")

    timestamp = datetime.now(timezone.utc).isoformat()
    stored = {
        "notification_id": str(uuid4()),
        "item_id": item_id,
        "message": message,
        "actions": list(actions),
        "status": "pending",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    with _LOCK:
        notifications = _read_unlocked()
        notifications.append(stored)
        _write_unlocked(notifications)
    return deepcopy(stored)


def get_pending() -> list[dict[str, Any]]:
    """Return defensive copies of every notification awaiting user action."""
    with _LOCK:
        pending = [
            notification
            for notification in _read_unlocked()
            if notification.get("status") == "pending"
        ]
    return deepcopy(pending)


def update_status(notification_id: str, status: str) -> dict[str, Any]:
    """Move one pending notification to an explicit user-selected terminal state."""
    if status not in _TERMINAL_STATUSES:
        raise ValueError(f"unsupported notification status: {status}")
    with _LOCK:
        notifications = _read_unlocked()
        for notification in notifications:
            if notification.get("notification_id") == notification_id:
                notification["status"] = status
                notification["updated_at"] = datetime.now(timezone.utc).isoformat()
                _write_unlocked(notifications)
                return deepcopy(notification)
    raise KeyError(f"unknown notification_id: {notification_id}")


def reset() -> None:
    """Clear all notifications while preserving a valid JSON store file."""
    with _LOCK:
        _write_unlocked([])
