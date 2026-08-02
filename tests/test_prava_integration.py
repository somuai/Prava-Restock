"""Live Prava sandbox checks.

Run non-interactive API checks with ``pytest -m integration -v``. Set
``PRAVA_INTERACTIVE=1`` to include the hosted test-card/passkey approval case;
the runner must open the short-lived URL printed by that test.
"""

import json
import os

import pytest
from dotenv import load_dotenv

from payments import prava_client


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def clean_ephemeral_prava_state() -> None:
    prava_client._INTENTS.clear()
    prava_client._CREDENTIALS.clear()


def require_sandbox_credentials() -> None:
    load_dotenv(prava_client._PROJECT_ROOT / ".env", override=False)
    api_key = os.getenv("PRAVA_API_KEY", "")
    base_url = os.getenv("PRAVA_SANDBOX_URL", "").rstrip("/")
    if not api_key.startswith("sk_test_"):
        pytest.skip("PRAVA_API_KEY must be a sandbox sk_test_ key")
    if base_url != "https://sandbox.api.prava.space":
        pytest.skip("PRAVA_SANDBOX_URL must be the official sandbox host")


def test_approved_mandate_with_documented_test_card_and_real_passkey() -> None:
    require_sandbox_credentials()
    if os.getenv("PRAVA_INTERACTIVE") != "1":
        pytest.skip(
            "set PRAVA_INTERACTIVE=1 to enter Prava's documented test card and approve WebAuthn"
        )

    intent_ref = prava_client.create_intent(
        "zepto",
        "9.99",
        "Restock Phase 7 sandbox approval",
        {
            "currency": "INR",
            # Leave time for the human passkey handoff while staying inside
            # Prava's documented 15-minute sandbox session lifetime.
            "poll_timeout_seconds": 840,
            "poll_interval_seconds": 2,
            "request_timeout_seconds": 45,
        },
    )
    approval_url = prava_client._INTENTS[intent_ref]["iframe_url"]
    print(f"PRAVA_APPROVAL_URL={approval_url}", flush=True)

    mandate = prava_client.await_mandate(intent_ref)

    assert mandate["status"] == "approved"
    assert mandate["mandate_id"]
    assert mandate["credential_reference"].startswith("prava_credential_")
    assert mandate["scope"] == {"merchant": "Zepto", "max_amount": "9.99"}
    serialized = json.dumps(mandate)
    assert "token" not in serialized.lower()
    assert "dynamic_cvv" not in serialized.lower()


def test_rejected_mandate_sandbox_limitation_is_explicit() -> None:
    pytest.skip(
        "Prava publishes no deterministic rejected-passkey sandbox card or API trigger; "
        "report-status DECLINED is a merchant outcome, not mandate rejection"
    )


def test_expired_mandate_sandbox_limitation_is_explicit() -> None:
    pytest.skip(
        "Prava publishes no sandbox clock-control or guaranteed short-expiry fixture; "
        "the documented session expiry is 15 minutes"
    )


def test_invalid_credentials_are_rejected_by_real_sandbox(monkeypatch) -> None:
    require_sandbox_credentials()
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_invalid_credentials")

    with pytest.raises(prava_client.PravaAPIError) as exc_info:
        prava_client.create_intent(
            "zepto",
            "9.99",
            "Restock invalid-credential check",
            {"currency": "INR", "request_timeout_seconds": 60},
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.code in {"AUTH_1001", "AUTH_1002"}


def test_pending_session_hits_client_poll_timeout_against_real_sandbox() -> None:
    require_sandbox_credentials()
    intent_ref = prava_client.create_intent(
        "zepto",
        "9.99",
        "Restock polling-timeout check",
        {
            "currency": "INR",
            "poll_timeout_seconds": 0.05,
            "poll_interval_seconds": 0.01,
        },
    )

    with pytest.raises(TimeoutError, match="mandate polling timed out"):
        prava_client.await_mandate(intent_ref)


def test_webhook_sandbox_limitation_is_explicit() -> None:
    pytest.skip(
        "The current Prava OpenAPI/docs expose polling but no webhook registration, "
        "event schema, signature contract, or sandbox trigger"
    )


def test_charge_mandate_stub_mode(monkeypatch) -> None:
    monkeypatch.setattr(prava_client, "STUB_MODE", True)
    res = prava_client.charge_mandate(
        mandate_id="mandate_test_123",
        amount=29.50,
        currency="usd",
        merchant_name="TeamTool Pro",
        idempotency_key="idem_test_456",
        description="Monthly renewal",
    )
    assert res["status"] == "approved"
    assert res["mandate_id"] == "mandate_test_123"
    assert res["charged_amount"] == "29.50"
    assert res["currency"] == "USD"
    assert res["merchant_name"] == "TeamTool Pro"
    assert res["idempotency_key"] == "idem_test_456"
    assert res["execution_mode"] == "sandbox"


def test_charge_mandate_validates_inputs() -> None:
    with pytest.raises(ValueError, match="mandate_id is required"):
        prava_client.charge_mandate("", 10, "USD", "Vendor", "idem")

    with pytest.raises(ValueError, match="idempotency_key is required"):
        prava_client.charge_mandate("mandate_1", 10, "USD", "Vendor", "")

    with pytest.raises(ValueError, match="merchant_name is required"):
        prava_client.charge_mandate("mandate_1", 10, "USD", "", "idem")

    with pytest.raises(ValueError, match="amount must be positive"):
        prava_client.charge_mandate("mandate_1", -5, "USD", "Vendor", "idem")

    with pytest.raises(ValueError, match="currency must be a three-letter code"):
        prava_client.charge_mandate("mandate_1", 10, "INVALID", "Vendor", "idem")

