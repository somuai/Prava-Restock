from inspect import signature

from merchant import zepto_checkout
from payments import prava_client


def test_prava_contract_signatures_are_exact() -> None:
    assert str(signature(prava_client.create_intent)) == (
        "(merchant, amount, item_description, constraints)"
    )
    assert str(signature(prava_client.await_mandate)) == "(intent_ref)"


def test_merchant_contract_signature_is_exact() -> None:
    assert str(signature(zepto_checkout.complete_checkout)) == (
        "(credential_reference, merchant_sku_id, amount, idempotency_key)"
    )


def test_stub_prava_happy_path() -> None:
    intent_ref = prava_client.create_intent(
        "zepto", "450.00", "Coffee", {"simulate_mandate": "approved"}
    )
    mandate = prava_client.await_mandate(intent_ref)
    assert intent_ref.startswith("stub_intent_")
    assert mandate["status"] == "approved"
    assert mandate["scope"] == {"merchant": "zepto", "max_amount": "450.00"}


def test_stub_prava_rejected_mandate() -> None:
    intent_ref = prava_client.create_intent(
        "zepto", 450, "Coffee", {"simulate_mandate": "rejected"}
    )
    assert prava_client.await_mandate(intent_ref) == {
        "status": "rejected",
        "intent_ref": intent_ref,
    }


def test_stub_merchant_out_of_stock() -> None:
    response = zepto_checkout.complete_checkout(
        "stub_credential", "out-of-stock-coffee", 450, "intent-oos"
    )
    assert response == {"merchant_order_id": None, "status": "out_of_stock"}


def test_stub_merchant_checkout_is_idempotent() -> None:
    first = zepto_checkout.complete_checkout(
        "stub_credential", "coffee-500g", 450, "intent-repeat"
    )
    second = zepto_checkout.complete_checkout(
        "stub_credential", "coffee-500g", 450, "intent-repeat"
    )
    assert first == second
    assert first["status"] == "completed"
