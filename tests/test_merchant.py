from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from merchant import mock_checkout, zepto_checkout
from merchant.models import ExecutionMode, MerchantQuote, StockStatus
from merchant.zepto_mcp import ZeptoMCPClient, ZeptoMCPError


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
    observed_at = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    quote = zepto_checkout.quote_from_preview(
        {"order": {"toPay": "412.50", "orderId": "preview-1", "inStock": True}},
        merchant_sku_id="coffee-500g",
        product_name="Coffee",
        quantity=1,
        address_ref="saved-address-1",
        observed_at=observed_at,
    )
    assert quote.amount == Decimal("412.50")
    assert quote.stock_status is StockStatus.IN_STOCK
    assert quote.quote_reference.startswith("zepto:v1:")
    assert "saved-address-1" not in quote.quote_reference


def test_terminal_to_pay_wins_over_nested_subtotal() -> None:
    quote = zepto_checkout.quote_from_preview(
        {
            "metadata": {"amount": "99.00", "subtotal": "99.00"},
            "order": {
                "toPay": "412.50",
                "deliverable": True,
                "currency": "INR",
                "orderId": "preview-terminal",
            },
        },
        merchant_sku_id="coffee-500g",
        product_name="Coffee",
        quantity=2,
        address_ref="saved-address-1",
    )
    assert quote.amount == Decimal("412.50")


@pytest.mark.parametrize(
    "preview, message",
    [
        ({"order": {"toPay": "0", "deliverable": True, "orderId": "q1"}}, "must be positive"),
        ({"order": {"toPay": "10", "orderId": "q2"}}, "explicitly state deliverability"),
        (
            {"order": {"toPay": "10", "deliverable": True, "currency": "USD", "orderId": "q3"}},
            "currency must be INR",
        ),
    ],
)
def test_preview_requires_positive_deliverable_inr_terminal_quote(
    preview, message
) -> None:
    with pytest.raises(zepto_checkout.ZeptoMCPError, match=message):
        zepto_checkout.quote_from_preview(
            preview,
            merchant_sku_id="coffee-500g",
            product_name="Coffee",
            quantity=1,
            address_ref="saved-address-1",
        )


def test_quote_fingerprint_binds_context_and_freshness() -> None:
    observed_at = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)

    def quote(quantity=1, address="address-1", amount="412.50", order_id="q-fingerprint"):
        return zepto_checkout.quote_from_preview(
            {"order": {"toPay": amount, "deliverable": True, "orderId": order_id}},
            merchant_sku_id="coffee-500g",
            product_name="Coffee",
            quantity=quantity,
            address_ref=address,
            observed_at=observed_at,
        )

    first = quote()
    assert first.quote_reference != quote(quantity=2).quote_reference
    assert first.quote_reference != quote(address="address-2").quote_reference
    assert first.quote_reference != quote(amount="400.00").quote_reference
    assert first.quote_reference != quote(order_id="other-cart").quote_reference
    assert zepto_checkout.quote_is_fresh(
        first, now=observed_at + timedelta(seconds=120)
    )
    assert not zepto_checkout.quote_is_fresh(
        first, now=observed_at + timedelta(seconds=121)
    )


def test_preview_rejects_merchant_returned_address_mismatch() -> None:
    with pytest.raises(zepto_checkout.ZeptoMCPError, match="address context"):
        zepto_checkout.quote_from_preview(
            {
                "order": {
                    "toPay": "412.50",
                    "deliverable": True,
                    "orderId": "q-address",
                    "userAddressId": "different-address",
                }
            },
            merchant_sku_id="coffee-500g",
            product_name="Coffee",
            quantity=1,
            address_ref="saved-address-1",
        )


def test_real_search_price_uses_exact_sku_and_minor_units() -> None:
    quote = zepto_checkout.quote_from_search(
        {
            "products": [
                {
                    "id": "other-sku",
                    "name": "A nearby product",
                    "price": 19900,
                    "availableQuantity": 5,
                },
                {
                    "productVariantId": "coffee-500g",
                    "name": "Exact Coffee",
                    "price": 38000,
                    "availableQuantity": 3,
                },
            ]
        },
        merchant_sku_id="coffee-500g",
        product_name="Coffee",
    )
    assert quote.amount == Decimal("380")
    assert quote.product_name == "Exact Coffee"
    assert quote.stock_status is StockStatus.IN_STOCK
    assert quote.execution_mode is ExecutionMode.REAL


def test_real_search_refuses_a_similar_product_substitution() -> None:
    with pytest.raises(ZeptoMCPError, match="refusing substitution"):
        zepto_checkout.quote_from_search(
            {
                "products": [
                    {
                        "id": "other-sku",
                        "name": "Similar Coffee",
                        "price": 35000,
                        "availableQuantity": 4,
                    }
                ]
            },
            merchant_sku_id="coffee-500g",
            product_name="Coffee",
        )


def test_real_price_check_calls_zepto_search(monkeypatch) -> None:
    class FakeClient:
        def search_products(self, query: str):
            assert query == "Coffee"
            return {
                "products": [
                    {
                        "id": "coffee-500g",
                        "name": "Coffee",
                        "price": 41250,
                        "availableQuantity": 2,
                    }
                ]
            }

    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    assert zepto_checkout.check_current_price(
        "item-1",
        merchant_sku_id="coffee-500g",
        product_name="Coffee",
        client=FakeClient(),
    ) == Decimal("412.5")


class FakeZeptoCartClient:
    def __init__(
        self,
        *,
        products=None,
        cart=None,
        payment_methods=None,
        preview=None,
    ) -> None:
        self.products = products or [
            {
                "productVariantId": "coffee-500g",
                "storeProductId": "store-coffee-500g",
                "name": "Exact Coffee",
                "price": 38000,
                "availableQuantity": 3,
            }
        ]
        self.cart = cart or {
            "cartItems": [{"productVariantId": "coffee-500g", "quantity": 1}]
        }
        self.payment_methods = payment_methods or {
            "paymentMethods": [
                {
                    "code": "ONLINE_CARD",
                    "displayName": "Pay Online (UPI / Cards / Wallets)",
                    "available": True,
                }
            ]
        }
        self.preview = preview or {
            "order": {"toPay": "412.50", "orderId": "preview-exact", "deliverable": True}
        }
        self.calls = []

    def select_saved_address(self, address_id):
        self.calls.append(("select_saved_address", address_id))
        return {"selected": address_id}

    def search_products(self, query):
        self.calls.append(("search_products", query))
        return {"products": self.products}

    def update_cart(self, arguments):
        self.calls.append(("update_cart", arguments))
        return {"updated": True}

    def view_cart(self):
        self.calls.append(("view_cart", None))
        return self.cart

    def get_payment_methods(self):
        self.calls.append(("get_payment_methods", None))
        return self.payment_methods

    def preview_order(self, address_id):
        self.calls.append(("preview_order", address_id))
        return self.preview


def test_exact_cart_preparation_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ZEPTO_CART_PREPARATION_ENABLED", raising=False)
    client = FakeZeptoCartClient()

    with pytest.raises(RuntimeError, match="cart preparation is disabled"):
        zepto_checkout.prepare_exact_cart_quote(
            "coffee-500g", "Coffee", "address-1", "device-1", client=client
        )

    assert client.calls == []


def test_exact_cart_preparation_uses_safe_schema_and_preview(monkeypatch) -> None:
    monkeypatch.setenv("ZEPTO_CART_PREPARATION_ENABLED", "1")
    client = FakeZeptoCartClient(
        products=[
            {
                "productVariantId": "similar-coffee",
                "storeProductId": "store-similar",
                "name": "Similar Coffee",
                "price": 30000,
                "availableQuantity": 5,
            },
            {
                "productVariantId": "coffee-500g",
                "storeProductId": "store-coffee-500g",
                "name": "Exact Coffee",
                "price": 38000,
                "availableQuantity": 3,
            },
        ]
    )

    quote = zepto_checkout.prepare_exact_cart_quote(
        "coffee-500g", "Coffee", "address-1", "device-1", client=client
    )

    assert quote.amount == Decimal("412.50")
    assert quote.quote_reference.startswith("zepto:v1:")
    assert [call[0] for call in client.calls] == [
        "select_saved_address",
        "search_products",
        "update_cart",
        "view_cart",
        "get_payment_methods",
        "preview_order",
    ]
    assert client.calls[2][1] == {
        "deviceId": "device-1",
        "cartItems": [
            {
                "productVariantId": "coffee-500g",
                "storeProductId": "store-coffee-500g",
                "quantity": 1,
            }
        ],
        "replaceCart": True,
    }


def test_preview_order_never_confirms_order(monkeypatch) -> None:
    client = ZeptoMCPClient()
    calls = []

    def fake_call(name, arguments=None):
        calls.append((name, arguments))
        return {"toPay": "412.50"}

    monkeypatch.setattr(client, "call", fake_call)

    client.preview_order("address-1")

    assert calls == [
        (
            "create_online_payment_order",
            {
                "confirmOrder": False,
                "riderTip": 0,
                "userAddressId": "address-1",
                "useZeptoCash": False,
            },
        )
    ]


def test_exact_cart_preparation_refuses_substitution_before_cart_mutation(monkeypatch) -> None:
    monkeypatch.setenv("ZEPTO_CART_PREPARATION_ENABLED", "1")
    client = FakeZeptoCartClient(
        products=[
            {
                "productVariantId": "similar-coffee",
                "storeProductId": "store-similar",
                "name": "Similar Coffee",
                "price": 30000,
                "availableQuantity": 5,
            }
        ]
    )

    with pytest.raises(ZeptoMCPError, match="refusing substitution"):
        zepto_checkout.prepare_exact_cart_quote(
            "coffee-500g", "Coffee", "address-1", "device-1", client=client
        )

    assert "update_cart" not in [call[0] for call in client.calls]


def test_exact_cart_preparation_refuses_out_of_stock_before_cart_mutation(monkeypatch) -> None:
    monkeypatch.setenv("ZEPTO_CART_PREPARATION_ENABLED", "1")
    client = FakeZeptoCartClient(
        products=[
            {
                "productVariantId": "coffee-500g",
                "storeProductId": "store-coffee-500g",
                "name": "Exact Coffee",
                "price": 38000,
                "availableQuantity": 0,
            }
        ]
    )

    with pytest.raises(ZeptoMCPError, match="out of stock"):
        zepto_checkout.prepare_exact_cart_quote(
            "coffee-500g", "Coffee", "address-1", "device-1", client=client
        )

    assert "update_cart" not in [call[0] for call in client.calls]


def test_exact_cart_preparation_refuses_cart_without_exact_sku(monkeypatch) -> None:
    monkeypatch.setenv("ZEPTO_CART_PREPARATION_ENABLED", "1")
    client = FakeZeptoCartClient(
        cart={"cartItems": [{"productVariantId": "different-sku", "quantity": 1}]}
    )

    with pytest.raises(ZeptoMCPError, match="does not exactly match"):
        zepto_checkout.prepare_exact_cart_quote(
            "coffee-500g", "Coffee", "address-1", "device-1", client=client
        )

    assert "preview_order" not in [call[0] for call in client.calls]


def test_cart_parser_never_accepts_sku_from_recommendations(monkeypatch) -> None:
    monkeypatch.setenv("ZEPTO_CART_PREPARATION_ENABLED", "1")
    client = FakeZeptoCartClient(
        cart={
            "cartItems": [{"productVariantId": "different-sku", "quantity": 1}],
            "recommendations": [
                {"productVariantId": "coffee-500g", "quantity": 1}
            ],
        }
    )

    with pytest.raises(ZeptoMCPError, match="does not exactly match"):
        zepto_checkout.prepare_exact_cart_quote(
            "coffee-500g", "Coffee", "address-1", "device-1", client=client
        )

    assert "preview_order" not in [call[0] for call in client.calls]


def test_exact_cart_preparation_refuses_unrequested_extra_item(monkeypatch) -> None:
    monkeypatch.setenv("ZEPTO_CART_PREPARATION_ENABLED", "1")
    client = FakeZeptoCartClient(
        cart={
            "cartItems": [
                {"productVariantId": "coffee-500g", "quantity": 1},
                {"productVariantId": "unrequested-snack", "quantity": 1},
            ]
        }
    )

    with pytest.raises(ZeptoMCPError, match="does not exactly match"):
        zepto_checkout.prepare_exact_cart_quote(
            "coffee-500g", "Coffee", "address-1", "device-1", client=client
        )

    assert "preview_order" not in [call[0] for call in client.calls]


def test_exact_cart_preparation_requires_available_online_card_method(monkeypatch) -> None:
    monkeypatch.setenv("ZEPTO_CART_PREPARATION_ENABLED", "1")
    client = FakeZeptoCartClient(
        payment_methods={
            "paymentMethods": [
                {"displayName": "Cash on Delivery", "available": True},
                {
                    "displayName": "Pay Online (UPI / Cards / Wallets)",
                    "available": False,
                },
            ]
        }
    )

    with pytest.raises(ZeptoMCPError, match="card method is unavailable"):
        zepto_checkout.prepare_exact_cart_quote(
            "coffee-500g", "Coffee", "address-1", "device-1", client=client
        )

    assert "preview_order" not in [call[0] for call in client.calls]


def test_payment_method_parser_rejects_unstructured_nested_card_text(monkeypatch) -> None:
    monkeypatch.setenv("ZEPTO_CART_PREPARATION_ENABLED", "1")
    client = FakeZeptoCartClient(
        payment_methods={
            "metadata": {"help": "cards accepted"},
            "paymentMethods": [{"displayName": "Cash on Delivery", "available": True}],
        }
    )

    with pytest.raises(ZeptoMCPError, match="card method is unavailable"):
        zepto_checkout.prepare_exact_cart_quote(
            "coffee-500g", "Coffee", "address-1", "device-1", client=client
        )


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
    monkeypatch.setenv("HOME_PAYMENT_MODE", "real")
    monkeypatch.delenv("ZEPTO_REAL_PAYMENT_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="real Zepto payment is disabled"):
        zepto_checkout.complete_checkout("credential", "coffee", "380", "intent")
