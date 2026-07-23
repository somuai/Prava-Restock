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


def test_known_category_seeds_from_lookup_table() -> None:
    """A new item in a known category uses the Instacart-derived prior."""
    cadence = consumption_model.seed_cadence_from_priors("grocery", user_estimate=20.0)
    assert cadence == 11.0  # Instacart grocery median, not the user's 20-day estimate


def test_unknown_category_falls_back_to_user_estimate() -> None:
    """A new item in an unknown category falls back to the user's own estimate."""
    cadence = consumption_model.seed_cadence_from_priors("stationery", user_estimate=45.0)
    assert cadence == 45.0


def test_no_prior_and_no_estimate_raises() -> None:
    """Neither a category match nor a user estimate is available."""
    with pytest.raises(ValueError, match="no category prior"):
        consumption_model.seed_cadence_from_priors("stationery")


def test_health_category_seeds_from_lookup_table() -> None:
    """Health category uses the personal-care derived prior."""
    cadence = consumption_model.seed_cadence_from_priors("health")
    assert cadence == 18.0


def test_recalibration_converges_regardless_of_seed_source() -> None:
    """EWMA recalibration converges correctly whether seeded from priors or user estimate."""
    # Item seeded from category prior (grocery = 11.0 days)
    prior_item = _predicted_item(category="grocery", cadence=11.0)
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
    assert abs(prior_item.typical_cadence_days - true_interval) < abs(11.0 - true_interval)
    assert abs(user_item.typical_cadence_days - true_interval) < abs(45.0 - true_interval)
    # And both are within 1 day of the true interval after 10 cycles
    assert abs(prior_item.typical_cadence_days - true_interval) < 1.0
    assert abs(user_item.typical_cadence_days - true_interval) < 1.0
