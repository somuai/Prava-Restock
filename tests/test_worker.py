from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from payments.models import TrackedItem, User
from storage import Database, RestockRepository
from workflow import worker


class RecordingService:
    def __init__(self, repository: RestockRepository) -> None:
        self.repository = repository
        self.created: list[tuple[User, TrackedItem]] = []

    def begin(self, user: User, item: TrackedItem) -> None:
        self.created.append((user, item))


def build_user() -> User:
    return User(
        user_id=uuid4(),
        display_name="Production user",
        prava_account_ref="prava-production-user",
        monthly_cap="5000",
        per_item_cap="1000",
        per_transaction_cap="1000",
        created_at=datetime.now(timezone.utc),
    )


def build_item(user: User, *, status: str = "active") -> TrackedItem:
    return TrackedItem(
        item_id=uuid4(),
        user_id=user.user_id,
        name="Persisted coffee",
        track="home",
        trigger_type="predicted",
        category="grocery",
        sensitive_flag=False,
        preferred_merchant="zepto",
        merchant_sku_id="persisted-coffee",
        currency="INR",
        status=status,
        typical_cadence_days=14,
        last_purchased_at=date.today() - timedelta(days=13),
        last_purchase_amount="380",
    )


def test_production_worker_scans_only_active_persisted_items(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'worker.db'}"))
    repository.create_schema()
    user = build_user()
    active = build_item(user)
    paused = build_item(user, status="paused")
    repository.upsert_user(user)
    repository.upsert_item(active)
    repository.upsert_item(paused)
    monkeypatch.setenv("RESTOCK_ENV", "production")
    requested = []
    monkeypatch.setattr(
        worker,
        "request_trigger",
        lambda item_id: requested.append(item_id) or {"status": "created"},
    )

    assert worker.triggered_item_ids(repository) == [str(active.item_id)]
    assert worker.run_production_tick(repository) == 1
    assert requested == [str(active.item_id)]


def test_production_worker_refuses_process_local_workflow_begin(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'worker.db'}"))
    repository.create_schema()
    monkeypatch.setenv("RESTOCK_ENV", "production")

    with pytest.raises(RuntimeError, match="through the API service"):
        worker.run_tick(RecordingService(repository))


def test_development_worker_keeps_deterministic_seed_harness(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'worker.db'}"))
    repository.create_schema()
    service = RecordingService(repository)
    monkeypatch.setenv("RESTOCK_ENV", "development")

    created = worker.run_tick(service)

    assert created >= 1
    assert all(item.name != "Persisted coffee" for _, item in service.created)
