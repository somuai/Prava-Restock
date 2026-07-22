"""Zepto quote integration with an explicitly disclosed payment boundary."""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from merchant import mock_checkout
from merchant.models import CheckoutStatus, ExecutionMode, MerchantCheckoutResult, MerchantQuote, StockStatus
from merchant.zepto_mcp import ZeptoMCPClient, ZeptoMCPError
from payments import prava_client
from storage.repository import RestockRepository

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


@dataclass(frozen=True)
class PaymentRedirectPolicy:
    """Fail-closed navigation policy for the short-lived payment browser."""

    # Prava documents the surface only as "Zepto/Juspay" and does not publish
    # exact hosts. Production must inject hosts observed and approved by the
    # operator; guessing a broad vendor domain would weaken this boundary.
    allowed_hosts: tuple[str, ...]

    def __post_init__(self) -> None:
        normalized = tuple(host.lower().rstrip(".") for host in self.allowed_hosts)
        if not normalized or any(
            not host or ":" in host or "/" in host for host in normalized
        ):
            raise ValueError("payment redirect policy requires explicit valid hostnames")
        object.__setattr__(self, "allowed_hosts", normalized)

    def validate_url(self, url: str) -> str:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        allowed = host in self.allowed_hosts
        if (
            parsed.scheme != "https"
            or not host
            or not allowed
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
        ):
            raise ZeptoMCPError(
                "payment navigation URL is outside the Zepto/Juspay allowlist"
            )
        return url


class BrowserPaymentExecutor(Protocol):
    """Interactive boundary that may expose one-time fields only to the browser.

    The executor must call ``redirect_policy.validate_url`` before every
    navigation (including redirects) and return all visited URLs for a second
    fail-closed boundary check.
    """

    def execute(
        self,
        *,
        payment_link: str,
        token: str,
        dynamic_cvv: str,
        expiry_month: str,
        expiry_year: str,
        redirect_policy: PaymentRedirectPolicy,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class RealCheckoutRuntime:
    repository: RestockRepository
    client: Any
    address_id: str
    executor: BrowserPaymentExecutor | None = None
    redirect_policy: PaymentRedirectPolicy | None = None


_REAL_CHECKOUT_RUNTIME: RealCheckoutRuntime | None = None


def configure_real_checkout_runtime(runtime: RealCheckoutRuntime | None) -> None:
    """Explicitly inject the operator-controlled dependencies for real checkout."""

    global _REAL_CHECKOUT_RUNTIME
    _REAL_CHECKOUT_RUNTIME = runtime


def real_checkout_runtime_ready() -> bool:
    """Return whether durable merchant reconciliation dependencies are injected."""

    runtime = _REAL_CHECKOUT_RUNTIME
    return bool(
        runtime is not None
        and runtime.repository
        and runtime.client
        and runtime.address_id
    )


def real_payment_runtime_ready() -> bool:
    """Return whether the fail-closed, credential-bearing boundary is ready."""

    runtime = _REAL_CHECKOUT_RUNTIME
    return bool(
        real_checkout_runtime_ready()
        and runtime is not None
        and runtime.executor is not None
        and runtime.redirect_policy is not None
        and runtime.redirect_policy.allowed_hosts
    )


def reconcile_checkout(idempotency_key: str) -> dict[str, Any]:
    """Reconcile an existing checkout without a credential or new mutation."""

    runtime = _REAL_CHECKOUT_RUNTIME
    if not real_checkout_runtime_ready() or runtime is None:
        raise RuntimeError("real Zepto checkout reconciliation runtime is not configured")
    attempt = runtime.repository.get_merchant_checkout_attempt(str(idempotency_key))
    if attempt is None:
        raise KeyError(f"unknown merchant checkout attempt: {idempotency_key}")
    return _resume_existing_attempt(runtime, attempt)


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


def _checkout_result(
    status: CheckoutStatus,
    *,
    merchant_order_id: str | None,
    amount: Decimal | None,
    retryable: bool = False,
    error_code: str | None = None,
) -> dict[str, Any]:
    return MerchantCheckoutResult(
        status=status,
        merchant_order_id=merchant_order_id,
        charged_amount=amount if status is CheckoutStatus.COMPLETED else None,
        currency="INR",
        retryable=retryable,
        execution_mode=ExecutionMode.REAL,
        error_code=error_code,
    ).model_dump(mode="json")


def _parse_payment_order(
    payload: dict[str, Any], redirect_policy: PaymentRedirectPolicy
) -> tuple[str, str | None, str, Decimal]:
    order_id = _first_value(payload, ("orderId", "order_id"))
    order_code = _first_value(payload, ("orderCode", "order_code"))
    payment_link = _first_value(payload, ("paymentLink", "payment_link"))
    raw_amount = _first_value(payload, ("toPay", "totalAmount"))
    if not order_id or not payment_link or raw_amount is None:
        raise ZeptoMCPError(
            "Zepto payment-order response is missing orderId, paymentLink, or toPay"
        )
    link = redirect_policy.validate_url(str(payment_link))
    amount = Decimal(str(raw_amount)).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ZeptoMCPError("Zepto payment order returned a non-positive total")
    return str(order_id), str(order_code) if order_code else None, link, amount


def _normalized_payment_status(payload: Any) -> str | None:
    raw = _first_value(
        payload,
        ("paymentStatus", "payment_status", "status", "orderStatus", "order_status"),
    )
    return str(raw).strip().upper() if raw is not None else None


def _status_kind(status: str | None) -> str:
    if status in {"SUCCESS", "SUCCEEDED", "PAID", "COMPLETED", "CONFIRMED"}:
        return "approved"
    if status in {"FAILED", "DECLINED", "CANCELLED", "CANCELED", "EXPIRED"}:
        return "declined"
    return "pending"


def _find_order(payload: Any, order_id: str) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        candidate_id = _first_value(payload, ("orderId", "order_id"))
        if candidate_id is not None and str(candidate_id) == order_id:
            return payload
        for value in payload.values():
            found = _find_order(value, order_id)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_order(value, order_id)
            if found is not None:
                return found
    return None


def _reconcile_order(client: Any, order_id: str) -> str:
    """Resolve terminal status without ever creating another merchant order."""

    try:
        first = client.check_payment_status(order_id, poll=False)
        kind = _status_kind(_normalized_payment_status(first))
        if kind != "pending":
            return kind
        polled = client.check_payment_status(order_id, poll=True)
        kind = _status_kind(_normalized_payment_status(polled))
        if kind != "pending":
            return kind
    except Exception:
        pass
    try:
        order = _find_order(client.list_order_history(), order_id)
    except Exception:
        order = None
    return _status_kind(_normalized_payment_status(order)) if order else "pending"


def _deliver_prava_report(
    repository: RestockRepository,
    attempt: dict[str, Any],
    credential_reference: str | None = None,
) -> dict[str, Any]:
    """Deliver one queued terminal report without blind retries.

    A crash after the remote POST but before the database commit leaves the
    row in ``sending``/``ambiguous``. A later reconciliation reads Prava's
    payment-result endpoint but never repeats the POST: a non-terminal read may
    lag the original write and is not proof that the first POST was unapplied.
    """

    if not attempt.get("credential_exposed") or not attempt.get("report_status"):
        return attempt
    if attempt.get("report_state") == "confirmed":
        return attempt

    if attempt.get("report_state") in {"sending", "ambiguous"}:
        remote = prava_client.get_payment_result_status(str(attempt["prava_session_id"]))
        desired = str(attempt["report_status"])
        matches = (desired == "APPROVED" and remote == "completed") or (
            desired == "DECLINED" and remote == "failed"
        )
        if matches:
            attempt = repository.update_merchant_checkout_attempt(
                attempt["idempotency_key"],
                expected_report_states={str(attempt["report_state"])},
                report_state="confirmed",
                prava_reported=True,
            )
            if credential_reference:
                prava_client.retire_credential(credential_reference)
            return attempt
        # Prava does not document report-status idempotency and payment-result
        # may lag. Any non-terminal observation therefore keeps the outbox
        # ambiguous; only an explicit operator resolution may permit a retry.
        return attempt

    claimed = repository.claim_merchant_checkout_report(attempt["idempotency_key"])
    if claimed is None:
        return (
            repository.get_merchant_checkout_attempt(attempt["idempotency_key"])
            or attempt
        )
    try:
        prava_client.report_checkout_outcome(
            str(claimed["prava_session_id"]),
            str(claimed["prava_txn_ref_id"]),
            str(claimed["report_status"]),
        )
    except Exception:
        return repository.update_merchant_checkout_attempt(
            claimed["idempotency_key"],
            expected_report_states={"sending"},
            report_state="ambiguous",
            last_error="PRAVA_REPORT_AMBIGUOUS",
        )
    attempt = repository.update_merchant_checkout_attempt(
        claimed["idempotency_key"],
        expected_report_states={"sending"},
        report_state="confirmed",
        prava_reported=True,
    )
    if credential_reference:
        prava_client.retire_credential(credential_reference)
    return attempt


def _persist_terminal_outcome(
    repository: RestockRepository,
    attempt: dict[str, Any],
    outcome: str,
) -> dict[str, Any]:
    terminal_state = "completed" if outcome == "approved" else "declined"
    changes: dict[str, Any] = {
        "state": terminal_state,
        "credential_used": (
            bool(attempt.get("credential_used")) or outcome == "approved"
        ),
        "last_error": None if outcome == "approved" else "PAYMENT_DECLINED",
    }
    if attempt.get("credential_exposed") and attempt.get("report_state") != "confirmed":
        changes.update(
            report_status="APPROVED" if outcome == "approved" else "DECLINED",
            report_state="pending",
        )
    try:
        return repository.update_merchant_checkout_attempt(
            attempt["idempotency_key"],
            expected_states={str(attempt["state"])},
            **changes,
        )
    except ValueError:
        # A competing reconciler won the compare-and-swap. Return its result.
        current = repository.get_merchant_checkout_attempt(attempt["idempotency_key"])
        if current is None:
            raise
        return current


def _resume_existing_attempt(
    runtime: RealCheckoutRuntime,
    attempt: dict[str, Any],
    credential_reference: str | None = None,
) -> dict[str, Any]:
    state = str(attempt["state"])
    order_id = attempt.get("merchant_order_id")
    amount = Decimal(str(attempt["expected_amount"]))
    if state == "completed":
        _deliver_prava_report(runtime.repository, attempt, credential_reference)
        return _checkout_result(
            CheckoutStatus.COMPLETED,
            merchant_order_id=order_id,
            amount=amount,
        )
    if state == "declined":
        _deliver_prava_report(runtime.repository, attempt, credential_reference)
        return _checkout_result(
            CheckoutStatus.FAILED,
            merchant_order_id=order_id,
            amount=None,
            error_code=attempt.get("last_error") or "PAYMENT_DECLINED",
        )
    if state in {"failed", "price_changed"}:
        checkout_status = (
            CheckoutStatus.PRICE_CHANGED
            if state == "price_changed"
            else CheckoutStatus.FAILED
        )
        return _checkout_result(
            checkout_status,
            merchant_order_id=order_id,
            amount=None,
            error_code=attempt.get("last_error") or state.upper(),
        )
    if not order_id:
        # `creating_order` was persisted before the remote mutation. After a crash,
        # absence of a response is ambiguous, so a retry must never create again.
        return _checkout_result(
            CheckoutStatus.PENDING,
            merchant_order_id=None,
            amount=None,
            retryable=False,
            error_code="AMBIGUOUS_ORDER_CREATION",
        )
    outcome = _reconcile_order(runtime.client, str(order_id))
    if outcome == "pending":
        try:
            runtime.repository.update_merchant_checkout_attempt(
                attempt["idempotency_key"],
                expected_states={state},
                state="pending",
                last_error="PAYMENT_PENDING",
            )
        except ValueError:
            pass
        return _checkout_result(
            CheckoutStatus.PENDING,
            merchant_order_id=str(order_id),
            amount=None,
            retryable=True,
            error_code="PAYMENT_PENDING",
        )
    attempt = _persist_terminal_outcome(runtime.repository, attempt, outcome)
    _deliver_prava_report(runtime.repository, attempt, credential_reference)
    return _checkout_result(
        CheckoutStatus.COMPLETED if outcome == "approved" else CheckoutStatus.FAILED,
        merchant_order_id=str(order_id),
        amount=amount if outcome == "approved" else None,
        error_code=None if outcome == "approved" else "PAYMENT_DECLINED",
    )


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
    if mode is not ExecutionMode.REAL:
        response = mock_checkout.complete_checkout(
            credential_reference,
            merchant_sku_id,
            amount,
            idempotency_key,
        )
        # A disclosed simulation never consumes the Prava card credential and must
        # not be reported as though a merchant authorization occurred.
        return response

    runtime = _REAL_CHECKOUT_RUNTIME
    if not real_payment_runtime_ready() or runtime is None:
        raise RuntimeError(
            "real payment-link executor/redirect policy is not configured; refusing to "
            "create a Zepto order"
        )
    if not runtime.address_id:
        raise RuntimeError("real Zepto checkout requires an injected saved address ID")
    if not credential_reference or not merchant_sku_id or not idempotency_key:
        raise ValueError("credential reference, SKU, and idempotency key are required")
    expected_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    if expected_amount <= 0:
        raise ValueError("amount must be positive")

    existing = runtime.repository.get_merchant_checkout_attempt(str(idempotency_key))
    if existing is not None:
        if (
            existing["merchant"] != "zepto"
            or existing["merchant_sku_id"] != str(merchant_sku_id)
            or Decimal(str(existing["expected_amount"])) != expected_amount
            or existing["currency"] != "INR"
        ):
            raise ValueError("idempotency key is already bound to another checkout")
        return _resume_existing_attempt(
            runtime, existing, str(credential_reference)
        )

    reporting = prava_client.credential_reporting_context(str(credential_reference))
    attempt, created = runtime.repository.reserve_merchant_checkout_attempt(
        idempotency_key=str(idempotency_key),
        merchant="zepto",
        merchant_sku_id=str(merchant_sku_id),
        expected_amount=expected_amount,
        currency="INR",
        prava_session_id=reporting["session_id"],
        prava_txn_ref_id=reporting["txn_ref_id"],
    )
    if not created:
        return _resume_existing_attempt(runtime, attempt)

    runtime.repository.update_merchant_checkout_attempt(
        str(idempotency_key),
        expected_states={"reserved"},
        state="creating_order",
    )
    try:
        payment_order = runtime.client.create_payment_link(runtime.address_id)
    except Exception:
        # The remote call may have committed before the connection failed. Persist
        # ambiguity and require operator/order-history reconciliation; never retry.
        runtime.repository.update_merchant_checkout_attempt(
            str(idempotency_key),
            expected_states={"creating_order"},
            state="ambiguous",
            last_error="ORDER_CREATION_AMBIGUOUS",
        )
        try:
            # There is no safe identifier to attach an order here; inspection is
            # diagnostic only and must never guess or trigger another creation.
            runtime.client.list_order_history()
        except Exception:
            pass
        return _checkout_result(
            CheckoutStatus.PENDING,
            merchant_order_id=None,
            amount=None,
            retryable=False,
            error_code="ORDER_CREATION_AMBIGUOUS",
        )

    try:
        order_id, order_code, payment_link, final_amount = _parse_payment_order(
            payment_order, runtime.redirect_policy
        )
    except (ValueError, ZeptoMCPError):
        runtime.repository.update_merchant_checkout_attempt(
            str(idempotency_key),
            expected_states={"creating_order"},
            state="ambiguous",
            last_error="INVALID_PAYMENT_ORDER_RESPONSE",
        )
        raise

    attempt = runtime.repository.update_merchant_checkout_attempt(
        str(idempotency_key),
        expected_states={"creating_order"},
        state="order_created",
        merchant_order_id=order_id,
        merchant_order_code=order_code,
    )
    if final_amount != expected_amount:
        runtime.repository.update_merchant_checkout_attempt(
            str(idempotency_key),
            expected_states={"order_created"},
            state="price_changed",
            last_error="PRICE_CHANGED",
        )
        return _checkout_result(
            CheckoutStatus.PRICE_CHANGED,
            merchant_order_id=order_id,
            amount=None,
            error_code="PRICE_CHANGED",
        )

    # Persist exposure intent before the consume-once operation. If the process
    # dies after this commit, restart reconciliation treats the payment as
    # ambiguous and can never consume or execute it again.
    runtime.repository.update_merchant_checkout_attempt(
        str(idempotency_key),
        expected_states={"order_created"},
        state="executing",
        credential_exposed=True,
        credential_used=False,
    )
    credential = prava_client.consume_credential(str(credential_reference))
    try:
        execution = runtime.executor.execute(
            payment_link=payment_link,
            token=str(credential["token"]),
            dynamic_cvv=str(credential["dynamic_cvv"]),
            expiry_month=str(credential["expiry_month"]),
            expiry_year=str(credential["expiry_year"]),
            redirect_policy=runtime.redirect_policy,
        )
        if not isinstance(execution, dict) or not isinstance(
            execution.get("visited_urls"), list
        ):
            raise RuntimeError("payment executor must return visited_urls")
        for visited_url in execution["visited_urls"]:
            runtime.redirect_policy.validate_url(str(visited_url))
        credential_used = execution.get("credential_used") is True
        runtime.repository.update_merchant_checkout_attempt(
            str(idempotency_key),
            expected_states={"executing"},
            credential_used=credential_used,
        )
    except Exception:
        # The executor had the credential and may have submitted it. Reconcile the
        # merchant state before deciding whether any Prava status can be reported.
        runtime.repository.update_merchant_checkout_attempt(
            str(idempotency_key),
            expected_states={"executing"},
            state="ambiguous",
            last_error="BROWSER_EXECUTION_AMBIGUOUS",
        )

    attempt = runtime.repository.get_merchant_checkout_attempt(str(idempotency_key))
    assert attempt is not None
    return _resume_existing_attempt(
        runtime, attempt, str(credential_reference)
    )
