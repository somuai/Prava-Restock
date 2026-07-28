from datetime import date, timedelta

from fastapi.testclient import TestClient

from nanda_trigger_service.app import app


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
