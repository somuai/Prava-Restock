import json

from fastapi.testclient import TestClient

from common import notification_store
from ui import api


client = TestClient(api.app)


def test_hello_world_and_health_endpoints(monkeypatch) -> None:
    monkeypatch.delenv("PRAVA_API_KEY", raising=False)
    monkeypatch.setenv("HOME_MERCHANT_MODE", "disclosed_mock")
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "service": "Restock",
        "status": "ok",
        "mode": "mixed",
        "capabilities": {
            "prava_mode": "sandbox_unconfigured",
            "home_merchant_mode": "disclosed_mock",
            "teams_billing_mode": "disclosed_mock",
            "real_money_enabled": False,
        },
    }
    assert client.get("/health").json() == {"status": "healthy"}
    assert client.get("/capabilities").json()["real_money_enabled"] is False


def test_audit_log_endpoint_reads_json_file(tmp_path, monkeypatch) -> None:
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps([{"event_type": "transaction_completed"}]))
    monkeypatch.setattr(api, "AUDIT_LOG_PATH", audit_path)
    assert client.get("/audit-log").json() == [
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

    assert client.get("/notifications/pending").json() == [created]
