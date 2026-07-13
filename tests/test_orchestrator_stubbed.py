import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from uuid import UUID

import pytest
from agents.tool_context import ToolContext
from agents.tool_guardrails import ToolInputGuardrailData

from agent.orchestrator import (
    JUDGMENT_MODEL,
    NOTIFICATION_AGENT,
    RESTOCK_AGENT,
    ROUTINE_MODEL,
    TEAMS_DECISION_AGENT,
    ApprovalRequired,
    OrchestratorContext,
    RestockOrchestrator,
    SpendCapExceeded,
    await_passkey_approval,
    request_prava_intent,
    spend_cap_guardrail,
)
from payments import prava_client
from payments.models import TrackedItem, User


USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def build_user(*, per_item_cap: str = "1000", monthly_cap: str = "5000") -> User:
    return User(
        user_id=USER_ID,
        display_name="Asha",
        prava_account_ref="prava_user_demo",
        monthly_cap=monthly_cap,
        per_item_cap=per_item_cap,
        per_transaction_cap="1500",
        created_at=datetime.now(timezone.utc),
    )


def build_item() -> TrackedItem:
    return TrackedItem(
        item_id=UUID("00000000-0000-0000-0000-000000000010"),
        user_id=USER_ID,
        name="Coffee",
        track="home",
        trigger_type="predicted",
        category="grocery",
        sensitive_flag=False,
        preferred_merchant="zepto",
        merchant_sku_id="coffee-500g",
        status="active",
        typical_cadence_days=14,
        last_purchased_at=date.today() - timedelta(days=12),
        last_purchase_amount="450",
    )


def test_full_stubbed_cycle_notifies_and_logs_transaction(tmp_path) -> None:
    item = build_item()
    context = OrchestratorContext(
        user=build_user(), items=[item], audit_log_path=tmp_path / "audit.json"
    )

    trace = RestockOrchestrator(context).run_cycle(item)

    assert trace["status"] == "completed"
    assert context.notifications[0]["status"] == "pending"
    assert context.transactions[0].amount == Decimal("450")
    assert context.audit_entries[-1].event_type.value == "transaction_completed"
    persisted = json.loads(context.audit_log_path.read_text())
    assert persisted[-1]["event_type"] == "transaction_completed"


@pytest.mark.parametrize(
    ("per_item_cap", "monthly_cap", "message"),
    [
        ("400", "5000", "per-item cap"),
        ("1000", "400", "monthly cap"),
    ],
)
def test_over_cap_rejected_before_stub_client(
    monkeypatch, tmp_path, per_item_cap: str, monthly_cap: str, message: str
) -> None:
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("Prava stub must not be reached")

    monkeypatch.setattr(prava_client, "create_intent", fail_if_called)
    item = build_item()
    context = OrchestratorContext(
        user=build_user(per_item_cap=per_item_cap, monthly_cap=monthly_cap),
        items=[item],
        audit_log_path=tmp_path / "audit.json",
    )

    with pytest.raises(SpendCapExceeded, match=message):
        RestockOrchestrator(context).run_cycle(item)

    assert called is False
    assert context.intents == {}
    assert context.notifications == []


def test_sdk_guardrail_is_attached_and_trips_on_over_cap(tmp_path) -> None:
    context = OrchestratorContext(
        user=build_user(per_item_cap="400"),
        items=[build_item()],
        audit_log_path=tmp_path / "audit.json",
    )
    tool_context = ToolContext(
        context=context,
        tool_name="request_prava_intent",
        tool_call_id="call-1",
        tool_arguments=json.dumps(
            {
                "merchant": "zepto",
                "amount": "450",
                "item_id": str(context.items[0].item_id),
                "constraints": {},
            }
        ),
    )
    data = ToolInputGuardrailData(context=tool_context, agent=RESTOCK_AGENT)

    output = asyncio.run(spend_cap_guardrail.run(data))

    assert request_prava_intent.tool_input_guardrails == [spend_cap_guardrail]
    assert output.behavior["type"] == "raise_exception"
    assert output.output_info["policy"] == "spend_caps"


def test_approval_tool_uses_sdk_resumable_approval_primitive() -> None:
    assert await_passkey_approval.needs_approval is True


def test_model_split_matches_spec() -> None:
    assert RESTOCK_AGENT.model == ROUTINE_MODEL == "gpt-5.4-mini"
    assert NOTIFICATION_AGENT.model == JUDGMENT_MODEL == "gpt-5.6-sol"
    assert TEAMS_DECISION_AGENT.model == JUDGMENT_MODEL


def test_checkout_without_approved_mandate_is_rejected(tmp_path) -> None:
    from agent.orchestrator import _complete_merchant_checkout

    context = OrchestratorContext(
        user=build_user(), items=[build_item()], audit_log_path=tmp_path / "audit.json"
    )
    with pytest.raises(ApprovalRequired):
        _complete_merchant_checkout(context, "missing", context.items[0].item_id)
