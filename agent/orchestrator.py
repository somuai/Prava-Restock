"""Restock's single-agent orchestration loop, wired only to offline stubs.

The OpenAI Agents SDK objects define the production tool surface. ``run_cycle``
is the deterministic, network-free executor used for pre-hackathon tests and
dry runs; it invokes the same policy and tool implementations directly.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from agents import (
    Agent,
    RunContextWrapper,
    Runner,
    ToolGuardrailFunctionOutput,
    function_tool,
    tool_input_guardrail,
)
from pydantic import BaseModel

from common import audit_store, notification_store
from merchant import mock_subscription_checkout, zepto_checkout
from payments import prava_client
from payments.models import (
    AuditEventType,
    AuditLogEntry,
    Intent,
    IntentStatus,
    ItemStatus,
    Mandate,
    TrackedItem,
    Transaction,
    TransactionStatus,
    TriggerType,
    User,
)
from triggers import consumption_model, renewal_model


ORCHESTRATOR_MODEL = "gpt-5.4-mini"
# ``audit_log_path`` is retained on ``OrchestratorContext`` for callers that
# configure an isolated audit store.  It now points to SQLite, not JSON.
DEFAULT_AUDIT_LOG_PATH = audit_store.AUDIT_STORE_PATH


class SpendCapExceeded(ValueError):
    """Raised before any Prava call when a proposal breaches a hard cap."""


class ApprovalRequired(ValueError):
    """Raised when checkout is attempted without an approved mandate."""


class MerchantCheckoutFailed(RuntimeError):
    """Raised when the merchant cannot complete an order."""


class PriceReapprovalRequired(RuntimeError):
    """Raised when a fresh merchant quote exceeds the approved tolerance."""


@dataclass(frozen=True)
class MandateResult:
    status: str
    mandate: Mandate | None = None

    @property
    def approved(self) -> bool:
        return self.status == "approved" and self.mandate is not None


class TeamsPlanDecision(BaseModel):
    proposed_action: Literal["renew_as_is", "switch_to_alternate"]
    rationale: str


@dataclass
class OrchestratorContext:
    user: User
    items: list[TrackedItem]
    audit_log_path: Path = DEFAULT_AUDIT_LOG_PATH
    intents: dict[UUID, Intent] = field(default_factory=dict)
    prava_intent_refs: dict[UUID, str] = field(default_factory=dict)
    mandates: dict[str, Mandate] = field(default_factory=dict)
    transactions: list[Transaction] = field(default_factory=list)
    audit_entries: list[AuditLogEntry] = field(default_factory=list)

    def item(self, item_id: UUID) -> TrackedItem:
        for item in self.items:
            if item.item_id == item_id:
                return item
        raise KeyError(f"unknown item_id: {item_id}")

    @property
    def monthly_spend(self) -> Decimal:
        now = datetime.now(timezone.utc)
        return sum(
            (
                transaction.amount
                for transaction in self.transactions
                if transaction.status is TransactionStatus.COMPLETED
                and transaction.completed_at.year == now.year
                and transaction.completed_at.month == now.month
            ),
            Decimal("0"),
        )


def enforce_spend_caps(context: OrchestratorContext, amount: Decimal) -> None:
    """The code-owned spend policy shared by SDK and deterministic execution."""
    if amount <= 0:
        raise SpendCapExceeded("proposed amount must be positive")
    if amount > context.user.per_item_cap:
        raise SpendCapExceeded(
            f"proposed amount {amount} exceeds per-item cap {context.user.per_item_cap}"
        )
    if amount > context.user.per_transaction_cap:
        raise SpendCapExceeded(
            "proposed amount exceeds the per-transaction cap"
        )
    if context.monthly_spend + amount > context.user.monthly_cap:
        raise SpendCapExceeded(
            f"proposal would exceed monthly cap {context.user.monthly_cap}"
        )


@tool_input_guardrail(name="spend_cap_guardrail")
def spend_cap_guardrail(data) -> ToolGuardrailFunctionOutput:
    """Agents SDK tool Guardrail that runs before request_prava_intent."""
    arguments = json.loads(data.context.tool_arguments or "{}")
    try:
        enforce_spend_caps(data.context.context, Decimal(str(arguments["amount"])))
    except (KeyError, SpendCapExceeded) as exc:
        return ToolGuardrailFunctionOutput.raise_exception(
            {"reason": str(exc), "policy": "spend_caps"}
        )
    return ToolGuardrailFunctionOutput.allow({"policy": "spend_caps"})


def _is_triggered(item: TrackedItem) -> bool:
    if item.trigger_type is TriggerType.PREDICTED:
        return consumption_model.should_fire(item)
    return renewal_model.should_fire(item)


def _proposal(item: TrackedItem) -> dict[str, Any]:
    if item.trigger_type is TriggerType.PREDICTED:
        return consumption_model.propose(item)
    return renewal_model.propose(item)


def _check_trigger_status(context: OrchestratorContext) -> list[TrackedItem]:
    pending_item_ids = {
        intent.item_id
        for intent in context.intents.values()
        if intent.status is IntentStatus.PENDING_APPROVAL
    }
    triggered_items = []
    for item in context.items:
        if item.status is not ItemStatus.ACTIVE or item.item_id in pending_item_ids:
            continue
        if (
            item.trigger_type is TriggerType.PREDICTED
            and item.price_threshold is not None
        ):
            item.last_observed_price = zepto_checkout.check_current_price(
                item.item_id,
                merchant_sku_id=item.merchant_sku_id,
                product_name=item.name,
            )
        if _is_triggered(item):
            triggered_items.append(item)
    return triggered_items


def _request_prava_intent(
    context: OrchestratorContext,
    merchant: str,
    amount: Decimal,
    item_id: UUID,
    constraints: dict,
) -> Intent:
    enforce_spend_caps(context, amount)
    item = context.item(item_id)
    intent = Intent(
        intent_id=uuid4(),
        item_id=item_id,
        proposed_amount=amount,
        proposed_merchant=merchant,
        currency=item.currency,
        status=IntentStatus.PENDING_APPROVAL,
        created_at=datetime.now(timezone.utc),
    )
    intent_ref = prava_client.create_intent(merchant, amount, item.name, constraints)
    context.intents[intent.intent_id] = intent
    context.prava_intent_refs[intent.intent_id] = intent_ref
    return intent


def _persist_audit_log(context: OrchestratorContext) -> None:
    """Persist only the new entry; primary-key insertion makes retries safe."""
    if context.audit_entries:
        audit_store.append(context.audit_entries[-1], context.audit_log_path)


def _log_event(
    context: OrchestratorContext,
    event_type: str,
    payload: dict,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        log_id=uuid4(),
        user_id=context.user.user_id,
        event_type=event_type,
        payload=payload,
        timestamp=datetime.now(timezone.utc),
    )
    context.audit_entries.append(entry)
    _persist_audit_log(context)
    return entry


def _notify_user(
    context: OrchestratorContext,
    item_id: UUID,
    message: str,
    actions: list[str],
) -> None:
    notification_store.create(
        {
            "item_id": str(item_id),
            "message": message,
            "actions": list(actions),
        }
    )
    _log_event(
        context,
        AuditEventType.NOTIFICATION_SENT.value,
        {"item_id": str(item_id), "message": message, "actions": list(actions)},
    )


def _await_passkey_approval(
    context: OrchestratorContext,
    intent_id: UUID,
) -> MandateResult:
    intent = context.intents[intent_id]
    result = prava_client.await_mandate(context.prava_intent_refs[intent_id])
    if result["status"] != "approved":
        intent.status = (
            IntentStatus.REJECTED
            if result["status"] == "rejected"
            else IntentStatus.EXPIRED
        )
        return MandateResult(status=result["status"])

    intent.status = IntentStatus.APPROVED
    approved_at = datetime.fromisoformat(result["approved_at"])
    mandate = Mandate(
        mandate_id=result["mandate_id"],
        intent_id=intent_id,
        credential_reference=result["credential_reference"],
        scope_merchant=result["scope"]["merchant"],
        scope_max_amount=result["scope"]["max_amount"],
        scope_expiry=approved_at + timedelta(minutes=15),
        passkey_approved_at=approved_at,
    )
    context.mandates[mandate.mandate_id] = mandate
    _log_event(
        context,
        AuditEventType.APPROVED.value,
        {"item_id": str(intent.item_id), "amount": str(intent.proposed_amount)},
    )
    return MandateResult(status="approved", mandate=mandate)


def _complete_merchant_checkout(
    context: OrchestratorContext,
    mandate_id: str,
    item_id: UUID,
) -> Transaction:
    mandate = context.mandates.get(mandate_id)
    if mandate is None:
        raise ApprovalRequired("an approved mandate is required before checkout")
    item = context.item(item_id)
    if (
        item.trigger_type is TriggerType.PREDICTED
        and item.last_observed_price is not None
    ):
        fresh_amount = zepto_checkout.check_current_price(
            item.item_id,
            merchant_sku_id=item.merchant_sku_id,
            product_name=item.name,
        )
        approved_amount = mandate.scope_max_amount
        deviation = abs(fresh_amount - approved_amount) / approved_amount
        item.last_observed_price = fresh_amount
        if deviation > Decimal("0.15"):
            _log_event(
                context,
                AuditEventType.TRANSACTION_FAILED.value,
                {
                    "item": item.name,
                    "merchant": item.preferred_merchant.value,
                    "reason": "price_reapproval_required",
                    "approved_amount": str(approved_amount),
                    "fresh_amount": str(fresh_amount),
                },
            )
            raise PriceReapprovalRequired(
                f"fresh amount {fresh_amount} differs from approved amount "
                f"{approved_amount} by more than 15%"
            )
    checkout_client = (
        mock_subscription_checkout
        if item.preferred_merchant.value == "mock_subscription_billing"
        else zepto_checkout
    )
    response = checkout_client.complete_checkout(
        mandate.credential_reference,
        item.merchant_sku_id,
        mandate.scope_max_amount,
        str(mandate.intent_id),
    )
    if response["status"] != "completed":
        _log_event(
            context,
            AuditEventType.TRANSACTION_FAILED.value,
            {"item": item.name, "merchant": item.preferred_merchant.value, "reason": response["status"]},
        )
        raise MerchantCheckoutFailed(response["status"])

    transaction = Transaction(
        transaction_id=uuid4(),
        mandate_id=mandate_id,
        item_id=item_id,
        merchant_order_id=response["merchant_order_id"],
        amount=mandate.scope_max_amount,
        currency=item.currency,
        status=TransactionStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    context.transactions.append(transaction)
    _log_event(
        context,
        AuditEventType.TRANSACTION_COMPLETED.value,
        {
            "item": item.name,
            "merchant": item.preferred_merchant.value,
            "amount": str(transaction.amount),
            "transaction_id": str(transaction.transaction_id),
        },
    )
    return transaction


@function_tool
def check_trigger_status(ctx: RunContextWrapper[OrchestratorContext]) -> list[dict]:
    """Return active triggered items that do not already have a pending Intent."""
    return [item.model_dump(mode="json") for item in _check_trigger_status(ctx.context)]


@function_tool(strict_mode=False, tool_input_guardrails=[spend_cap_guardrail])
async def request_prava_intent(
    ctx: RunContextWrapper[OrchestratorContext],
    merchant: str,
    amount: Decimal,
    item_id: UUID,
    constraints: dict,
) -> dict:
    """Create a bounded local Intent and send it to the offline Prava stub."""
    item = ctx.context.item(item_id)
    if item.trigger_type is TriggerType.KNOWN_DATE:
        decision = await Runner.run(
            TEAMS_DECISION_AGENT,
            (
                f"Review {item.name}: current amount {item.current_plan_amount}; "
                f"alternate {item.alternate_plan_label} amount {item.alternate_plan_amount}."
            ),
        )
        constraints = dict(constraints)
        constraints["teams_proposed_action"] = decision.final_output.proposed_action
    intent = _request_prava_intent(ctx.context, merchant, amount, item_id, constraints)
    return intent.model_dump(mode="json")


@function_tool
async def notify_user(
    ctx: RunContextWrapper[OrchestratorContext],
    item_id: UUID,
    message: str,
    actions: list[str] = ["approve", "adjust", "skip"],
) -> None:
    """Push a proactive approve/adjust/skip notification to the user."""
    drafted = await Runner.run(NOTIFICATION_AGENT, message)
    _notify_user(ctx.context, item_id, str(drafted.final_output), actions)


@function_tool(needs_approval=True)
def await_passkey_approval(
    ctx: RunContextWrapper[OrchestratorContext],
    intent_id: UUID,
) -> dict:
    """Resume after human approval, then resolve the fake Prava mandate."""
    result = _await_passkey_approval(ctx.context, intent_id)
    return {
        "status": result.status,
        "mandate": result.mandate.model_dump(mode="json") if result.mandate else None,
    }


@function_tool
def complete_merchant_checkout(
    ctx: RunContextWrapper[OrchestratorContext],
    mandate_id: str,
    item_id: UUID,
) -> dict:
    """Complete checkout only with a stored passkey-approved mandate."""
    transaction = _complete_merchant_checkout(ctx.context, mandate_id, item_id)
    return transaction.model_dump(mode="json")


@function_tool(strict_mode=False)
def log_event(
    ctx: RunContextWrapper[OrchestratorContext],
    event_type: str,
    payload: dict,
) -> None:
    """Append a payment-data-free event to the audit log."""
    _log_event(ctx.context, event_type, payload)


SYSTEM_PROMPT = (Path(__file__).with_name("system_prompt.md")).read_text().strip()

NOTIFICATION_AGENT = Agent(
    name="Restock Notification Writer",
    instructions="Write concise proactive Restock proposal copy. Preserve all amounts and merchants.",
    model=ORCHESTRATOR_MODEL,
)

TEAMS_DECISION_AGENT = Agent(
    name="Restock Teams Plan Reviewer",
    instructions="Compare renew-as-is and alternate plans; never switch without explicit approval.",
    model=ORCHESTRATOR_MODEL,
    output_type=TeamsPlanDecision,
)

RESTOCK_AGENT = Agent(
    name="Restock Orchestrator",
    instructions=SYSTEM_PROMPT,
    model=ORCHESTRATOR_MODEL,
    tools=[
        check_trigger_status,
        request_prava_intent,
        notify_user,
        await_passkey_approval,
        complete_merchant_checkout,
        log_event,
    ],
)


class RestockOrchestrator:
    """Deterministic pre-hackathon runner over the same tool implementations."""

    def __init__(self, context: OrchestratorContext):
        self.context = context
        self.agent = RESTOCK_AGENT

    def run_cycle(
        self,
        item: TrackedItem,
        *,
        mandate_outcome: str = "approved",
    ) -> dict[str, Any]:
        if item not in _check_trigger_status(self.context):
            return {"item": item.name, "status": "not_triggered", "steps": []}

        proposal = _proposal(item)
        intent = _request_prava_intent(
            self.context,
            proposal["merchant"],
            Decimal(str(proposal["proposed_amount"])),
            item.item_id,
            {"simulate_mandate": mandate_outcome},
        )
        _notify_user(
            self.context,
            item.item_id,
            proposal["message"],
            ["approve", "adjust", "skip"],
        )
        mandate_result = _await_passkey_approval(self.context, intent.intent_id)
        if not mandate_result.approved:
            return {
                "item": item.name,
                "status": mandate_result.status,
                "steps": ["triggered", "intent_created", "notified", mandate_result.status],
            }
        assert mandate_result.mandate is not None
        transaction = _complete_merchant_checkout(
            self.context,
            mandate_result.mandate.mandate_id,
            item.item_id,
        )
        return {
            "item": item.name,
            "status": "completed",
            "amount": str(transaction.amount),
            "merchant": item.preferred_merchant.value,
            "steps": [
                "triggered",
                "intent_created",
                "notified",
                "passkey_approved",
                "mandate_created",
                "checkout_completed",
                "logged",
            ],
        }
