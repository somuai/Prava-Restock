#!/usr/bin/env python3
"""Provision an isolated, expiring reviewer account without printing secrets."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv

from demo.seed_reset import load_seed_items
from payments.models import User
from storage import Database, RestockRepository

ROOT = Path(__file__).resolve().parents[1]


def provision_reviewer(repository: RestockRepository, *, user_id: UUID) -> tuple[int, int]:
    """Create the reviewer and copy five safe demo fixtures idempotently."""

    repository.upsert_user(
        User(
            user_id=user_id,
            display_name="Prava Review",
            prava_account_ref=f"prava_reviewer_{user_id.hex[:12]}",
            monthly_cap="5000.00",
            per_item_cap="1000.00",
            per_transaction_cap="1000.00",
            created_at=datetime.now(timezone.utc),
        )
    )
    existing_skus = {
        str(item.get("merchant_sku_id", ""))
        for item in repository.list_items(str(user_id))
    }
    created = 0
    for fixture in load_seed_items():
        if fixture.merchant_sku_id in existing_skus:
            continue
        repository.upsert_item(
            fixture.model_copy(
                update={
                    "item_id": uuid4(),
                    "user_id": user_id,
                    "tenant_id": None,
                    "merchant_address_ref": None,
                }
            )
        )
        created += 1
    return created, len(repository.list_items(str(user_id)))


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    raw_user_id = os.getenv("RESTOCK_REVIEWER_USER_ID", "").strip()
    raw_expiry = os.getenv("RESTOCK_REVIEWER_EXPIRES_AT", "").strip()
    if not raw_user_id or not raw_expiry:
        raise SystemExit("RESTOCK_REVIEWER_USER_ID and expiry must be configured")
    try:
        user_id = UUID(raw_user_id)
        expires_at = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
        if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
            raise ValueError("expiry must be a future timezone-aware instant")
    except ValueError as exc:
        raise SystemExit("reviewer identity or expiry is invalid") from exc

    repository = RestockRepository(Database())
    repository.create_schema()
    created, total = provision_reviewer(repository, user_id=user_id)
    print(f"PASS reviewer provisioned; created_items={created}; total_items={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
