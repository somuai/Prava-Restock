from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from payments.models import TrackedItem, User
from storage import Database, RestockRepository


OWNER = UUID("00000000-0000-0000-0000-000000000101")
MEMBER = UUID("00000000-0000-0000-0000-000000000102")
OUTSIDER = UUID("00000000-0000-0000-0000-000000000103")


def user(user_id: UUID, name: str) -> User:
    return User(
        user_id=user_id,
        display_name=name,
        prava_account_ref=f"prava-{user_id}",
        monthly_cap="5000",
        per_item_cap="1000",
        per_transaction_cap="1000",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def repository(tmp_path) -> RestockRepository:
    value = RestockRepository(Database(f"sqlite:///{tmp_path / 'tenants.db'}"))
    value.create_schema()
    for value_user in (user(OWNER, "Owner"), user(MEMBER, "Member"), user(OUTSIDER, "Outsider")):
        value.upsert_user(value_user)
    return value


def tenant_item(tenant_id: str) -> TrackedItem:
    return TrackedItem(
        item_id=UUID("00000000-0000-0000-0000-000000000110"),
        user_id=OWNER,
        tenant_id=UUID(tenant_id),
        name="Office coffee",
        track="home",
        trigger_type="predicted",
        category="grocery",
        sensitive_flag=False,
        preferred_merchant="zepto",
        merchant_sku_id="coffee",
        currency="INR",
        status="active",
        typical_cadence_days=14,
        last_purchased_at=date.today() - timedelta(days=13),
        last_purchase_amount="400",
    )


def test_invitation_and_cross_tenant_isolation(repository) -> None:
    tenant = repository.create_tenant(name="Build Team", kind="organization", owner_user_id=str(OWNER))
    tenant_id = tenant["tenant_id"]
    repository.upsert_item(tenant_item(tenant_id))

    with pytest.raises(PermissionError):
        repository.list_items(str(OUTSIDER), tenant_id)
    with pytest.raises(PermissionError):
        repository.invite_member(
            tenant_id=tenant_id,
            actor_user_id=str(OUTSIDER),
            email="member@example.test",
            role="member",
        )

    invitation = repository.invite_member(
        tenant_id=tenant_id,
        actor_user_id=str(OWNER),
        email="member@example.test",
        role="approver",
    )
    assert "token_hash" not in invitation
    membership = repository.accept_invitation(token=invitation["token"], user_id=str(MEMBER))
    assert membership["role"] == "approver"
    assert repository.list_items(str(MEMBER), tenant_id)[0]["name"] == "Office coffee"
    with pytest.raises(ValueError, match="already used"):
        repository.accept_invitation(token=invitation["token"], user_id=str(MEMBER))


def test_consent_policy_export_and_conflict_rule(repository) -> None:
    tenant_id = repository.create_tenant(
        name="Household",
        kind="household",
        owner_user_id=str(OWNER),
    )["tenant_id"]
    repository.upsert_item(tenant_item(tenant_id))
    consent = repository.set_consent(
        tenant_id=tenant_id,
        user_id=str(OWNER),
        kind="forecasting",
        granted=True,
    )
    assert consent["granted"] is True
    policy = repository.create_approval_policy(
        tenant_id=tenant_id,
        actor_user_id=str(OWNER),
        max_amount=Decimal("1000"),
        currency="INR",
        required_approvals=2,
    )
    assert policy["required_approvals"] == 2
    export = repository.privacy_export(str(OWNER))
    assert export["user"]["display_name"] == "Owner"
    assert export["items"][0]["tenant_id"] == tenant_id


def test_approval_conflict_is_vetoed_and_decisions_are_one_time(repository) -> None:
    tenant_id = repository.create_tenant(
        name="Approvals",
        kind="organization",
        owner_user_id=str(OWNER),
    )["tenant_id"]
    invitation = repository.invite_member(
        tenant_id=tenant_id,
        actor_user_id=str(OWNER),
        email="member@example.test",
        role="approver",
    )
    repository.accept_invitation(token=invitation["token"], user_id=str(MEMBER))
    repository.upsert_item(tenant_item(tenant_id))
    run = repository.create_workflow(
        user_id=str(OWNER),
        item_id=str(tenant_item(tenant_id).item_id),
        trigger_reason="depletion",
        proposed_amount=Decimal("400"),
        currency="INR",
        merchant="zepto",
        proposed_action=None,
        quote=None,
        modes={"prava": "sandbox"},
        idempotency_key="tenant-run",
    )
    first = repository.record_approval_decision(
        tenant_id=tenant_id,
        run_id=run["run_id"],
        user_id=str(OWNER),
        decision="approve",
        required_approvals=2,
    )
    assert first["outcome"] == "pending"
    second = repository.record_approval_decision(
        tenant_id=tenant_id,
        run_id=run["run_id"],
        user_id=str(MEMBER),
        decision="skip",
        required_approvals=2,
    )
    assert second["outcome"] == "vetoed"
    with pytest.raises(ValueError, match="already decided"):
        repository.record_approval_decision(
            tenant_id=tenant_id,
            run_id=run["run_id"],
            user_id=str(OWNER),
            decision="approve",
            required_approvals=2,
        )


def test_privacy_delete_pseudonymizes_payment_owner(repository) -> None:
    repository.delete_user_data(str(OUTSIDER))
    deleted = repository.get_user(str(OUTSIDER))
    assert deleted["display_name"] == "Deleted user"
    assert deleted["prava_account_ref"] == "deleted"
