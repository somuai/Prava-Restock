"""Swiggy catalog/cart adapter with card checkout explicitly gated."""

from datetime import datetime, timezone
from decimal import Decimal
import os
from typing import Any
from uuid import uuid4

from merchant.models import (
    CheckoutStatus,
    ExecutionMode,
    MerchantCheckoutResult,
    MerchantQuote,
    StockStatus,
)
from merchant import mock_checkout
from merchant.swiggy_mcp import SwiggyMCPClient


def _first(payload: Any, names: tuple[str, ...]) -> Any:
    if isinstance(payload, dict):
        for name in names:
            if payload.get(name) is not None:
                return payload[name]
        for value in payload.values():
            found = _first(value, names)
            if found is not None:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _first(value, names)
            if found is not None:
                return found
    return None


class SwiggyAdapter:
    def __init__(self, client: SwiggyMCPClient | None = None) -> None:
        self.client = client or SwiggyMCPClient()

    def quote(self, *, merchant_sku_id: str, product_name: str, cart: dict[str, Any] | None = None) -> MerchantQuote:
        payload = cart if cart is not None else self.client.view_cart()
        amount = _first(payload, ("toPay", "total", "totalAmount", "amount"))
        if amount is None:
            raise ValueError("Swiggy cart did not contain a final amount")
        available = _first(payload, ("available", "inStock", "deliverable"))
        return MerchantQuote(
            merchant="swiggy",
            merchant_sku_id=merchant_sku_id,
            product_name=product_name,
            amount=Decimal(str(amount)),
            currency="INR",
            stock_status=StockStatus.OUT_OF_STOCK if available is False else StockStatus.IN_STOCK,
            quote_reference=str(_first(payload, ("cartId", "quoteId")) or f"swiggy_{uuid4().hex}"),
            observed_at=datetime.now(timezone.utc),
            execution_mode=ExecutionMode.REAL,
        )

    def checkout(self, credential_reference: str, merchant_sku_id: str, amount: Decimal, idempotency_key: str) -> MerchantCheckoutResult:
        raise RuntimeError(
            "Swiggy MCP may place COD orders, but Restock never substitutes COD for the "
            "approved Prava card path; online checkout requires an explicit browser session"
        )

    def reconcile(self, merchant_order_id: str) -> MerchantCheckoutResult:
        return MerchantCheckoutResult(
            status=CheckoutStatus.PENDING,
            merchant_order_id=merchant_order_id,
            charged_amount=None,
            currency="INR",
            retryable=False,
            execution_mode=ExecutionMode.REAL,
            error_code="INTERACTIVE_RECONCILIATION_REQUIRED",
        )


def payment_mode() -> ExecutionMode:
    return (
        ExecutionMode.REAL
        if os.getenv("SWIGGY_PAYMENT_MODE") == "interactive_browser"
        else ExecutionMode.DISCLOSED_MOCK
    )


def complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key):
    """Keep automation safe: only the disclosed boundary runs unattended."""
    if payment_mode() is ExecutionMode.REAL:
        raise RuntimeError("Swiggy card checkout requires an explicitly confirmed browser session")
    return mock_checkout.complete_checkout(
        credential_reference,
        f"swiggy:{merchant_sku_id}",
        amount,
        idempotency_key,
    )
