from datetime import date, timedelta

from fastapi.testclient import TestClient

from nanda_trigger_service.app import app
from nanda_trigger_service.trigger_math_core import evaluate_renewal, predict_depletion
from payments.models import TrackedItem
from triggers import consumption_model, renewal_model
from uuid import UUID


client = TestClient(app)


def test_predict_depletion_is_stateless_and_deterministic_for_its_date() -> None:
    last_purchase = date.today() - timedelta(days=12)
    response = client.post(
        "/predict-depletion",
        json={"last_purchased_at": last_purchase.isoformat(), "typical_cadence_days": 14},
    )
    assert response.status_code == 200
    assert response.json() == {
        "predicted_depletion_date": (last_purchase + timedelta(days=14)).isoformat(),
        "days_until_depletion": 2,
    }


def test_predict_depletion_rejects_non_positive_cadence() -> None:
    response = client.post(
        "/predict-depletion",
        json={"last_purchased_at": "2026-07-10", "typical_cadence_days": 0},
    )
    assert response.status_code == 422


def test_evaluate_renewal_recommends_switch_and_reports_savings() -> None:
    response = client.post(
        "/evaluate-renewal",
        json={"current_plan_amount": "2400.00", "alternate_plan_amount": "2200.00"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "recommended_action": "switch_to_alternate",
        "savings_amount": "200.00",
    }


def test_evaluate_renewal_keeps_current_plan_when_alternate_is_not_cheaper() -> None:
    response = client.post(
        "/evaluate-renewal",
        json={"current_plan_amount": "2200.00", "alternate_plan_amount": "2200.00"},
    )
    assert response.status_code == 200
    assert response.json() == {"recommended_action": "renew_as_is", "savings_amount": "0"}


def test_public_depletion_endpoint_uses_the_same_math_as_restock() -> None:
    last_purchase = date.today() - timedelta(days=9)
    item = TrackedItem(
        item_id=UUID("00000000-0000-0000-0000-000000000090"),
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        name="Parity coffee",
        track="home",
        trigger_type="predicted",
        category="grocery",
        sensitive_flag=False,
        preferred_merchant="zepto",
        merchant_sku_id="coffee",
        currency="INR",
        status="active",
        typical_cadence_days=14,
        last_purchased_at=last_purchase,
        last_purchase_amount="400",
    )

    expected_date, expected_days = predict_depletion(last_purchase, 14)
    assert consumption_model.predicted_depletion_date(item) == expected_date
    assert consumption_model.days_until_depletion(item) == expected_days


def test_public_renewal_endpoint_uses_the_same_math_as_restock() -> None:
    item = TrackedItem(
        item_id=UUID("00000000-0000-0000-0000-000000000091"),
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        name="Parity SaaS",
        track="teams",
        trigger_type="known_date",
        category="saas_subscription",
        sensitive_flag=False,
        preferred_merchant="mock_subscription_billing",
        merchant_sku_id="saas",
        currency="INR",
        status="active",
        renewal_date=date.today() + timedelta(days=2),
        current_plan_amount="2400",
        alternate_plan_amount="2200",
        alternate_plan_label="Annual",
    )

    expected_action, expected_savings = evaluate_renewal(
        item.current_plan_amount,
        item.alternate_plan_amount,
    )
    assert renewal_model.proposed_action(item) == expected_action
    assert expected_savings == 200
