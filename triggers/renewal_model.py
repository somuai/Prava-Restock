"""Deterministic known-date trigger for Restock Teams."""

from datetime import date

from payments.models import TrackedItem, TriggerType


TRIGGER_WINDOW_DAYS = 2


def _require_known_date(item: TrackedItem) -> None:
    if item.trigger_type is not TriggerType.KNOWN_DATE:
        raise ValueError("renewal trigger requires trigger_type=known_date")


def days_until_renewal(item: TrackedItem, today: date | None = None) -> int:
    _require_known_date(item)
    assert item.renewal_date is not None
    return (item.renewal_date - (today or date.today())).days


def trigger_condition(
    item: TrackedItem,
    today: date | None = None,
    trigger_window_days: int = TRIGGER_WINDOW_DAYS,
) -> bool:
    return days_until_renewal(item, today) <= trigger_window_days


def proposed_action(item: TrackedItem) -> str:
    _require_known_date(item)
    assert item.current_plan_amount is not None
    assert item.alternate_plan_amount is not None
    if item.alternate_plan_amount >= item.current_plan_amount:
        return "renew_as_is"
    return "switch_to_alternate"


def should_fire(item: TrackedItem) -> bool:
    return trigger_condition(item)


def propose(item: TrackedItem) -> dict:
    action = proposed_action(item)
    assert item.current_plan_amount is not None
    assert item.alternate_plan_amount is not None
    assert item.alternate_plan_label is not None
    if action == "switch_to_alternate":
        amount = item.alternate_plan_amount
        detail = f"switch to {item.alternate_plan_label} for {amount}"
    else:
        amount = item.current_plan_amount
        detail = f"renew the current plan for {amount}"
    merchant = item.preferred_merchant.value
    return {
        "proposed_amount": amount,
        "merchant": merchant,
        "proposed_action": action,
        "message": (
            f"{item.name} renews in {days_until_renewal(item)} day(s). "
            f"Proposed action: {detail}. Approve, adjust, or skip?"
        ),
    }
