from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import json
from uuid import UUID, uuid4

import pytest

from merchant.models import MerchantQuote
from merchant.quote_provider import HomeQuoteError, build_home_quote_provider
from payments import prava_client
from payments.models import TrackedItem, User
from storage import Database, RestockRepository
from storage.schema import (
    MerchantCheckoutAttemptRow,
    NotificationActionRow,
    NotificationRow,
    SchedulerLeaseRow,
    TrackedItemRow,
    TransactionRow,
    UserRow,
)
from triggers import renewal_model
from workflow import WorkflowService


USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class FakePrava:
    def __init__(self, outcome: str = "approved") -> None:
        self.outcome = outcome
        self.calls = 0
        self.await_calls = 0
        self.amounts: list[Decimal] = []
        self.retired: list[str] = []
        self.reports: list[tuple] = []
        self._INTENTS: dict[str, dict] = {}

    def create_intent(self, merchant, amount, item_description, constraints):
        self.calls += 1
        self.amounts.append(Decimal(str(amount)))
        reference = f"intent-{self.calls}"
        self._INTENTS[reference] = {"iframe_url": f"https://approval.test/{reference}"}
        return reference

    def await_mandate(self, intent_ref):
        self.await_calls += 1
        if self.outcome != "approved":
            return {"status": self.outcome, "intent_ref": intent_ref}
        return {
            "status": "approved",
            "mandate_id": f"mandate-{intent_ref}",
            "credential_reference": f"credential-{intent_ref}",
            "scope": {"merchant": "zepto", "max_amount": "380"},
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }

    def retire_credential(self, credential_reference):
        self.retired.append(str(credential_reference))

    def report_checkout_outcome(self, *args):
        self.reports.append(args)


class FakeCheckout:
    def __init__(self, status: str = "completed") -> None:
        self.status = status
        self.calls = 0
        self.amounts: list[Decimal] = []

    def complete_checkout(self, credential_reference, merchant_sku_id, amount, idempotency_key):
        self.calls += 1
        self.amounts.append(Decimal(str(amount)))
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


def build_teams_item(*, renewal_method: str = "hosted_link") -> TrackedItem:
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
        renewal_method=renewal_method,
    )


def quote(amount: str, *, stock_status: str = "in_stock", reference: str = "quote") -> MerchantQuote:
    return MerchantQuote(
        merchant="zepto",
        merchant_sku_id="coffee-500g",
        product_name="Coffee",
        amount=amount,
        currency="INR",
        stock_status=stock_status,
        quote_reference=reference,
        observed_at=datetime.now(timezone.utc),
        execution_mode="real",
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
    item = build_home_item()
    run = service.begin(build_user(), item)

    assert run["state"] == "notified"
    pending = repository.pending_notifications(str(USER_ID))
    assert pending[0]["run_id"] == run["run_id"]
    assert pending[0]["item_id"] == str(item.item_id)
    assert pending[0]["track"] == "home"
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


def test_teams_switch_requires_a_separately_sourced_alternate_invoice_link(
    repository,
) -> None:
    prava = FakePrava()
    item = build_teams_item().model_copy(
        update={
            "hosted_payment_reference": "current-invoice-123",
        }
    )
    service = WorkflowService(repository, prava=prava, teams_checkout=FakeCheckout())

    with pytest.raises(ValueError, match="alternate plan requires its own sourced"):
        service.begin(build_user(), item)

    assert prava.calls == 0


def test_real_teams_mode_requires_invoice_reference_before_prava(
    repository, monkeypatch
) -> None:
    monkeypatch.setenv("TEAMS_BILLING_MODE", "real")
    prava = FakePrava()
    service = WorkflowService(repository, prava=prava, teams_checkout=FakeCheckout())

    with pytest.raises(ValueError, match="requires a sourced hosted invoice reference"):
        service.begin(build_user(), build_teams_item())

    assert prava.calls == 0


def test_teams_switch_binds_the_alternate_invoice_before_prava(repository) -> None:
    prava = FakePrava()
    item = build_teams_item().model_copy(
        update={
            "hosted_payment_reference": "current-invoice-123",
            "alternate_hosted_payment_reference": "annual-invoice-456",
        }
    )
    service = WorkflowService(repository, prava=prava, teams_checkout=FakeCheckout())

    run = service.begin(build_user(), item)

    assert prava.calls == 1
    assert run["quote"]["quote_reference"] == item.alternate_hosted_payment_reference
    assert Decimal(str(run["proposed_amount"])) == item.alternate_plan_amount


def test_initial_over_cap_proposal_never_reaches_prava_or_durable_workflow(
    repository,
) -> None:
    prava = FakePrava()
    checkout = FakeCheckout()
    user = build_user().model_copy(update={"per_item_cap": Decimal("300")})
    service = WorkflowService(
        repository,
        prava=prava,
        home_checkout=checkout,
    )

    with pytest.raises(ValueError, match="cap"):
        service.begin(user, build_home_item())

    assert prava.calls == 0
    assert prava.await_calls == 0
    assert checkout.calls == 0
    assert repository.list_workflows(str(USER_ID)) == []
    assert repository.pending_notifications(str(USER_ID)) == []
    assert repository.list_audit(str(USER_ID)) == []
    with repository.database.session() as session:
        for row_type in (
            UserRow,
            TrackedItemRow,
            NotificationRow,
            NotificationActionRow,
            MerchantCheckoutAttemptRow,
            TransactionRow,
            SchedulerLeaseRow,
        ):
            assert session.query(row_type).count() == 0


def test_resume_from_notified_cannot_reach_mandate_or_checkout(repository) -> None:
    prava = FakePrava()
    checkout = FakeCheckout()
    service = WorkflowService(
        repository,
        prava=prava,
        home_checkout=checkout,
    )
    run = service.begin(build_user(), build_home_item())
    assert run["state"] == "notified"

    with pytest.raises(ValueError, match="not waiting for passkey approval"):
        service.resume_after_passkey(run["run_id"])

    assert prava.await_calls == 0
    assert checkout.calls == 0
    assert repository.get_workflow(run["run_id"])["state"] == "notified"
    assert repository.transaction_for_run(run["run_id"]) is None


def test_manual_renewal_persists_notification_without_payment_boundaries(
    repository,
) -> None:
    prava = FakePrava()
    checkout = FakeCheckout()
    item = build_teams_item(renewal_method="manual_required")
    service = WorkflowService(
        repository,
        prava=prava,
        teams_checkout=checkout,
    )

    run = service.begin(build_user(), item)

    assert run["state"] == "notified"
    assert run["proposed_amount"] is None
    assert run["merchant"] is None
    assert run["proposed_action"] == "flag_for_manual_renewal"
    notifications = repository.pending_notifications(str(USER_ID))
    assert len(notifications) == 1
    assert notifications[0]["message"] == renewal_model.propose(item)["message"]
    assert notifications[0]["actions"] == ["skip"]
    assert prava.calls == 0
    assert prava.await_calls == 0
    assert checkout.calls == 0
    assert repository.transaction_for_run(run["run_id"]) is None

    audit = [
        entry
        for entry in repository.list_audit(str(USER_ID))
        if entry["run_id"] == run["run_id"]
    ]
    flagged = next(
        entry for entry in audit if entry["event_type"] == "manual_renewal_flagged"
    )
    assert flagged["payload"] == {
        "notification_id": notifications[0]["notification_id"],
        "actions": ["skip"],
        "renewal_method": "manual_required",
    }
    assert flagged["modes"] == run["modes"]
    assert all(entry["modes"] for entry in audit)

    with pytest.raises(ValueError, match="manual-renewal workflow only supports skip"):
        service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    assert prava.calls == 0
    assert prava.await_calls == 0

    with pytest.raises(ValueError, match="active workflow"):
        service.begin(build_user(), item)

    skipped = service.act(run["run_id"], user_id=str(USER_ID), action="skip")
    assert skipped["state"] == "skipped"
    assert skipped["active_item_key"] is None
    assert repository.pending_notifications(str(USER_ID)) == []
    assert prava.calls == 0
    assert prava.await_calls == 0
    assert checkout.calls == 0


@pytest.mark.parametrize(
    ("proposed_action", "proposed_amount", "merchant"),
    [
        ("flag_for_manual_renewal", Decimal("1"), None),
        ("flag_for_manual_renewal", None, "mock_subscription_billing"),
        ("flag_for_manual_renewal", Decimal("1"), "mock_subscription_billing"),
        ("renew_as_is", None, "mock_subscription_billing"),
        ("renew_as_is", Decimal("1"), None),
        ("renew_as_is", None, None),
        (None, None, None),
    ],
)
def test_repository_rejects_inconsistent_workflow_payment_shape(
    repository,
    proposed_action,
    proposed_amount,
    merchant,
) -> None:
    user = build_user()
    item = build_teams_item()
    repository.upsert_user(user)
    repository.upsert_item(item)

    with pytest.raises(ValueError, match="workflow payment proposal shape"):
        repository.create_workflow(
            user_id=str(user.user_id),
            item_id=str(item.item_id),
            trigger_reason="known_renewal_date",
            proposed_amount=proposed_amount,
            currency="USD",
            merchant=merchant,
            proposed_action=proposed_action,
            quote=None,
            modes={"prava": "not_applicable"},
            idempotency_key=f"invalid-{proposed_action}-{proposed_amount}-{merchant}",
        )


def test_repository_transition_rejects_inconsistent_workflow_payment_shape(
    repository,
) -> None:
    user = build_user()
    item = build_teams_item()
    repository.upsert_user(user)
    repository.upsert_item(item)
    normal = repository.create_workflow(
        user_id=str(user.user_id),
        item_id=str(item.item_id),
        trigger_reason="known_renewal_date",
        proposed_amount=Decimal("900"),
        currency="USD",
        merchant="mock_subscription_billing",
        proposed_action="renew_as_is",
        quote=None,
        modes={"prava": "sandbox"},
        idempotency_key="normal-shape",
    )

    with pytest.raises(ValueError, match="workflow payment proposal shape"):
        repository.transition(
            normal["run_id"],
            expected={"triggered"},
            state="triggered",
            proposed_amount=None,
        )
    with pytest.raises(ValueError, match="workflow payment proposal shape"):
        repository.transition(
            normal["run_id"],
            expected={"triggered"},
            state="triggered",
            proposed_action="flag_for_manual_renewal",
        )


def test_duplicate_item_is_reserved_before_quote_mutation(repository) -> None:
    quote_calls = 0

    def provider(item):
        nonlocal quote_calls
        quote_calls += 1
        return quote("380")

    service = WorkflowService(
        repository,
        prava=FakePrava(),
        home_checkout=FakeCheckout(),
        quote_provider=provider,
    )
    service.begin(build_user(), build_home_item())
    with pytest.raises(ValueError, match="active workflow"):
        service.begin(build_user(), build_home_item())
    assert quote_calls == 1


def test_real_quote_and_disclosed_payment_are_tagged_independently(
    repository, monkeypatch
) -> None:
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setenv("HOME_PAYMENT_MODE", "disclosed_mock")
    prava = FakePrava()
    service = WorkflowService(
        repository,
        prava=prava,
        home_checkout=FakeCheckout(),
        quote_provider=lambda item: quote("380", reference="real-cart-quote"),
    )

    run = service.begin(build_user(), build_home_item())
    assert run["modes"]["home_catalog"] == "real"
    assert run["modes"]["home_payment"] == "disclosed_mock"
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    completed = service.resume_after_passkey(run["run_id"])

    assert completed["state"] == "completed"
    assert repository.transaction_for_run(run["run_id"])["execution_mode"] == "disclosed_mock"
    assert prava.retired == ["credential-intent-1"]
    assert all(
        entry["modes"]["home_catalog"] == "real"
        and entry["modes"]["home_payment"] == "disclosed_mock"
        for entry in repository.list_audit(str(USER_ID))
        if entry["run_id"] == run["run_id"]
    )


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
    initial_quote = MerchantQuote(
        merchant="zepto",
        merchant_sku_id="coffee-500g",
        product_name="Coffee",
        amount="380",
        currency="INR",
        stock_status="in_stock",
        quote_reference="quote-initial",
        observed_at=datetime.now(timezone.utc),
        execution_mode="real",
    )
    fresh_quote = initial_quote.model_copy(
        update={"amount": Decimal("500"), "quote_reference": "quote-new"}
    )
    quotes = iter((initial_quote, fresh_quote))
    service = WorkflowService(
        repository,
        prava=FakePrava(),
        home_checkout=checkout,
        quote_provider=lambda item: next(quotes),
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


def test_transaction_and_terminal_workflow_survive_crash_as_one_commit(
    repository, monkeypatch
) -> None:
    checkout = PendingThenCompletedCheckout()
    service = WorkflowService(repository, prava=FakePrava(), home_checkout=checkout)
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    assert service.resume_after_passkey(run["run_id"])["state"] == "checkout_pending"

    def crash_after_terminal_commit(**_kwargs):
        raise RuntimeError("process stopped after terminal database commit")

    monkeypatch.setattr(repository, "apply_completion_effects", crash_after_terminal_commit)
    with pytest.raises(RuntimeError, match="terminal database commit"):
        service.reconcile_checkout(run["run_id"])

    restarted = RestockRepository(Database(repository.database.url))
    durable_run = restarted.get_workflow(run["run_id"])
    durable_transaction = restarted.transaction_for_run(run["run_id"])
    assert durable_run["state"] == "completed"
    assert durable_run["active_item_key"] is None
    assert durable_transaction["merchant_order_id"] == "order-reconciled"
    assert restarted.completion_effects_for_run(run["run_id"])["status"] == "pending"

    with pytest.raises(ValueError, match="completion effects are pending"):
        WorkflowService(
            restarted, prava=FakePrava(), home_checkout=checkout
        ).begin(build_user(), restarted.get_item(run["item_id"]))

    repaired_service = WorkflowService(
        restarted, prava=FakePrava(), home_checkout=checkout
    )
    assert repaired_service.repair_pending_completion_effects() == 1
    assert restarted.get_workflow(run["run_id"])["state"] == "completed"
    assert restarted.completion_effects_for_run(run["run_id"])["status"] == "completed"
    completion_audits = [
        entry
        for entry in restarted.list_audit(str(USER_ID))
        if entry["run_id"] == run["run_id"]
        and entry["event_type"] == "transaction_completed"
    ]
    assert len(completion_audits) == 1
    repaired_item = restarted.get_item(run["item_id"])
    repaired_cadence = repaired_item.typical_cadence_days
    repaired_service.repair_completion_effects(run["run_id"])
    assert repaired_service.repair_pending_completion_effects() == 0
    assert restarted.get_item(run["item_id"]).typical_cadence_days == repaired_cadence
    assert len(
        [
            entry
            for entry in restarted.list_audit(str(USER_ID))
            if entry["run_id"] == run["run_id"]
            and entry["event_type"] == "transaction_completed"
        ]
    ) == 1

    verified_run, verified_transaction = restarted.complete_checkout_atomically(
        run_id=run["run_id"],
        expected_state="checkout_pending",
        item_id=run["item_id"],
        mandate_ref=str(durable_run["mandate_ref"]),
        merchant_order_id="order-reconciled",
        amount=Decimal("380.00"),
        currency="INR",
        execution_mode="real",
    )
    assert verified_run["state"] == "completed"
    assert verified_transaction["transaction_id"] == durable_transaction["transaction_id"]

    next_run = repaired_service.begin(build_user(), restarted.get_item(run["item_id"]))
    assert next_run["state"] == "notified"


def test_atomic_checkout_completion_is_idempotent_under_concurrency(repository) -> None:
    user = build_user()
    item = build_home_item()
    repository.upsert_user(user)
    repository.upsert_item(item)
    run = repository.create_workflow(
        user_id=str(user.user_id),
        item_id=str(item.item_id),
        trigger_reason="predicted_depletion",
        proposed_amount=Decimal("380"),
        currency="INR",
        merchant="zepto",
        proposed_action=None,
        quote=None,
        modes={"home_payment": "real"},
        idempotency_key="concurrent-terminal",
    )

    def complete():
        return repository.complete_checkout_atomically(
            run_id=run["run_id"],
            expected_state="triggered",
            item_id=str(item.item_id),
            mandate_ref="mandate-concurrent",
            merchant_order_id="order-concurrent",
            amount=Decimal("380"),
            currency="INR",
            execution_mode="real",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: complete(), range(2)))

    assert {result[0]["state"] for result in results} == {"completed"}
    assert len({result[1]["transaction_id"] for result in results}) == 1


@pytest.mark.parametrize(
    ("amount", "currency"),
    [(Decimal("381.00"), "INR"), (Decimal("380.00"), "USD")],
)
def test_atomic_completion_rejects_outcome_not_bound_to_locked_run(
    repository, amount, currency
) -> None:
    user = build_user()
    item = build_home_item()
    repository.upsert_user(user)
    repository.upsert_item(item)
    run = repository.create_workflow(
        user_id=str(user.user_id),
        item_id=str(item.item_id),
        trigger_reason="predicted_depletion",
        proposed_amount=Decimal("380.00"),
        currency="INR",
        merchant="zepto",
        proposed_action=None,
        quote=None,
        modes={"home_payment": "real"},
        idempotency_key=f"mismatch-{currency}-{amount}",
    )

    with pytest.raises(ValueError, match="locked workflow"):
        repository.complete_checkout_atomically(
            run_id=run["run_id"],
            expected_state="triggered",
            item_id=str(item.item_id),
            mandate_ref="mandate-mismatch",
            merchant_order_id="order-mismatch",
            amount=amount,
            currency=currency,
            execution_mode="real",
        )

    assert repository.transaction_for_run(run["run_id"]) is None
    assert repository.completion_effects_for_run(run["run_id"]) is None
    assert repository.get_workflow(run["run_id"])["state"] == "triggered"


def test_terminal_reconciliation_releases_preserved_deterministic_cart_lease(
    repository, monkeypatch
) -> None:
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    provider = build_home_quote_provider(repository)
    monkeypatch.setattr(provider, "quote_locked", lambda item: quote("380"))
    monkeypatch.setattr(provider, "revalidate_locked", lambda item: quote("380"))
    checkout = PendingThenCompletedCheckout()
    service = WorkflowService(
        repository,
        prava=FakePrava(),
        home_checkout=checkout,
        quote_provider=provider,
    )
    item = build_home_item()
    run = service.begin(build_user(), item)
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    assert service.resume_after_passkey(run["run_id"])["state"] == "checkout_pending"
    with pytest.raises(HomeQuoteError, match="another checkout"):
        with provider.checkout_scope(item):
            pass

    assert service.reconcile_checkout(run["run_id"])["state"] == "completed"
    with provider.checkout_scope(item):
        pass


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


def test_reapproval_new_intent_holds_user_budget_lease(repository) -> None:
    class LeaseCheckingPrava(FakePrava):
        def create_intent(self, merchant, amount, item_description, constraints):
            assert repository.acquire_lease(
                lease_name=f"spend-budget:{USER_ID}",
                owner_id="competing-owner",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
            ) is False
            return super().create_intent(merchant, amount, item_description, constraints)

    quotes = iter((quote("380"), quote("500"), quote("500")))
    prava = LeaseCheckingPrava()
    service = WorkflowService(
        repository,
        prava=prava,
        home_checkout=FakeCheckout(),
        quote_provider=lambda item: next(quotes),
    )
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    assert service.resume_after_passkey(run["run_id"])["state"] == "reapproval_required"

    reapproved = service.act(run["run_id"], user_id=str(USER_ID), action="approve")

    assert reapproved["state"] == "passkey_pending"
    assert prava.calls == 2


def test_expired_budget_owner_cannot_resume_after_competing_quote_reservation(
    repository,
) -> None:
    prava = FakePrava()

    def quote_after_lease_takeover(item):
        lease_name = f"spend-budget:{USER_ID}"
        with repository.database.session() as session:
            lease = session.get(SchedulerLeaseRow, lease_name)
            assert lease is not None
            lease.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert repository.acquire_lease(
            lease_name=lease_name,
            owner_id="newer-budget-owner",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        return quote("900", reference="late-expensive-quote")

    service = WorkflowService(
        repository,
        prava=prava,
        home_checkout=FakeCheckout(),
        quote_provider=quote_after_lease_takeover,
    )

    with pytest.raises(ValueError, match="expired or changed owner"):
        service.begin(build_user(), build_home_item())

    run = repository.list_workflows(str(USER_ID))[0]
    assert run["state"] == "failed"
    assert run["error_code"] == "HOME_QUOTE_FAILED"
    assert Decimal(str(run["proposed_amount"])) == Decimal("380")
    assert prava.calls == 0
    assert repository.acquire_lease(
        lease_name=f"spend-budget:{USER_ID}",
        owner_id="third-owner",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    ) is False


@pytest.mark.parametrize(
    ("fresh_amount", "expected_state", "checkout_amount"),
    [
        ("380", "completed", Decimal("380")),
        ("350", "completed", Decimal("350")),
        ("381", "reapproval_required", None),
        ("300", "reapproval_required", None),
    ],
)
def test_fresh_quote_price_policy(
    repository, fresh_amount, expected_state, checkout_amount
) -> None:
    quotes = iter((quote("380", reference="initial"), quote(fresh_amount, reference="fresh")))
    checkout = FakeCheckout()
    prava = FakePrava()
    service = WorkflowService(
        repository,
        prava=prava,
        home_checkout=checkout,
        quote_provider=lambda item: next(quotes),
    )
    run = service.begin(build_user(), build_home_item())
    assert prava.amounts == [Decimal("380")]
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")

    result = service.resume_after_passkey(run["run_id"])

    assert result["state"] == expected_state
    transaction = repository.transaction_for_run(run["run_id"])
    assert (transaction is None) is (expected_state != "completed")
    if checkout_amount is None:
        assert checkout.calls == 0
        assert prava.retired == ["credential-intent-1"]
    else:
        assert checkout.amounts == [checkout_amount]
        assert Decimal(str(result["proposed_amount"])) == checkout_amount
        # Disclosed checkout never exposes the one-time credential, so the
        # payment boundary deletes it after recording the simulated result.
        assert prava.retired == ["credential-intent-1"]


def test_quote_failure_is_audited_and_releases_active_item(repository) -> None:
    class FailingPrava(FakePrava):
        def create_intent(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    service = WorkflowService(repository, prava=FailingPrava())
    with pytest.raises(RuntimeError, match="provider unavailable"):
        service.begin(build_user(), build_home_item())
    run = repository.list_workflows(str(USER_ID))[0]
    assert run["state"] == "failed"
    assert run["error_code"] == "PRAVA_INTENT_CREATION_FAILED"
    assert any(
        entry["event_type"] == "intent_creation_failed"
        for entry in repository.list_audit(str(USER_ID))
    )
    # Terminal failure cleared active_item_key, so the item is not suppressed forever.
    assert WorkflowService(repository, prava=FakePrava()).begin(
        build_user(), build_home_item()
    )["state"] == "notified"


def test_out_of_stock_quote_never_calls_prava_and_keeps_audit(repository) -> None:
    prava = FakePrava()
    service = WorkflowService(
        repository,
        prava=prava,
        quote_provider=lambda item: quote("380", stock_status="out_of_stock"),
    )
    with pytest.raises(ValueError, match="out of stock"):
        service.begin(build_user(), build_home_item())
    run = repository.list_workflows(str(USER_ID))[0]
    assert run["state"] == "failed"
    assert run["error_code"] == "HOME_QUOTE_FAILED"
    assert prava.calls == 0
    assert any(
        entry["event_type"] == "quote_failed"
        for entry in repository.list_audit(str(USER_ID))
    )


def test_out_of_stock_revalidation_retires_unused_credential(repository) -> None:
    quotes = iter((quote("380", reference="initial"), quote(
        "380", stock_status="out_of_stock", reference="fresh"
    )))
    prava = FakePrava()
    checkout = FakeCheckout()
    service = WorkflowService(
        repository,
        prava=prava,
        home_checkout=checkout,
        quote_provider=lambda item: next(quotes),
    )
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")

    result = service.resume_after_passkey(run["run_id"])

    assert result["state"] == "failed"
    assert prava.retired == ["credential-intent-1"]
    assert checkout.calls == 0
    assert repository.transaction_for_run(run["run_id"]) is None


def test_currency_mismatched_initial_quote_never_reaches_prava(repository) -> None:
    item = build_home_item().model_copy(update={"currency": "USD"})
    prava = FakePrava()
    service = WorkflowService(
        repository,
        prava=prava,
        quote_provider=lambda candidate: quote("380"),
    )

    with pytest.raises(ValueError, match="currency"):
        service.begin(build_user(), item)

    assert prava.calls == 0
    run = repository.list_workflows(str(USER_ID))[0]
    assert run["state"] == "failed"
    assert run["error_code"] == "HOME_QUOTE_FAILED"


@pytest.mark.parametrize(
    ("quote_case", "error_match"),
    [
        ("out_of_stock", "out of stock"),
        ("naive", "timezone-aware"),
        ("future", "future"),
        ("expired", "expired"),
    ],
)
def test_caller_supplied_unusable_quote_is_rejected_before_prava(
    repository, monkeypatch, quote_case, error_match
) -> None:
    monkeypatch.setenv("ZEPTO_QUOTE_MAX_AGE_SECONDS", "60")
    quote_update = {
        "out_of_stock": {"stock_status": "out_of_stock"},
        "naive": {"observed_at": datetime.now()},
        # Construct clock-sensitive cases during the test instead of at module
        # collection time, so a slow CI run cannot turn a future quote valid.
        "future": {"observed_at": datetime.now(timezone.utc) + timedelta(minutes=1)},
        "expired": {"observed_at": datetime.now(timezone.utc) - timedelta(seconds=61)},
    }[quote_case]
    supplied = MerchantQuote.model_validate(
        quote("380").model_dump() | quote_update
    )
    prava = FakePrava()
    service = WorkflowService(repository, prava=prava, home_checkout=FakeCheckout())

    with pytest.raises(ValueError, match=error_match):
        service.begin(build_user(), build_home_item(), quote=supplied)

    assert prava.calls == 0
    assert repository.list_workflows(str(USER_ID)) == []


@pytest.mark.parametrize("restart_state", ["mandate_approved", "quote_revalidated"])
def test_restart_without_merchant_attempt_terminalizes_lost_credential_safely(
    repository, restart_state
) -> None:
    initial_service = WorkflowService(
        repository, prava=FakePrava(), home_checkout=FakeCheckout()
    )
    run = initial_service.begin(build_user(), build_home_item())
    initial_service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    repository.transition(
        run["run_id"],
        expected={"passkey_pending"},
        state="mandate_approved",
        mandate_ref="mandate-before-restart",
    )
    if restart_state == "quote_revalidated":
        repository.transition(
            run["run_id"],
            expected={"mandate_approved"},
            state="quote_revalidated",
        )

    restarted_repository = RestockRepository(Database(repository.database.url))
    restarted_prava = FakePrava()
    restarted_checkout = FakeCheckout()
    restarted_service = WorkflowService(
        restarted_repository,
        prava=restarted_prava,
        home_checkout=restarted_checkout,
    )

    recovered = restarted_service.resume_after_passkey(run["run_id"])

    assert recovered["state"] == "failed"
    assert recovered["error_code"] == "CREDENTIAL_LOST_BEFORE_EXPOSURE"
    assert restarted_checkout.calls == 0
    assert restarted_repository.transaction_for_run(run["run_id"]) is None
    assert restarted_repository.get_merchant_checkout_attempt(run["idempotency_key"]) is None
    assert restarted_prava.retired == []
    assert restarted_prava.reports == []
    audit = restarted_repository.list_audit(str(USER_ID))
    recovery_entries = [
        entry for entry in audit if entry["event_type"] == "credential_lost_before_exposure"
    ]
    assert len(recovery_entries) == 1
    serialized = json.dumps(recovery_entries[0], default=str).lower()
    assert "credential_reference" not in serialized
    assert "mandate-before-restart" not in serialized


@pytest.mark.parametrize(
    "fresh_quote",
    [
        quote("380").model_copy(update={"merchant": "swiggy"}),
        quote("380").model_copy(update={"merchant_sku_id": "other-sku"}),
        quote("380").model_copy(update={"currency": "USD"}),
    ],
)
def test_revalidation_binding_failure_is_durable_and_retires_unexposed_credential(
    repository, fresh_quote
) -> None:
    quotes = iter((quote("380", reference="initial"), fresh_quote))
    prava = FakePrava()
    checkout = FakeCheckout()
    service = WorkflowService(
        repository,
        prava=prava,
        home_checkout=checkout,
        quote_provider=lambda item: next(quotes),
    )
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")

    with pytest.raises(RuntimeError, match="durable workflow state"):
        service.resume_after_passkey(run["run_id"])

    persisted = repository.get_workflow(run["run_id"])
    assert persisted["state"] == "failed"
    assert persisted["error_code"] == "PRECHECK_BOUNDARY_FAILED"
    assert prava.retired == ["credential-intent-1"]
    assert checkout.calls == 0
    assert repository.transaction_for_run(run["run_id"]) is None


def test_cart_lease_failure_after_approval_is_sanitized_and_durable(repository) -> None:
    class LeaseFailingProvider:
        @staticmethod
        def supports(item):
            return True

        def __call__(self, item):
            return quote("380")

        @contextmanager
        def checkout_scope(self, item, *, owner_key=None):
            raise RuntimeError("raw oauth session and address must not leak")
            yield

    prava = FakePrava()
    service = WorkflowService(
        repository,
        prava=prava,
        home_checkout=FakeCheckout(),
        quote_provider=LeaseFailingProvider(),
    )
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")

    with pytest.raises(RuntimeError, match="durable workflow state"):
        service.resume_after_passkey(run["run_id"])

    persisted = repository.get_workflow(run["run_id"])
    assert persisted["state"] == "failed"
    assert persisted["error_code"] == "PRECHECK_BOUNDARY_FAILED"
    assert prava.retired == ["credential-intent-1"]
    audit_text = json.dumps(repository.list_audit(str(USER_ID)), default=str).lower()
    assert "raw oauth" not in audit_text
    assert "address must not leak" not in audit_text


@pytest.mark.parametrize("boundary_error", ["runtime unavailable", "context invalid"])
def test_checkout_boundary_exception_is_ambiguous_without_credential_retirement(
    repository, boundary_error
) -> None:
    class FailingCheckout(FakeCheckout):
        def complete_checkout(self, *args):
            raise RuntimeError(boundary_error)

    quotes = iter((quote("380"), quote("380")))
    prava = FakePrava()
    service = WorkflowService(
        repository,
        prava=prava,
        home_checkout=FailingCheckout(),
        quote_provider=lambda item: next(quotes),
    )
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")

    with pytest.raises(RuntimeError, match="durable workflow state"):
        service.resume_after_passkey(run["run_id"])

    persisted = repository.get_workflow(run["run_id"])
    assert persisted["state"] == "checkout_pending"
    assert persisted["error_code"] == "CHECKOUT_BOUNDARY_AMBIGUOUS"
    assert prava.retired == []
    assert repository.transaction_for_run(run["run_id"]) is None
    audit_text = json.dumps(repository.list_audit(str(USER_ID)), default=str).lower()
    assert boundary_error not in audit_text


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


def test_adjust_enforces_caps_before_recording_action(repository) -> None:
    service = WorkflowService(repository, prava=FakePrava(), home_checkout=FakeCheckout())
    run = service.begin(build_user(), build_home_item())

    with pytest.raises(ValueError, match="cap"):
        service.act(
            run["run_id"],
            user_id=str(USER_ID),
            action="adjust",
            adjusted_amount=Decimal("1001"),
        )

    assert repository.get_workflow(run["run_id"])["state"] == "notified"


def test_active_workflows_reserve_monthly_spend(repository) -> None:
    user = build_user().model_copy(update={"monthly_cap": Decimal("700")})
    first = build_home_item()
    second = build_home_item().model_copy(update={"item_id": uuid4(), "name": "Tea"})
    service = WorkflowService(repository, prava=FakePrava(), home_checkout=FakeCheckout())

    service.begin(user, first)
    with pytest.raises(ValueError, match="monthly cap"):
        service.begin(user, second)

    assert len(repository.list_workflows(str(USER_ID))) == 1


def test_revalidation_holds_cart_scope_through_checkout(repository) -> None:
    class ScopedProvider:
        active = False

        def __call__(self, item):
            return quote("380", reference="initial")

        @contextmanager
        def checkout_scope(self, item, *, owner_key=None):
            assert owner_key
            assert not self.active
            self.active = True
            try:
                yield object()
            finally:
                self.active = False

        def quote_locked(self, item):
            assert self.active
            return quote("380", reference="fresh")

    provider = ScopedProvider()

    class ScopeCheckingCheckout(FakeCheckout):
        def complete_checkout(self, *args):
            assert provider.active
            return super().complete_checkout(*args)

    service = WorkflowService(
        repository,
        prava=FakePrava(),
        home_checkout=ScopeCheckingCheckout(),
        quote_provider=provider,
    )
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")

    assert service.resume_after_passkey(run["run_id"])["state"] == "completed"
    assert provider.active is False


def test_quote_audit_is_complete_and_excludes_address_device_context(repository) -> None:
    quotes = iter((quote("380", reference="initial-ref"), quote("370", reference="fresh-ref")))
    service = WorkflowService(
        repository,
        prava=FakePrava(),
        home_checkout=FakeCheckout(),
        quote_provider=lambda item: next(quotes),
    )
    run = service.begin(build_user(), build_home_item())
    service.act(run["run_id"], user_id=str(USER_ID), action="approve")
    service.resume_after_passkey(run["run_id"])

    quote_entries = [
        entry for entry in repository.list_audit(str(USER_ID))
        if entry["event_type"] in {"quote_obtained", "quote_revalidated"}
    ]
    assert len(quote_entries) == 2
    required = {
        "quote_reference", "observed_at", "amount", "currency",
        "stock_status", "execution_mode",
    }
    assert all(required == set(entry["payload"]) for entry in quote_entries)
    serialized = json.dumps(quote_entries, default=str)
    assert "merchant_address_ref" not in serialized
    assert "saved-address" not in serialized
    assert "device" not in serialized.lower()
    assert "oauth" not in serialized.lower()


def test_audit_rejects_payment_secret_fields(repository) -> None:
    repository.upsert_user(build_user())
    with pytest.raises(ValueError, match="forbidden field"):
        repository.audit(
            user_id=str(USER_ID),
            event_type="bad",
            payload={"nested": {"dynamic_cvv": "123"}},
            modes={"prava": "sandbox"},
        )


@pytest.mark.parametrize(
    ("key", "url", "production_gate", "expected"),
    [
        ("sk_test_placeholder", "https://sandbox.api.prava.space", None, "sandbox"),
        ("sk_live_placeholder", "https://api.prava.space", "1", "production"),
    ],
)
def test_configured_prava_mode_is_truthful(
    monkeypatch, key, url, production_gate, expected
) -> None:
    monkeypatch.setenv("PRAVA_API_KEY", key)
    monkeypatch.setenv("PRAVA_API_URL", url)
    if production_gate is None:
        monkeypatch.delenv("PRAVA_PRODUCTION_ENABLED", raising=False)
    else:
        monkeypatch.setenv("PRAVA_PRODUCTION_ENABLED", production_gate)
    assert prava_client.configured_mode() == expected


def test_injected_fake_boundary_is_disclosed_in_workflow_audit(repository) -> None:
    service = WorkflowService(repository, prava=FakePrava(), home_checkout=FakeCheckout())
    run = service.begin(build_user(), build_home_item())
    assert run["modes"]["prava"] == "disclosed_mock"
    assert {
        entry["modes"]["prava"] for entry in repository.list_audit(str(USER_ID))
    } == {"disclosed_mock"}
