from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from merchant import saas_invoice_checkout
from merchant.models import ExecutionMode, StockStatus
from merchant.swiggy_checkout import SwiggyAdapter
from merchant.zepto_checkout import PaymentRedirectPolicy
from payments import prava_client
from payments.models import TrackedItem, User
from storage import Database, RestockRepository


class FakeSwiggy:
    def view_cart(self):
        return {"cart": {"cartId": "cart-1", "toPay": "512.50", "available": True}}


def test_swiggy_quote_is_real_but_card_checkout_is_never_replaced_by_cod() -> None:
    adapter = SwiggyAdapter(FakeSwiggy())
    quote = adapter.quote(merchant_sku_id="sku-1", product_name="Rice")
    assert quote.amount == Decimal("512.50")
    assert quote.stock_status is StockStatus.IN_STOCK
    assert quote.execution_mode is ExecutionMode.REAL
    with pytest.raises(RuntimeError, match="never substitutes COD"):
        adapter.checkout("credential", "sku-1", quote.amount, "idem-1")


def test_swiggy_out_of_stock_is_not_substituted() -> None:
    adapter = SwiggyAdapter(FakeSwiggy())
    quote = adapter.quote(
        merchant_sku_id="sku-1",
        product_name="Rice",
        cart={"total": "500", "available": False},
    )
    assert quote.stock_status is StockStatus.OUT_OF_STOCK


def test_one_time_invoice_is_https_idempotent_and_disclosed(monkeypatch) -> None:
    quote = saas_invoice_checkout.quote_invoice(
        invoice_reference="example-invoice-123",
        vendor="Example SaaS",
        invoice_id="invoice-123",
        amount=Decimal("29"),
        currency="USD",
    )
    assert quote.execution_mode is ExecutionMode.REAL
    first = saas_invoice_checkout.complete_checkout("credential", "invoice-123", "29", "invoice-idem")
    second = saas_invoice_checkout.complete_checkout("credential", "invoice-123", "29", "invoice-idem")
    assert first == second
    assert first["execution_mode"] == "disclosed_mock"
    with pytest.raises(ValueError, match="unsupported characters"):
        saas_invoice_checkout.quote_invoice(
            invoice_reference="not/a/reference",
            vendor="Example SaaS",
            invoice_id="invoice-123",
            amount=Decimal("29"),
            currency="USD",
        )
    monkeypatch.setenv("TEAMS_RECURRING_ENABLED", "1")
    recurring_res = saas_invoice_checkout.complete_checkout("mandate-124", "invoice-124", "29", "invoice-idem-2")
    assert recurring_res["status"] == "completed"
    assert recurring_res["execution_mode"] == "disclosed_mock"
    assert "recurring billing" in recurring_res.get("disclosure_reason", "").lower()

    # Test real recurring mandate charging
    monkeypatch.setenv("TEAMS_BILLING_MODE", "real")
    monkeypatch.setenv("TEAMS_REAL_PAYMENT_ENABLED", "1")
    monkeypatch.setattr(prava_client, "STUB_MODE", True)
    real_recurring = saas_invoice_checkout.complete_checkout("mandate-125", "invoice-125", "29.99", "invoice-idem-3")
    assert real_recurring["status"] == "completed"
    assert real_recurring["execution_mode"] == "real"
    assert str(real_recurring["charged_amount"]) == "29.99"



class _HostedExecutor:
    def __init__(self, *, observed_amount: str = "29.00") -> None:
        self.calls = 0
        self.observed_amount = observed_amount

    def execute(self, **kwargs):
        self.calls += 1
        kwargs["redirect_policy"].validate_url(kwargs["payment_link"])
        return {
            "visited_urls": [kwargs["payment_link"]],
            "credential_used": False if self.observed_amount != "29.00" else True,
            "payment_status": "pending" if self.observed_amount != "29.00" else "completed",
            "merchant_order_id": "invoice-order-123",
            "observed_amount": self.observed_amount,
            "currency": "USD",
        }


def _real_invoice_repository(tmp_path) -> tuple[RestockRepository, str]:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'teams.db'}"))
    repository.create_schema()
    user_id = UUID("00000000-0000-0000-0000-000000000071")
    item = TrackedItem(
        item_id=UUID("00000000-0000-0000-0000-000000000072"),
        user_id=user_id,
        name="Example SaaS",
        track="teams",
        trigger_type="known_date",
        category="saas_subscription",
        sensitive_flag=False,
        preferred_merchant="mock_subscription_billing",
        merchant_sku_id="invoice-123",
        currency="USD",
        status="active",
        renewal_date=date.today() + timedelta(days=2),
        current_plan_amount="29",
        alternate_plan_amount="24",
        alternate_plan_label="annual",
        renewal_method="hosted_link",
        hosted_payment_reference="example-invoice-123",
    )
    repository.upsert_user(User(
        user_id=user_id,
        display_name="Asha",
        prava_account_ref="prava-user",
        monthly_cap="1000",
        per_item_cap="100",
        per_transaction_cap="100",
        created_at=datetime.now(timezone.utc),
    ))
    repository.upsert_item(item)
    quote = saas_invoice_checkout.quote_invoice(
        invoice_reference=item.hosted_payment_reference or "",
        vendor=item.preferred_merchant.value,
        invoice_id=item.merchant_sku_id,
        amount=Decimal("29"),
        currency="USD",
    )
    run = repository.create_workflow(
        user_id=str(user_id),
        item_id=str(item.item_id),
        trigger_reason="known_renewal_date",
        proposed_amount=Decimal("29"),
        currency="USD",
        merchant=item.preferred_merchant.value,
        proposed_action="renew_as_is",
        quote=quote.model_dump(mode="json"),
        modes={"prava": "production", "teams_billing": "real"},
        idempotency_key="teams-idem-1",
    )
    return repository, run["idempotency_key"]


def _configure_real_invoice(monkeypatch, repository, executor) -> list[str]:
    monkeypatch.setenv("TEAMS_BILLING_MODE", "real")
    monkeypatch.setenv("TEAMS_REAL_PAYMENT_ENABLED", "1")
    monkeypatch.setenv("TEAMS_RECURRING_ENABLED", "0")
    saas_invoice_checkout.configure_runtime(
        saas_invoice_checkout.HostedInvoiceRuntime(
            repository=repository,
            executor=executor,
            redirect_policy=PaymentRedirectPolicy(("billing.example.test",)),
            link_resolver=lambda reference: (
                "https://billing.example.test/invoice/123"
                if reference == "example-invoice-123"
                else ""
            ),
        )
    )
    retired: list[str] = []
    monkeypatch.setattr(
        prava_client,
        "credential_reporting_context",
        lambda _: {"session_id": "session-1", "txn_ref_id": "txn-1"},
    )
    monkeypatch.setattr(
        prava_client,
        "consume_credential",
        lambda _: {
            "token": "one-time-token",
            "dynamic_cvv": "123",
            "expiry_month": "12",
            "expiry_year": "30",
        },
    )
    monkeypatch.setattr(prava_client, "report_checkout_outcome", lambda *args, **kwargs: {})
    monkeypatch.setattr(prava_client, "retire_credential", retired.append)
    return retired


def test_real_hosted_invoice_is_allowlisted_durable_and_idempotent(tmp_path, monkeypatch) -> None:
    repository, idempotency_key = _real_invoice_repository(tmp_path)
    executor = _HostedExecutor()
    retired = _configure_real_invoice(monkeypatch, repository, executor)

    first = saas_invoice_checkout.complete_checkout(
        "credential-1", "invoice-123", "29", idempotency_key
    )
    second = saas_invoice_checkout.complete_checkout(
        "credential-1", "invoice-123", "29", idempotency_key
    )

    assert first["status"] == "completed"
    assert first["execution_mode"] == "real"
    assert second == first
    assert executor.calls == 1
    assert retired == ["credential-1"]
    attempt = repository.get_merchant_checkout_attempt(idempotency_key)
    assert attempt is not None
    assert attempt["state"] == "completed"
    assert attempt["report_state"] == "confirmed"


def test_real_hosted_invoice_price_change_never_uses_credential(tmp_path, monkeypatch) -> None:
    repository, idempotency_key = _real_invoice_repository(tmp_path)
    executor = _HostedExecutor(observed_amount="35.00")
    retired = _configure_real_invoice(monkeypatch, repository, executor)

    result = saas_invoice_checkout.complete_checkout(
        "credential-2", "invoice-123", "29", idempotency_key
    )

    assert result["status"] == "price_changed"
    assert result["charged_amount"] == "35.00"
    assert result["credential_used"] is False
    assert retired == ["credential-2"]
