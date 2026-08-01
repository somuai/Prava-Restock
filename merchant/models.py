"""Stable merchant boundary shared by real and disclosed-simulation adapters."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ExecutionMode(str, Enum):
    REAL = "real"
    SANDBOX = "sandbox"
    DISCLOSED_MOCK = "disclosed_mock"


class StockStatus(str, Enum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


class CheckoutStatus(str, Enum):
    COMPLETED = "completed"
    OUT_OF_STOCK = "out_of_stock"
    PRICE_CHANGED = "price_changed"
    PENDING = "pending"
    FAILED = "failed"


class MerchantModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MerchantQuote(MerchantModel):
    merchant: str
    merchant_sku_id: str
    product_name: str
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(min_length=3, max_length=3)
    stock_status: StockStatus
    quote_reference: str
    observed_at: datetime
    merchant_context_reference: str | None = None
    execution_mode: ExecutionMode


class MerchantAddressSummary(MerchantModel):
    """Minimal saved-address data safe to return to an authenticated UI."""

    reference: str = Field(min_length=1, max_length=255)
    label: str = Field(min_length=1, max_length=120)


class MerchantCatalogProduct(MerchantModel):
    """A current provider result, not a Restock-owned catalog fixture."""

    merchant: str
    merchant_sku_id: str = Field(min_length=1, max_length=255)
    store_product_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=300)
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(min_length=3, max_length=3)
    available_quantity: int = Field(ge=0)
    stock_status: StockStatus
    execution_mode: ExecutionMode


class MerchantCheckoutResult(MerchantModel):
    status: CheckoutStatus
    merchant_order_id: str | None = None
    charged_amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    currency: str
    retryable: bool = False
    execution_mode: ExecutionMode
    error_code: str | None = None
    disclosure_reason: str | None = None
    credential_exposed: bool = False
    credential_used: bool = False


class MerchantAdapter(Protocol):
    """Merchant-independent quote/checkout/reconciliation contract."""

    def quote(self, **context: Any) -> MerchantQuote: ...
    def checkout(
        self,
        credential_reference: str,
        merchant_sku_id: str,
        amount: Decimal,
        idempotency_key: str,
    ) -> MerchantCheckoutResult: ...
    def reconcile(self, merchant_order_id: str) -> MerchantCheckoutResult: ...
