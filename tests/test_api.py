import json

from fastapi.testclient import TestClient

from common import notification_store
from demo.seed_reset import demo_user, load_seed_items
from storage import Database, RestockRepository
from ui import api


client = TestClient(api.app)
AUTH_HEADERS = {"Authorization": "Bearer restock-local-demo-token"}


def test_hello_world_and_health_endpoints(monkeypatch) -> None:
    monkeypatch.delenv("PRAVA_API_KEY", raising=False)
    monkeypatch.setenv("HOME_MERCHANT_MODE", "disclosed_mock")
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "Restock"
    assert payload["mode"] == "mixed"
    assert payload["capabilities"]["prava_mode"] == "sandbox_unconfigured"
    assert payload["capabilities"]["home_merchant_mode"] == "disclosed_mock"
    assert payload["capabilities"]["real_money_enabled"] is False
    assert client.get("/health").json() == {"status": "healthy"}
    assert client.get("/capabilities").json()["real_money_enabled"] is False


def test_audit_log_endpoint_reads_json_file(tmp_path, monkeypatch) -> None:
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps([{"event_type": "transaction_completed"}]))
    monkeypatch.setattr(api, "AUDIT_LOG_PATH", audit_path)
    assert client.get("/audit-log", headers=AUTH_HEADERS).json() == [
        {"event_type": "transaction_completed"}
    ]


def test_pending_notifications_endpoint_returns_only_pending_store(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        notification_store, "NOTIFICATION_STORE_PATH", tmp_path / "notifications.json"
    )
    notification_store.reset()
    created = notification_store.create(
        {
            "item_id": "coffee-500g",
            "message": "Coffee will run out soon.",
            "actions": ["approve", "adjust", "skip"],
        }
    )

    assert client.get("/notifications/pending", headers=AUTH_HEADERS).json() == [created]


def test_behavioral_endpoints_require_authentication() -> None:
    assert client.get("/audit-log").status_code == 401
    assert client.get("/api/v1/workflows").status_code == 401


def test_authenticated_v1_endpoints_and_action(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'api.db'}"))
    repository.create_schema()
    user = demo_user()
    item = load_seed_items()[0]
    repository.upsert_user(user)
    repository.upsert_item(item)
    run = repository.create_workflow(
        user_id=str(user.user_id),
        item_id=str(item.item_id),
        trigger_reason="predicted_depletion",
        proposed_amount=item.last_purchase_amount,
        currency=item.currency,
        merchant="zepto",
        proposed_action=None,
        quote=None,
        modes={"prava": "sandbox", "home_merchant": "disclosed_mock"},
        idempotency_key="api-test-run",
    )
    repository.transition(
        run["run_id"], expected={"triggered"}, state="intent_created", prava_intent_ref="intent"
    )
    repository.create_notification(
        run_id=run["run_id"],
        user_id=str(user.user_id),
        message="Coffee is due.",
        actions=["approve", "adjust", "skip"],
    )
    repository.transition(run["run_id"], expected={"intent_created"}, state="notified")
    monkeypatch.setattr(api, "REPOSITORY", repository)

    assert client.get("/api/v1/me", headers=AUTH_HEADERS).status_code == 200
    assert len(client.get("/api/v1/items", headers=AUTH_HEADERS).json()) == 1
    response = client.post(
        f"/api/v1/workflows/{run['run_id']}/actions",
        headers=AUTH_HEADERS,
        json={"action": "skip"},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "skipped"
    assert response.headers["x-content-type-options"] == "nosniff"
