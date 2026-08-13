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


def provision_reviewer(
    repository: RestockRepository,
    *,
    user_id: UUID,
    reset_history: bool = False,
) -> tuple[int, int]:
    """Create the reviewer and copy five safe demo fixtures idempotently."""

    if reset_history:
        repository.reset_reviewer_fixture(user_id=str(user_id))

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
    existing_by_sku = {
        str(item.get("merchant_sku_id", "")): item
        for item in repository.list_items(str(user_id))
    }
    created = 0
    for fixture in load_seed_items():
        existing = existing_by_sku.get(fixture.merchant_sku_id)
        if existing is not None:
            # Reviewer fixtures are curated demonstration data. Keep their
            # original identity stable while refreshing the visible product
            # metadata after a safe fixture update (for example, replacing a
            # generic subscription name with the real provider being shown).
            repository.upsert_item(
                fixture.model_copy(
                    update={
                        "item_id": UUID(str(existing["item_id"])),
                        "user_id": user_id,
                        "tenant_id": None,
                        "merchant_address_ref": None,
                    }
                )
            )
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
    total = len(repository.list_items(str(user_id)))
    if reset_history:
        repository.audit(
            user_id=str(user_id),
            event_type="reviewer_fixture_refreshed",
            payload={"fixture_items": total, "purpose": "isolated_reviewer_showcase"},
            modes={
                "prava": "sandbox",
                "home_catalog": "real",
                "home_payment": "disclosed_mock",
                "teams_billing": "disclosed_mock",
            },
        )
    return created, total


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset-history",
        action="store_true",
        help="Clear only the expiring reviewer fixture before reseeding it.",
    )
    args = parser.parse_args()
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
    created, total = provision_reviewer(
        repository, user_id=user_id, reset_history=args.reset_history
    )
    print(
        "PASS reviewer provisioned; "
        f"created_items={created}; total_items={total}; reset_history={args.reset_history}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
