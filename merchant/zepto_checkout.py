"""Zepto quote integration with an explicitly disclosed payment boundary."""

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from merchant import mock_checkout
from merchant.models import ExecutionMode, MerchantQuote, StockStatus
from merchant.zepto_mcp import ZeptoMCPClient, ZeptoMCPError
STUB_MODE = False
HOME_MERCHANT_MODE_ENV = "HOME_MERCHANT_MODE"
REAL_PAYMENT_MODE_ENV = "ZEPTO_REAL_PAYMENT_ENABLED"
CART_PREPARATION_MODE_ENV = "ZEPTO_CART_PREPARATION_ENABLED"

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


def _exact_search_product(
    payload: dict[str, Any], merchant_sku_id: str
) -> dict[str, Any]:
    products = payload.get("products")
    if not isinstance(products, list):
        raise ZeptoMCPError("Zepto search response did not contain products")
    product = next(
        (
            candidate
            for candidate in products
            if isinstance(candidate, dict)
            and merchant_sku_id
            in {
                str(candidate[key])
                for key in _ZEPTO_PRODUCT_ID_KEYS
                if candidate.get(key) is not None
            }
        ),
        None,
    )
    if product is None:
        raise ZeptoMCPError(
            f"exact Zepto SKU {merchant_sku_id!r} was not returned; refusing substitution"
        )
    return product


def _contains_exact_sku(payload: Any, merchant_sku_id: str) -> bool:
    if isinstance(payload, dict):
        identifiers = {
            str(payload[key])
            for key in _ZEPTO_PRODUCT_ID_KEYS
            if payload.get(key) is not None
        }
        return merchant_sku_id in identifiers or any(
            _contains_exact_sku(value, merchant_sku_id) for value in payload.values()
        )
    if isinstance(payload, list):
        return any(_contains_exact_sku(value, merchant_sku_id) for value in payload)
    return False


def _cart_line_items(payload: Any) -> list[dict[str, Any]] | None:
    """Find an explicit cart-item collection without accepting unrelated metadata."""
    if isinstance(payload, dict):
        for key in ("cartItems", "items", "products"):
            value = payload.get(key)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                if any(
                    any(item.get(id_key) is not None for id_key in _ZEPTO_PRODUCT_ID_KEYS)
                    for item in value
                ):
                    return value
        for value in payload.values():
            found = _cart_line_items(value)
            if found is not None:
                return found
    return None


def _online_card_method_available(payload: Any) -> bool:
    if isinstance(payload, dict):
        if any(
            payload.get(key) is False
            for key in ("available", "enabled", "isAvailable", "isEnabled")
        ):
            return False
        labels = " ".join(
            str(payload[key]).lower()
            for key in ("name", "displayName", "label", "method", "type", "code")
            if payload.get(key) is not None
        )
        if any(term in labels for term in ("card", "credit", "debit")):
            return True
        return any(_online_card_method_available(value) for value in payload.values())
    if isinstance(payload, list):
        return any(_online_card_method_available(value) for value in payload)
    if isinstance(payload, str):
        lowered = payload.lower()
        return any(term in lowered for term in ("card", "credit", "debit"))
    return False


def prepare_exact_cart_quote(
    merchant_sku_id: str,
    product_name: str,
    address_id: str,
    device_id: str,
    *,
    quantity: int = 1,
    client: ZeptoMCPClient | None = None,
) -> MerchantQuote:
    """Replace the cart with one exact SKU and create a non-confirming preview.

    This operation is disabled by default because it mutates the authenticated
    Zepto cart. It never creates a payment link and never calls the
    ``confirmOrder=true`` boundary.
    """
    if os.getenv(CART_PREPARATION_MODE_ENV) != "1":
        raise RuntimeError(
            "Zepto cart preparation is disabled; explicitly set "
            f"{CART_PREPARATION_MODE_ENV}=1 for an operator-controlled run"
        )
    if not all(value and str(value).strip() for value in (
        merchant_sku_id,
        product_name,
        address_id,
        device_id,
    )):
        raise ValueError("SKU, product name, address ID, and device ID are required")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("quantity must be a positive integer")

    mcp_client = client or ZeptoMCPClient()
    mcp_client.select_saved_address(address_id)
    product = _exact_search_product(
        mcp_client.search_products(product_name), merchant_sku_id
    )
    available_quantity = product.get("availableQuantity")
    if available_quantity is not None and Decimal(str(available_quantity)) < quantity:
        raise ZeptoMCPError(f"exact Zepto SKU {merchant_sku_id!r} is out of stock")

    product_variant_id = product.get("productVariantId") or product.get("id")
    store_product_id = product.get("storeProductId") or product.get("id")
    if product_variant_id is None or store_product_id is None:
        raise ZeptoMCPError("exact Zepto product lacks required cart identifiers")
    mcp_client.update_cart(
        {
            "deviceId": device_id,
            "cartItems": [
                {
                    "productVariantId": product_variant_id,
                    "storeProductId": store_product_id,
                    "quantity": quantity,
                }
            ],
            "replaceCart": True,
        }
    )
    cart = mcp_client.view_cart()
    cart_items = _cart_line_items(cart)
    exact_cart = (
        cart_items is not None
        and len(cart_items) == 1
        and _contains_exact_sku(cart_items[0], merchant_sku_id)
        and Decimal(str(cart_items[0].get("quantity", quantity))) == quantity
    )
    if not exact_cart:
        raise ZeptoMCPError(
            f"Zepto cart does not exactly match SKU {merchant_sku_id!r} and quantity; "
            "refusing preview"
        )
    if not _online_card_method_available(mcp_client.get_payment_methods()):
        raise ZeptoMCPError("Pay Online card method is unavailable")

    preview = mcp_client.preview_order(address_id)
    quote = quote_from_preview(
        preview,
        merchant_sku_id=merchant_sku_id,
        product_name=str(product.get("name") or product_name),
    )
    if quote.stock_status is StockStatus.OUT_OF_STOCK:
        raise ZeptoMCPError(f"exact Zepto SKU {merchant_sku_id!r} is out of stock")
    return quote


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
    product = _exact_search_product(payload, merchant_sku_id)

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
    # A disclosed simulation never consumes the Prava card credential and must not
    # be reported to Prava as though a real merchant authorization occurred.
    return response
