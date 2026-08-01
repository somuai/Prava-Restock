"""Server-owned starter pantry templates for first-run onboarding.

These are ordinary tracked items, not proof of a live merchant quote.  A later
Zepto catalog resolution replaces the stable template SKU with the exact live
variant before any real checkout is allowed.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from payments.models import (
    Category,
    ItemStatus,
    PreferredMerchant,
    Track,
    TrackedItem,
    TriggerType,
)


StarterTemplateId = Literal["coffee", "milk", "toothpaste", "detergent"]


STARTER_TEMPLATE_SUMMARIES: dict[StarterTemplateId, dict[str, str]] = {
    "coffee": {
        "name": "Attikan Estate coffee",
        "description": "500 g · usually every 21 days",
    },
    "milk": {
        "name": "Amul Taaza milk",
        "description": "1 L · usually every 7 days",
    },
    "toothpaste": {
        "name": "Colgate Strong Teeth",
        "description": "200 g · usually every 45 days",
    },
    "detergent": {
        "name": "Surf Excel detergent",
        "description": "500 g · usually every 35 days",
    },
}


_TEMPLATES: dict[StarterTemplateId, dict[str, object]] = {
    "coffee": {
        "name": "Attikan Estate coffee",
        "category": Category.GROCERY,
        "merchant_sku_id": "zepto-arabica-coffee-500g",
        "cadence": 21.0,
        "days_since_purchase": 19,
        "amount": Decimal("380.00"),
        "price_threshold": Decimal("400.00"),
    },
    "milk": {
        "name": "Amul Taaza milk",
        "category": Category.GROCERY,
        "merchant_sku_id": "zepto-amul-taaza-1l",
        "cadence": 7.0,
        "days_since_purchase": 3,
        "amount": Decimal("57.00"),
    },
    "toothpaste": {
        "name": "Colgate Strong Teeth",
        "category": Category.HEALTH,
        "merchant_sku_id": "zepto-toothpaste-twin-pack",
        "cadence": 45.0,
        "days_since_purchase": 36,
        "amount": Decimal("119.00"),
    },
    "detergent": {
        "name": "Surf Excel detergent",
        "category": Category.OTHER,
        "merchant_sku_id": "zepto-surf-excel-500g",
        "cadence": 35.0,
        "days_since_purchase": 29,
        "amount": Decimal("145.00"),
    },
}


def build_starter_item(
    template_id: StarterTemplateId,
    *,
    user_id: str,
    today: date | None = None,
) -> TrackedItem:
    template = _TEMPLATES[template_id]
    effective_today = today or date.today()
    amount = Decimal(str(template["amount"]))
    threshold = template.get("price_threshold")
    return TrackedItem(
        item_id=uuid4(),
        user_id=UUID(user_id),
        name=str(template["name"]),
        track=Track.HOME,
        trigger_type=TriggerType.PREDICTED,
        category=template["category"],
        sensitive_flag=False,
        preferred_merchant=PreferredMerchant.ZEPTO,
        merchant_sku_id=str(template["merchant_sku_id"]),
        merchant_address_ref=None,
        quantity=1,
        currency="INR",
        status=ItemStatus.ACTIVE,
        typical_cadence_days=float(template["cadence"]),
        last_purchased_at=effective_today
        - timedelta(days=int(template["days_since_purchase"])),
        last_purchase_amount=amount,
        price_threshold=Decimal(str(threshold)) if threshold is not None else None,
        last_observed_price=amount,
    )


def starter_template_sku(template_id: StarterTemplateId) -> str:
    return str(_TEMPLATES[template_id]["merchant_sku_id"])
