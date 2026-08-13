from uuid import UUID

from payments.models import TrackedItem
from scripts.provision_reviewer import provision_reviewer
from storage import Database, RestockRepository


def test_reviewer_provisioning_is_isolated_and_idempotent(tmp_path) -> None:
    repository = RestockRepository(
        Database(f"sqlite:///{tmp_path / 'reviewer.db'}")
    )
    repository.create_schema()
    reviewer_id = UUID("00000000-0000-0000-0000-000000000099")

    first_created, first_total = provision_reviewer(
        repository, user_id=reviewer_id
    )
    stale_teams_fixture = next(
        item
        for item in repository.list_items(str(reviewer_id))
        if item["merchant_sku_id"] == "teamtool-pro-monthly"
    )
    repository.upsert_item(
        TrackedItem.model_validate(stale_teams_fixture | {"name": "TeamTool Pro"})
    )
    second_created, second_total = provision_reviewer(
        repository, user_id=reviewer_id
    )

    assert (first_created, first_total) == (5, 5)
    assert (second_created, second_total) == (0, 5)
    assert repository.get_user(str(reviewer_id))["display_name"] == "Prava Review"
    assert all(
        item["user_id"] == str(reviewer_id)
        for item in repository.list_items(str(reviewer_id))
    )
    refreshed_teams_fixture = next(
        item
        for item in repository.list_items(str(reviewer_id))
        if item["merchant_sku_id"] == "teamtool-pro-monthly"
    )
    assert refreshed_teams_fixture["name"] == "GitHub Copilot Business"


def test_reviewer_history_reset_removes_only_reviewer_replay_data(tmp_path) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'reviewer-reset.db'}"))
    repository.create_schema()
    reviewer_id = UUID("00000000-0000-0000-0000-000000000099")
    provision_reviewer(repository, user_id=reviewer_id)
    item = repository.list_items(str(reviewer_id))[0]
    run = repository.create_workflow(
        user_id=str(reviewer_id),
        item_id=item["item_id"],
        trigger_reason="review",
        proposed_amount="10.00",
        currency="INR",
        merchant="zepto",
        proposed_action=None,
        quote=None,
        modes={"prava": "sandbox"},
        idempotency_key="reviewer-history-reset",
    )
    repository.audit(
        user_id=str(reviewer_id),
        run_id=run["run_id"],
        item_id=item["item_id"],
        event_type="old_reviewer_event",
        payload={},
        modes={"prava": "sandbox"},
    )

    created, total = provision_reviewer(repository, user_id=reviewer_id, reset_history=True)

    assert (created, total) == (5, 5)
    assert repository.list_workflows(str(reviewer_id)) == []
    audit = repository.list_audit(str(reviewer_id))
    assert [entry["event_type"] for entry in audit] == ["reviewer_fixture_refreshed"]
