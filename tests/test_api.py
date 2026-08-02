import json
import os
from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient

from common import audit_store, notification_store, password_auth, session_auth
from demo.seed_reset import demo_user, load_seed_items
from merchant import zepto_checkout
from payments.models import AuditLogEntry
from storage import Database, RestockRepository
from ui import api
from scripts.validate_service_env import validate as validate_service_environment


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
    assert payload["capabilities"]["home_payment_mode"] == "disclosed_mock"
    assert payload["capabilities"]["real_money_enabled"] is False
    assert client.get("/health").json() == {"status": "healthy"}
    assert client.get("/capabilities").json()["real_money_enabled"] is False
    correlated = client.get("/health", headers={"X-Correlation-ID": "test-correlation"})
    assert correlated.headers["x-correlation-id"] == "test-correlation"
    assert client.get("/metrics").json()["http_requests_total"] >= 1


def test_whatsapp_capability_requires_send_and_webhook_credentials(monkeypatch) -> None:
    required = (
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
        "WHATSAPP_APP_SECRET",
        "WHATSAPP_VERIFY_TOKEN",
    )
    for name in required:
        monkeypatch.setenv(name, f"configured-{name.lower()}")

    assert api.runtime_modes()["whatsapp_configured"] is True

    for missing in required:
        monkeypatch.delenv(missing)
        assert api.runtime_modes()["whatsapp_configured"] is False
        monkeypatch.setenv(missing, f"configured-{missing.lower()}")

    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "   ")
    assert api.runtime_modes()["whatsapp_configured"] is False


def test_runtime_modes_require_complete_slack_and_environment_bound_prava(monkeypatch) -> None:
    slack_required = (
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
        "SLACK_SIGNING_SECRET",
        "SLACK_CHANNEL_ID",
        "RESTOCK_SLACK_SERVICE_TOKEN",
        "RESTOCK_PUBLIC_API_URL",
        "RESTOCK_PUBLIC_APP_URL",
    )
    for name in slack_required:
        monkeypatch.setenv(name, f"configured-{name.lower()}")
    assert api.runtime_modes()["slack_configured"] is True
    monkeypatch.delenv("SLACK_CHANNEL_ID")
    assert api.runtime_modes()["slack_configured"] is False

    monkeypatch.setenv("PRAVA_API_KEY", "sk_live_runtime")
    monkeypatch.setenv("PRAVA_API_URL", "https://api.prava.space")
    monkeypatch.delenv("PRAVA_PRODUCTION_ENABLED", raising=False)
    assert api.runtime_modes()["prava_mode"] == "production_disabled"
    assert api.runtime_modes()["real_money_enabled"] is False

    monkeypatch.setenv("PRAVA_PRODUCTION_ENABLED", "1")
    monkeypatch.setenv("RESTOCK_ENV", "production")
    monkeypatch.setenv("RESTOCK_DEMO_MODE", "0")
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setenv("HOME_PAYMENT_MODE", "real")
    monkeypatch.setenv("ZEPTO_REAL_PAYMENT_ENABLED", "1")
    monkeypatch.setenv("ZEPTO_CART_PREPARATION_ENABLED", "1")
    monkeypatch.setenv("ZEPTO_DEVICE_ID", "device-reference")
    monkeypatch.setattr(api, "mcp_remote_runtime_ready", lambda: True)
    monkeypatch.setattr(api, "_zepto_oauth_status", lambda: "verified_recently")
    monkeypatch.delattr(zepto_checkout, "real_payment_runtime_ready", raising=False)
    assert api.runtime_modes()["real_money_enabled"] is False
    assert api.runtime_modes()["home_checkout_runtime_configured"] is False
    monkeypatch.setattr(
        zepto_checkout, "real_payment_runtime_ready", lambda: True, raising=False
    )
    assert api.runtime_modes()["prava_mode"] == "production_configured"
    assert api.runtime_modes()["real_money_enabled"] is True
    assert api.runtime_modes()["home_checkout_runtime_configured"] is True


def test_production_readiness_fails_closed_without_real_checkout_runtime(monkeypatch) -> None:
    monkeypatch.setenv("RESTOCK_ENV", "production")
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setenv("HOME_PAYMENT_MODE", "real")
    monkeypatch.setenv("ZEPTO_REAL_PAYMENT_ENABLED", "1")
    monkeypatch.delattr(zepto_checkout, "real_payment_runtime_ready", raising=False)
    monkeypatch.setattr(api, "validate_service_environment", lambda service, env: [])
    monkeypatch.setattr(api, "mcp_remote_runtime_ready", lambda: True)
    monkeypatch.setattr(api, "_zepto_oauth_status", lambda: "verified_recently")

    assert api.production_configuration_issues() == [
        "ZEPTO_REAL_CHECKOUT_RUNTIME_UNAVAILABLE"
    ]
    assert client.get("/ready").status_code == 503


def test_capabilities_fail_closed_for_invalid_checkout_executor(monkeypatch) -> None:
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setenv("HOME_PAYMENT_MODE", "real")
    monkeypatch.setenv("ZEPTO_REAL_PAYMENT_ENABLED", "1")
    monkeypatch.setenv("ZEPTO_PAYMENT_EXECUTOR_PATH", "/missing/restock-executor")

    response = client.get("/capabilities")

    assert response.status_code == 200
    assert response.json()["real_money_enabled"] is False
    assert response.json()["home_checkout_runtime_configured"] is False
    assert response.json()["home_checkout_runtime_status"] == "invalid_configuration"


def test_real_money_requires_cart_device_mcp_and_oauth_prerequisites(monkeypatch) -> None:
    monkeypatch.setenv("RESTOCK_ENV", "production")
    monkeypatch.setenv("RESTOCK_DEMO_MODE", "0")
    monkeypatch.setenv("PRAVA_API_KEY", "sk_live_runtime")
    monkeypatch.setenv("PRAVA_API_URL", "https://api.prava.space")
    monkeypatch.setenv("PRAVA_PRODUCTION_ENABLED", "1")
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setenv("HOME_PAYMENT_MODE", "real")
    monkeypatch.setenv("ZEPTO_REAL_PAYMENT_ENABLED", "1")
    monkeypatch.setattr(zepto_checkout, "real_payment_runtime_ready", lambda: True)
    monkeypatch.setattr(api, "mcp_remote_runtime_ready", lambda: True)
    monkeypatch.setattr(api, "_zepto_oauth_status", lambda: "configured_unverified")

    monkeypatch.delenv("ZEPTO_CART_PREPARATION_ENABLED", raising=False)
    monkeypatch.delenv("ZEPTO_DEVICE_ID", raising=False)
    assert api.runtime_modes()["real_money_enabled"] is False

    monkeypatch.setenv("ZEPTO_CART_PREPARATION_ENABLED", "1")
    assert api.runtime_modes()["real_money_enabled"] is False

    monkeypatch.setenv("ZEPTO_DEVICE_ID", "device-reference")
    assert api.runtime_modes()["real_money_enabled"] is False

    monkeypatch.setattr(api, "_zepto_oauth_status", lambda: "verified_recently")
    assert api.runtime_modes()["real_money_enabled"] is True

    monkeypatch.setattr(api, "mcp_remote_runtime_ready", lambda: False)
    assert api.runtime_modes()["real_money_enabled"] is False


def test_configured_unverified_oauth_allows_readiness_but_not_money(monkeypatch) -> None:
    monkeypatch.setenv("RESTOCK_ENV", "production")
    monkeypatch.setenv("HOME_PAYMENT_MODE", "real")
    monkeypatch.setenv("ZEPTO_REAL_PAYMENT_ENABLED", "1")
    monkeypatch.setattr(api, "validate_service_environment", lambda service, env: [])
    monkeypatch.setattr(api, "_merchant_runtime_status", lambda: (True, "configured"))
    monkeypatch.setattr(api, "mcp_remote_runtime_ready", lambda: True)
    monkeypatch.setattr(api, "_zepto_oauth_status", lambda: "configured_unverified")

    assert api.production_configuration_issues() == []
    assert api.runtime_modes()["real_money_enabled"] is False


def test_zepto_oauth_capability_reports_presence_without_verification(
    tmp_path, monkeypatch
) -> None:
    cache = tmp_path / "mcp-auth"
    monkeypatch.setenv("MCP_REMOTE_CONFIG_DIR", str(cache))
    monkeypatch.setattr(api, "mcp_authorization_verified_recently", lambda: False)
    assert api.runtime_modes()["zepto_oauth_status"] == "unknown"

    version = cache / "mcp-remote-0.1.37"
    version.mkdir(parents=True)
    prefix = "9b36d85502a1fef918a5db7d2b8d830b"
    (version / f"{prefix}_tokens.json").write_text("not inspected")
    assert api.runtime_modes()["zepto_oauth_status"] == "unknown"
    (version / f"{prefix}_client_info.json").write_text("not inspected")
    (version / f"{prefix}_code_verifier.txt").write_text("not inspected")
    assert api.runtime_modes()["zepto_oauth_status"] == "configured_unverified"

    monkeypatch.setattr(api, "mcp_authorization_verified_recently", lambda: True)
    assert api.runtime_modes()["zepto_oauth_status"] == "verified_recently"


def test_audit_log_endpoint_reads_sqlite_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RESTOCK_ENV", "development")
    audit_path = tmp_path / "audit.db"
    monkeypatch.setattr(api, "AUDIT_LOG_PATH", audit_path)
    entry = AuditLogEntry(
        log_id=UUID("00000000-0000-0000-0000-000000000088"),
        user_id=UUID(api.DEFAULT_USER_ID),
        event_type="transaction_completed",
        payload={"amount": "380.00"},
        timestamp=datetime.now(timezone.utc),
    )
    expected = audit_store.append(entry, audit_path)
    assert client.get("/audit-log", headers=AUTH_HEADERS).json() == [expected]


def test_pending_notifications_endpoint_returns_only_pending_store(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("RESTOCK_ENV", "development")
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


def test_production_disables_unscoped_legacy_stores(monkeypatch) -> None:
    """An authenticated production user cannot read cross-user compatibility data."""

    secret = "production-session-secret-used-only-for-this-test"
    user_id = "00000000-0000-0000-0000-000000000099"
    token = session_auth.mint(user_id, secret)
    monkeypatch.setenv("RESTOCK_ENV", "production")
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", secret)

    def compatibility_store_must_not_be_read(*_args, **_kwargs):
        raise AssertionError("production touched an unscoped compatibility store")

    monkeypatch.setattr(api, "_read_audit_log", compatibility_store_must_not_be_read)
    monkeypatch.setattr(
        notification_store, "get_pending", compatibility_store_must_not_be_read
    )
    headers = {"Authorization": f"Bearer {token}"}

    audit_response = client.get("/audit-log", headers=headers)
    notifications_response = client.get("/notifications/pending", headers=headers)

    assert audit_response.status_code == 404
    assert notifications_response.status_code == 404
    assert audit_response.json() == {"detail": "not found"}
    assert notifications_response.json() == {"detail": "not found"}


def test_behavioral_endpoints_require_authentication() -> None:
    assert client.get("/audit-log").status_code == 401
    assert client.get("/api/v1/workflows").status_code == 401


def test_readiness_rejects_unsafe_production_configuration(monkeypatch) -> None:
    monkeypatch.setenv("RESTOCK_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///logs/restock.db")
    monkeypatch.delenv("RESTOCK_SESSION_SECRET", raising=False)
    monkeypatch.setenv("RESTOCK_DEMO_MODE", "1")

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "production configuration incomplete"}
    assert api.production_configuration_issues() == validate_service_environment(
        "api", os.environ
    )


def test_production_configuration_accepts_postgres_secret_and_no_demo(monkeypatch) -> None:
    monkeypatch.setenv("RESTOCK_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://restock:secret@db/restock")
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", "a-secure-random-session-secret-over-32-characters")
    monkeypatch.setenv("RESTOCK_SOLO_USER_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv(
        "RESTOCK_SOLO_PASSWORD_HASH",
        password_auth.hash_password("not-a-real-password", salt=b"api-test-salt-01"),
    )
    monkeypatch.setenv("RESTOCK_DEMO_MODE", "0")
    monkeypatch.setenv("PRAVA_API_KEY", "sk_test_placeholder")
    monkeypatch.setenv("PRAVA_API_URL", "https://sandbox.api.prava.space")
    monkeypatch.setenv(
        "RESTOCK_SLACK_SERVICE_TOKEN",
        "slack-service-placeholder-over-32-characters",
    )
    monkeypatch.setenv(
        "RESTOCK_WORKER_SERVICE_TOKEN",
        "worker-service-placeholder-over-32-characters",
    )

    assert api.production_configuration_issues() == []


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

    profile = client.get("/api/v1/me", headers=AUTH_HEADERS)
    assert profile.status_code == 200
    assert profile.json()["reviewer_fixture"] is False
    assert len(client.get("/api/v1/items", headers=AUTH_HEADERS).json()) == 1
    response = client.post(
        f"/api/v1/workflows/{run['run_id']}/actions",
        headers=AUTH_HEADERS,
        json={"action": "skip"},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "skipped"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_live_zepto_onboarding_persists_only_provider_resolved_product(
    tmp_path, monkeypatch
) -> None:
    from merchant.models import MerchantCatalogProduct

    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'catalog.db'}"))
    repository.create_schema()
    repository.upsert_user(demo_user())
    monkeypatch.setattr(api, "REPOSITORY", repository)
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setattr(api, "_user_zepto_client", lambda **_: object())
    monkeypatch.setattr(
        api.zepto_checkout,
        "list_saved_address_summaries",
        lambda *, client: [
            api.zepto_checkout.MerchantAddressSummary(
                reference="address-1", label="Home"
            )
        ],
    )
    monkeypatch.setattr(
        api.zepto_checkout,
        "search_catalog",
        lambda query, *, address_ref, client: [
            MerchantCatalogProduct(
                merchant="zepto",
                merchant_sku_id="real-coffee-variant",
                store_product_id="real-coffee-store-product",
                name="Current Zepto Coffee 500 g",
                amount="389",
                currency="INR",
                available_quantity=2,
                stock_status="in_stock",
                execution_mode="real",
            )
        ],
    )

    addresses = client.get(
        "/api/v1/integrations/zepto/addresses", headers=AUTH_HEADERS
    )
    assert addresses.status_code == 200
    assert addresses.json() == {
        "addresses": [{"reference": "address-1", "label": "Home"}]
    }

    response = client.post(
        "/api/v1/items/home",
        headers=AUTH_HEADERS,
        json={
            "query": "coffee",
            "merchant_sku_id": "real-coffee-variant",
            "merchant_address_ref": "address-1",
            "category": "grocery",
            "quantity": 1,
            "price_threshold": "400",
        },
    )
    assert response.status_code == 201
    item = response.json()
    assert item["merchant_sku_id"] == "real-coffee-variant"
    assert item["merchant_address_ref"] == "address-1"
    assert item["last_observed_price"] == "389"
    assert item["last_purchased_at"] is None


def test_production_rejects_estimated_starter_items(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'starter.db'}"))
    repository.create_schema()
    repository.upsert_user(demo_user())
    monkeypatch.setattr(api, "REPOSITORY", repository)
    monkeypatch.setenv("RESTOCK_ENV", "production")
    secret = "production-starter-test-secret-over-32-characters"
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", secret)
    headers = {
        "Authorization": f"Bearer {session_auth.mint(api.DEFAULT_USER_ID, secret)}"
    }

    response = client.post(
        "/api/v1/onboarding/starter-items",
        headers=headers,
        json={"template_ids": ["coffee"]},
    )

    assert response.status_code == 409
    assert "live Zepto product" in response.json()["detail"]
