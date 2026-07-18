"""Offline Zepto checkout contract stub for pre-hackathon development."""

from decimal import Decimal
from uuid import uuid4


STUB_MODE = True

_CHECKOUTS_BY_IDEMPOTENCY_KEY: dict[str, dict] = {}
_PRICE_CHECK_COUNTS: dict[str, int] = {}
_STUB_BASE_PRICES = {
    "00000000-0000-0000-0000-000000000101": Decimal("380.00"),
}
_STUB_PRICE_OFFSETS = (
    Decimal("0.00"),
    Decimal("-12.00"),
    Decimal("8.00"),
)


def check_current_price(item_id) -> Decimal:
    """Return a deterministic sequence of fake fluctuating merchant prices."""
    if not item_id:
        raise ValueError("item_id is required")

    # STUB ONLY: replace with a real merchant price query in Phase 8/9.
    item_key = str(item_id)
    check_count = _PRICE_CHECK_COUNTS.get(item_key, 0)
    _PRICE_CHECK_COUNTS[item_key] = check_count + 1
    base_price = _STUB_BASE_PRICES.get(item_key, Decimal("399.00"))
    offset = _STUB_PRICE_OFFSETS[check_count % len(_STUB_PRICE_OFFSETS)]
    return base_price + offset


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
