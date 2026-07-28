"""SQLite-backed persistence for the legacy Restock notification surface.

The workflow repository owns production notification delivery.  This small
module remains for the original ``/notifications/pending`` endpoint and the
offline orchestrator harness.  Its four public functions deliberately retain
their Phase 4 interface while storing data in ``logs/restock.db`` rather than
a mutable JSON file.
"""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
# Kept as a public configuration point for callers and tests.  It now names a
# SQLite database, not a JSON document.
NOTIFICATION_STORE_PATH = ROOT / "logs" / "restock.db"

_INPUT_FIELDS = frozenset({"item_id", "message", "actions"})
_TERMINAL_STATUSES = frozenset({"approved", "adjusted", "skipped"})
_ALL_STATUSES = frozenset({"pending", *_TERMINAL_STATUSES})
_TABLE = "legacy_notifications"


def _connect(database_path: Path | None = None) -> sqlite3.Connection:
    """Open a connection configured for safe concurrent local writers."""
    path = Path(database_path or NOTIFICATION_STORE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    # WAL allows readers to continue while one writer owns the short write
    # transaction.  SQLite serializes the writers, preventing lost updates.
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            notification_id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL,
            message TEXT NOT NULL,
            actions TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'adjusted', 'skipped')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS ix_{_TABLE}_pending "
        f"ON {_TABLE}(status, created_at)"
    )


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "notification_id": str(row["notification_id"]),
        "item_id": str(row["item_id"]),
        "message": str(row["message"]),
        "actions": json.loads(str(row["actions"])),
        "status": str(row["status"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _validate_input(notification: Mapping[str, Any]) -> tuple[str, str, list[str]]:
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
    return item_id, message, list(actions)


def _insert_stored(
    stored: Mapping[str, Any], database_path: Path | None = None
) -> dict[str, Any]:
    """Insert one fully formed historical row, idempotently by its UUID.

    It is intentionally private: ordinary callers use :func:`create`, while
    the JSON-to-SQLite migration uses this path to preserve legacy IDs and
    timestamps.
    """
    required = {
        "notification_id",
        "item_id",
        "message",
        "actions",
        "status",
        "created_at",
        "updated_at",
    }
    if set(stored) != required:
        raise ValueError("stored notification has an invalid shape")
    actions = stored["actions"]
    if (
        not isinstance(actions, list)
        or not actions
        or not all(isinstance(action, str) for action in actions)
        or stored["status"] not in _ALL_STATUSES
    ):
        raise ValueError("stored notification has invalid values")

    with _connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (notification_id, item_id, message, actions, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(stored["notification_id"]),
                str(stored["item_id"]),
                str(stored["message"]),
                json.dumps(actions, separators=(",", ":")),
                str(stored["status"]),
                str(stored["created_at"]),
                str(stored["updated_at"]),
            ),
        )
    return deepcopy(dict(stored))


def create(notification: Mapping[str, Any]) -> dict[str, Any]:
    """Create a pending notification from the deliberately narrow public payload."""
    item_id, message, actions = _validate_input(notification)
    timestamp = datetime.now(timezone.utc).isoformat()
    stored = {
        "notification_id": str(uuid4()),
        "item_id": item_id,
        "message": message,
        "actions": actions,
        "status": "pending",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    return _insert_stored(stored)


def get_pending() -> list[dict[str, Any]]:
    """Return defensive copies of every notification awaiting user action."""
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM {_TABLE} WHERE status = 'pending' "
            "ORDER BY created_at ASC, notification_id ASC"
        ).fetchall()
    return deepcopy([_decode(row) for row in rows])


def update_status(notification_id: str, status: str) -> dict[str, Any]:
    """Move one pending notification to an explicit user-selected terminal state."""
    if status not in _TERMINAL_STATUSES:
        raise ValueError(f"unsupported notification status: {status}")
    timestamp = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            f"""
            UPDATE {_TABLE}
            SET status = ?, updated_at = ?
            WHERE notification_id = ? AND status = 'pending'
            """,
            (status, timestamp, notification_id),
        )
        if cursor.rowcount != 1:
            exists = connection.execute(
                f"SELECT 1 FROM {_TABLE} WHERE notification_id = ?", (notification_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(f"unknown notification_id: {notification_id}")
            raise ValueError("notification already has a terminal status")
        row = connection.execute(
            f"SELECT * FROM {_TABLE} WHERE notification_id = ?", (notification_id,)
        ).fetchone()
    if row is None:  # defensive: the completed transaction must have returned it.
        raise KeyError(f"unknown notification_id: {notification_id}")
    return deepcopy(_decode(row))


def reset() -> None:
    """Clear every legacy notification in one SQLite transaction."""
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(f"DELETE FROM {_TABLE}")


def migrate_records(
    records: Sequence[Mapping[str, Any]], database_path: Path | None = None
) -> int:
    """Import complete JSON-era notification records, preserving their IDs.

    Re-running the import is safe because ``notification_id`` is the primary
    key.  The return value is the count of accepted source records.
    """
    for record in records:
        _insert_stored(record, database_path)
    return len(records)
