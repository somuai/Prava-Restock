#!/usr/bin/env python3
"""Retry bounded welcome-email outbox entries without printing recipients."""

from __future__ import annotations

import argparse
import json
import os

from common.waitlist_email import (
    bounded_delivery_settings,
    retry_waitlist_welcome_emails,
)
from storage import Database, RestockRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=int(os.getenv("RESTOCK_WAITLIST_EMAIL_LEASE_SECONDS", "60")),
    )
    args = parser.parse_args()
    batch_size, lease_seconds = bounded_delivery_settings(
        configured_batch=args.limit,
        configured_lease_seconds=args.lease_seconds,
    )
    repository = RestockRepository(Database())
    summary = retry_waitlist_welcome_emails(
        repository,
        max_attempts=args.max_attempts,
        limit=batch_size,
        lease_seconds=lease_seconds,
    )
    print(json.dumps(summary, sort_keys=True))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
