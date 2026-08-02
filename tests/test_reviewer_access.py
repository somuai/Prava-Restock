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
