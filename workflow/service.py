"""Durable workflow state machine; models propose, code owns payment safety."""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol
from uuid import uuid4

from merchant import saas_invoice_checkout, swiggy_checkout, zepto_checkout
from merchant.models import CheckoutStatus, MerchantQuote, StockStatus
from payments import prava_client
from payments.models import TrackedItem, TriggerType, User
from storage.repository import RestockRepository
from triggers import consumption_model, renewal_model


class WorkflowState(str, Enum):
    TRIGGERED = "triggered"
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

    def _enforce_caps(self, user: User, amount: Decimal) -> None:
        if amount <= 0:
            raise ValueError("proposed amount must be positive")
        if amount > user.per_item_cap or amount > user.per_transaction_cap:
            raise ValueError("proposal exceeds per-item or per-transaction cap")
        if self.repository.monthly_spend(str(user.user_id)) + amount > user.monthly_cap:
            raise ValueError("proposal would exceed monthly cap")

    def _checkout_for_item(self, item: TrackedItem) -> CheckoutBoundary:
        if item.trigger_type is TriggerType.KNOWN_DATE:
            return self.teams_checkout
        if self.home_checkout is not None:
            return self.home_checkout
        if item.preferred_merchant.value == "swiggy":
            return swiggy_checkout
        return zepto_checkout

    def _finish_checkout(
        self,
        run: dict[str, Any],
        item: TrackedItem,
        response: dict[str, Any],
        *,
        expected_state: WorkflowState,
    ) -> dict[str, Any]:
        """Persist a merchant outcome without treating uncertainty as failure."""

        raw_status = response.get("status")
        status_value = raw_status.value if isinstance(raw_status, CheckoutStatus) else str(raw_status)
        if status_value == CheckoutStatus.PENDING.value:
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
                    "reason": response.get("error_code") or "PAYMENT_PENDING",
                },
                modes=run["modes"],
            )
            return pending
        if status_value == CheckoutStatus.PRICE_CHANGED.value:
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
                modes=run["modes"],
            )
            return reapproval
        if status_value != CheckoutStatus.COMPLETED.value:
            failed = self.repository.transition(
                run["run_id"],
                expected={expected_state.value},
                state=WorkflowState.FAILED.value,
                error_code=status_value.upper(),
            )
            self.repository.audit(
                user_id=run["user_id"], run_id=run["run_id"], item_id=run["item_id"],
                event_type="checkout_failed", payload={"reason": status_value}, modes=run["modes"]
            )
            return failed

        transaction = self.repository.create_transaction(
            run_id=run["run_id"],
            item_id=run["item_id"],
            mandate_ref=str(run["mandate_ref"]),
            merchant_order_id=response["merchant_order_id"],
            amount=Decimal(str(response.get("charged_amount") or run["proposed_amount"])),
            currency=str(response.get("currency") or run["currency"]),
            execution_mode=str(response.get("execution_mode") or "disclosed_mock"),
        )
        if item.trigger_type is TriggerType.PREDICTED:
            assert item.last_purchased_at is not None
            predicted_date = consumption_model.predicted_depletion_date(item)
            observed = max(1, (date.today() - item.last_purchased_at).days)
            tenant_id = str(item.tenant_id) if item.tenant_id else self.repository.personal_tenant_id(str(item.user_id))
            self.repository.log_forecast_observation(
                tenant_id=tenant_id,
                user_id=str(item.user_id),
                item_id=str(item.item_id),
                predicted_depletion_date=predicted_date.isoformat(),
                actual_reorder_date=date.today().isoformat(),
                category=item.category.value,
                trigger_cause=run["trigger_reason"],
                notification_action="approved",
                forecast_error_days=float((date.today() - predicted_date).days),
            )
            consumption_model.recalibrate(item, observed)
            item.last_purchased_at = date.today()
            item.last_purchase_amount = Decimal(str(transaction["amount"]))
            self.repository.upsert_item(item)
        final = self.repository.transition(
            run["run_id"],
            expected={expected_state.value},
            state=WorkflowState.COMPLETED.value,
            error_code=None,
        )
        self.repository.audit(
            user_id=run["user_id"],
            run_id=run["run_id"],
            item_id=run["item_id"],
            event_type="transaction_completed",
            payload={
                "transaction_id": transaction["transaction_id"],
                "amount": str(transaction["amount"]),
                "currency": transaction["currency"],
            },
            modes=run["modes"],
        )
        return final

    def begin(
        self,
        user: User,
        item: TrackedItem,
        *,
        quote: MerchantQuote | None = None,
    ) -> dict[str, Any]:
        proposal = self._proposal(item)
        amount = quote.amount if quote is not None else Decimal(str(proposal["proposed_amount"]))
        self._enforce_caps(user, amount)
        home_payment_mode = (
            zepto_checkout.merchant_mode().value
            if item.preferred_merchant.value == "zepto"
            else swiggy_checkout.payment_mode().value
        )
        modes = {
            "prava": "sandbox",
            "home_merchant": item.preferred_merchant.value,
            "home_payment": home_payment_mode,
            "teams_billing": "disclosed_mock",
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
        constraints = {
            "currency": item.currency,
            "product_id": item.merchant_sku_id,
            "user_id": str(user.user_id),
        }
        intent_ref = self.prava.create_intent(
            proposal["merchant"], amount, item.name, constraints
        )
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
        if run.get("proposed_action") == "switch_to_alternate" and action == "approve":
            raise ValueError("plan switches require the explicit switch_plan action")
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
        elif action == "adjust":
            if adjusted_amount is None or adjusted_amount <= 0:
                raise ValueError("adjust requires a positive adjusted_amount")
            next_run = self.repository.transition(
                run_id,
                expected={WorkflowState.NOTIFIED.value, WorkflowState.REAPPROVAL_REQUIRED.value},
                state=(
                    WorkflowState.REAPPROVAL_REQUIRED.value
                    if run["state"] == WorkflowState.REAPPROVAL_REQUIRED.value
                    else WorkflowState.NOTIFIED.value
                ),
                proposed_amount=adjusted_amount,
            )
        else:
            changes: dict[str, Any] = {}
            if run["state"] == WorkflowState.REAPPROVAL_REQUIRED.value:
                item = self.repository.get_item(run["item_id"])
                amount = Decimal(str(run["proposed_amount"]))
                quote = None
                if self.quote_provider is not None and item.trigger_type is TriggerType.PREDICTED:
                    quote = self.quote_provider(item)
                    if quote.stock_status is StockStatus.OUT_OF_STOCK:
                        raise ValueError("item is out of stock; reapproval cannot proceed")
                    amount = quote.amount
                user_data = self.repository.get_user(user_id)
                if user_data is None:
                    raise ValueError("workflow user no longer exists")
                self._enforce_caps(User.model_validate(user_data), amount)
                constraints = {
                    "currency": run["currency"],
                    "product_id": item.merchant_sku_id,
                    "user_id": user_id,
                }
                changes = {
                    "proposed_amount": amount,
                    "quote": quote.model_dump(mode="json") if quote is not None else run.get("quote"),
                    "prava_intent_ref": self.prava.create_intent(
                        run["merchant"], amount, item.name, constraints
                    ),
                    "error_code": None,
                }
            next_run = self.repository.transition(
                run_id,
                expected={WorkflowState.NOTIFIED.value, WorkflowState.REAPPROVAL_REQUIRED.value},
                state=WorkflowState.PASSKEY_PENDING.value,
                **changes,
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
        item = self.repository.get_item(run["item_id"])
        if self.quote_provider is not None and item.trigger_type is TriggerType.PREDICTED:
            fresh_quote: MerchantQuote = self.quote_provider(item)
            if fresh_quote.stock_status is StockStatus.OUT_OF_STOCK:
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
            approved_amount = Decimal(str(run["proposed_amount"]))
            deviation = abs(fresh_quote.amount - approved_amount) / approved_amount
            if deviation > Decimal("0.15"):
                reapproval = self.repository.transition(
                    run_id,
                    expected={WorkflowState.MANDATE_APPROVED.value},
                    state=WorkflowState.REAPPROVAL_REQUIRED.value,
                    proposed_amount=fresh_quote.amount,
                    quote=fresh_quote.model_dump(mode="json"),
                    mandate_ref=None,
                    error_code="PRICE_CHANGED",
                )
                self.repository.audit(
                    user_id=run["user_id"], run_id=run_id, item_id=run["item_id"],
                    event_type="reapproval_required",
                    payload={"reason": "price_changed", "fresh_amount": str(fresh_quote.amount)},
                    modes=run["modes"],
                )
                return reapproval
        run = self.repository.transition(
            run_id,
            expected={WorkflowState.MANDATE_APPROVED.value},
            state=WorkflowState.QUOTE_REVALIDATED.value,
        )
        self.repository.audit(
            user_id=run["user_id"], run_id=run_id, item_id=run["item_id"],
            event_type="quote_revalidated", payload={"amount": str(run["proposed_amount"])}, modes=run["modes"]
        )
        checkout = self._checkout_for_item(item)
        response = checkout.complete_checkout(
            result["credential_reference"],
            item.merchant_sku_id,
            run["proposed_amount"],
            run["idempotency_key"],
        )
        return self._finish_checkout(
            run,
            item,
            response,
            expected_state=WorkflowState.QUOTE_REVALIDATED,
        )

    def reconcile_checkout(self, run_id: str) -> dict[str, Any]:
        """Reconcile a durable pending checkout without needing card credentials."""

        run = self.repository.get_workflow(run_id)
        if run["state"] != WorkflowState.CHECKOUT_PENDING.value:
            raise ValueError("workflow is not waiting for checkout reconciliation")
        item = self.repository.get_item(run["item_id"])
        checkout = self._checkout_for_item(item)
        reconcile = getattr(checkout, "reconcile_checkout", None)
        if not callable(reconcile):
            raise RuntimeError("merchant checkout reconciliation is not configured")
        response = reconcile(run["idempotency_key"])
        return self._finish_checkout(
            run,
            item,
            response,
            expected_state=WorkflowState.CHECKOUT_PENDING,
        )
