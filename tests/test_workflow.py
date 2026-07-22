from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from merchant.models import MerchantQuote
from payments.models import TrackedItem, User
from storage import Database, RestockRepository
from workflow import WorkflowService


USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class FakePrava:
    def __init__(self, outcome: str = "approved") -> None:
        self.outcome = outcome
        self.calls = 0
        self._INTENTS: dict[str, dict] = {}

    def create_intent(self, merchant, amount, item_description, constraints):
        self.calls += 1
        reference = f"intent-{self.calls}"
        self._INTENTS[reference] = {"iframe_url": f"https://approval.test/{reference}"}
        return reference

    def await_mandate(self, intent_ref):
        if self.outcome != "approved":
            return {"status": self.outcome, "intent_ref": intent_ref}
        return {
            "status": "approved",
            "mandate_id": f"mandate-{intent_ref}",
            "credential_reference": f"credential-{intent_ref}",
            "scope": {"merchant": "zepto", "max_amount": "380"},
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }


class FakeCheckout:
    def __init__(self, status: str = "completed") -> None:
        self.status = status
        self.calls = 0

    def complete_checkout(self, credential_reference, merchant_sku_id, amount, idempotency_key):
        self.calls += 1
        return {
            "status": self.status,
            "merchant_order_id": "order-1" if self.status == "completed" else None,
            "charged_amount": str(amount) if self.status == "completed" else None,
            "currency": "INR",
            "execution_mode": "disclosed_mock",
        }


class PendingThenCompletedCheckout(FakeCheckout):
    def __init__(self) -> None:
        super().__init__("pending")
        self.reconcile_calls = 0

    def reconcile_checkout(self, idempotency_key):
        self.reconcile_calls += 1
        return {
            "status": "completed",
            "merchant_order_id": "order-reconciled",
            "charged_amount": "380.00",
            "currency": "INR",
            "retryable": False,
            "execution_mode": "real",
        }


def build_user() -> User:
    return User(
        user_id=USER_ID,
        display_name="Asha",
        prava_account_ref="prava-user",
        monthly_cap="5000",
        per_item_cap="1000",
        per_transaction_cap="1000",
        created_at=datetime.now(timezone.utc),
    )


def build_home_item() -> TrackedItem:
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
        currency="INR",
        status="active",
        typical_cadence_days=14,
        last_purchased_at=date.today() - timedelta(days=12),
        last_purchase_amount="380",
    )


def build_teams_item() -> TrackedItem:
    return TrackedItem(
        item_id=UUID("00000000-0000-0000-0000-000000000011"),
        user_id=USER_ID,
        name="TeamTool",
        track="teams",
        trigger_type="known_date",
        category="saas_subscription",
        sensitive_flag=False,
        preferred_merchant="mock_subscription_billing",
        merchant_sku_id="teamtool",
        currency="USD",
        status="active",
        renewal_date=date.today() + timedelta(days=2),
        current_plan_amount="900",
        alternate_plan_amount="800",
        alternate_plan_label="annual",
    )


@pytest.fixture
def repository(tmp_path) -> RestockRepository:
    value = RestockRepository(Database(f"sqlite:///{tmp_path / 'restock.db'}"))
    value.create_schema()
    return value


def test_proactive_workflow_resumes_and_survives_repository_restart(repository) -> None:
    prava = FakePrava()
    checkout = FakeCheckout()
    service = WorkflowService(repository, prava=prava, home_checkout=checkout)
    run = service.begin(build_user(), build_home_item())

    assert run["state"] == "notified"
    assert repository.pending_notifications(str(USER_ID))[0]["run_id"] == run["run_id"]
    assert service.approval_url(run["run_id"]).startswith("https://approval.test/")

    restarted = RestockRepository(Database(repository.database.url))
    assert restarted.get_workflow(run["run_id"])["state"] == "notified"

    service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    final = service.resume_after_passkey(run["run_id"])
    assert final["state"] == "completed"
    assert checkout.calls == 1
    assert repository.transaction_for_run(run["run_id"])["execution_mode"] == "disclosed_mock"
    assert all(entry["modes"] for entry in repository.list_audit(str(USER_ID)))


def test_duplicate_trigger_is_suppressed_by_unique_active_item(repository) -> None:
    service = WorkflowService(repository, prava=FakePrava(), home_checkout=FakeCheckout())
    service.begin(build_user(), build_home_item())
    with pytest.raises(ValueError, match="active workflow"):
        service.begin(build_user(), build_home_item())


@pytest.mark.parametrize("outcome", ["rejected", "expired"])
def test_nonapproved_mandate_creates_no_transaction(repository, outcome) -> None:
    service = WorkflowService(
        repository,
        prava=FakePrava(outcome),
        home_checkout=FakeCheckout(),
    )
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    final = service.resume_after_passkey(run["run_id"])
    assert final["state"] == outcome
    assert repository.transaction_for_run(run["run_id"]) is None


def test_price_change_requires_reapproval_before_checkout(repository) -> None:
    checkout = FakeCheckout()
    fresh_quote = MerchantQuote(
        merchant="zepto",
        merchant_sku_id="coffee-500g",
        product_name="Coffee",
        amount="500",
        currency="INR",
        stock_status="in_stock",
        quote_reference="quote-new",
        observed_at=datetime.now(timezone.utc),
        execution_mode="real",
    )
    service = WorkflowService(
        repository,
        prava=FakePrava(),
        home_checkout=checkout,
        quote_provider=lambda item: fresh_quote,
    )
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    result = service.resume_after_passkey(run["run_id"])
    assert result["state"] == "reapproval_required"
    assert checkout.calls == 0
    assert repository.transaction_for_run(run["run_id"]) is None


def test_pending_checkout_is_durable_and_reconciles_before_transaction(repository) -> None:
    checkout = PendingThenCompletedCheckout()
    service = WorkflowService(repository, prava=FakePrava(), home_checkout=checkout)
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")

    pending = service.resume_after_passkey(run["run_id"])

    assert pending["state"] == "checkout_pending"
    assert repository.transaction_for_run(run["run_id"]) is None
    restarted_repository = RestockRepository(Database(repository.database.url))
    restarted_service = WorkflowService(
        restarted_repository,
        prava=FakePrava(),
        home_checkout=checkout,
    )
    completed = restarted_service.reconcile_checkout(run["run_id"])
    assert completed["state"] == "completed"
    assert checkout.reconcile_calls == 1
    assert restarted_repository.transaction_for_run(run["run_id"])["merchant_order_id"] == "order-reconciled"


def test_checkout_price_change_returns_to_explicit_reapproval(repository) -> None:
    checkout = FakeCheckout(status="price_changed")
    prava = FakePrava()
    service = WorkflowService(repository, prava=prava, home_checkout=checkout)
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")

    changed = service.resume_after_passkey(run["run_id"])

    assert changed["state"] == "reapproval_required"
    assert changed["mandate_ref"] is None
    assert repository.transaction_for_run(run["run_id"]) is None
    pending = repository.pending_notifications(str(USER_ID))
    assert any("price changed" in notification["message"].lower() for notification in pending)
    reapproved = service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    assert reapproved["state"] == "passkey_pending"
    assert reapproved["prava_intent_ref"] != run["prava_intent_ref"]
    assert prava.calls == 2


def test_teams_switch_requires_explicit_action(repository) -> None:
    service = WorkflowService(
        repository,
        prava=FakePrava(),
        teams_checkout=FakeCheckout(),
    )
    run = service.begin(build_user(), build_teams_item())
    with pytest.raises(ValueError, match="explicit switch_plan"):
        service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    accepted = service.act(run["run_id"], user_id=str(USER_ID), action="switch_plan")
    assert accepted["state"] == "passkey_pending"


def test_audit_rejects_payment_secret_fields(repository) -> None:
    repository.upsert_user(build_user())
    with pytest.raises(ValueError, match="forbidden field"):
        repository.audit(
            user_id=str(USER_ID),
            event_type="bad",
            payload={"nested": {"dynamic_cvv": "123"}},
            modes={"prava": "sandbox"},
        )
