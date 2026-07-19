"""Zepto quote integration with an explicitly disclosed payment boundary."""

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from merchant import mock_checkout
from merchant.models import ExecutionMode, MerchantQuote, StockStatus
from merchant.zepto_mcp import ZeptoMCPClient, ZeptoMCPError
from payments import prava_client


STUB_MODE = False
HOME_MERCHANT_MODE_ENV = "HOME_MERCHANT_MODE"
REAL_PAYMENT_MODE_ENV = "ZEPTO_REAL_PAYMENT_ENABLED"

_PRICE_CHECK_COUNTS: dict[str, int] = {}
_STUB_BASE_PRICES = {
    "00000000-0000-0000-0000-000000000101": Decimal("380.00"),
}
_STUB_PRICE_OFFSETS = (Decimal("0.00"), Decimal("-12.00"), Decimal("8.00"))
_ZEPTO_PRICE_MINOR_UNITS = Decimal("100")
_ZEPTO_PRODUCT_ID_KEYS = (
    "id",
    "productVariantId",
    "storeProductId",
    "cartProductId",
    "variantId",
)


def merchant_mode() -> ExecutionMode:
    raw = os.getenv(HOME_MERCHANT_MODE_ENV, ExecutionMode.DISCLOSED_MOCK.value)
    try:
        return ExecutionMode(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{HOME_MERCHANT_MODE_ENV} must be real, sandbox, or disclosed_mock"
        ) from exc


def _first_value(payload: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(payload, dict):
        for key in keys:
            if payload.get(key) is not None:
                return payload[key]
        for value in payload.values():
            found = _first_value(value, keys)
            if found is not None:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _first_value(value, keys)
            if found is not None:
                return found
    return None


def quote_from_preview(
    preview: dict[str, Any],
    *,
    merchant_sku_id: str,
    product_name: str,
) -> MerchantQuote:
    raw_amount = _first_value(preview, ("toPay", "total", "totalAmount", "amount"))
    if raw_amount is None:
        raise ValueError("Zepto preview did not contain a final amount")
    available = _first_value(
        preview,
        ("deliverable", "inStock", "available", "isAvailable"),
    )
    order_ref = _first_value(preview, ("quoteId", "orderId", "orderCode"))
    return MerchantQuote(
        merchant="zepto",
        merchant_sku_id=merchant_sku_id,
        product_name=product_name,
        amount=Decimal(str(raw_amount)),
        currency="INR",
        stock_status=(
            StockStatus.OUT_OF_STOCK if available is False else StockStatus.IN_STOCK
        ),
        quote_reference=str(order_ref or f"zepto_preview_{uuid4().hex}"),
        observed_at=datetime.now(timezone.utc),
        execution_mode=ExecutionMode.REAL,
    )


def fetch_real_quote(
    merchant_sku_id: str,
    product_name: str,
    address_id: str,
    *,
    client: ZeptoMCPClient | None = None,
) -> MerchantQuote:
    """Preview the already-prepared Zepto cart at its exact final amount."""
    mcp_client = client or ZeptoMCPClient()
    mcp_client.select_saved_address(address_id)
    preview = mcp_client.preview_order(address_id)
    return quote_from_preview(
        preview,
        merchant_sku_id=merchant_sku_id,
        product_name=product_name,
    )


def quote_from_search(
    payload: dict[str, Any],
    *,
    merchant_sku_id: str,
    product_name: str,
) -> MerchantQuote:
    """Normalize the exact Zepto SKU from a real search response.

    Zepto search prices are integer minor units. Product selection remains exact:
    a nearby result is never accepted when the requested SKU is absent.
    """
    products = payload.get("products")
    if not isinstance(products, list):
        raise ZeptoMCPError("Zepto search response did not contain products")

    product = next(
        (
            candidate
            for candidate in products
            if isinstance(candidate, dict)
            and merchant_sku_id
            in {str(candidate.get(key)) for key in _ZEPTO_PRODUCT_ID_KEYS}
        ),
        None,
    )
    if product is None:
        raise ZeptoMCPError(
            f"exact Zepto SKU {merchant_sku_id!r} was not returned; refusing substitution"
        )

    raw_price = product.get("price")
    if raw_price is None:
        raise ZeptoMCPError("exact Zepto product did not contain a current price")
    available_quantity = product.get("availableQuantity")
    stock_status = (
        StockStatus.OUT_OF_STOCK
        if available_quantity is not None and Decimal(str(available_quantity)) <= 0
        else StockStatus.IN_STOCK
    )
    observed_at = datetime.now(timezone.utc)
    exact_id = str(product.get("productVariantId") or product.get("id"))
    return MerchantQuote(
        merchant="zepto",
        merchant_sku_id=merchant_sku_id,
        product_name=str(product.get("name") or product_name),
        amount=Decimal(str(raw_price)) / _ZEPTO_PRICE_MINOR_UNITS,
        currency="INR",
        stock_status=stock_status,
        quote_reference=f"zepto_search:{exact_id}:{observed_at.isoformat()}",
        observed_at=observed_at,
        execution_mode=ExecutionMode.REAL,
    )


def fetch_real_price_quote(
    merchant_sku_id: str,
    product_name: str,
    *,
    client: ZeptoMCPClient | None = None,
) -> MerchantQuote:
    """Read the current unit price for one exact SKU without mutating the cart."""
    mcp_client = client or ZeptoMCPClient()
    return quote_from_search(
        mcp_client.search_products(product_name),
        merchant_sku_id=merchant_sku_id,
        product_name=product_name,
    )


def check_current_price(
    item_id,
    *,
    merchant_sku_id: str | None = None,
    product_name: str | None = None,
    client: ZeptoMCPClient | None = None,
) -> Decimal:
    """Read a real exact-SKU price in real mode; otherwise use demo fluctuations."""
    if not item_id:
        raise ValueError("item_id is required")
    if merchant_mode() is ExecutionMode.REAL:
        if not merchant_sku_id or not product_name:
            raise ValueError(
                "real Zepto price checks require merchant_sku_id and product_name"
            )
        quote = fetch_real_price_quote(
            merchant_sku_id,
            product_name,
            client=client,
        )
        if quote.stock_status is StockStatus.OUT_OF_STOCK:
            raise ZeptoMCPError(
                f"exact Zepto SKU {merchant_sku_id!r} is currently out of stock"
            )
        return quote.amount

    item_key = str(item_id)
    check_count = _PRICE_CHECK_COUNTS.get(item_key, 0)
    _PRICE_CHECK_COUNTS[item_key] = check_count + 1
    base_price = _STUB_BASE_PRICES.get(item_key, Decimal("399.00"))
    return base_price + _STUB_PRICE_OFFSETS[check_count % len(_STUB_PRICE_OFFSETS)]


def complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key):
    """Complete the safe configured boundary without silently spending real money."""
    mode = merchant_mode()
    if mode is ExecutionMode.REAL and os.getenv(REAL_PAYMENT_MODE_ENV) != "1":
        raise RuntimeError(
            "real Zepto payment is disabled; set ZEPTO_REAL_PAYMENT_ENABLED=1 only "
            "for an operator-controlled compatible-card checkout"
        )
    if mode is ExecutionMode.REAL:
        raise RuntimeError(
            "real payment-link browser execution requires an interactive operator; "
            "the API never performs it unattended"
        )

    response = mock_checkout.complete_checkout(
        credential_reference,
        merchant_sku_id,
        amount,
        idempotency_key,
    )
    status = "APPROVED" if response["status"] == "completed" else "DECLINED"
    if str(credential_reference).startswith("prava_credential_"):
        prava_client.finalize_credential(credential_reference, status)
    return response
