"""Offline Zepto checkout contract stub for pre-hackathon development."""

from decimal import Decimal
from uuid import uuid4


STUB_MODE = True

_CHECKOUTS_BY_IDEMPOTENCY_KEY: dict[str, dict] = {}


def complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key):
    """Return a fake merchant order, including a controllable stock failure."""
    if not credential_reference:
        raise ValueError("credential_reference is required")
    if Decimal(str(amount)) <= 0:
        raise ValueError("amount must be positive")
    if idempotency_key in _CHECKOUTS_BY_IDEMPOTENCY_KEY:
        return _CHECKOUTS_BY_IDEMPOTENCY_KEY[idempotency_key]

    # TODO: replace with real Prava SDK call — see TECHNICAL_PRD.md §15
    if merchant_sku_id.startswith("out-of-stock"):
        response = {"merchant_order_id": None, "status": "out_of_stock"}
    else:
        response = {
            "merchant_order_id": f"stub_zepto_order_{uuid4().hex}",
            "status": "completed",
        }
    _CHECKOUTS_BY_IDEMPOTENCY_KEY[idempotency_key] = response
    return response
