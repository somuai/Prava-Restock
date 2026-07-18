#!/usr/bin/env python3
"""Apply configured data retention without touching transaction proof."""

from datetime import datetime, timedelta, timezone
import os

from storage import Database, RestockRepository


def main() -> None:
    days = int(os.getenv("RESTOCK_RETENTION_DAYS", "365"))
    if days < 30:
        raise SystemExit("RESTOCK_RETENTION_DAYS must be at least 30")
    repository = RestockRepository(Database())
    result = repository.enforce_retention(before=datetime.now(timezone.utc) - timedelta(days=days))
    print(f"PASS retention cleanup: {result}")


if __name__ == "__main__":
    main()
