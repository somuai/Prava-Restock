from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from merchant.models import ExecutionMode, MerchantQuote, StockStatus
from merchant.quote_provider import (
    HomeQuoteError,
    build_checkout_context_provider,
    build_home_quote_provider,
)
from merchant import zepto_checkout
from payments.models import TrackedItem, User
from storage import Database, RestockRepository


def setup_item(repository: RestockRepository, *, sku: str = "coffee-exact") -> TrackedItem:
    user = User(
        user_id=uuid4(),
        display_name="Quote user",
        prava_account_ref="prava-quote-user",
        monthly_cap="5000",
        per_item_cap="1000",
        per_transaction_cap="1000",
        created_at=datetime.now(timezone.utc),
    )
    item = TrackedItem(
        item_id=uuid4(),
        user_id=user.user_id,
        name="Exact coffee",
        track="home",
        trigger_type="predicted",
        category="grocery",
        sensitive_flag=False,
        preferred_merchant="zepto",
        merchant_sku_id=sku,
        merchant_address_ref="saved-address-opaque",
        quantity=2,
        currency="INR",
        status="active",
        typical_cadence_days=14,
        last_purchased_at=date.today() - timedelta(days=13),
        last_purchase_amount="380",
    )
    repository.upsert_user(user)
    repository.upsert_item(item)
    return item


@pytest.fixture
def repository(tmp_path) -> RestockRepository:
    value = RestockRepository(Database(f"sqlite:///{tmp_path / 'quotes.db'}"))
    value.create_schema()
    return value


def test_disclosed_mock_quote_is_deterministic_and_exact(repository, monkeypatch) -> None:
    monkeypatch.setenv("HOME_MERCHANT_MODE", "disclosed_mock")
    item = setup_item(repository)
    provider = build_home_quote_provider(repository)

    first = provider(item)
    second = provider(item)

    assert first.amount == second.amount == Decimal("380")
    assert first.merchant_sku_id == second.merchant_sku_id == "coffee-exact"
    assert first.execution_mode is ExecutionMode.DISCLOSED_MOCK
    assert first.quote_reference == second.quote_reference


def test_production_never_falls_back_to_a_deterministic_quote(
    repository, monkeypatch
) -> None:
    monkeypatch.setenv("RESTOCK_ENV", "production")
    monkeypatch.setenv("HOME_MERCHANT_MODE", "disclosed_mock")
    item = setup_item(repository)

    with pytest.raises(HomeQuoteError, match="live Zepto catalog"):
        build_home_quote_provider(repository)(item)


def test_real_provider_passes_only_exact_item_context(repository, monkeypatch) -> None:
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setenv("ZEPTO_DEVICE_ID", "device-env-only")
    item = setup_item(repository)
    calls = []

    def fake_prepare(sku, name, address_ref, device_id, *, quantity, client):
        calls.append((sku, name, address_ref, device_id, quantity, client))
        return MerchantQuote(
            merchant="zepto",
            merchant_sku_id=sku,
            product_name=name,
            amount="399",
            currency="INR",
            stock_status=StockStatus.IN_STOCK,
            quote_reference="bound-quote-ref",
            observed_at=datetime.now(timezone.utc),
            execution_mode=ExecutionMode.REAL,
        )

    client = object()
    monkeypatch.setattr(zepto_checkout, "prepare_exact_cart_quote", fake_prepare)
    quote = build_home_quote_provider(repository, zepto_client=client)(item)

    assert quote.merchant_sku_id == "coffee-exact"
    assert calls == [(
        "coffee-exact",
        "Exact coffee",
        "saved-address-opaque",
        "device-env-only",
        2,
        client,
    )]


def test_cart_lease_prevents_second_item_from_replacing_same_user_cart(
    repository, monkeypatch
) -> None:
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setenv("ZEPTO_DEVICE_ID", "device-env-only")
    first = setup_item(repository, sku="coffee-one")
    second = first.model_copy(update={"item_id": uuid4(), "merchant_sku_id": "coffee-two"})
    repository.upsert_item(second)
    provider = build_home_quote_provider(repository)

    with provider.checkout_scope(first):
        with pytest.raises(HomeQuoteError, match="another checkout"):
            provider(second)

    # The owner-token release frees the profile only after the first scope exits.
    with provider.checkout_scope(second):
        pass


def test_checkout_context_resolves_only_from_persisted_run_and_item(repository) -> None:
    item = setup_item(repository)
    observed_at = datetime.now(timezone.utc)
    persisted_quote = zepto_checkout.quote_from_preview(
        {
            "order": {
                "toPay": "399",
                "deliverable": True,
                "orderId": "opaque-merchant-cart-ref",
            }
        },
        merchant_sku_id=item.merchant_sku_id,
        product_name=item.name,
        quantity=2,
        address_ref="saved-address-opaque",
        observed_at=observed_at,
    )
    run = repository.create_workflow(
        user_id=str(item.user_id),
        item_id=str(item.item_id),
        trigger_reason="predicted_depletion",
        proposed_amount="399",
        currency="INR",
        merchant="zepto",
        proposed_action=None,
        quote=persisted_quote.model_dump(mode="json"),
        modes={"home_payment": "real"},
        idempotency_key="bound-checkout-key",
    )

    context = build_checkout_context_provider(repository)(run["idempotency_key"])

    assert context.merchant_sku_id == item.merchant_sku_id
    assert context.quantity == 2
    assert context.merchant_address_ref == "saved-address-opaque"
    assert context.quoted_amount == Decimal("399")
    assert context.quote_reference == persisted_quote.quote_reference
    assert context.merchant_context_reference == "opaque-merchant-cart-ref"


def test_revalidation_checks_existing_exact_cart_without_replacing_it(
    repository, monkeypatch
) -> None:
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    item = setup_item(repository)
    calls = []

    def fake_fetch(sku, name, address_ref, *, quantity, client):
        calls.append((sku, address_ref, quantity, client))
        return MerchantQuote(
            merchant="zepto",
            merchant_sku_id=sku,
            product_name=name,
            amount="390",
            currency="INR",
            stock_status="in_stock",
            quote_reference="fresh-bound-reference",
            observed_at=datetime.now(timezone.utc),
            execution_mode="real",
        )

    monkeypatch.setattr(zepto_checkout, "fetch_real_quote", fake_fetch)
    client = object()
    provider = build_home_quote_provider(repository, zepto_client=client)
    with provider.checkout_scope(item):
        result = provider.revalidate_locked(item)

    assert result.amount == Decimal("390")
    assert calls == [("coffee-exact", "saved-address-opaque", 2, client)]


def test_pending_checkout_can_preserve_cart_lease_until_expiry(repository, monkeypatch) -> None:
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    item = setup_item(repository)
    provider = build_home_quote_provider(repository)

    with provider.checkout_scope(item) as lease:
        lease.preserve()

    with pytest.raises(HomeQuoteError, match="another checkout"):
        with provider.checkout_scope(item):
            pass


def test_stale_lease_owner_cannot_release_new_owner_claim(repository) -> None:
    now = datetime.now(timezone.utc)
    assert repository.acquire_lease(
        lease_name="merchant-cart:zepto:user",
        owner_id="old-owner",
        expires_at=now - timedelta(seconds=1),
    )
    assert repository.acquire_lease(
        lease_name="merchant-cart:zepto:user",
        owner_id="new-owner",
        expires_at=now + timedelta(minutes=5),
    )

    assert repository.release_lease(
        lease_name="merchant-cart:zepto:user", owner_id="old-owner"
    ) is False
    assert repository.acquire_lease(
        lease_name="merchant-cart:zepto:user",
        owner_id="third-owner",
        expires_at=now + timedelta(minutes=5),
    ) is False
    assert repository.release_lease(
        lease_name="merchant-cart:zepto:user", owner_id="new-owner"
    ) is True
