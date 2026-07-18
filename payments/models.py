"""Canonical in-memory data contracts for both Restock trigger tracks.

Payment instrument details never belong in these models. Mandates retain only
the opaque credential reference supplied by Prava.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Track(str, Enum):
    HOME = "home"
    TEAMS = "teams"


class TriggerType(str, Enum):
    PREDICTED = "predicted"
    KNOWN_DATE = "known_date"


class Category(str, Enum):
    GROCERY = "grocery"
    STATIONERY = "stationery"
    HEALTH = "health"
    SAAS_SUBSCRIPTION = "saas_subscription"
    OTHER = "other"


class PreferredMerchant(str, Enum):
    ZEPTO = "zepto"
    SWIGGY = "swiggy"
    MOCK_SUBSCRIPTION_BILLING = "mock_subscription_billing"
    MOCK = "mock"


class ItemStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class IntentStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ADJUSTED = "adjusted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TransactionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    DISPUTED = "disputed"


class AuditEventType(str, Enum):
    NOTIFICATION_SENT = "notification_sent"
    APPROVED = "approved"
    ADJUSTED = "adjusted"
    SKIPPED = "skipped"
    TRANSACTION_COMPLETED = "transaction_completed"
    TRANSACTION_FAILED = "transaction_failed"
    ITEM_DELETED = "item_deleted"
    DATA_EXPORTED = "data_exported"


PositiveDecimal = Field(gt=Decimal("0"))
PositiveFloat = Field(gt=0)


class RestockModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class User(RestockModel):
    user_id: UUID
    display_name: str
    prava_account_ref: str
    monthly_cap: Decimal = PositiveDecimal
    per_item_cap: Decimal = PositiveDecimal
    per_transaction_cap: Decimal = PositiveDecimal
    created_at: datetime


class TrackedItem(RestockModel):
    """An item on either the forecast track or the known-renewal track.

    Predicted items carry cadence and last-purchase data. Known-date items carry
    a factual renewal date plus current and alternate plan pricing.
    """

    item_id: UUID
    user_id: UUID
    tenant_id: UUID | None = None
    name: str
    track: Track
    trigger_type: TriggerType
    category: Category
    sensitive_flag: bool
    preferred_merchant: PreferredMerchant
    merchant_sku_id: str
    currency: str = Field(min_length=3, max_length=3)
    status: ItemStatus

    typical_cadence_days: float | None = Field(default=None, gt=0)
    last_purchased_at: date | None = None
    last_purchase_amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    price_threshold: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    last_observed_price: Optional[Decimal] = Field(default=None, gt=Decimal("0"))

    renewal_date: date | None = None
    current_plan_amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    alternate_plan_amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    alternate_plan_label: str | None = None

    @model_validator(mode="after")
    def validate_trigger_fields(self) -> "TrackedItem":
        predicted_fields = (
            self.typical_cadence_days,
            self.last_purchased_at,
            self.last_purchase_amount,
        )
        optional_predicted_fields = (
            self.price_threshold,
            self.last_observed_price,
        )
        known_date_fields = (
            self.renewal_date,
            self.current_plan_amount,
            self.alternate_plan_amount,
            self.alternate_plan_label,
        )
        if self.trigger_type is TriggerType.PREDICTED:
            if any(value is None for value in predicted_fields):
                raise ValueError("predicted items require all predicted-trigger fields")
            if any(value is not None for value in known_date_fields):
                raise ValueError("predicted items cannot set known-date fields")
        else:
            if any(value is None for value in known_date_fields):
                raise ValueError("known-date items require all known-date fields")
            if any(
                value is not None
                for value in predicted_fields + optional_predicted_fields
            ):
                raise ValueError("known-date items cannot set predicted-trigger fields")
        return self


class Intent(RestockModel):
    intent_id: UUID
    item_id: UUID
    proposed_amount: Decimal = PositiveDecimal
    proposed_merchant: str
    currency: str = Field(min_length=3, max_length=3)
    status: IntentStatus
    created_at: datetime


class Mandate(RestockModel):
    mandate_id: str
    intent_id: UUID
    credential_reference: str
    scope_merchant: str
    scope_max_amount: Decimal = PositiveDecimal
    scope_expiry: datetime
    passkey_approved_at: datetime


class Transaction(RestockModel):
    transaction_id: UUID
    mandate_id: str
    item_id: UUID
    merchant_order_id: str
    amount: Decimal = PositiveDecimal
    currency: str = Field(min_length=3, max_length=3)
    status: TransactionStatus
    completed_at: datetime


class AuditLogEntry(RestockModel):
    log_id: UUID
    user_id: UUID
    event_type: AuditEventType
    payload: dict[str, Any]
    timestamp: datetime
