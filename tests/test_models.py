from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from payments.models import (
    AuditLogEntry,
    Intent,
    Mandate,
    TrackedItem,
    Transaction,
    User,
)


USER_ID = UUID("00000000-0000-0000-0000-000000000001")
ITEM_ID = UUID("00000000-0000-0000-0000-000000000002")
INTENT_ID = UUID("00000000-0000-0000-0000-000000000003")
NOW = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)


def user_data() -> dict:
    return {
        "user_id": USER_ID,
        "display_name": "Asha",
        "prava_account_ref": "prava_user_demo",
        "monthly_cap": "5000.00",
        "per_item_cap": "1000.00",
        "per_transaction_cap": "1500.00",
        "created_at": NOW,
    }


def predicted_item_data() -> dict:
    return {
        "item_id": ITEM_ID,
        "user_id": USER_ID,
        "name": "Coffee",
        "track": "home",
        "trigger_type": "predicted",
        "category": "grocery",
        "sensitive_flag": False,
        "preferred_merchant": "zepto",
        "merchant_sku_id": "coffee-500g",
        "status": "active",
        "typical_cadence_days": 14.0,
        "last_purchased_at": date(2026, 7, 2),
        "last_purchase_amount": "450.00",
    }


def known_date_item_data() -> dict:
    return {
        "item_id": ITEM_ID,
        "user_id": USER_ID,
        "name": "TeamTool Pro",
        "track": "teams",
        "trigger_type": "known_date",
        "category": "saas_subscription",
        "sensitive_flag": False,
        "preferred_merchant": "mock_subscription_billing",
        "merchant_sku_id": "teamtool-pro-monthly",
        "status": "active",
        "renewal_date": date(2026, 7, 16),
        "current_plan_amount": "2400.00",
        "alternate_plan_amount": "2200.00",
        "alternate_plan_label": "Annual plan",
    }


def test_valid_user() -> None:
    assert User(**user_data()).monthly_cap == Decimal("5000.00")


@pytest.mark.parametrize(("field", "value"), [("monthly_cap", 0), ("per_item_cap", -1)])
def test_user_rejects_non_positive_caps(field: str, value: int) -> None:
    data = user_data() | {field: value}
    with pytest.raises(ValidationError):
        User(**data)


def test_valid_tracked_items_cover_both_trigger_tracks() -> None:
    assert TrackedItem(**predicted_item_data()).renewal_date is None
    assert TrackedItem(**known_date_item_data()).typical_cadence_days is None


def test_predicted_item_requires_its_trigger_fields() -> None:
    data = predicted_item_data()
    data.pop("typical_cadence_days")
    with pytest.raises(ValidationError):
        TrackedItem(**data)


def test_known_date_item_requires_its_trigger_fields() -> None:
    data = known_date_item_data()
    data.pop("renewal_date")
    with pytest.raises(ValidationError):
        TrackedItem(**data)


def test_valid_intent() -> None:
    intent = Intent(
        intent_id=INTENT_ID,
        item_id=ITEM_ID,
        proposed_amount="450.00",
        proposed_merchant="zepto",
        status="pending_approval",
        created_at=NOW,
    )
    assert intent.proposed_amount == Decimal("450.00")


@pytest.mark.parametrize(("field", "value"), [("proposed_amount", 0), ("status", "paid")])
def test_invalid_intent(field: str, value: object) -> None:
    data = {
        "intent_id": INTENT_ID,
        "item_id": ITEM_ID,
        "proposed_amount": "450.00",
        "proposed_merchant": "zepto",
        "status": "pending_approval",
        "created_at": NOW,
    } | {field: value}
    with pytest.raises(ValidationError):
        Intent(**data)


def mandate_data() -> dict:
    return {
        "mandate_id": "mandate_demo_1",
        "intent_id": INTENT_ID,
        "credential_reference": "cred_one_time_demo",
        "scope_merchant": "zepto",
        "scope_max_amount": "450.00",
        "scope_expiry": NOW,
        "passkey_approved_at": NOW,
    }


def test_valid_mandate() -> None:
    assert Mandate(**mandate_data()).mandate_id == "mandate_demo_1"


@pytest.mark.parametrize(("field", "value"), [("scope_max_amount", -1), ("intent_id", "not-a-uuid")])
def test_invalid_mandate(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Mandate(**(mandate_data() | {field: value}))


def transaction_data() -> dict:
    return {
        "transaction_id": UUID("00000000-0000-0000-0000-000000000004"),
        "mandate_id": "mandate_demo_1",
        "item_id": ITEM_ID,
        "merchant_order_id": "order_demo_1",
        "amount": "450.00",
        "status": "completed",
        "completed_at": NOW,
    }


def test_valid_transaction() -> None:
    assert Transaction(**transaction_data()).status.value == "completed"


@pytest.mark.parametrize(("field", "value"), [("amount", 0), ("status", "refunded")])
def test_invalid_transaction(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Transaction(**(transaction_data() | {field: value}))


def audit_data() -> dict:
    return {
        "log_id": UUID("00000000-0000-0000-0000-000000000005"),
        "user_id": USER_ID,
        "event_type": "notification_sent",
        "payload": {"item": "Coffee", "amount": "450.00"},
        "timestamp": NOW,
    }


def test_valid_audit_log_entry() -> None:
    assert AuditLogEntry(**audit_data()).payload["item"] == "Coffee"


@pytest.mark.parametrize(("field", "value"), [("event_type", "card_saved"), ("payload", ["raw-card-data"])])
def test_invalid_audit_log_entry(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        AuditLogEntry(**(audit_data() | {field: value}))
