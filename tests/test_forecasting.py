from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from demo.forecast_benchmark import benchmark
from forecasting.evaluation import ForecastCase, evaluate_predictions, ewma_predictions
from forecasting.priors import cadence_prior_days
from payments.models import TrackedItem, User
from storage import Database, RestockRepository


USER_ID = UUID("00000000-0000-0000-0000-000000000201")


def seeded_repository(tmp_path) -> tuple[RestockRepository, str, TrackedItem]:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'forecast.db'}"))
    repository.create_schema()
    user = User(
        user_id=USER_ID,
        display_name="Forecast user",
        prava_account_ref="prava-forecast",
        monthly_cap="5000",
        per_item_cap="1000",
        per_transaction_cap="1000",
        created_at=datetime.now(timezone.utc),
    )
    repository.upsert_user(user)
    tenant_id = repository.personal_tenant_id(str(USER_ID))
    item = TrackedItem(
        item_id=UUID("00000000-0000-0000-0000-000000000202"),
        user_id=USER_ID,
        tenant_id=UUID(tenant_id),
        name="Coffee",
        track="home",
        trigger_type="predicted",
        category="grocery",
        sensitive_flag=False,
        preferred_merchant="zepto",
        merchant_sku_id="coffee",
        currency="INR",
        status="active",
        typical_cadence_days=14,
        last_purchased_at=date.today() - timedelta(days=14),
        last_purchase_amount="400",
    )
    repository.upsert_item(item)
    return repository, tenant_id, item


def test_ewma_and_metrics_are_deterministic() -> None:
    predictions = ewma_predictions([10, 10, 10], initial=20, alpha=0.3)
    assert predictions == pytest.approx([20, 17.0, 14.9])
    metrics = evaluate_predictions([
        ForecastCase(10, 10, user_acted=True),
        ForecastCase(12, 10, user_acted=False),
    ])
    assert metrics.mae_days == 1
    assert metrics.user_action_rate == 0.5
    assert cadence_prior_days("grocery") == 11


def test_forecast_storage_requires_consent_and_can_be_deleted(tmp_path) -> None:
    repository, tenant_id, item = seeded_repository(tmp_path)
    values = dict(
        tenant_id=tenant_id,
        user_id=str(USER_ID),
        item_id=str(item.item_id),
        predicted_depletion_date=date.today().isoformat(),
        actual_reorder_date=date.today().isoformat(),
        category="grocery",
        trigger_cause="predicted_depletion",
        notification_action="approved",
        forecast_error_days=0,
    )
    assert repository.log_forecast_observation(**values) is None
    repository.set_consent(tenant_id=tenant_id, user_id=str(USER_ID), kind="forecasting", granted=True)
    assert repository.log_forecast_observation(**values)["model_version"] == "ewma-v1"
    assert len(repository.list_forecast_observations(tenant_id=tenant_id, user_id=str(USER_ID))) == 1
    assert repository.delete_forecast_observations(tenant_id=tenant_id, user_id=str(USER_ID)) == 1
    assert repository.list_forecast_observations(tenant_id=tenant_id, user_id=str(USER_ID)) == []


def test_csv_benchmark_uses_category_prior(tmp_path) -> None:
    data = tmp_path / "observations.csv"
    data.write_text("category,actual_interval_days,user_acted\n" "grocery,14,true\n" "grocery,12,false\n")
    result = benchmark(data)
    assert result["sample_count"] == 2
    assert result["mae_days"] >= 0
