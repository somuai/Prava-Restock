"""Deterministic predicted-depletion trigger for Restock Home."""

from datetime import date, timedelta

from payments.models import TrackedItem, TriggerType


ALPHA = 0.3
TRIGGER_WINDOW_DAYS = 2


def _require_predicted(item: TrackedItem) -> None:
    if item.trigger_type is not TriggerType.PREDICTED:
        raise ValueError("consumption trigger requires trigger_type=predicted")


def predicted_depletion_date(item: TrackedItem) -> date:
    _require_predicted(item)
    assert item.last_purchased_at is not None
    assert item.typical_cadence_days is not None
    return item.last_purchased_at + timedelta(days=item.typical_cadence_days)


def days_until_depletion(item: TrackedItem, today: date | None = None) -> int:
    effective_today = today or date.today()
    return (predicted_depletion_date(item) - effective_today).days


def trigger_condition(
    item: TrackedItem,
    today: date | None = None,
    trigger_window_days: int = TRIGGER_WINDOW_DAYS,
) -> bool:
    return days_until_depletion(item, today) <= trigger_window_days


def recalibrate(
    item: TrackedItem,
    observed_interval_days: int,
    alpha: float = ALPHA,
) -> float:
    """Move the stored cadence toward the latest observed reorder interval."""
    _require_predicted(item)
    if observed_interval_days <= 0:
        raise ValueError("observed_interval_days must be positive")
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in the interval (0, 1]")
    assert item.typical_cadence_days is not None
    item.typical_cadence_days = (
        alpha * observed_interval_days
        + (1 - alpha) * item.typical_cadence_days
    )
    return item.typical_cadence_days


def should_fire(item: TrackedItem) -> bool:
    return trigger_condition(item)


def propose(item: TrackedItem) -> dict:
    _require_predicted(item)
    assert item.last_purchase_amount is not None
    depletion_days = days_until_depletion(item)
    merchant = item.preferred_merchant.value
    return {
        "proposed_amount": item.last_purchase_amount,
        "merchant": merchant,
        "message": (
            f"{item.name} is expected to run out in {depletion_days} day(s). "
            f"Reorder from {merchant} for {item.last_purchase_amount}?"
        ),
    }
