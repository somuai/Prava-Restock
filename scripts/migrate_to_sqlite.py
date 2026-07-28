#!/usr/bin/env python3
"""One-way, idempotent migration of Restock's JSON-era local state.

The core workflow models are already durable through ``storage``.  This tool
moves the two remaining compatibility stores—legacy notifications and
``AuditLogEntry`` records—from JSON arrays into the same SQLite ``restock.db``
file.  It never deletes the source files; retain them until the import has
been reviewed and backed up.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from common import audit_store, notification_store


ROOT = Path(__file__).resolve().parents[1]


def _read_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc.msg}") from exc
    if not isinstance(decoded, list) or not all(isinstance(row, dict) for row in decoded):
        raise ValueError(f"{path} must contain a JSON array of objects")
    return decoded


def migrate(
    *, notification_json: Path, audit_json: Path, database: Path
) -> tuple[int, int]:
    """Import historical rows; safe to execute repeatedly."""
    notification_count = notification_store.migrate_records(
        _read_array(notification_json), database
    )
    audit_count = audit_store.migrate_records(_read_array(audit_json), database)
    return notification_count, audit_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--notifications-json",
        type=Path,
        default=ROOT / "logs" / "notifications.json",
        help="legacy notifications JSON array (default: logs/notifications.json)",
    )
    parser.add_argument(
        "--audit-json",
        type=Path,
        default=ROOT / "logs" / "audit_log.json",
        help="legacy audit JSON array (default: logs/audit_log.json)",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / "logs" / "restock.db",
        help="target SQLite database (default: logs/restock.db)",
    )
    args = parser.parse_args(argv)
    try:
        notification_count, audit_count = migrate(
            notification_json=args.notifications_json,
            audit_json=args.audit_json,
            database=args.database,
        )
    except (OSError, ValueError) as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1
    print(
        "migration complete: "
        f"notifications={notification_count}, audit_entries={audit_count}, database={args.database}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
