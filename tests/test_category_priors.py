"""Tests for category-level cold-start cadence seeding."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from payments.models import TrackedItem
from triggers import consumption_model


USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _predicted_item(
    category: str = "grocery",
    cadence: float = 14.0,
) -> TrackedItem:
    return TrackedItem(
        item_id=UUID("00000000-0000-0000-0000-000000000099"),
        user_id=USER_ID,
        name="Test Item",
        track="home",
        trigger_type="predicted",
        category=category,
        sensitive_flag=False,
        preferred_merchant="zepto",
        merchant_sku_id="test-sku",
        currency="INR",
        status="active",
        typical_cadence_days=cadence,
        last_purchased_at=date.today() - timedelta(days=10),
        last_purchase_amount="100.00",
    )


def _cold_start_item(category: str, cadence: float | None) -> TrackedItem:
    return TrackedItem(
        item_id=UUID("00000000-0000-0000-0000-000000000098"),
        user_id=USER_ID,
        name="New item",
        track="home",
        trigger_type="predicted",
        category=category,
        sensitive_flag=False,
        preferred_merchant="zepto",
        merchant_sku_id="new-sku",
        currency="INR",
        status="active",
        typical_cadence_days=cadence,
    )


def test_new_known_category_item_seeds_from_lookup_table() -> None:
    """A new item in a known category ignores its estimate for the public prior."""
    item = _cold_start_item("grocery", cadence=20.0)
    assert item.typical_cadence_days == 7.0
    assert item.last_purchased_at is None
    assert consumption_model.trigger_condition(item) is False


def test_new_unknown_category_item_falls_back_to_user_estimate() -> None:
    """A new item in an unknown category falls back to the user's own estimate."""
    item = _cold_start_item("stationery", cadence=45.0)
    assert item.typical_cadence_days == 45.0


def test_no_prior_and_no_estimate_raises() -> None:
    """Neither a category match nor a user estimate is available."""
    with pytest.raises(ValueError, match="user cadence estimate"):
        _cold_start_item("stationery", None)


def test_health_category_seeds_from_lookup_table() -> None:
    """Health category uses the personal-care derived prior."""
    cadence = consumption_model.seed_cadence_from_priors("health")
    assert cadence == 7.0


def test_cold_start_price_signal_can_propose_without_purchase_history() -> None:
    item = _cold_start_item("grocery", cadence=None).model_copy(
        update={"price_threshold": Decimal("400"), "last_observed_price": Decimal("380")}
    )
    assert consumption_model.should_fire(item) is True
    proposal = consumption_model.propose(item)
    assert proposal["proposed_amount"] == Decimal("380")


def test_recalibration_converges_regardless_of_seed_source() -> None:
    """EWMA recalibration converges correctly whether seeded from priors or user estimate."""
    # Item seeded from the checked-in grocery prior (7.0 days).
    prior_item = _predicted_item(category="grocery", cadence=7.0)
    # Item seeded from user estimate (stationery fallback = 45.0 days)
    user_item = _predicted_item(category="stationery", cadence=45.0)

    true_interval = 14  # actual reorder interval

    # Both should converge toward 14 over multiple recalibrations
    for _ in range(10):
        consumption_model.recalibrate(prior_item, true_interval)
        consumption_model.recalibrate(user_item, true_interval)

    assert prior_item.typical_cadence_days is not None
    assert user_item.typical_cadence_days is not None
    # Both converge toward 14 — closer than their starting points
    assert abs(prior_item.typical_cadence_days - true_interval) < abs(7.0 - true_interval)
    assert abs(user_item.typical_cadence_days - true_interval) < abs(45.0 - true_interval)
    # And both are within 1 day of the true interval after 10 cycles
    assert abs(prior_item.typical_cadence_days - true_interval) < 1.0
    assert abs(user_item.typical_cadence_days - true_interval) < 1.0
