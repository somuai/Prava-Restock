import json
from io import BytesIO
from inspect import signature
from urllib.error import HTTPError

import pytest

from merchant import zepto_checkout
from payments import prava_client


class FakeResponse:
    def __init__(self, payload: dict, *, headers: dict | None = None):
        self._body = json.dumps(payload).encode("utf-8")
        self.headers = headers or {}

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
    assert str(signature(prava_client.get_payment_result)) == "(session_id)"
    assert str(signature(prava_client.report_status)) == (
        "(session_id, txn_ref_id, txn_status, authorization_code=None, "
        "response_code=None, amount_paid=None)"
    )


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
                "session_token": "session-token-unit",
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
    assert mandate["txn_ref_id"] == "txn_ref_unit"
    assert mandate["scope"] == {"merchant": "Zepto", "max_amount": "450.00"}
    assert mandate["credential_reference"].startswith("prava_credential_")
    serialized = json.dumps(mandate)
    assert "virtual-network-token" not in serialized
    assert "unit-cvv" not in serialized


def test_create_session_uses_documented_request_contract(monkeypatch) -> None:
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_unit_key")
    monkeypatch.setenv("PRAVA_SANDBOX_URL", "https://sandbox.api.prava.space")
    captured = {}

    def fake_urlopen(request, **kwargs):
        captured["url"] = request.full_url
        captured["method"] = request.method
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = kwargs["timeout"]
        captured["payload"] = json.loads(request.data)
        return FakeResponse(
            {
                "session_id": "sess_contract",
                "session_token": "session-token-contract",
                "iframe_url": "https://sandbox.collect.prava.space/contract",
                "order_id": "ord_contract",
                "expires_at": "2099-12-31T23:59:59Z",
            }
        )

    monkeypatch.setattr(prava_client, "urlopen", fake_urlopen)

    result = prava_client.create_session(
        "user-1",
        "user@example.com",
        "450.00",
        "inr",
        "Zepto",
        "https://www.zeptonow.com",
        "in",
        "Coffee",
        "450.00",
        product_id="coffee-500g",
    )

    assert captured["url"] == "https://sandbox.api.prava.space/v1/sessions"
    assert captured["method"] == "POST"
    assert captured["authorization"] == "Bearer sk_test_unit_key"
    assert captured["timeout"] == 20
    assert len(captured["payload"]["purchase_context"]) == 1
    context = captured["payload"]["purchase_context"][0]
    assert context["merchant_details"]["country_code_iso2"] == "IN"
    assert context["product_details"] == [
        {
            "description": "Coffee",
            "unit_price": "450.00",
            "quantity": 1,
            "product_id": "coffee-500g",
        }
    ]
    assert result["session_token"] == "session-token-contract"


def test_create_intent_forwards_request_timeout_to_http_transport(monkeypatch) -> None:
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_unit_key")
    monkeypatch.setenv("PRAVA_SANDBOX_URL", "https://sandbox.api.prava.space")
    captured = {}

    def fake_urlopen(_request, **kwargs):
        captured["timeout"] = kwargs["timeout"]
        return FakeResponse(
            {
                "session_id": "sess_timeout",
                "session_token": "session-token-timeout",
                "iframe_url": "https://sandbox.collect.prava.space/timeout",
                "order_id": "ord_timeout",
                "expires_at": "2099-12-31T23:59:59Z",
            }
        )

    monkeypatch.setattr(prava_client, "urlopen", fake_urlopen)

    prava_client.create_intent(
        "zepto",
        "9.99",
        "Timeout forwarding check",
        {"currency": "INR", "request_timeout_seconds": 60},
    )

    assert captured["timeout"] == 60


@pytest.mark.parametrize(
    "invalid_timeout",
    [True, False, float("nan"), float("inf"), 0, -1],
)
def test_create_intent_rejects_non_finite_or_non_positive_request_timeout(
    monkeypatch,
    invalid_timeout,
) -> None:
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_unit_key")
    monkeypatch.setenv("PRAVA_SANDBOX_URL", "https://sandbox.api.prava.space")
    monkeypatch.setattr(
        prava_client,
        "urlopen",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid request timeout must be rejected before transport"
        ),
    )

    with pytest.raises(
        ValueError,
        match="request_timeout_seconds must be a finite positive number",
    ):
        prava_client.create_intent(
            "zepto",
            "9.99",
            "Invalid timeout check",
            {"currency": "INR", "request_timeout_seconds": invalid_timeout},
        )


@pytest.mark.parametrize(
    "invalid_timeout",
    [True, False, float("nan"), float("inf"), 0, -1],
)
def test_private_session_transport_cannot_bypass_request_timeout_validation(
    monkeypatch,
    invalid_timeout,
) -> None:
    monkeypatch.setattr(
        prava_client,
        "urlopen",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid request timeout must be rejected before transport"
        ),
    )

    with pytest.raises(
        ValueError,
        match="request_timeout_seconds must be a finite positive number",
    ):
        prava_client._create_session(
            "user-1",
            "user@example.com",
            "9.99",
            "INR",
            "Zepto",
            "https://www.zeptonow.com",
            "IN",
            "Invalid timeout check",
            "9.99",
            request_timeout_seconds=invalid_timeout,
        )


def test_get_payment_result_uses_documented_request_contract(monkeypatch) -> None:
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_unit_key")
    monkeypatch.setenv("PRAVA_SANDBOX_URL", "https://sandbox.api.prava.space")
    captured = {}

    def fake_urlopen(request, **kwargs):
        captured["url"] = request.full_url
        captured["method"] = request.method
        captured["authorization"] = request.headers["Authorization"]
        return FakeResponse(
            {"session_id": "session/unsafe", "status": "pending", "transactions": []}
        )

    monkeypatch.setattr(prava_client, "urlopen", fake_urlopen)

    result = prava_client.get_payment_result("session/unsafe")

    assert captured["url"].endswith(
        "/v1/sessions/session%2Funsafe/payment-result"
    )
    assert captured["method"] == "GET"
    assert captured["authorization"] == "Bearer sk_test_unit_key"
    assert result["status"] == "pending"


def test_report_status_uses_documented_optional_fields(monkeypatch) -> None:
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_unit_key")
    monkeypatch.setenv("PRAVA_SANDBOX_URL", "https://sandbox.api.prava.space")
    captured = {}

    def fake_urlopen(request, **_kwargs):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        return FakeResponse(
            {
                "status": "confirmed",
                "txn_ref_id": "txn-contract",
                "txn_status": "APPROVED",
                "visa_confirmation": "SUCCESS",
            }
        )

    monkeypatch.setattr(prava_client, "urlopen", fake_urlopen)

    prava_client.report_status(
        "session-contract",
        "txn-contract",
        "APPROVED",
        authorization_code="AUTH42",
        response_code="00",
        amount_paid="450.00",
    )

    assert captured["url"].endswith(
        "/v1/sessions/session-contract/report-status"
    )
    assert captured["payload"] == {
        "txn_ref_id": "txn-contract",
        "txn_status": "APPROVED",
        "authorization_code": "AUTH42",
        "response_code": "00",
        "amount_paid": "450.00",
    }


def test_mandate_expired_is_typed_and_never_creates_a_new_session(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_unit_key")
    monkeypatch.setenv("PRAVA_SANDBOX_URL", "https://sandbox.api.prava.space")
    monkeypatch.setattr(
        prava_client,
        "create_session",
        lambda *_args, **_kwargs: pytest.fail(
            "MANDATE_EXPIRED must require a new explicit user approval"
        ),
    )

    def expired(*_args, **_kwargs):
        body = BytesIO(
            json.dumps(
                {
                    "error": {
                        "code": "MANDATE_EXPIRED",
                        "message": "Register a new intent.",
                    }
                }
            ).encode("utf-8")
        )
        raise HTTPError(
            "https://sandbox.api.prava.space/v1/sessions/session/report-status",
            400,
            "Bad Request",
            {"X-Response-ID": "response-expired"},
            body,
        )

    monkeypatch.setattr(prava_client, "urlopen", expired)

    with pytest.raises(prava_client.MandateExpiredError) as exc_info:
        prava_client.report_status("session", "txn", "APPROVED")

    assert exc_info.value.code == "MANDATE_EXPIRED"
    assert exc_info.value.response_id == "response-expired"
    assert "Register a new intent." in str(exc_info.value)


def test_prava_client_normalizes_failed_session_as_rejected(monkeypatch) -> None:
    responses = iter(
        [
            {
                "session_id": "sess_unit_rejected",
                "session_token": "session-token-unit",
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


def test_prava_polling_retries_transient_server_errors(monkeypatch) -> None:
    intent_ref = "sess_transient_server_error"
    prava_client._INTENTS[intent_ref] = {
        "merchant": "Zepto",
        "amount": "9.99",
        "item_description": "Sandbox retry check",
        "constraints": {
            "poll_timeout_seconds": 1,
            "poll_interval_seconds": 0,
        },
    }
    responses = iter(
        [
            prava_client.PravaAPIError(
                status_code=500,
                code="INTERNAL_ERROR",
                message="An internal error occurred",
                response_id="response-transient",
            ),
            {
                "session_id": intent_ref,
                "status": "awaiting_result",
                "transactions": [
                    {
                        "txn_id": "txn_retry",
                        "line_items": [
                            {
                                "txn_ref_id": "txn_ref_retry",
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

    def get_result(_session_id):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(prava_client, "get_payment_result", get_result)

    mandate = prava_client.await_mandate(intent_ref)

    assert mandate["status"] == "approved"
    assert mandate["txn_ref_id"] == "txn_ref_retry"


def test_completed_prava_session_never_reissues_checkout_credentials(monkeypatch) -> None:
    responses = iter(
        [
            {
                "session_id": "sess_unit_completed",
                "session_token": "session-token-unit",
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
