"""Factory for exact, serialized Home merchant quotes.

The provider owns the Zepto cart lease because ``replaceCart`` is user-scoped:
two workflows for the same user must never prepare or charge different carts
concurrently.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import os
from typing import Any
from uuid import uuid4

from merchant import zepto_checkout
from merchant.models import ExecutionMode, MerchantQuote, StockStatus
from merchant.zepto_mcp import ZeptoMCPError
from payments.models import TrackedItem
from storage.repository import RestockRepository


class HomeQuoteError(RuntimeError):
    """A safe, non-secret reason why an exact Home quote cannot be produced."""


@dataclass
class CartLease:
    preserve_until_expiry: bool = False

    def preserve(self) -> None:
        self.preserve_until_expiry = True


class HomeQuoteProvider:
    def __init__(
        self,
        repository: RestockRepository,
        *,
        zepto_client: Any | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.repository = repository
        self.zepto_client = zepto_client
        self.environment = environment if environment is not None else os.environ

    @staticmethod
    def _lease_name(item: TrackedItem) -> str:
        return f"merchant-cart:zepto:{item.user_id}"

    @staticmethod
    def supports(item: TrackedItem) -> bool:
        return (
            item.trigger_type.value == "predicted"
            and item.preferred_merchant.value == "zepto"
        )

    @staticmethod
    def _owner_id(owner_key: str | None) -> str:
        if owner_key is None:
            return f"quote-{uuid4().hex}"
        return f"checkout-{sha256(owner_key.encode('utf-8')).hexdigest()}"

    @contextmanager
    def checkout_scope(
        self, item: TrackedItem, *, owner_key: str | None = None
    ) -> Iterator[CartLease]:
        """Serialize exact cart preparation through the checkout mutation."""

        if zepto_checkout.merchant_mode() is not ExecutionMode.REAL:
            yield CartLease()
            return
        owner_id = self._owner_id(owner_key)
        seconds = int(self.environment.get("ZEPTO_CART_LEASE_SECONDS", "300"))
        seconds = min(max(seconds, 30), 900)
        lease_name = self._lease_name(item)
        acquired = self.repository.acquire_lease(
            lease_name=lease_name,
            owner_id=owner_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=seconds),
        )
        if not acquired:
            raise HomeQuoteError(
                "another checkout is using this user's Zepto cart; retry later"
            )
        lease = CartLease()
        try:
            yield lease
        finally:
            if not lease.preserve_until_expiry:
                self.repository.release_lease(lease_name=lease_name, owner_id=owner_id)

    def release_checkout_scope(self, item: TrackedItem, *, owner_key: str) -> bool:
        """Release a preserved checkout lease using its deterministic owner token."""

        return self.repository.release_lease(
            lease_name=self._lease_name(item),
            owner_id=self._owner_id(owner_key),
        )

    def quote_locked(self, item: TrackedItem) -> MerchantQuote:
        """Produce a quote while the caller holds ``checkout_scope`` in real mode."""

        if item.trigger_type.value != "predicted":
            raise HomeQuoteError("Home quote provider only accepts predicted items")
        if item.preferred_merchant.value != "zepto":
            raise HomeQuoteError("real Home quoting currently supports exact Zepto SKUs only")
        if zepto_checkout.merchant_mode() is not ExecutionMode.REAL:
            amount = item.last_observed_price or item.last_purchase_amount
            if amount is None:
                raise HomeQuoteError("mock quote requires an observed or prior purchase price")
            return MerchantQuote(
                merchant="zepto",
                merchant_sku_id=item.merchant_sku_id,
                product_name=item.name,
                amount=Decimal(str(amount)),
                currency=item.currency,
                stock_status=StockStatus.IN_STOCK,
                quote_reference=f"mock:{item.item_id}:{Decimal(str(amount))}",
                observed_at=datetime.now(timezone.utc),
                execution_mode=ExecutionMode.DISCLOSED_MOCK,
            )

        address_ref = (item.merchant_address_ref or "").strip()
        device_id = self.environment.get("ZEPTO_DEVICE_ID", "").strip()
        if not address_ref:
            raise HomeQuoteError("real Zepto quote requires a saved merchant address reference")
        if not device_id:
            raise HomeQuoteError("real Zepto quote requires ZEPTO_DEVICE_ID")
        try:
            return zepto_checkout.prepare_exact_cart_quote(
                item.merchant_sku_id,
                item.name,
                address_ref,
                device_id,
                quantity=item.quantity or 1,
                client=self.zepto_client,
            )
        except ZeptoMCPError as exc:
            raise HomeQuoteError(str(exc)) from exc

    def revalidate_locked(self, item: TrackedItem) -> MerchantQuote:
        """Verify the already-prepared exact cart without replacing it again."""

        if zepto_checkout.merchant_mode() is not ExecutionMode.REAL:
            return self.quote_locked(item)
        address_ref = (item.merchant_address_ref or "").strip()
        if not address_ref or item.quantity is None:
            raise HomeQuoteError("real Zepto revalidation requires saved address and quantity")
        try:
            quote = zepto_checkout.fetch_real_quote(
                item.merchant_sku_id,
                item.name,
                address_ref,
                quantity=item.quantity,
                client=self.zepto_client,
            )
        except ZeptoMCPError as exc:
            raise HomeQuoteError(str(exc)) from exc
        max_age = int(self.environment.get("ZEPTO_QUOTE_MAX_AGE_SECONDS", "60"))
        if not zepto_checkout.quote_is_fresh(
            quote, ttl=timedelta(seconds=max(1, max_age))
        ):
            raise HomeQuoteError("Zepto quote is stale; refusing checkout")
        return quote

    def __call__(self, item: TrackedItem) -> MerchantQuote:
        with self.checkout_scope(item):
            return self.quote_locked(item)


def build_home_quote_provider(
    repository: RestockRepository,
    *,
    zepto_client: Any | None = None,
    environment: Mapping[str, str] | None = None,
) -> HomeQuoteProvider:
    """Build the canonical provider used by workers and passkey resumption."""

    return HomeQuoteProvider(
        repository,
        zepto_client=zepto_client,
        environment=environment,
    )


def build_checkout_context_provider(repository: RestockRepository):
    """Resolve non-secret, durable cart context for the real checkout boundary."""

    def resolve(idempotency_key: str) -> zepto_checkout.CheckoutCartContext:
        run = repository.workflow_for_checkout_key(idempotency_key)
        item = repository.get_item(run["item_id"])
        quote = run.get("quote")
        if not isinstance(quote, dict):
            raise HomeQuoteError("checkout requires a persisted exact quote")
        address_ref = (item.merchant_address_ref or "").strip()
        quantity = item.quantity
        if not address_ref or quantity is None:
            raise HomeQuoteError("checkout requires saved address and quantity context")
        if str(quote.get("merchant_sku_id")) != item.merchant_sku_id:
            raise HomeQuoteError("persisted quote does not match the tracked exact SKU")
        merchant_context_reference = str(
            quote.get("merchant_context_reference") or ""
        ).strip()
        if not merchant_context_reference:
            raise HomeQuoteError("persisted quote lacks merchant cart/order context")
        if str(quote.get("currency")) != str(run["currency"]):
            raise HomeQuoteError("persisted quote currency does not match the workflow")
        observed_at = datetime.fromisoformat(str(quote["observed_at"]).replace("Z", "+00:00"))
        return zepto_checkout.CheckoutCartContext(
            merchant_sku_id=item.merchant_sku_id,
            quantity=quantity,
            merchant_address_ref=address_ref,
            quoted_amount=Decimal(str(run["proposed_amount"])),
            currency=str(quote["currency"]),
            merchant_context_reference=merchant_context_reference,
            quote_reference=str(quote["quote_reference"]),
            observed_at=observed_at,
        )

    return resolve
