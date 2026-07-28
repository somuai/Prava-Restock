"""Shared, side-effect-free trigger calculations.

This module is deliberately dependency-free so the standalone NANDA utility
and Restock's own trigger engine execute the same implementation.
"""

from datetime import date, timedelta
from decimal import Decimal


def predict_depletion(
    last_purchased_at: date,
    typical_cadence_days: float,
    *,
    today: date | None = None,
) -> tuple[date, int]:
    """Return the predicted depletion date and whole days remaining."""
    if typical_cadence_days <= 0:
        raise ValueError("typical_cadence_days must be positive")
    depletion_date = last_purchased_at + timedelta(days=typical_cadence_days)
    return depletion_date, (depletion_date - (today or date.today())).days


def evaluate_renewal(
    current_plan_amount: Decimal,
    alternate_plan_amount: Decimal,
) -> tuple[str, Decimal]:
    """Return the cheaper action and savings from switching, if any."""
    if current_plan_amount <= 0 or alternate_plan_amount <= 0:
        raise ValueError("plan amounts must be positive")
    if alternate_plan_amount < current_plan_amount:
        return (
            "switch_to_alternate",
            current_plan_amount - alternate_plan_amount,
        )
    return "renew_as_is", Decimal("0")
