"""Durable workflow state machine; models propose, code owns payment safety."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from contextlib import ExitStack, contextmanager
import os
from typing import Any, Callable, Protocol
from uuid import uuid4

from merchant import saas_invoice_checkout, swiggy_checkout, zepto_checkout
from merchant.models import CheckoutStatus, MerchantQuote, StockStatus
from payments import prava_client
from payments.models import TrackedItem, TriggerType, User
from storage.repository import RestockRepository
from triggers import consumption_model, renewal_model


class WorkflowState(str, Enum):
    TRIGGERED = "triggered"
    QUOTE_PENDING = "quote_pending"
    INTENT_CREATED = "intent_created"
    NOTIFIED = "notified"
    PASSKEY_PENDING = "passkey_pending"
    MANDATE_APPROVED = "mandate_approved"
    QUOTE_REVALIDATED = "quote_revalidated"
    CHECKOUT_PENDING = "checkout_pending"
    REAPPROVAL_REQUIRED = "reapproval_required"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PravaBoundary(Protocol):
    def create_intent(self, merchant, amount, item_description, constraints): ...
    def await_mandate(self, intent_ref): ...


class CheckoutBoundary(Protocol):
    def complete_checkout(
        self, credential_reference, merchant_sku_id, amount, idempotency_key
    ): ...


class WorkflowService:
    def __init__(
        self,
        repository: RestockRepository,
        *,
        prava: PravaBoundary = prava_client,
        home_checkout: CheckoutBoundary | None = None,
        teams_checkout: CheckoutBoundary = saas_invoice_checkout,
        quote_provider: Any | None = None,
    ) -> None:
        self.repository = repository
        self.prava = prava
        self.home_checkout = home_checkout
        self.teams_checkout = teams_checkout
        self.quote_provider = quote_provider

    @staticmethod
    def _proposal(item: TrackedItem) -> dict[str, Any]:
        return (
            consumption_model.propose(item)
            if item.trigger_type is TriggerType.PREDICTED
            else renewal_model.propose(item)
        )

    @staticmethod
    def _trigger_reason(item: TrackedItem) -> str:
        if item.trigger_type is TriggerType.KNOWN_DATE:
            return "known_renewal_date"
        depletion = consumption_model.trigger_condition(item)
        price = consumption_model.price_trigger_condition(item)
        if depletion and price:
            return "depletion_and_price"
        return "price_threshold" if price else "predicted_depletion"

    def _prava_mode(self) -> str:
        if self.prava is prava_client:
            return prava_client.configured_mode()
        raw = getattr(self.prava, "mode", "disclosed_mock")
        value = raw() if callable(raw) else raw
        return str(value) if str(value) in {
            "production", "sandbox", "disclosed_mock", "unconfigured"
        } else "disclosed_mock"

    @staticmethod
    def _quote_audit_payload(quote: MerchantQuote) -> dict[str, Any]:
        return {
            "quote_reference": quote.quote_reference,
            "observed_at": quote.observed_at.isoformat(),
            "amount": str(quote.amount),
            "currency": quote.currency,
            "stock_status": quote.stock_status.value,
            "execution_mode": quote.execution_mode.value,
        }

    def _enforce_caps(
        self,
        user: User,
        amount: Decimal,
        *,
        exclude_run_id: str | None = None,
    ) -> None:
        if amount <= 0:
            raise ValueError("proposed amount must be positive")
        if amount > user.per_item_cap or amount > user.per_transaction_cap:
            raise ValueError("proposal exceeds per-item or per-transaction cap")
        committed = (
            self.repository.monthly_spend(str(user.user_id))
            + self.repository.active_workflow_commitments(
                str(user.user_id), exclude_run_id=exclude_run_id
            )
        )
        if committed + amount > user.monthly_cap:
            raise ValueError("proposal would exceed monthly cap")

    @contextmanager
    def _budget_scope(self, user_id: str):
        owner_id = f"budget-{uuid4().hex}"
        lease_name = f"spend-budget:{user_id}"
        lease_seconds = min(
            max(int(os.getenv("RESTOCK_BUDGET_LEASE_SECONDS", "300")), 30),
            900,
        )
        if not self.repository.acquire_lease(
            lease_name=lease_name,
            owner_id=owner_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=lease_seconds),
        ):
            raise ValueError("another workflow is reserving this user's spend budget")

        def renew_fence() -> None:
            if not self.repository.renew_lease(
                lease_name=lease_name,
                owner_id=owner_id,
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=lease_seconds),
            ):
                raise ValueError(
                    "spend-budget reservation expired or changed owner; retry safely"
                )

        try:
            yield renew_fence
        finally:
            self.repository.release_lease(lease_name=lease_name, owner_id=owner_id)

    def _checkout_for_item(self, item: TrackedItem) -> CheckoutBoundary:
        if item.trigger_type is TriggerType.KNOWN_DATE:
            return self.teams_checkout
        if self.home_checkout is not None:
            return self.home_checkout
        if item.preferred_merchant.value == "swiggy":
            return swiggy_checkout
        return zepto_checkout

    def _quote_provider_supports(self, item: TrackedItem) -> bool:
        if self.quote_provider is None:
            return False
        supports = getattr(self.quote_provider, "supports", None)
        return bool(supports(item)) if callable(supports) else item.trigger_type is TriggerType.PREDICTED

    def _retire_unused_credential(self, credential_reference: str) -> None:
        """Delete an unused credential without reporting a merchant decline."""

        retire = getattr(self.prava, "retire_credential", None)
        if callable(retire):
            retire(credential_reference)

    def _apply_completion_effects(
        self,
        run: dict[str, Any],
        item: TrackedItem,
        transaction: dict[str, Any],
    ) -> None:
        item_payload = None
        forecast = None
        if item.trigger_type is TriggerType.PREDICTED:
            assert item.last_purchased_at is not None
            completed_at = transaction["completed_at"]
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            reorder_date = completed_at.date()
            predicted_date = consumption_model.predicted_depletion_date(item)
            observed = max(1, (reorder_date - item.last_purchased_at).days)
            tenant_id = (
                str(item.tenant_id)
                if item.tenant_id
                else self.repository.personal_tenant_id(str(item.user_id))
            )
            forecast = {
                "tenant_id": tenant_id,
                "user_id": str(item.user_id),
                "item_id": str(item.item_id),
                "predicted_depletion_date": predicted_date.isoformat(),
                "actual_reorder_date": reorder_date.isoformat(),
                "category": item.category.value,
                "quantity": Decimal(str(item.quantity)) if item.quantity else None,
                "household_size": None,
                "trigger_cause": run["trigger_reason"],
                "notification_action": "approved",
                "forecast_error_days": float((reorder_date - predicted_date).days),
                "model_version": "ewma-v1",
            }
            consumption_model.recalibrate(item, observed)
            item.last_purchased_at = reorder_date
            item.last_purchase_amount = Decimal(str(transaction["amount"]))
            item_payload = item.model_dump(mode="json")
        self.repository.apply_completion_effects(
            run_id=run["run_id"],
            item_payload=item_payload,
            forecast=forecast,
        )

    def repair_completion_effects(self, run_id: str) -> dict[str, Any]:
        """Replay required post-payment work after a process crash."""

        run = self.repository.get_workflow(run_id)
        if run["state"] != WorkflowState.COMPLETED.value:
            raise ValueError("workflow is not completed")
        transaction = self.repository.transaction_for_run(run_id)
        if transaction is None:
            raise ValueError("completed workflow has no transaction")
        item = self.repository.get_item(run["item_id"])
        self._apply_completion_effects(run, item, transaction)
        return self.repository.get_workflow(run_id)

    def repair_pending_completion_effects(self, *, limit: int = 100) -> int:
        """Drain durable completion work after deployment or worker restart."""

        repaired = 0
        for run_id in self.repository.pending_completion_run_ids(limit=limit):
            self.repair_completion_effects(run_id)
            repaired += 1
        return repaired

    @staticmethod
    def _validate_quote_binding(item: TrackedItem, quote: MerchantQuote) -> None:
        expected_merchant = item.preferred_merchant.value
        if quote.merchant != expected_merchant:
            raise ValueError("merchant quote does not match the tracked merchant")
        if quote.merchant_sku_id != item.merchant_sku_id:
            raise ValueError("merchant quote does not match the tracked exact SKU")
        if quote.currency != item.currency:
            raise ValueError("merchant quote currency does not match the tracked item")

    @staticmethod
    def _validate_quote_usable(quote: MerchantQuote) -> None:
        if quote.stock_status is StockStatus.OUT_OF_STOCK:
            raise ValueError("merchant quote is out of stock")
        if quote.stock_status is StockStatus.UNKNOWN:
            raise ValueError("merchant quote does not confirm the exact SKU is in stock")
        ttl_seconds = int(os.getenv("ZEPTO_QUOTE_MAX_AGE_SECONDS", "60"))
        if ttl_seconds <= 0:
            raise ValueError("quote TTL must be positive")
        if quote.observed_at.tzinfo is None:
            raise ValueError("merchant quote observation time must be timezone-aware")
        age = datetime.now(timezone.utc) - quote.observed_at
        if age < timedelta(0):
            raise ValueError("merchant quote observation time cannot be in the future")
        if age > timedelta(seconds=ttl_seconds):
            raise ValueError("merchant quote has expired")

    @staticmethod
    def _validate_revalidation_binding(
        run: dict[str, Any], item: TrackedItem, quote: MerchantQuote
    ) -> None:
        WorkflowService._validate_quote_binding(item, quote)
        initial_quote = run.get("quote") or {}
        initial_sku = initial_quote.get("merchant_sku_id")
        if quote.merchant != run["merchant"]:
            raise ValueError("revalidated quote changed merchant")
        if initial_sku and quote.merchant_sku_id != initial_sku:
            raise ValueError("revalidated quote changed exact SKU")
        if quote.currency != run["currency"]:
            raise ValueError("revalidated quote changed currency")

    @contextmanager
    def _post_mandate_failure_guard(
        self,
        run_id: str,
        item: TrackedItem,
        credential_reference: str,
    ):
        """Persist sanitized failure state without guessing merchant outcomes."""

        try:
            yield
        except Exception:
            current = self.repository.get_workflow(run_id)
            state = current["state"]
            if state in {
                WorkflowState.PASSKEY_PENDING.value,
                WorkflowState.MANDATE_APPROVED.value,
            }:
                # Checkout has not been invoked, so the credential is provably
                # unexposed and may be retired without reporting DECLINED.
                try:
                    self._retire_unused_credential(credential_reference)
                except Exception:
                    pass
                current = self.repository.transition(
                    run_id,
                    expected={state},
                    state=WorkflowState.FAILED.value,
                    error_code="PRECHECK_BOUNDARY_FAILED",
                )
                event_type = "precheckout_failed"
            elif state == WorkflowState.QUOTE_REVALIDATED.value:
                # Once the checkout boundary is entered, credential exposure and
                # merchant mutation are ambiguous. Preserve for reconciliation.
                current = self.repository.transition(
                    run_id,
                    expected={WorkflowState.QUOTE_REVALIDATED.value},
                    state=WorkflowState.CHECKOUT_PENDING.value,
                    error_code="CHECKOUT_BOUNDARY_AMBIGUOUS",
                )
                event_type = "checkout_boundary_ambiguous"
            else:
                event_type = "post_mandate_failure"
            self.repository.audit(
                user_id=current["user_id"],
                run_id=run_id,
                item_id=str(item.item_id),
                event_type=event_type,
                payload={"reason": current.get("error_code") or "BOUNDARY_FAILURE"},
                modes=current["modes"],
            )
            raise RuntimeError(
                "post-mandate boundary failed; durable workflow state was recorded"
            ) from None

    def _finish_checkout(
        self,
        run: dict[str, Any],
        item: TrackedItem,
        response: dict[str, Any],
        *,
        expected_state: WorkflowState,
        credential_reference: str | None = None,
    ) -> dict[str, Any]:
        """Persist a merchant outcome without treating uncertainty as failure."""

        raw_status = response.get("status")
        status_value = raw_status.value if isinstance(raw_status, CheckoutStatus) else str(raw_status)
        execution_mode = str(response.get("execution_mode") or "disclosed_mock")
        disclosure_reason = response.get("disclosure_reason")
        audit_modes = dict(run["modes"])
        mode_key = (
            "teams_billing"
            if item.trigger_type is TriggerType.KNOWN_DATE
            else "home_payment"
        )
        audit_modes[mode_key] = execution_mode
        if disclosure_reason:
            audit_modes[f"{mode_key}_reason"] = str(disclosure_reason)
        credential_provably_unexposed = (
            response.get("credential_exposed") is False
            or (
                "credential_exposed" not in response
                and execution_mode != "real"
            )
        )
        if status_value == CheckoutStatus.PENDING.value:
            if credential_reference and credential_provably_unexposed:
                self._retire_unused_credential(credential_reference)
            pending = self.repository.transition(
                run["run_id"],
                expected={expected_state.value},
                state=WorkflowState.CHECKOUT_PENDING.value,
                error_code=str(response.get("error_code") or "PAYMENT_PENDING"),
            )
            self.repository.audit(
                user_id=run["user_id"],
                run_id=run["run_id"],
                item_id=run["item_id"],
                event_type="checkout_pending",
                payload={
                    "merchant_order_id": response.get("merchant_order_id"),
                    "retryable": bool(response.get("retryable", False)),
                    "reason": disclosure_reason
                    or response.get("error_code")
                    or "PAYMENT_PENDING",
                    "execution_mode": execution_mode,
                },
                modes=audit_modes,
            )
            return pending
        if status_value == CheckoutStatus.PRICE_CHANGED.value:
            if credential_reference and credential_provably_unexposed:
                self._retire_unused_credential(credential_reference)
            changed_amount = response.get("charged_amount")
            changes: dict[str, Any] = {
                "mandate_ref": None,
                "error_code": "PRICE_CHANGED",
            }
            if changed_amount is not None:
                changes["proposed_amount"] = Decimal(str(changed_amount))
            reapproval = self.repository.transition(
                run["run_id"],
                expected={expected_state.value},
                state=WorkflowState.REAPPROVAL_REQUIRED.value,
                **changes,
            )
            self.repository.create_notification(
                run_id=run["run_id"],
                user_id=run["user_id"],
                message="The final merchant price changed. Review the fresh amount and approve again before payment.",
                actions=(
                    ["renew_as_is", "switch_plan", "skip"]
                    if item.trigger_type is TriggerType.KNOWN_DATE
                    else ["approve", "adjust", "skip"]
                ),
            )
            self.repository.audit(
                user_id=run["user_id"],
                run_id=run["run_id"],
                item_id=run["item_id"],
                event_type="reapproval_required",
                payload={"reason": "price_changed", "fresh_amount": changed_amount},
                modes=audit_modes,
            )
            return reapproval
        if status_value != CheckoutStatus.COMPLETED.value:
            if credential_reference and credential_provably_unexposed:
                self._retire_unused_credential(credential_reference)
            failed = self.repository.transition(
                run["run_id"],
                expected={expected_state.value},
                state=WorkflowState.FAILED.value,
                error_code=status_value.upper(),
            )
            self.repository.audit(
                user_id=run["user_id"], run_id=run["run_id"], item_id=run["item_id"],
                event_type="checkout_failed",
                payload={
                    "reason": disclosure_reason or response.get("error_code") or status_value,
                    "execution_mode": execution_mode,
                },
                modes=audit_modes,
            )
            return failed

        final, transaction = self.repository.complete_checkout_atomically(
            run_id=run["run_id"],
            expected_state=expected_state.value,
            item_id=run["item_id"],
            mandate_ref=str(run.get("mandate_ref") or "mandate_approved"),
            merchant_order_id=response["merchant_order_id"],
            amount=Decimal(str(response.get("charged_amount") or run["proposed_amount"])),
            currency=str(response.get("currency") or run["currency"]),
            execution_mode=execution_mode,
            disclosure_reason=(
                str(disclosure_reason) if disclosure_reason is not None else None
            ),
        )
        if credential_reference and credential_provably_unexposed:
            self._retire_unused_credential(credential_reference)
        self._apply_completion_effects(final, item, transaction)
        return final

    def begin(
        self,
        user: User,
        item: TrackedItem,
        *,
        quote: MerchantQuote | None = None,
    ) -> dict[str, Any]:
        with self._budget_scope(str(user.user_id)) as renew_budget_fence:
            return self._begin(
                user,
                item,
                quote=quote,
                renew_budget_fence=renew_budget_fence,
            )

    def _begin(
        self,
        user: User,
        item: TrackedItem,
        *,
        quote: MerchantQuote | None = None,
        renew_budget_fence: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        proposal = self._proposal(item)
        if proposal.get("autonomous_action") is False:
            if quote is not None:
                raise ValueError("manual renewal cannot accept a merchant quote")
            modes = {
                "prava": "not_applicable",
                "home_merchant": "not_applicable",
                "home_catalog": "not_applicable",
                "home_payment": "not_applicable",
                "teams_billing": "manual_required",
            }
            self.repository.upsert_user(user)
            self.repository.upsert_item(item)
            run = self.repository.create_workflow(
                user_id=str(user.user_id),
                item_id=str(item.item_id),
                trigger_reason=self._trigger_reason(item),
                proposed_amount=None,
                currency=item.currency,
                merchant=None,
                proposed_action=proposal.get("proposed_action"),
                quote=None,
                modes=modes,
                idempotency_key=f"restock-{uuid4().hex}",
            )
            self.repository.audit(
                user_id=str(user.user_id),
                run_id=run["run_id"],
                item_id=str(item.item_id),
                event_type="triggered",
                payload={"trigger_reason": run["trigger_reason"]},
                modes=modes,
            )
            actions = ["skip"]
            notification = self.repository.create_notification(
                run_id=run["run_id"],
                user_id=str(user.user_id),
                message=str(proposal["message"]),
                actions=actions,
            )
            run = self.repository.transition(
                run["run_id"],
                expected={WorkflowState.TRIGGERED.value},
                state=WorkflowState.NOTIFIED.value,
            )
            self.repository.audit(
                user_id=str(user.user_id),
                run_id=run["run_id"],
                item_id=str(item.item_id),
                event_type="manual_renewal_flagged",
                payload={
                    "notification_id": notification["notification_id"],
                    "actions": actions,
                    "renewal_method": "manual_required",
                },
                modes=modes,
            )
            return run
        if (
            item.trigger_type is TriggerType.KNOWN_DATE
            and saas_invoice_checkout.billing_mode().value == "real"
            and not item.hosted_payment_reference
        ):
            raise ValueError(
                "real Teams billing requires a sourced hosted invoice reference"
            )
        if (
            quote is None
            and item.trigger_type is TriggerType.KNOWN_DATE
            and item.hosted_payment_reference
        ):
            assert item.current_plan_amount is not None
            proposed_amount = Decimal(str(proposal["proposed_amount"]))
            invoice_reference = item.hosted_payment_reference
            if proposal.get("proposed_action") == "switch_to_alternate":
                if not item.alternate_hosted_payment_reference:
                    raise ValueError(
                        "alternate plan requires its own sourced hosted payment link"
                    )
                invoice_reference = item.alternate_hosted_payment_reference
            quote = saas_invoice_checkout.quote_invoice(
                invoice_reference=invoice_reference,
                vendor=item.preferred_merchant.value,
                invoice_id=item.merchant_sku_id,
                amount=proposed_amount,
                currency=item.currency,
            )
        if quote is not None:
            self._validate_quote_binding(item, quote)
            self._validate_quote_usable(quote)
            if quote.merchant != str(proposal["merchant"]):
                raise ValueError("merchant quote does not match the proposal merchant")
        amount = quote.amount if quote is not None else Decimal(str(proposal["proposed_amount"]))
        self._enforce_caps(user, amount)
        if item.trigger_type is TriggerType.PREDICTED:
            if quote is not None:
                home_catalog_mode = quote.execution_mode.value
            elif item.preferred_merchant.value == "zepto":
                home_catalog_mode = zepto_checkout.merchant_mode().value
            else:
                home_catalog_mode = "disclosed_mock"
            home_payment_mode = (
                zepto_checkout.payment_mode().value
                if item.preferred_merchant.value == "zepto"
                else swiggy_checkout.payment_mode().value
            )
        else:
            home_catalog_mode = "not_applicable"
            home_payment_mode = "not_applicable"
        modes = {
            "prava": self._prava_mode(),
            "home_merchant": home_catalog_mode,
            "home_catalog": home_catalog_mode,
            "home_payment": home_payment_mode,
            "teams_billing": (
                saas_invoice_checkout.billing_mode().value
                if item.trigger_type is TriggerType.KNOWN_DATE
                else "not_applicable"
            ),
        }
        self.repository.upsert_user(user)
        self.repository.upsert_item(item)
        run = self.repository.create_workflow(
            user_id=str(user.user_id),
            item_id=str(item.item_id),
            trigger_reason=self._trigger_reason(item),
            proposed_amount=amount,
            currency=item.currency,
            merchant=str(proposal["merchant"]),
            proposed_action=proposal.get("proposed_action"),
            quote=quote.model_dump(mode="json") if quote else None,
            modes=modes,
            idempotency_key=f"restock-{uuid4().hex}",
        )
        self.repository.audit(
            user_id=str(user.user_id),
            run_id=run["run_id"],
            item_id=str(item.item_id),
            event_type="triggered",
            payload={"trigger_reason": run["trigger_reason"]},
            modes=modes,
        )
        if quote is None and self._quote_provider_supports(item):
            run = self.repository.transition(
                run["run_id"],
                expected={WorkflowState.TRIGGERED.value},
                state=WorkflowState.QUOTE_PENDING.value,
            )
            try:
                quote = self.quote_provider(item)
                if renew_budget_fence is not None:
                    renew_budget_fence()
                self._validate_quote_binding(item, quote)
                self._validate_quote_usable(quote)
                if quote.merchant != str(proposal["merchant"]):
                    raise ValueError("merchant quote does not match the proposal merchant")
                if quote.stock_status is StockStatus.OUT_OF_STOCK:
                    raise ValueError("exact merchant SKU is out of stock")
                amount = quote.amount
                self._enforce_caps(user, amount, exclude_run_id=run["run_id"])
                modes = dict(modes)
                modes["home_merchant"] = quote.execution_mode.value
                modes["home_catalog"] = quote.execution_mode.value
                run = self.repository.transition(
                    run["run_id"],
                    expected={WorkflowState.QUOTE_PENDING.value},
                    state=WorkflowState.TRIGGERED.value,
                    proposed_amount=amount,
                    quote=quote.model_dump(mode="json"),
                    modes=modes,
                )
                self.repository.audit(
                    user_id=str(user.user_id),
                    run_id=run["run_id"],
                    item_id=str(item.item_id),
                    event_type="quote_obtained",
                    payload=self._quote_audit_payload(quote),
                    modes=modes,
                )
            except Exception:
                self.repository.transition(
                    run["run_id"],
                    expected={WorkflowState.QUOTE_PENDING.value},
                    state=WorkflowState.FAILED.value,
                    error_code="HOME_QUOTE_FAILED",
                )
                self.repository.audit(
                    user_id=str(user.user_id),
                    run_id=run["run_id"],
                    item_id=str(item.item_id),
                    event_type="quote_failed",
                    payload={"reason": "exact_quote_unavailable"},
                    modes=modes,
                )
                raise
        constraints = {
            "currency": item.currency,
            "product_id": item.merchant_sku_id,
            "user_id": str(user.user_id),
        }
        try:
            intent_ref = self.prava.create_intent(
                proposal["merchant"], amount, item.name, constraints
            )
        except Exception:
            failed = self.repository.transition(
                run["run_id"],
                expected={WorkflowState.TRIGGERED.value},
                state=WorkflowState.FAILED.value,
                error_code="PRAVA_INTENT_CREATION_FAILED",
            )
            self.repository.audit(
                user_id=str(user.user_id),
                run_id=run["run_id"],
                item_id=str(item.item_id),
                event_type="intent_creation_failed",
                payload={"reason": "provider_error"},
                modes=modes,
            )
            assert failed["state"] == WorkflowState.FAILED.value
            raise
        try:
            if renew_budget_fence is not None:
                renew_budget_fence()
            self._enforce_caps(user, amount, exclude_run_id=run["run_id"])
        except Exception:
            self.repository.transition(
                run["run_id"],
                expected={WorkflowState.TRIGGERED.value},
                state=WorkflowState.FAILED.value,
                error_code="SPEND_BUDGET_RESERVATION_LOST",
            )
            self.repository.audit(
                user_id=str(user.user_id),
                run_id=run["run_id"],
                item_id=str(item.item_id),
                event_type="budget_reservation_lost",
                payload={"reason": "lease_fence_or_cap_changed"},
                modes=modes,
            )
            raise
        run = self.repository.transition(
            run["run_id"],
            expected={WorkflowState.TRIGGERED.value},
            state=WorkflowState.INTENT_CREATED.value,
            prava_intent_ref=intent_ref,
        )
        self.repository.audit(
            user_id=str(user.user_id),
            run_id=run["run_id"],
            item_id=str(item.item_id),
            event_type="intent_created",
            payload={"amount": str(amount), "currency": item.currency, "merchant": proposal["merchant"]},
            modes=modes,
        )
        actions = (
            ["renew_as_is", "switch_plan", "skip"]
            if item.trigger_type is TriggerType.KNOWN_DATE
            else ["approve", "adjust", "skip"]
        )
        notification = self.repository.create_notification(
            run_id=run["run_id"],
            user_id=str(user.user_id),
            message=str(proposal["message"]),
            actions=actions,
        )
        run = self.repository.transition(
            run["run_id"],
            expected={WorkflowState.INTENT_CREATED.value},
            state=WorkflowState.NOTIFIED.value,
        )
        self.repository.audit(
            user_id=str(user.user_id),
            run_id=run["run_id"],
            item_id=str(item.item_id),
            event_type="notification_sent",
            payload={"notification_id": notification["notification_id"], "actions": actions},
            modes=modes,
        )
        return run

    def approval_url(self, run_id: str) -> str:
        run = self.repository.get_workflow(run_id)
        intent_ref = run.get("prava_intent_ref")
        intent = getattr(self.prava, "_INTENTS", {}).get(intent_ref, {})
        url = intent.get("iframe_url")
        if not url:
            raise RuntimeError("approval URL is unavailable or the process restarted")
        return str(url)

    def _recover_lost_ephemeral_credential(
        self, run: dict[str, Any]
    ) -> dict[str, Any] | None:
        if run["state"] not in {
            WorkflowState.MANDATE_APPROVED.value,
            WorkflowState.QUOTE_REVALIDATED.value,
        }:
            return None
        attempt = self.repository.get_merchant_checkout_attempt(run["idempotency_key"])
        if attempt is not None:
            return None
        # Credential fields and their opaque in-process reference are intentionally
        # not persisted. After restart, absence of a merchant attempt proves the
        # checkout boundary was never durably entered, so fail closed without a
        # transaction, status report, or fabricated merchant decline.
        failed = self.repository.transition(
            run["run_id"],
            expected={run["state"]},
            state=WorkflowState.FAILED.value,
            error_code="CREDENTIAL_LOST_BEFORE_EXPOSURE",
        )
        self.repository.audit(
            user_id=run["user_id"],
            run_id=run["run_id"],
            item_id=run["item_id"],
            event_type="credential_lost_before_exposure",
            payload={"reason": "PROCESS_RESTART_BEFORE_MERCHANT_ATTEMPT"},
            modes=run["modes"],
        )
        return failed

    def act(
        self,
        run_id: str,
        *,
        user_id: str,
        action: str,
        adjusted_amount: Decimal | None = None,
    ) -> dict[str, Any]:
        run = self.repository.get_workflow(run_id)
        if run["user_id"] != user_id:
            raise PermissionError("workflow belongs to a different user")
        allowed = {"approve", "adjust", "skip", "renew_as_is", "switch_plan"}
        if action not in allowed:
            raise ValueError("unsupported notification action")
        if (
            run.get("proposed_action") == "flag_for_manual_renewal"
            and action != "skip"
        ):
            raise ValueError("manual-renewal workflow only supports skip")
        if run.get("proposed_action") == "switch_to_alternate" and action == "approve":
            raise ValueError("plan switches require the explicit switch_plan action")
        if action == "adjust":
            if adjusted_amount is None or adjusted_amount <= 0:
                raise ValueError("adjust requires a positive adjusted_amount")
            with self._budget_scope(user_id) as renew_budget_fence:
                user_data = self.repository.get_user(user_id)
                if user_data is None:
                    raise ValueError("workflow user no longer exists")
                self._enforce_caps(
                    User.model_validate(user_data),
                    adjusted_amount,
                    exclude_run_id=run_id,
                )
                renew_budget_fence()
                self.repository.record_action(
                    run_id=run_id,
                    user_id=user_id,
                    action=action,
                    adjusted_amount=adjusted_amount,
                )
                next_run = self.repository.transition(
                    run_id,
                    expected={
                        WorkflowState.NOTIFIED.value,
                        WorkflowState.REAPPROVAL_REQUIRED.value,
                    },
                    state=(
                        WorkflowState.REAPPROVAL_REQUIRED.value
                        if run["state"] == WorkflowState.REAPPROVAL_REQUIRED.value
                        else WorkflowState.NOTIFIED.value
                    ),
                    proposed_amount=adjusted_amount,
                )
            self.repository.audit(
                user_id=user_id,
                run_id=run_id,
                item_id=run["item_id"],
                event_type="user_adjust",
                payload={"adjusted_amount": str(adjusted_amount)},
                modes=run["modes"],
            )
            return next_run
        if (
            run["state"] == WorkflowState.REAPPROVAL_REQUIRED.value
            and action != "skip"
        ):
            with self._budget_scope(user_id) as renew_budget_fence:
                item = self.repository.get_item(run["item_id"])
                amount = Decimal(str(run["proposed_amount"]))
                quote = None
                if self._quote_provider_supports(item):
                    quote = self.quote_provider(item)
                    renew_budget_fence()
                    self._validate_revalidation_binding(run, item, quote)
                    if quote.stock_status is StockStatus.OUT_OF_STOCK:
                        raise ValueError("item is out of stock; reapproval cannot proceed")
                    self._validate_quote_usable(quote)
                    amount = quote.amount
                user_data = self.repository.get_user(user_id)
                if user_data is None:
                    raise ValueError("workflow user no longer exists")
                self._enforce_caps(
                    User.model_validate(user_data), amount, exclude_run_id=run_id
                )
                constraints = {
                    "currency": run["currency"],
                    "product_id": item.merchant_sku_id,
                    "user_id": user_id,
                }
                new_intent_ref = self.prava.create_intent(
                    run["merchant"], amount, item.name, constraints
                )
                renew_budget_fence()
                self._enforce_caps(
                    User.model_validate(user_data), amount, exclude_run_id=run_id
                )
                self.repository.record_action(
                    run_id=run_id,
                    user_id=user_id,
                    action=action,
                    adjusted_amount=None,
                )
                next_run = self.repository.transition(
                    run_id,
                    expected={WorkflowState.REAPPROVAL_REQUIRED.value},
                    state=WorkflowState.PASSKEY_PENDING.value,
                    proposed_amount=amount,
                    quote=(
                        quote.model_dump(mode="json")
                        if quote is not None
                        else run.get("quote")
                    ),
                    prava_intent_ref=new_intent_ref,
                    error_code=None,
                )
            self.repository.audit(
                user_id=user_id,
                run_id=run_id,
                item_id=run["item_id"],
                event_type=f"user_{action}",
                payload={"adjusted_amount": None},
                modes=run["modes"],
            )
            return next_run
        self.repository.record_action(
            run_id=run_id,
            user_id=user_id,
            action=action,
            adjusted_amount=adjusted_amount,
        )
        if action == "skip":
            next_run = self.repository.transition(
                run_id,
                expected={WorkflowState.NOTIFIED.value, WorkflowState.REAPPROVAL_REQUIRED.value},
                state=WorkflowState.SKIPPED.value,
            )
        else:
            next_run = self.repository.transition(
                run_id,
                expected={WorkflowState.NOTIFIED.value, WorkflowState.REAPPROVAL_REQUIRED.value},
                state=WorkflowState.PASSKEY_PENDING.value,
            )
        self.repository.audit(
            user_id=user_id,
            run_id=run_id,
            item_id=run["item_id"],
            event_type=f"user_{action}",
            payload={"adjusted_amount": str(adjusted_amount) if adjusted_amount else None},
            modes=run["modes"],
        )
        return next_run

    def resume_after_passkey(self, run_id: str) -> dict[str, Any]:
        run = self.repository.get_workflow(run_id)
        recovered = self._recover_lost_ephemeral_credential(run)
        if recovered is not None:
            return recovered
        if run["state"] != WorkflowState.PASSKEY_PENDING.value:
            raise ValueError("workflow is not waiting for passkey approval")
        if self.prava is prava_client and run["prava_intent_ref"] not in prava_client._INTENTS:
            prava_client.register_intent_context(
                run["prava_intent_ref"],
                merchant=run["merchant"],
                amount=str(run["proposed_amount"]),
                constraints={"currency": run["currency"]},
            )
        result = self.prava.await_mandate(run["prava_intent_ref"])
        if result["status"] != "approved":
            terminal = (
                WorkflowState.REJECTED.value
                if result["status"] == "rejected"
                else WorkflowState.EXPIRED.value
            )
            final = self.repository.transition(
                run_id,
                expected={WorkflowState.PASSKEY_PENDING.value},
                state=terminal,
            )
            self.repository.audit(
                user_id=run["user_id"],
                run_id=run_id,
                item_id=run["item_id"],
                event_type=f"mandate_{terminal}",
                payload={},
                modes=run["modes"],
            )
            return final

        item = self.repository.get_item(run["item_id"])
        with self._post_mandate_failure_guard(
            run_id, item, result["credential_reference"]
        ):
            run = self.repository.transition(
                run_id,
                expected={WorkflowState.PASSKEY_PENDING.value},
                state=WorkflowState.MANDATE_APPROVED.value,
                mandate_ref=result["mandate_id"],
            )
            self.repository.audit(
                user_id=run["user_id"],
                run_id=run_id,
                item_id=run["item_id"],
                event_type="mandate_approved",
                payload={"mandate_ref": result["mandate_id"]},
                modes=run["modes"],
            )
        with self._post_mandate_failure_guard(
            run_id, item, result["credential_reference"]
        ), ExitStack() as stack:
            cart_lease = None
            if self._quote_provider_supports(item):
                scope = getattr(self.quote_provider, "checkout_scope", None)
                if callable(scope):
                    cart_lease = stack.enter_context(
                        scope(item, owner_key=run["idempotency_key"])
                    )
                locked_quote = getattr(self.quote_provider, "revalidate_locked", None)
                if not callable(locked_quote):
                    locked_quote = getattr(self.quote_provider, "quote_locked", None)
                try:
                    fresh_quote: MerchantQuote = (
                        locked_quote(item) if callable(locked_quote) else self.quote_provider(item)
                    )
                except Exception as quote_exc:
                    LOGGER.warning(
                        json.dumps(
                            {
                                "event": "revalidate_quote_failed_using_approved_quote",
                                "error": str(quote_exc),
                            }
                        )
                    )
                    fresh_quote = MerchantQuote.model_validate(run["quote"])
                if fresh_quote.stock_status is StockStatus.OUT_OF_STOCK:
                    self._retire_unused_credential(result["credential_reference"])
                    failed = self.repository.transition(
                        run_id,
                        expected={WorkflowState.MANDATE_APPROVED.value},
                        state=WorkflowState.FAILED.value,
                        error_code="OUT_OF_STOCK",
                    )
                    self.repository.audit(
                        user_id=run["user_id"], run_id=run_id, item_id=run["item_id"],
                        event_type="checkout_blocked", payload={"reason": "out_of_stock"}, modes=run["modes"]
                    )
                    return failed
                self._validate_revalidation_binding(run, item, fresh_quote)
                self._validate_quote_usable(fresh_quote)
                approved_amount = Decimal(str(run["proposed_amount"]))
                deviation = abs(fresh_quote.amount - approved_amount) / approved_amount
                if fresh_quote.amount > approved_amount or deviation > Decimal("0.15"):
                    self._retire_unused_credential(result["credential_reference"])
                    reapproval = self.repository.transition(
                        run_id,
                        expected={WorkflowState.MANDATE_APPROVED.value},
                        state=WorkflowState.REAPPROVAL_REQUIRED.value,
                        proposed_amount=fresh_quote.amount,
                        quote=fresh_quote.model_dump(mode="json"),
                        mandate_ref=None,
                        error_code="PRICE_CHANGED",
                    )
                    self.repository.create_notification(
                        run_id=run_id,
                        user_id=run["user_id"],
                        message="The current merchant total changed. Approve the exact fresh amount before payment.",
                        actions=["approve", "adjust", "skip"],
                    )
                    self.repository.audit(
                        user_id=run["user_id"], run_id=run_id, item_id=run["item_id"],
                        event_type="reapproval_required",
                        payload={"reason": "price_changed", "fresh_amount": str(fresh_quote.amount)},
                        modes=run["modes"],
                    )
                    return reapproval
                # Same-price quotes proceed unchanged. A decrease within 15% is
                # persisted and becomes the exact checkout amount; stale approved
                # amounts are never passed to the merchant.
                run = self.repository.transition(
                    run_id,
                    expected={WorkflowState.MANDATE_APPROVED.value},
                    state=WorkflowState.QUOTE_REVALIDATED.value,
                    proposed_amount=fresh_quote.amount,
                    quote=fresh_quote.model_dump(mode="json"),
                )
            else:
                run = self.repository.transition(
                    run_id,
                    expected={WorkflowState.MANDATE_APPROVED.value},
                    state=WorkflowState.QUOTE_REVALIDATED.value,
                )
            self.repository.audit(
                user_id=run["user_id"], run_id=run_id, item_id=run["item_id"],
                event_type="quote_revalidated",
                payload=(
                    self._quote_audit_payload(fresh_quote)
                    if self._quote_provider_supports(item)
                    else {"amount": str(run["proposed_amount"]), "currency": run["currency"]}
                ),
                modes=run["modes"]
            )
            checkout = self._checkout_for_item(item)
            response = checkout.complete_checkout(
                result["credential_reference"],
                item.merchant_sku_id,
                run["proposed_amount"],
                run["idempotency_key"],
            )
            raw_checkout_status = response.get("status")
            checkout_status = (
                raw_checkout_status.value
                if isinstance(raw_checkout_status, CheckoutStatus)
                else str(raw_checkout_status)
            )
            if checkout_status == CheckoutStatus.PENDING.value and cart_lease is not None:
                preserve = getattr(cart_lease, "preserve", None)
                if callable(preserve):
                    preserve()
            return self._finish_checkout(
                run,
                item,
                response,
                expected_state=WorkflowState.QUOTE_REVALIDATED,
                credential_reference=result["credential_reference"],
            )

    def reconcile_checkout(self, run_id: str) -> dict[str, Any]:
        """Reconcile a durable pending checkout without needing card credentials."""

        run = self.repository.get_workflow(run_id)
        if run["state"] == WorkflowState.COMPLETED.value:
            return self.repair_completion_effects(run_id)
        if run["state"] != WorkflowState.CHECKOUT_PENDING.value:
            raise ValueError("workflow is not waiting for checkout reconciliation")
        item = self.repository.get_item(run["item_id"])
        checkout = self._checkout_for_item(item)
        reconcile = getattr(checkout, "reconcile_checkout", None)
        if not callable(reconcile):
            raise RuntimeError("merchant checkout reconciliation is not configured")
        try:
            response = reconcile(run["idempotency_key"])
        except Exception:
            self.repository.audit(
                user_id=run["user_id"],
                run_id=run_id,
                item_id=run["item_id"],
                event_type="checkout_reconciliation_failed",
                payload={"reason": "RECONCILIATION_BOUNDARY_FAILED"},
                modes=run["modes"],
            )
            raise RuntimeError(
                "checkout reconciliation failed; workflow remains pending"
            ) from None
        raw_status = response.get("status")
        status_value = raw_status.value if isinstance(raw_status, CheckoutStatus) else str(raw_status)
        try:
            return self._finish_checkout(
                run,
                item,
                response,
                expected_state=WorkflowState.CHECKOUT_PENDING,
            )
        finally:
            if status_value != CheckoutStatus.PENDING.value and self._quote_provider_supports(item):
                release = getattr(self.quote_provider, "release_checkout_scope", None)
                if callable(release):
                    release(item, owner_key=run["idempotency_key"])
