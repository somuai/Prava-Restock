from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from payments.models import TrackedItem
from triggers import consumption_model, renewal_model


USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def home_item(*, days_until_depletion: int, cadence: float = 14.0) -> TrackedItem:
    return TrackedItem(
        item_id=UUID("00000000-0000-0000-0000-000000000010"),
        user_id=USER_ID,
        name="Coffee",
        track="home",
        trigger_type="predicted",
        category="grocery",
        sensitive_flag=False,
        preferred_merchant="zepto",
        merchant_sku_id="coffee-500g",
        status="active",
        typical_cadence_days=cadence,
        last_purchased_at=date.today() - timedelta(days=cadence - days_until_depletion),
        last_purchase_amount="450.00",
    )


def teams_item(*, days_until_renewal: int, current: str, alternate: str) -> TrackedItem:
    return TrackedItem(
        item_id=UUID("00000000-0000-0000-0000-000000000011"),
        user_id=USER_ID,
        name="TeamTool Pro",
        track="teams",
        trigger_type="known_date",
        category="saas_subscription",
        sensitive_flag=False,
        preferred_merchant="mock_subscription_billing",
        merchant_sku_id="teamtool-pro",
        status="active",
        renewal_date=date.today() + timedelta(days=days_until_renewal),
        current_plan_amount=current,
        alternate_plan_amount=alternate,
        alternate_plan_label="Annual plan",
    )


def test_predicted_item_inside_window_fires() -> None:
    item = home_item(days_until_depletion=2)
    assert consumption_model.should_fire(item) is True
    assert consumption_model.propose(item)["proposed_amount"] == Decimal("450.00")


def test_predicted_item_outside_window_does_not_fire() -> None:
    assert consumption_model.should_fire(home_item(days_until_depletion=3)) is False


def test_predicted_depletion_helpers_follow_the_spec() -> None:
    item = home_item(days_until_depletion=2)
    assert consumption_model.predicted_depletion_date(item) == date.today() + timedelta(days=2)
    assert consumption_model.days_until_depletion(item) == 2


def test_recalibration_converges_toward_true_interval_over_four_cycles() -> None:
    item = home_item(days_until_depletion=2, cadence=20.0)
    values = [consumption_model.recalibrate(item, 10) for _ in range(4)]
    assert values == pytest.approx([17.0, 14.9, 13.43, 12.401])
    assert abs(values[-1] - 10) < abs(20 - 10)


def test_recalibration_rejects_invalid_inputs() -> None:
    item = home_item(days_until_depletion=2)
    with pytest.raises(ValueError):
        consumption_model.recalibrate(item, 0)
    with pytest.raises(ValueError):
        consumption_model.recalibrate(item, 10, alpha=1.1)


def test_known_date_item_inside_window_fires() -> None:
    assert renewal_model.should_fire(
        teams_item(days_until_renewal=2, current="2400", alternate="2200")
    ) is True


def test_known_date_item_outside_window_does_not_fire() -> None:
    assert renewal_model.should_fire(
        teams_item(days_until_renewal=3, current="2400", alternate="2200")
    ) is False


def test_teams_switches_when_alternate_is_cheaper() -> None:
    proposal = renewal_model.propose(
        teams_item(days_until_renewal=2, current="2400", alternate="2200")
    )
    assert proposal["proposed_action"] == "switch_to_alternate"
    assert proposal["proposed_amount"] == Decimal("2200")


def test_teams_renews_as_is_when_alternate_is_not_cheaper() -> None:
    proposal = renewal_model.propose(
        teams_item(days_until_renewal=2, current="2400", alternate="2500")
    )
    assert proposal["proposed_action"] == "renew_as_is"
    assert proposal["proposed_amount"] == Decimal("2400")
