from inspect import signature
from concurrent.futures import ThreadPoolExecutor
import time

import pytest

from merchant import mock_subscription_checkout
from merchant.models import MerchantCheckoutResult


@pytest.fixture(autouse=True)
def clear_mock_checkouts() -> None:
    mock_subscription_checkout._CHECKOUTS_BY_IDEMPOTENCY_KEY.clear()


def test_complete_checkout_keeps_the_legacy_four_argument_contract() -> None:
    assert str(signature(mock_subscription_checkout.complete_checkout)) == (
        "(credential_reference, merchant_sku_id, amount, idempotency_key)"
    )


def test_completed_subscription_checkout_matches_the_stable_result_schema() -> None:
    payload = mock_subscription_checkout.complete_checkout(
        "credential-reference", "invoice-123", "29.00", "idem-123"
    )
    result = MerchantCheckoutResult.model_validate(payload)

    assert result.status.value == "completed"
    assert result.merchant_order_id is not None
    assert str(result.charged_amount) == "29.00"
    assert result.currency == "USD"
    assert result.retryable is False
    assert result.execution_mode.value == "disclosed_mock"
    assert result.credential_exposed is False
    assert result.credential_used is True


def test_duplicate_idempotency_key_returns_the_same_order() -> None:
    first = mock_subscription_checkout.complete_checkout(
        "credential-reference", "invoice-123", "29.00", "idem-repeat"
    )
    second = mock_subscription_checkout.complete_checkout(
        "credential-reference", "invoice-123", "29.00", "idem-repeat"
    )

    assert first == second
    assert first["merchant_order_id"] == second["merchant_order_id"]


@pytest.mark.parametrize(
    ("second_sku", "second_amount"),
    [("invoice-456", "29.00"), ("invoice-123", "31.00")],
)
def test_idempotency_key_rejects_conflicting_checkout_parameters(
    second_sku, second_amount
) -> None:
    mock_subscription_checkout.complete_checkout(
        "credential-one", "invoice-123", "29.00", "idem-conflict"
    )

    with pytest.raises(
        ValueError,
        match="idempotency_key already used with different checkout parameters",
    ):
        mock_subscription_checkout.complete_checkout(
            "credential-two", second_sku, second_amount, "idem-conflict"
        )


def test_equivalent_decimal_amounts_have_the_same_idempotency_fingerprint() -> None:
    first = mock_subscription_checkout.complete_checkout(
        "credential-one", "invoice-123", "29.0", "idem-canonical"
    )
    second = mock_subscription_checkout.complete_checkout(
        "credential-two", "invoice-123", "29.00", "idem-canonical"
    )

    assert first == second


def test_returned_payload_cannot_mutate_the_stored_idempotent_result() -> None:
    first = mock_subscription_checkout.complete_checkout(
        "credential", "invoice-123", "29", "idem-defensive"
    )
    original_order_id = first["merchant_order_id"]
    first["merchant_order_id"] = "caller-corrupted-order"
    first["status"] = "failed"

    replay = mock_subscription_checkout.complete_checkout(
        "credential", "invoice-123", "29", "idem-defensive"
    )

    assert replay["merchant_order_id"] == original_order_id
    assert replay["status"] == "completed"


def test_concurrent_same_key_calls_create_exactly_one_order(monkeypatch) -> None:
    real_uuid4 = mock_subscription_checkout.uuid4

    def delayed_uuid4():
        time.sleep(0.02)
        return real_uuid4()

    monkeypatch.setattr(mock_subscription_checkout, "uuid4", delayed_uuid4)

    def checkout(_index):
        return mock_subscription_checkout.complete_checkout(
            "credential", "invoice-123", "29", "idem-concurrent"
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(checkout, range(16)))

    assert len({result["merchant_order_id"] for result in results}) == 1
    assert len(mock_subscription_checkout._CHECKOUTS_BY_IDEMPOTENCY_KEY) == 1


@pytest.mark.parametrize(
    ("credential_reference", "merchant_sku_id", "amount", "idempotency_key", "message"),
    [
        ("", "invoice-123", "29", "idem", "credential_reference is required"),
        ("   ", "invoice-123", "29", "idem", "credential_reference is required"),
        ("credential", "", "29", "idem", "merchant_sku_id is required"),
        ("credential", None, "29", "idem", "merchant_sku_id is required"),
        ("credential", "invoice-123", "0", "idem", "amount must be positive"),
        ("credential", "invoice-123", "29", "", "idempotency_key is required"),
        ("credential", "invoice-123", "29", None, "idempotency_key is required"),
    ],
)
def test_checkout_rejects_invalid_boundary_inputs(
    credential_reference, merchant_sku_id, amount, idempotency_key, message
) -> None:
    with pytest.raises(ValueError, match=message):
        mock_subscription_checkout.complete_checkout(
            credential_reference, merchant_sku_id, amount, idempotency_key
        )
