"""Deterministic predicted-depletion trigger for Restock Home."""

from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from nanda_trigger_service.trigger_math_core import predict_depletion
from payments.models import TrackedItem, TriggerType


ALPHA = 0.3
TRIGGER_WINDOW_DAYS = 2


_PRIORS_PATH = Path(__file__).resolve().parent / "category_priors.json"
_category_priors_cache: dict[str, float] | None = None


def _load_category_priors() -> dict[str, float]:
    """Load the static category-level reorder-interval priors (cached)."""
    global _category_priors_cache
    if _category_priors_cache is None:
        raw = json.loads(_PRIORS_PATH.read_text(encoding="utf-8"))
        _category_priors_cache = {
            k: float(v) for k, v in raw.items() if not k.startswith("_")
        }
    return _category_priors_cache


def seed_cadence_from_priors(
    category: str, user_estimate: float | None = None
) -> float:
    """Return a cold-start cadence for a new item with no purchase history.

    Uses a public category-level prior (Instacart Market Basket dataset) when
    available, falling back to the user-provided estimate.  Raises ValueError
    if neither source provides a value.
    """
    priors = _load_category_priors()
    if category in priors:
        return priors[category]
    if user_estimate is not None and user_estimate > 0:
        return user_estimate
    raise ValueError(
        f"no category prior for {category!r} and no user estimate provided"
    )


def _require_predicted(item: TrackedItem) -> None:
    if item.trigger_type is not TriggerType.PREDICTED:
        raise ValueError("consumption trigger requires trigger_type=predicted")


def predicted_depletion_date(item: TrackedItem) -> date:
    _require_predicted(item)
    if item.last_purchased_at is None:
        raise ValueError("cold-start items have no predicted depletion date before a purchase")
    assert item.typical_cadence_days is not None
    predicted, _ = predict_depletion(
        item.last_purchased_at,
        item.typical_cadence_days,
    )
    return predicted


def days_until_depletion(item: TrackedItem, today: date | None = None) -> int:
    _require_predicted(item)
    if item.last_purchased_at is None:
        raise ValueError("cold-start items have no predicted depletion date before a purchase")
    assert item.typical_cadence_days is not None
    _, remaining_days = predict_depletion(
        item.last_purchased_at,
        item.typical_cadence_days,
        today=today,
    )
    return remaining_days


def trigger_condition(
    item: TrackedItem,
    today: date | None = None,
    trigger_window_days: int = TRIGGER_WINDOW_DAYS,
) -> bool:
    # A cadence prior is an onboarding estimate, not evidence that a user has
    # purchased the item. Do not create a depletion notification until the
    # first purchase establishes a clock. A price threshold may still fire.
    if item.last_purchased_at is None:
        return False
    return days_until_depletion(item, today) <= trigger_window_days


def price_trigger_condition(item: TrackedItem) -> bool:
    """Return whether the latest observed price meets the user's threshold."""
    _require_predicted(item)
    return (
        item.price_threshold is not None
        and item.last_observed_price is not None
        and item.last_observed_price <= item.price_threshold
    )


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
    return trigger_condition(item) or price_trigger_condition(item)


def _format_rupees(amount: Decimal) -> str:
    formatted = format(amount, "f")
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def _depletion_reason(item: TrackedItem, depletion_days: int) -> str:
    if depletion_days < 0:
        return (
            f"You were expected to run out of {item.name} "
            f"{abs(depletion_days)} day(s) ago"
        )
    if depletion_days == 0:
        return f"You'll run out of {item.name} today"
    unit = "day" if depletion_days == 1 else "days"
    return f"You'll run out of {item.name} in {depletion_days} {unit}"


def _price_reason(item: TrackedItem) -> str:
    assert item.last_observed_price is not None
    assert item.price_threshold is not None
    return (
        f"{item.name} dropped to ₹{_format_rupees(item.last_observed_price)} — "
        f"below your ₹{_format_rupees(item.price_threshold)} threshold"
    )


def propose(item: TrackedItem) -> dict:
    _require_predicted(item)
    depletion_fired = trigger_condition(item)
    price_fired = price_trigger_condition(item)
    depletion_days = days_until_depletion(item) if depletion_fired else None
    merchant = item.preferred_merchant.value

    if depletion_fired and price_fired:
        assert depletion_days is not None
        reason = f"{_depletion_reason(item, depletion_days)}, and {_price_reason(item)}."
    elif depletion_fired:
        assert depletion_days is not None
        reason = f"{_depletion_reason(item, depletion_days)}."
    elif price_fired:
        reason = f"{_price_reason(item)}."
    else:
        if item.last_purchase_amount is None:
            raise ValueError("cold-start proposal requires a current observed price")
        reason = f"{item.name} has not reached a reorder trigger yet."

    proposed_amount = (
        item.last_observed_price
        if price_fired and item.last_observed_price is not None
        else item.last_purchase_amount
    )
    if proposed_amount is None:
        raise ValueError("cold-start proposal requires a current observed price")
    return {
        "proposed_amount": proposed_amount,
        "merchant": merchant,
        "message": (
            f"{reason} Reorder from {merchant} for {proposed_amount}?"
        ),
    }
