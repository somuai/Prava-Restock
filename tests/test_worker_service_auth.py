from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from merchant.models import MerchantQuote
from payments import prava_client
from payments.models import TrackedItem, User
from storage import Database, RestockRepository
from ui.api import app
from workflow import service_routes


SERVICE_TOKEN = "worker-service-token-with-more-than-32-characters"


def persisted_item(repository: RestockRepository) -> TrackedItem:
    user = User(
        user_id=uuid4(),
        display_name="Worker API user",
        prava_account_ref="prava-worker-user",
        monthly_cap="5000",
        per_item_cap="1000",
        per_transaction_cap="1000",
        created_at=datetime.now(timezone.utc),
    )
    item = TrackedItem(
        item_id=uuid4(),
        user_id=user.user_id,
        name="Worker coffee",
        track="home",
        trigger_type="predicted",
        category="grocery",
        sensitive_flag=False,
        preferred_merchant="zepto",
        merchant_sku_id="worker-coffee",
        currency="INR",
        status="active",
        typical_cadence_days=14,
        last_purchased_at=date.today() - timedelta(days=13),
        last_purchase_amount="380",
    )
    repository.upsert_user(user)
    repository.upsert_item(item)
    return item


def test_worker_service_route_owns_workflow_creation_and_suppresses_duplicate(
    tmp_path, monkeypatch
) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'service.db'}"))
    repository.create_schema()
    item = persisted_item(repository)
    monkeypatch.setattr(service_routes, "REPOSITORY", repository)
    monkeypatch.setattr(prava_client, "create_intent", lambda *_args, **_kwargs: "intent-1")
    monkeypatch.setenv("RESTOCK_WORKER_SERVICE_TOKEN", SERVICE_TOKEN)
    client = TestClient(app)
    path = f"/api/v1/service/worker/items/{item.item_id}/trigger"

    assert client.post(path).status_code == 401
    first = client.post(path, headers={"Authorization": f"Bearer {SERVICE_TOKEN}"})
    second = client.post(path, headers={"Authorization": f"Bearer {SERVICE_TOKEN}"})

    assert first.status_code == 200
    assert first.json()["status"] == "created"
    assert second.status_code == 200
    assert second.json() == {
        "status": "duplicate_suppressed",
        "item_id": str(item.item_id),
    }
    assert len(repository.list_workflows(str(item.user_id))) == 1
    assert client.get(
        "/api/v1/audit",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
    ).status_code != 200


def test_worker_service_route_rechecks_trigger_condition(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'service.db'}"))
    repository.create_schema()
    item = persisted_item(repository)
    item.last_purchased_at = date.today()
    repository.upsert_item(item)
    monkeypatch.setattr(service_routes, "REPOSITORY", repository)
    monkeypatch.setenv("RESTOCK_WORKER_SERVICE_TOKEN", SERVICE_TOKEN)

    response = TestClient(app).post(
        f"/api/v1/service/worker/items/{item.item_id}/trigger",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "tracked item is not due"}
    assert repository.list_workflows(str(item.user_id)) == []


def test_worker_scan_is_authenticated_leased_and_duplicate_safe(
    tmp_path, monkeypatch
) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'scan.db'}"))
    repository.create_schema()
    item = persisted_item(repository)
    monkeypatch.setattr(service_routes, "REPOSITORY", repository)
    monkeypatch.setattr(prava_client, "create_intent", lambda *_args, **_kwargs: "intent-1")
    monkeypatch.setenv("RESTOCK_WORKER_SERVICE_TOKEN", SERVICE_TOKEN)
    client = TestClient(app)

    assert client.post("/api/v1/service/worker/scan").status_code == 401
    first = client.post(
        "/api/v1/service/worker/scan",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
    )
    second = client.post(
        "/api/v1/service/worker/scan",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
    )

    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert first.json()["due"] == 1
    assert first.json()["created"] == 1
    assert first.json()["failed"] == 0
    assert second.status_code == 200
    assert second.json()["duplicate_suppressed"] == 1
    assert len(repository.list_workflows(str(item.user_id))) == 1


def test_worker_uses_fresh_exact_quote_for_prava_amount(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'service.db'}"))
    repository.create_schema()
    item = persisted_item(repository)
    monkeypatch.setattr(service_routes, "REPOSITORY", repository)
    monkeypatch.setenv("RESTOCK_WORKER_SERVICE_TOKEN", SERVICE_TOKEN)
    amounts = []

    class FakeProvider:
        def __call__(self, canonical_item):
            assert canonical_item.item_id == item.item_id
            return MerchantQuote(
                merchant="zepto",
                merchant_sku_id=canonical_item.merchant_sku_id,
                product_name=canonical_item.name,
                amount="415",
                currency="INR",
                stock_status="in_stock",
                quote_reference="exact-cart-quote",
                observed_at=datetime.now(timezone.utc),
                execution_mode="real",
            )

    monkeypatch.setattr(
        service_routes,
        "build_home_quote_provider",
        lambda repository: FakeProvider(),
    )
    monkeypatch.setattr(
        prava_client,
        "create_intent",
        lambda merchant, amount, description, constraints: amounts.append(amount) or "intent",
    )

    response = TestClient(app).post(
        f"/api/v1/service/worker/items/{item.item_id}/trigger",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
    )

    assert response.status_code == 200
    assert amounts == [415]
    run = repository.list_workflows(str(item.user_id))[0]
    assert str(run["proposed_amount"]) == "415.00"
    assert run["quote"]["merchant_sku_id"] == item.merchant_sku_id


def test_worker_swiggy_item_never_touches_zepto_quote_provider(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'service.db'}"))
    repository.create_schema()
    original = persisted_item(repository)
    item = TrackedItem.model_validate(
        original.model_dump() | {
            "item_id": uuid4(),
            "name": "Seeded printer paper",
            "preferred_merchant": "swiggy",
            "merchant_sku_id": "swiggy-paper-exact",
        }
    )
    repository.upsert_item(item)
    monkeypatch.setattr(service_routes, "REPOSITORY", repository)
    monkeypatch.setenv("RESTOCK_WORKER_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setattr(
        service_routes,
        "build_home_quote_provider",
        lambda repository: type(
            "ZeptoOnlyProvider",
            (),
            {
                "supports": staticmethod(lambda candidate: False),
                "__call__": lambda self, candidate: (_ for _ in ()).throw(
                    AssertionError("Swiggy item touched Zepto")
                ),
            },
        )(),
    )
    monkeypatch.setattr(prava_client, "create_intent", lambda *_args, **_kwargs: "intent")

    response = TestClient(app).post(
        f"/api/v1/service/worker/items/{item.item_id}/trigger",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
    )

    assert response.status_code == 200
    run = repository.list_workflows(str(item.user_id))[0]
    assert run["state"] == "notified"
    assert run["quote"] is None


def test_worker_service_route_fails_closed_without_secure_token(monkeypatch) -> None:
    monkeypatch.delenv("RESTOCK_WORKER_SERVICE_TOKEN", raising=False)

    response = TestClient(app).post(
        "/api/v1/service/worker/items/unknown/trigger",
        headers={"Authorization": "Bearer any-value"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "worker service authentication is not configured"}


def test_worker_quote_failure_cooldown_avoids_repeated_merchant_calls(
    tmp_path, monkeypatch
) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'service.db'}"))
    repository.create_schema()
    item = persisted_item(repository)
    run = repository.create_workflow(
        user_id=str(item.user_id),
        item_id=str(item.item_id),
        trigger_reason="predicted_depletion",
        proposed_amount="380",
        currency="INR",
        merchant="zepto",
        proposed_action=None,
        quote=None,
        modes={"prava": "sandbox", "home_payment": "real"},
        idempotency_key=f"cooldown-{uuid4().hex}",
    )
    repository.transition(
        run["run_id"],
        expected={"triggered"},
        state="failed",
        error_code="HOME_QUOTE_FAILED",
    )
    monkeypatch.setattr(service_routes, "REPOSITORY", repository)
    monkeypatch.setenv("RESTOCK_WORKER_SERVICE_TOKEN", SERVICE_TOKEN)

    response = TestClient(app).post(
        f"/api/v1/service/worker/items/{item.item_id}/trigger",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "quote_cooldown"
    assert len(repository.list_workflows(str(item.user_id))) == 1
