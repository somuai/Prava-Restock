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


def test_prava_configuration_is_environment_bound_and_live_is_gated(monkeypatch) -> None:
    monkeypatch.setenv("PRAVA_API_KEY", "sk_live_unit_key")
    monkeypatch.setenv("PRAVA_API_URL", "https://api.prava.space")
    monkeypatch.delenv("PRAVA_PRODUCTION_ENABLED", raising=False)

    with pytest.raises(RuntimeError, match="production is disabled"):
        prava_client._load_prava_config()

    monkeypatch.setenv("PRAVA_PRODUCTION_ENABLED", "1")
    assert prava_client._load_prava_config() == (
        "sk_live_unit_key",
        "https://api.prava.space",
    )

    monkeypatch.setenv("PRAVA_API_URL", "https://sandbox.api.prava.space")
    with pytest.raises(RuntimeError, match="live keys require"):
        prava_client._load_prava_config()


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


def test_completed_prava_session_never_reissues_checkout_credentials(monkeypatch) -> None:
    responses = iter(
        [
            {
                "session_id": "sess_unit_completed",
                "iframe_url": "https://sandbox.collect.prava.space/unit",
                "order_id": "ord_unit",
                "expires_at": "2099-12-31T23:59:59Z",
            },
            {
                "session_id": "sess_unit_completed",
                "status": "completed",
                "transactions": [],
            },
        ]
    )
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_unit_key")
    monkeypatch.setenv("PRAVA_SANDBOX_URL", "https://sandbox.api.prava.space")
    monkeypatch.delenv("PRAVA_API_URL", raising=False)
    monkeypatch.setattr(
        prava_client,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(next(responses)),
    )

    intent_ref = prava_client.create_intent(
        "zepto", 450, "Coffee", {"poll_interval_seconds": 0}
    )
    with pytest.raises(RuntimeError, match="already completed"):
        prava_client.await_mandate(intent_ref)


def test_prava_polling_context_can_be_restored_without_approval_url(monkeypatch) -> None:
    prava_client._INTENTS.clear()
    prava_client.register_intent_context(
        "sess_restored",
        merchant="Zepto",
        amount="412.50",
        constraints={"currency": "INR"},
    )

    restored = prava_client._INTENTS["sess_restored"]
    assert restored["merchant"] == "Zepto"
    assert restored["amount"] == "412.50"
    assert restored["expires_at"] is None
    assert "iframe_url" not in restored


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
        "consumed_at": None,
    }

    consumed = prava_client.consume_credential(reference)

    assert consumed["token"] == "one-time-token"
    assert reference in prava_client._CREDENTIALS
    retained = prava_client._CREDENTIALS[reference]
    assert retained["session_id"] == "session"
    assert retained["txn_ref_id"] == "txn"
    assert retained["consumed_at"] is not None
    assert "token" not in retained
    assert "dynamic_cvv" not in retained
    with pytest.raises(ValueError, match="already-consumed"):
        prava_client.consume_credential(reference)


def test_prava_credential_must_be_consumed_before_status_report(monkeypatch) -> None:
    from datetime import datetime, timezone

    reference = "prava_credential_not_consumed"
    prava_client._CREDENTIALS[reference] = {
        "token": "one-time-token",
        "dynamic_cvv": "123",
        "expiry_month": "12",
        "expiry_year": "2099",
        "session_id": "session",
        "txn_ref_id": "txn",
        "created_at": datetime.now(timezone.utc),
        "consumed_at": None,
    }

    with pytest.raises(ValueError, match="must be consumed"):
        prava_client.finalize_credential(reference, "APPROVED")


def test_prava_status_report_uses_retained_refs_then_deletes_record(monkeypatch) -> None:
    from datetime import datetime, timezone

    reference = "prava_credential_report"
    prava_client._CREDENTIALS[reference] = {
        "token": "one-time-token",
        "dynamic_cvv": "123",
        "expiry_month": "12",
        "expiry_year": "2099",
        "session_id": "session",
        "txn_ref_id": "txn",
        "created_at": datetime.now(timezone.utc),
        "consumed_at": None,
    }
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_unit_key")
    monkeypatch.setenv("PRAVA_SANDBOX_URL", "https://sandbox.api.prava.space")
    captured = {}

    def fake_urlopen(request, **_kwargs):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        return FakeResponse(
            {
                "status": "confirmed",
                "txn_ref_id": "txn",
                "txn_status": "APPROVED",
                "visa_confirmation": "SUCCESS",
            }
        )

    monkeypatch.setattr(prava_client, "urlopen", fake_urlopen)
    prava_client.consume_credential(reference)
    prava_client.finalize_credential(reference, "APPROVED")

    assert captured["url"].endswith("/v1/sessions/session/report-status")
    assert captured["payload"] == {"txn_ref_id": "txn", "txn_status": "APPROVED"}
    assert reference not in prava_client._CREDENTIALS


def test_disclosed_checkout_never_reports_a_simulation_to_prava(monkeypatch) -> None:
    monkeypatch.setenv("HOME_MERCHANT_MODE", "disclosed_mock")
    monkeypatch.setattr(
        prava_client,
        "finalize_credential",
        lambda *_args: pytest.fail("simulation must not report a real merchant outcome"),
    )

    response = zepto_checkout.complete_checkout(
        "prava_credential_not_really_used", "coffee-500g", 450, "simulation-only"
    )

    assert response["status"] == "completed"
    assert response["execution_mode"] == "disclosed_mock"
