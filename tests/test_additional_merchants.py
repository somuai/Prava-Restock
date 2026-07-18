from decimal import Decimal

import pytest

from merchant import saas_invoice_checkout
from merchant.models import ExecutionMode, StockStatus
from merchant.swiggy_checkout import SwiggyAdapter


class FakeSwiggy:
    def view_cart(self):
        return {"cart": {"cartId": "cart-1", "toPay": "512.50", "available": True}}


def test_swiggy_quote_is_real_but_card_checkout_is_never_replaced_by_cod() -> None:
    adapter = SwiggyAdapter(FakeSwiggy())
    quote = adapter.quote(merchant_sku_id="sku-1", product_name="Rice")
    assert quote.amount == Decimal("512.50")
    assert quote.stock_status is StockStatus.IN_STOCK
    assert quote.execution_mode is ExecutionMode.REAL
    with pytest.raises(RuntimeError, match="never substitutes COD"):
        adapter.checkout("credential", "sku-1", quote.amount, "idem-1")


def test_swiggy_out_of_stock_is_not_substituted() -> None:
    adapter = SwiggyAdapter(FakeSwiggy())
    quote = adapter.quote(
        merchant_sku_id="sku-1",
        product_name="Rice",
        cart={"total": "500", "available": False},
    )
    assert quote.stock_status is StockStatus.OUT_OF_STOCK


def test_one_time_invoice_is_https_idempotent_and_disclosed(monkeypatch) -> None:
    quote = saas_invoice_checkout.quote_invoice(
        invoice_url="https://billing.example.test/invoice/123",
        vendor="Example SaaS",
        invoice_id="invoice-123",
        amount=Decimal("29"),
        currency="USD",
    )
    assert quote.execution_mode is ExecutionMode.REAL
    first = saas_invoice_checkout.complete_checkout("credential", "invoice-123", "29", "invoice-idem")
    second = saas_invoice_checkout.complete_checkout("credential", "invoice-123", "29", "invoice-idem")
    assert first == second
    assert first["execution_mode"] == "disclosed_mock"
    with pytest.raises(ValueError, match="HTTPS"):
        saas_invoice_checkout.quote_invoice(
            invoice_url="http://billing.example.test/invoice/123",
            vendor="Example SaaS",
            invoice_id="invoice-123",
            amount=Decimal("29"),
            currency="USD",
        )
    monkeypatch.setenv("TEAMS_RECURRING_ENABLED", "1")
    with pytest.raises(RuntimeError, match="pending Prava confirmation"):
        saas_invoice_checkout.complete_checkout("credential", "invoice-124", "29", "invoice-idem-2")
