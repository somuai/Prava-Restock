"""One-time hosted-invoice adapter; recurring mandates remain unsupported."""

from datetime import datetime, timezone
from decimal import Decimal
import os
from urllib.parse import urlparse
from uuid import uuid4

from merchant.models import CheckoutStatus, ExecutionMode, MerchantCheckoutResult, MerchantQuote, StockStatus


_RESULTS: dict[str, MerchantCheckoutResult] = {}


def quote_invoice(*, invoice_url: str, vendor: str, invoice_id: str, amount: Decimal, currency: str) -> MerchantQuote:
    parsed = urlparse(invoice_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("hosted invoice must use HTTPS")
    if amount <= 0:
        raise ValueError("invoice amount must be positive")
    return MerchantQuote(
        merchant=vendor,
        merchant_sku_id=invoice_id,
        product_name=f"{vendor} hosted invoice",
        amount=amount,
        currency=currency,
        stock_status=StockStatus.IN_STOCK,
        quote_reference=invoice_url,
        observed_at=datetime.now(timezone.utc),
        execution_mode=ExecutionMode.REAL,
    )


def complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key):
    if os.getenv("TEAMS_RECURRING_ENABLED") == "1":
        raise RuntimeError("recurring Teams charging is disabled pending Prava confirmation")
    if not credential_reference or not idempotency_key:
        raise ValueError("credential reference and idempotency key are required")
    parsed_amount = Decimal(str(amount))
    if parsed_amount <= 0:
        raise ValueError("amount must be positive")
    if idempotency_key not in _RESULTS:
        _RESULTS[idempotency_key] = MerchantCheckoutResult(
            status=CheckoutStatus.COMPLETED,
            merchant_order_id=f"invoice_mock_{uuid4().hex}",
            charged_amount=parsed_amount,
            currency=os.getenv("TEAMS_BILLING_CURRENCY", "USD"),
            retryable=False,
            execution_mode=ExecutionMode.DISCLOSED_MOCK,
        )
    return _RESULTS[idempotency_key].model_dump(mode="json")


def reconcile(merchant_order_id: str) -> MerchantCheckoutResult:
    for result in _RESULTS.values():
        if result.merchant_order_id == merchant_order_id:
            return result
    return MerchantCheckoutResult(
        status=CheckoutStatus.FAILED,
        merchant_order_id=merchant_order_id,
        currency=os.getenv("TEAMS_BILLING_CURRENCY", "USD"),
        retryable=False,
        execution_mode=ExecutionMode.DISCLOSED_MOCK,
        error_code="UNKNOWN_INVOICE",
    )
