import json
from inspect import signature

import pytest

from merchant import zepto_checkout
from payments import prava_client


class FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self._body


def test_prava_contract_signatures_are_exact() -> None:
    assert str(signature(prava_client.create_intent)) == (
        "(merchant, amount, item_description, constraints)"
    )
    assert str(signature(prava_client.await_mandate)) == "(intent_ref)"


def test_merchant_contract_signature_is_exact() -> None:
    assert str(signature(zepto_checkout.complete_checkout)) == (
        "(credential_reference, merchant_sku_id, amount, idempotency_key)"
    )


def test_prava_client_normalizes_approved_result_without_exposing_tokens(
    monkeypatch,
) -> None:
    responses = iter(
        [
            {
                "session_id": "sess_unit_approved",
                "iframe_url": "https://sandbox.collect.prava.space/unit",
                "order_id": "ord_unit",
                "expires_at": "2099-12-31T23:59:59Z",
            },
            {
                "session_id": "sess_unit_approved",
                "order_id": "ord_unit",
                "status": "awaiting_result",
                "transactions": [
                    {
                        "txn_id": "txn_unit",
                        "line_items": [
                            {
                                "txn_ref_id": "txn_ref_unit",
                                "token": "virtual-network-token",
                                "dynamic_cvv": "unit-cvv",
                                "expiry_month": "12",
                                "expiry_year": "2099",
                            }
                        ],
                    }
                ],
            },
        ]
    )
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_unit_key")
    monkeypatch.setenv("PRAVA_SANDBOX_URL", "https://sandbox.api.prava.space")
    monkeypatch.setattr(
        prava_client,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(next(responses)),
    )

    intent_ref = prava_client.create_intent(
        "zepto", "450.00", "Coffee", {"poll_interval_seconds": 0}
    )
    mandate = prava_client.await_mandate(intent_ref)
    assert intent_ref == "sess_unit_approved"
    assert mandate["status"] == "approved"
    assert mandate["scope"] == {"merchant": "Zepto", "max_amount": "450.00"}
    assert mandate["credential_reference"].startswith("prava_credential_")
    serialized = json.dumps(mandate)
    assert "virtual-network-token" not in serialized
    assert "unit-cvv" not in serialized


def test_prava_client_normalizes_failed_session_as_rejected(monkeypatch) -> None:
    responses = iter(
        [
            {
                "session_id": "sess_unit_rejected",
                "iframe_url": "https://sandbox.collect.prava.space/unit",
                "order_id": "ord_unit",
                "expires_at": "2099-12-31T23:59:59Z",
            },
            {
                "session_id": "sess_unit_rejected",
                "status": "failed",
                "transactions": [
                    {
                        "txn_id": "txn_unit",
                        "line_items": [],
                        "error": {
                            "code": "PASSKEY_REJECTED",
                            "message": "User rejected passkey approval",
                        },
                    }
                ],
            },
        ]
    )
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_unit_key")
    monkeypatch.setenv("PRAVA_SANDBOX_URL", "https://sandbox.api.prava.space")
    monkeypatch.setattr(
        prava_client,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(next(responses)),
    )

    intent_ref = prava_client.create_intent(
        "zepto", 450, "Coffee", {"poll_interval_seconds": 0}
    )
    assert prava_client.await_mandate(intent_ref) == {
        "status": "rejected",
        "intent_ref": intent_ref,
    }


def test_stub_merchant_out_of_stock() -> None:
    response = zepto_checkout.complete_checkout(
        "stub_credential", "out-of-stock-coffee", 450, "intent-oos"
    )
    assert response["merchant_order_id"] is None
    assert response["status"] == "out_of_stock"
    assert response["execution_mode"] == "disclosed_mock"


def test_stub_merchant_checkout_is_idempotent() -> None:
    first = zepto_checkout.complete_checkout(
        "stub_credential", "coffee-500g", 450, "intent-repeat"
    )
    second = zepto_checkout.complete_checkout(
        "stub_credential", "coffee-500g", 450, "intent-repeat"
    )
    assert first == second
    assert first["status"] == "completed"


def test_prava_credential_can_be_consumed_only_once(monkeypatch) -> None:
    from datetime import datetime, timezone

    reference = "prava_credential_consume_once"
    prava_client._CREDENTIALS[reference] = {
        "token": "one-time-token",
        "dynamic_cvv": "123",
        "expiry_month": "12",
        "expiry_year": "2099",
        "session_id": "session",
        "txn_ref_id": "txn",
        "created_at": datetime.now(timezone.utc),
    }

    consumed = prava_client.consume_credential(reference)

    assert consumed["token"] == "one-time-token"
    assert reference not in prava_client._CREDENTIALS
    with pytest.raises(ValueError, match="already-consumed"):
        prava_client.consume_credential(reference)
