"""Disclosed simulation of the Restock Teams billing-portal call."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import threading
from uuid import uuid4

from merchant.models import (
    CheckoutStatus,
    ExecutionMode,
    MerchantCheckoutResult,
)


STUB_MODE = True
DISCLOSED_SIMULATION = True

_CHECKOUTS_BY_IDEMPOTENCY_KEY: dict[str, tuple[str, dict]] = {}
_CHECKOUT_LOCK = threading.RLock()


def _request_fingerprint(merchant_sku_id: str, amount: Decimal) -> str:
    canonical_amount = format(amount.normalize(), "f")
    canonical_request = f"{merchant_sku_id}\0{canonical_amount}\0USD"
    return sha256(canonical_request.encode("utf-8")).hexdigest()


def complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key):
    if credential_reference is None or not str(credential_reference).strip():
        raise ValueError("credential_reference is required")
    canonical_sku = "" if merchant_sku_id is None else str(merchant_sku_id).strip()
    if not canonical_sku:
        raise ValueError("merchant_sku_id is required")
    canonical_key = "" if idempotency_key is None else str(idempotency_key).strip()
    if not canonical_key:
        raise ValueError("idempotency_key is required")
    try:
        parsed_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("amount must be positive") from exc
    if not parsed_amount.is_finite() or parsed_amount <= 0:
        raise ValueError("amount must be positive")

    fingerprint = _request_fingerprint(canonical_sku, parsed_amount)
    with _CHECKOUT_LOCK:
        existing = _CHECKOUTS_BY_IDEMPOTENCY_KEY.get(canonical_key)
        if existing is not None:
            existing_fingerprint, existing_result = existing
            if existing_fingerprint != fingerprint:
                raise ValueError(
                    "idempotency_key already used with different checkout parameters"
                )
            return deepcopy(existing_result)

        result = MerchantCheckoutResult(
            merchant_order_id=f"stub_subscription_order_{uuid4().hex}",
            status=CheckoutStatus.COMPLETED,
            charged_amount=parsed_amount,
            currency="USD",
            retryable=False,
            execution_mode=ExecutionMode.DISCLOSED_MOCK,
            disclosure_reason="Subscription checkout is a disclosed simulation.",
            credential_exposed=False,
            credential_used=True,
        )
        serialized = result.model_dump(mode="json")
        _CHECKOUTS_BY_IDEMPOTENCY_KEY[canonical_key] = (fingerprint, serialized)
        return deepcopy(serialized)
