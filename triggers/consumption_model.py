"""Deterministic predicted-depletion trigger for Restock Home."""

from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path

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
    assert item.last_purchase_amount is not None
    depletion_days = days_until_depletion(item)
    depletion_fired = trigger_condition(item)
    price_fired = price_trigger_condition(item)
    merchant = item.preferred_merchant.value

    if depletion_fired and price_fired:
        reason = f"{_depletion_reason(item, depletion_days)}, and {_price_reason(item)}."
    elif depletion_fired:
        reason = f"{_depletion_reason(item, depletion_days)}."
    elif price_fired:
        reason = f"{_price_reason(item)}."
    else:
        reason = f"{item.name} has not reached a reorder trigger yet."

    proposed_amount = (
        item.last_observed_price
        if price_fired and item.last_observed_price is not None
        else item.last_purchase_amount
    )
    return {
        "proposed_amount": proposed_amount,
        "merchant": merchant,
        "message": (
            f"{reason} Reorder from {merchant} for {proposed_amount}?"
        ),
    }
