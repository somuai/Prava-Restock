from datetime import datetime, timezone
from decimal import Decimal

import pytest

from merchant import mock_checkout, zepto_checkout
from merchant.models import ExecutionMode, MerchantQuote, StockStatus


@pytest.fixture(autouse=True)
def isolated_checkout_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        mock_checkout, "CHECKOUT_STORE_PATH", tmp_path / "merchant_checkouts.json"
    )
    mock_checkout.reset()


def test_merchant_contract_models_are_typed() -> None:
    quote = MerchantQuote(
        merchant="zepto",
        merchant_sku_id="coffee-500g",
        product_name="Coffee",
        amount="380",
        currency="INR",
        stock_status="in_stock",
        quote_reference="quote-1",
        observed_at=datetime.now(timezone.utc),
        execution_mode="real",
    )
    assert quote.amount == Decimal("380")
    assert quote.execution_mode is ExecutionMode.REAL


def test_real_preview_is_normalized_without_payment_creation() -> None:
    quote = zepto_checkout.quote_from_preview(
        {"order": {"toPay": "412.50", "orderId": "preview-1", "inStock": True}},
        merchant_sku_id="coffee-500g",
        product_name="Coffee",
    )
    assert quote.amount == Decimal("412.50")
    assert quote.stock_status is StockStatus.IN_STOCK
    assert quote.quote_reference == "preview-1"


def test_disclosed_checkout_is_durable_and_idempotent() -> None:
    first = mock_checkout.complete_checkout(
        "credential", "coffee-500g", "380", "intent-1"
    )
    second = mock_checkout.complete_checkout(
        "different-credential", "coffee-500g", "999", "intent-1"
    )
    assert first == second
    assert first["execution_mode"] == "disclosed_mock"


def test_out_of_stock_never_silently_substitutes() -> None:
    result = mock_checkout.complete_checkout(
        "credential", "out-of-stock-coffee", "380", "intent-oos"
    )
    assert result["status"] == "out_of_stock"
    assert result["merchant_order_id"] is None
    assert result["charged_amount"] is None


def test_real_money_path_is_disabled_without_operator_flag(monkeypatch) -> None:
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.delenv("ZEPTO_REAL_PAYMENT_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="real Zepto payment is disabled"):
        zepto_checkout.complete_checkout("credential", "coffee", "380", "intent")

