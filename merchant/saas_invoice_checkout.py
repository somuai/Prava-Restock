"""One-time hosted-invoice checkout with an explicit real-payment gate.

Restock never signs into a vendor dashboard.  A Teams item may carry an HTTPS
hosted invoice URL, which is the only surface this adapter can open.  Real card
execution is disabled unless an operator supplies a reviewed executor and an
exact hostname allowlist; disclosed demo mode never consumes a Prava credential.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import os
from typing import Any, Callable
from uuid import uuid4

from merchant.models import (
    CheckoutStatus,
    ExecutionMode,
    MerchantCheckoutResult,
    MerchantQuote,
    StockStatus,
)
from merchant.zepto_checkout import PaymentRedirectPolicy
from payments import prava_client
from storage.repository import RestockRepository


TEAMS_BILLING_MODE_ENV = "TEAMS_BILLING_MODE"
TEAMS_REAL_PAYMENT_ENABLED_ENV = "TEAMS_REAL_PAYMENT_ENABLED"
TEAMS_RECURRING_ENABLED_ENV = "TEAMS_RECURRING_ENABLED"


@dataclass(frozen=True)
class HostedInvoiceRuntime:
    repository: RestockRepository
    executor: Any
    redirect_policy: PaymentRedirectPolicy
    link_resolver: Callable[[str], str]


_RUNTIME: HostedInvoiceRuntime | None = None
_MOCK_RESULTS: dict[str, MerchantCheckoutResult] = {}


def configure_runtime(runtime: HostedInvoiceRuntime | None) -> None:
    """Inject the reviewed credential-bearing boundary without doing I/O."""

    global _RUNTIME
    _RUNTIME = runtime


def billing_mode() -> ExecutionMode:
    raw = os.getenv(TEAMS_BILLING_MODE_ENV, ExecutionMode.DISCLOSED_MOCK.value)
    if raw not in {ExecutionMode.REAL.value, ExecutionMode.DISCLOSED_MOCK.value}:
        raise RuntimeError(
            f"{TEAMS_BILLING_MODE_ENV} must be real or disclosed_mock; "
            "no generic SaaS billing sandbox exists"
        )
    return ExecutionMode(raw)


def real_payment_runtime_ready() -> bool:
    runtime = _RUNTIME
    return bool(
        runtime is not None
        and runtime.repository
        and runtime.executor is not None
        and runtime.redirect_policy.allowed_hosts
    )


def quote_invoice(
    *,
    invoice_reference: str,
    vendor: str,
    invoice_id: str,
    amount: Decimal,
    currency: str,
) -> MerchantQuote:
    if not invoice_reference or len(invoice_reference) > 255:
        raise ValueError("hosted invoice requires an opaque invoice reference")
    if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-" for character in invoice_reference):
        raise ValueError("hosted invoice reference contains unsupported characters")
    if amount <= 0:
        raise ValueError("invoice amount must be positive")
    if len(currency) != 3:
        raise ValueError("invoice currency must be a three-letter code")
    return MerchantQuote(
        merchant=vendor,
        merchant_sku_id=invoice_id,
        product_name=f"{vendor} hosted invoice",
        amount=amount,
        currency=currency.upper(),
        stock_status=StockStatus.IN_STOCK,
        # This is an opaque lookup key, never the payment URL itself.
        quote_reference=invoice_reference,
        observed_at=datetime.now(timezone.utc),
        execution_mode=ExecutionMode.REAL,
    )


def _result(
    status: CheckoutStatus,
    *,
    order_id: str | None,
    amount: Decimal | None,
    currency: str,
    mode: ExecutionMode,
    error_code: str | None = None,
    retryable: bool = False,
    credential_exposed: bool = False,
    credential_used: bool = False,
) -> dict[str, Any]:
    return MerchantCheckoutResult(
        status=status,
        merchant_order_id=order_id,
        charged_amount=amount,
        currency=currency,
        retryable=retryable,
        execution_mode=mode,
        error_code=error_code,
        credential_exposed=credential_exposed,
        credential_used=credential_used,
    ).model_dump(mode="json")


def _attempt_result(attempt: dict[str, Any]) -> dict[str, Any]:
    state = str(attempt["state"])
    status = {
        "completed": CheckoutStatus.COMPLETED,
        "declined": CheckoutStatus.FAILED,
        "price_changed": CheckoutStatus.PRICE_CHANGED,
        "failed": CheckoutStatus.FAILED,
    }.get(state, CheckoutStatus.PENDING)
    return _result(
        status,
        order_id=attempt.get("merchant_order_id"),
        amount=(
            Decimal(str(attempt["expected_amount"]))
            if status is CheckoutStatus.COMPLETED
            else None
        ),
        currency=str(attempt["currency"]),
        mode=ExecutionMode.REAL,
        error_code=attempt.get("last_error"),
        retryable=False,
        credential_exposed=bool(attempt.get("credential_exposed")),
        credential_used=bool(attempt.get("credential_used")),
    )


def _deliver_report(
    runtime: HostedInvoiceRuntime,
    attempt: dict[str, Any],
    credential_reference: str,
) -> dict[str, Any]:
    claimed = runtime.repository.claim_merchant_checkout_report(
        str(attempt["idempotency_key"])
    )
    if claimed is None:
        return runtime.repository.get_merchant_checkout_attempt(
            str(attempt["idempotency_key"])
        ) or attempt
    try:
        prava_client.report_checkout_outcome(
            str(claimed["prava_session_id"]),
            str(claimed["prava_txn_ref_id"]),
            str(claimed["report_status"]),
            amount_paid=(
                claimed["expected_amount"]
                if claimed["report_status"] == "APPROVED"
                else None
            ),
        )
    except Exception:
        return runtime.repository.update_merchant_checkout_attempt(
            str(claimed["idempotency_key"]),
            expected_report_states={"sending"},
            report_state="ambiguous",
            last_error="PRAVA_REPORT_AMBIGUOUS",
        )
    confirmed = runtime.repository.update_merchant_checkout_attempt(
        str(claimed["idempotency_key"]),
        expected_report_states={"sending"},
        report_state="confirmed",
        prava_reported=True,
    )
    prava_client.retire_credential(credential_reference)
    return confirmed


def _mock_checkout(amount: Decimal, idempotency_key: str) -> dict[str, Any]:
    if idempotency_key not in _MOCK_RESULTS:
        _MOCK_RESULTS[idempotency_key] = MerchantCheckoutResult(
            status=CheckoutStatus.COMPLETED,
            merchant_order_id=f"invoice_mock_{uuid4().hex}",
            charged_amount=amount,
            currency=os.getenv("TEAMS_BILLING_CURRENCY", "USD"),
            retryable=False,
            execution_mode=ExecutionMode.DISCLOSED_MOCK,
            credential_exposed=False,
            credential_used=False,
        )
    return _MOCK_RESULTS[idempotency_key].model_dump(mode="json")


def complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key):
    """Execute one hosted invoice or recurring subscription charge while preserving the Phase-3 signature."""

    if not credential_reference or not merchant_sku_id or not idempotency_key:
        raise ValueError("credential reference, invoice ID, and idempotency key are required")
    try:
        parsed_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("amount must be a valid decimal") from exc
    if parsed_amount <= 0:
        raise ValueError("amount must be positive")

    mode = billing_mode()

    if os.getenv(TEAMS_RECURRING_ENABLED_ENV) == "1":
        if mode is not ExecutionMode.REAL:
            if idempotency_key not in _MOCK_RESULTS:
                _MOCK_RESULTS[idempotency_key] = MerchantCheckoutResult(
                    status=CheckoutStatus.COMPLETED,
                    merchant_order_id=f"recurring_invoice_mock_{uuid4().hex}",
                    charged_amount=parsed_amount,
                    currency=os.getenv("TEAMS_BILLING_CURRENCY", "USD"),
                    retryable=False,
                    execution_mode=ExecutionMode.DISCLOSED_MOCK,
                    disclosure_reason="Subscription checkout is a disclosed simulation with active mandate recurring billing.",
                    credential_exposed=False,
                    credential_used=False,
                )
            return _MOCK_RESULTS[idempotency_key].model_dump(mode="json")

        if os.getenv(TEAMS_REAL_PAYMENT_ENABLED_ENV) != "1":
            raise RuntimeError(
                "real Teams payment is disabled; operator approval is required"
            )

        try:
            charge_result = prava_client.charge_mandate(
                mandate_id=str(credential_reference),
                amount=parsed_amount,
                currency=os.getenv("TEAMS_BILLING_CURRENCY", "USD"),
                merchant_name=str(merchant_sku_id),
                idempotency_key=str(idempotency_key),
                description=f"Teams recurring subscription renewal for {merchant_sku_id}",
            )
            charged_amt = Decimal(str(charge_result.get("charged_amount") or parsed_amount))
            return MerchantCheckoutResult(
                status=CheckoutStatus.COMPLETED,
                merchant_order_id=str(
                    charge_result.get("charge_id")
                    or charge_result.get("txn_ref_id")
                    or f"recurring_{uuid4().hex}"
                ),
                charged_amount=charged_amt,
                currency=str(charge_result.get("currency") or os.getenv("TEAMS_BILLING_CURRENCY", "USD")),
                retryable=False,
                execution_mode=ExecutionMode.REAL,
                credential_exposed=False,
                credential_used=True,
            ).model_dump(mode="json")
        except prava_client.PravaAPIError as exc:
            return MerchantCheckoutResult(
                status=CheckoutStatus.FAILED,
                merchant_order_id=None,
                charged_amount=None,
                currency=os.getenv("TEAMS_BILLING_CURRENCY", "USD"),
                retryable=False,
                execution_mode=ExecutionMode.REAL,
                error_code=str(exc.code),
                credential_exposed=False,
                credential_used=False,
            ).model_dump(mode="json")

    if mode is not ExecutionMode.REAL:
        # A disclosed simulation intentionally does not consume, expose, or
        # report the one-time Prava credential.
        return _mock_checkout(parsed_amount, str(idempotency_key))
    if os.getenv(TEAMS_REAL_PAYMENT_ENABLED_ENV) != "1":
        raise RuntimeError(
            "real Teams payment is disabled; operator approval is required"
        )
    runtime = _RUNTIME
    if runtime is None or not real_payment_runtime_ready():
        raise RuntimeError("hosted-invoice payment runtime is not configured")

    existing = runtime.repository.get_merchant_checkout_attempt(str(idempotency_key))
    if existing is not None:
        if (
            existing["merchant"] != "teams_hosted_invoice"
            or existing["merchant_sku_id"] != str(merchant_sku_id)
            or Decimal(str(existing["expected_amount"])) != parsed_amount
        ):
            raise ValueError("idempotency key is already bound to another checkout")
        return _attempt_result(existing)

    run = runtime.repository.workflow_for_checkout_key(str(idempotency_key))
    quote = run.get("quote") or {}
    invoice_reference = str(quote.get("quote_reference") or "")
    invoice_url = runtime.link_resolver(invoice_reference)
    runtime.redirect_policy.validate_url(invoice_url)
    if (
        str(quote.get("merchant_sku_id")) != str(merchant_sku_id)
        or Decimal(str(quote.get("amount"))) != parsed_amount
        or str(quote.get("currency", "")).upper() != str(run["currency"]).upper()
    ):
        raise ValueError("hosted invoice does not match the approved workflow quote")

    reporting = prava_client.credential_reporting_context(str(credential_reference))
    attempt, created = runtime.repository.reserve_merchant_checkout_attempt(
        idempotency_key=str(idempotency_key),
        merchant="teams_hosted_invoice",
        merchant_sku_id=str(merchant_sku_id),
        expected_amount=parsed_amount,
        currency=str(run["currency"]).upper(),
        prava_session_id=reporting["session_id"],
        prava_txn_ref_id=reporting["txn_ref_id"],
    )
    if not created:
        return _attempt_result(attempt)

    runtime.repository.update_merchant_checkout_attempt(
        str(idempotency_key),
        expected_states={"reserved"},
        state="executing",
        credential_exposed=True,
        credential_used=False,
    )
    credential = prava_client.consume_credential(str(credential_reference))
    try:
        execution = runtime.executor.execute(
            payment_link=invoice_url,
            token=str(credential["token"]),
            dynamic_cvv=str(credential["dynamic_cvv"]),
            expiry_month=str(credential["expiry_month"]),
            expiry_year=str(credential["expiry_year"]),
            redirect_policy=runtime.redirect_policy,
            expected_amount=str(parsed_amount),
            currency=str(run["currency"]).upper(),
        )
    except Exception:
        attempt = runtime.repository.update_merchant_checkout_attempt(
            str(idempotency_key),
            expected_states={"executing"},
            state="ambiguous",
            last_error="AUTOMATION_FAILURE",
        )
        return _attempt_result(attempt)

    observed_currency = str(execution.get("currency") or run["currency"]).upper()
    observed_amount = Decimal(str(execution.get("observed_amount") or parsed_amount))
    credential_used = execution.get("credential_used") is True
    if observed_currency != str(run["currency"]).upper() or observed_amount != parsed_amount:
        state = "ambiguous" if credential_used else "price_changed"
        attempt = runtime.repository.update_merchant_checkout_attempt(
            str(idempotency_key),
            expected_states={"executing"},
            state=state,
            credential_used=credential_used,
            last_error=(
                "PRICE_CHANGED_AFTER_CREDENTIAL_EXPOSURE"
                if credential_used
                else "PRICE_CHANGED"
            ),
        )
        if not credential_used:
            prava_client.retire_credential(str(credential_reference))
        if state == "price_changed":
            return _result(
                CheckoutStatus.PRICE_CHANGED,
                order_id=None,
                amount=observed_amount,
                currency=observed_currency,
                mode=ExecutionMode.REAL,
                error_code="PRICE_CHANGED",
                credential_exposed=True,
                credential_used=False,
            )
        return _attempt_result(attempt)

    payment_status = str(execution.get("payment_status", "pending"))
    order_id = execution.get("merchant_order_id")
    if payment_status == "completed" and (not credential_used or not order_id):
        payment_status = "pending"
    state = {
        "completed": "completed",
        "failed": "declined",
    }.get(payment_status, "pending")
    changes: dict[str, Any] = {
        "state": state,
        "merchant_order_id": str(order_id) if order_id else None,
        "credential_used": credential_used,
        "last_error": None if state == "completed" else (
            "PAYMENT_DECLINED" if state == "declined" else "PAYMENT_PENDING"
        ),
    }
    if state in {"completed", "declined"} and credential_used:
        changes.update(
            report_status="APPROVED" if state == "completed" else "DECLINED",
            report_state="pending",
        )
    attempt = runtime.repository.update_merchant_checkout_attempt(
        str(idempotency_key), expected_states={"executing"}, **changes
    )
    if changes.get("report_state") == "pending":
        attempt = _deliver_report(runtime, attempt, str(credential_reference))
    return _attempt_result(attempt)


def reconcile_checkout(idempotency_key: str) -> dict[str, Any]:
    """Return durable status without blindly repeating a hosted payment."""

    if _RUNTIME is None:
        raise RuntimeError("hosted-invoice payment runtime is not configured")
    attempt = _RUNTIME.repository.get_merchant_checkout_attempt(str(idempotency_key))
    if attempt is None:
        raise KeyError(f"unknown hosted-invoice checkout: {idempotency_key}")
    return _attempt_result(attempt)


def reconcile(merchant_order_id: str) -> MerchantCheckoutResult:
    """Compatibility lookup for disclosed-mock invoice results."""

    for result in _MOCK_RESULTS.values():
        if result.merchant_order_id == merchant_order_id:
            return result
    return MerchantCheckoutResult(
        status=CheckoutStatus.FAILED,
        merchant_order_id=merchant_order_id,
        currency=os.getenv("TEAMS_BILLING_CURRENCY", "USD"),
        retryable=False,
        execution_mode=ExecutionMode.DISCLOSED_MOCK,
        error_code="UNKNOWN_INVOICE",
    )
