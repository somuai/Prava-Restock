#!/usr/bin/env python3
"""Back up or restore Restock data; never uploads data to a third party."""

import argparse
import os
from pathlib import Path

from storage import backup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["backup", "restore", "verify"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:///logs/restock.db"))
    args = parser.parse_args()
    is_sqlite = args.database_url.startswith("sqlite")
    if args.operation == "backup":
        result = backup.backup_sqlite(args.database_url, args.path) if is_sqlite else backup.backup_postgres(args.database_url, args.path)
    elif args.operation == "restore":
        result = backup.restore_sqlite(args.path, args.database_url) if is_sqlite else backup.restore_postgres(args.path, args.database_url)
    else:
        if not is_sqlite:
            raise SystemExit("Postgres verification requires restoring into a disposable database")
        backup.verify_sqlite(args.path)
        result = backup.sha256(args.path)
    print(f"PASS {args.operation}: {result or args.path}")


if __name__ == "__main__":
    main()
