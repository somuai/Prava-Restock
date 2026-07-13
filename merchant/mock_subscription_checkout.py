"""Disclosed simulation of the Restock Teams billing-portal call."""

from decimal import Decimal
from uuid import uuid4


STUB_MODE = True
DISCLOSED_SIMULATION = True

_CHECKOUTS_BY_IDEMPOTENCY_KEY: dict[str, dict] = {}


def complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key):
    if not credential_reference:
        raise ValueError("credential_reference is required")
    if Decimal(str(amount)) <= 0:
        raise ValueError("amount must be positive")
    if idempotency_key not in _CHECKOUTS_BY_IDEMPOTENCY_KEY:
        _CHECKOUTS_BY_IDEMPOTENCY_KEY[idempotency_key] = {
            "merchant_order_id": f"stub_subscription_order_{uuid4().hex}",
            "status": "completed",
        }
    return _CHECKOUTS_BY_IDEMPOTENCY_KEY[idempotency_key]
