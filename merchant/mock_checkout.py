"""Disclosed, deterministic Home fulfillment simulation.

The real Zepto catalog/cart/quote adapter lives in ``zepto_checkout``. This
module simulates only the final live-money boundary that Zepto does not expose
as a merchant sandbox.
"""

from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import threading
from uuid import uuid4

from merchant.models import (
    CheckoutStatus,
    ExecutionMode,
    MerchantCheckoutResult,
)


DISCLOSED_SIMULATION = True
CHECKOUT_STORE_PATH = (
    Path(__file__).resolve().parents[1] / "logs" / "merchant_checkouts.json"
)
_LOCK = threading.RLock()


def _read() -> dict[str, dict]:
    if not CHECKOUT_STORE_PATH.exists():
        return {}
    value = json.loads(CHECKOUT_STORE_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("merchant checkout store must contain an object")
    return value


def _write(value: dict[str, dict]) -> None:
    CHECKOUT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=CHECKOUT_STORE_PATH.parent,
            prefix=f".{CHECKOUT_STORE_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(value, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, CHECKOUT_STORE_PATH)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def reset() -> None:
    with _LOCK:
        _write({})


def complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key):
    if not credential_reference:
        raise ValueError("credential_reference is required")
    parsed_amount = Decimal(str(amount))
    if parsed_amount <= 0:
        raise ValueError("amount must be positive")
    if not idempotency_key:
        raise ValueError("idempotency_key is required")
    with _LOCK:
        checkouts = _read()
        if idempotency_key in checkouts:
            return dict(checkouts[idempotency_key])

    status = (
        CheckoutStatus.OUT_OF_STOCK
        if str(merchant_sku_id).startswith("out-of-stock")
        else CheckoutStatus.COMPLETED
    )
    result = MerchantCheckoutResult(
        status=status,
        merchant_order_id=(
            None
            if status is CheckoutStatus.OUT_OF_STOCK
            else f"mock_{'swiggy' if str(merchant_sku_id).startswith('swiggy:') else 'zepto'}_{uuid4().hex}"
        ),
        charged_amount=(parsed_amount if status is CheckoutStatus.COMPLETED else None),
        currency="INR",
        retryable=False,
        execution_mode=ExecutionMode.DISCLOSED_MOCK,
        error_code=("OUT_OF_STOCK" if status is CheckoutStatus.OUT_OF_STOCK else None),
    )
    serialized = result.model_dump(mode="json")
    with _LOCK:
        checkouts = _read()
        existing = checkouts.get(idempotency_key)
        if existing is not None:
            return dict(existing)
        checkouts[idempotency_key] = serialized
        _write(checkouts)
    return serialized
