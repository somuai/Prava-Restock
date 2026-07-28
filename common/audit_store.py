"""SQLite persistence for the JSON-era ``AuditLogEntry`` compatibility log."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from typing import Any

from payments.models import AuditLogEntry


ROOT = Path(__file__).resolve().parents[1]
# The public workflow repository stores its own richer audit rows.  This table
# keeps the original model-shaped audit endpoint and offline harness durable.
AUDIT_STORE_PATH = ROOT / "logs" / "restock.db"
_TABLE = "legacy_audit_log_entries"


def _connect(database_path: Path | None = None) -> sqlite3.Connection:
    path = Path(database_path or AUDIT_STORE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            log_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (
                event_type IN (
                    'notification_sent', 'approved', 'adjusted', 'skipped',
                    'transaction_completed', 'transaction_failed', 'item_deleted',
                    'data_exported'
                )
            ),
            payload TEXT NOT NULL,
            execution_mode TEXT,
            reason TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )
    columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({_TABLE})").fetchall()
    }
    if "execution_mode" not in columns:
        connection.execute(f"ALTER TABLE {_TABLE} ADD COLUMN execution_mode TEXT")
    if "reason" not in columns:
        connection.execute(f"ALTER TABLE {_TABLE} ADD COLUMN reason TEXT")
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS ix_{_TABLE}_timestamp "
        f"ON {_TABLE}(timestamp, log_id)"
    )
    return connection


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "log_id": str(row["log_id"]),
        "user_id": str(row["user_id"]),
        "event_type": str(row["event_type"]),
        "payload": json.loads(str(row["payload"])),
        "execution_mode": row["execution_mode"],
        "reason": row["reason"],
        "timestamp": str(row["timestamp"]),
    }


def append(entry: AuditLogEntry, database_path: Path | None = None) -> dict[str, Any]:
    """Store one Pydantic-validated audit entry, idempotently by ``log_id``."""
    record = entry.model_dump(mode="json")
    with _connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (log_id, user_id, event_type, payload, execution_mode, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["log_id"],
                record["user_id"],
                record["event_type"],
                json.dumps(record["payload"], separators=(",", ":")),
                record["execution_mode"],
                record["reason"],
                record["timestamp"],
            ),
        )
    return deepcopy(record)


def get_all(database_path: Path | None = None) -> list[dict[str, Any]]:
    """Return model-shaped audit entries in their original chronological order."""
    with _connect(database_path) as connection:
        rows = connection.execute(
            f"SELECT * FROM {_TABLE} ORDER BY timestamp ASC, log_id ASC"
        ).fetchall()
    return deepcopy([_decode(row) for row in rows])


def reset(database_path: Path | None = None) -> None:
    with _connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(f"DELETE FROM {_TABLE}")


def migrate_records(
    records: Sequence[Mapping[str, Any]], database_path: Path | None = None
) -> int:
    """Import JSON-era model records without changing IDs or timestamps."""
    for record in records:
        append(AuditLogEntry.model_validate(record), database_path)
    return len(records)
