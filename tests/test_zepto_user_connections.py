"""User-owned Zepto OAuth and consented history onboarding tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from common import session_auth
from demo.seed_reset import demo_user
from merchant.zepto_oauth import ZeptoOAuthToken
from storage import Database, RestockRepository
from ui import api


SESSION_SECRET = "a-high-entropy-placeholder-at-least-32-chars"


def configured_client(tmp_path, monkeypatch) -> tuple[TestClient, RestockRepository, dict[str, str]]:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'connections.db'}"))
    repository.create_schema()
    user = demo_user()
    repository.upsert_user(user)
    monkeypatch.setattr(api, "REPOSITORY", repository)
    monkeypatch.setenv("RESTOCK_ENV", "development")
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", SESSION_SECRET)
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setenv("RESTOCK_PUBLIC_API_URL", "https://restock.example.test")
    monkeypatch.setenv("RESTOCK_PUBLIC_APP_URL", "https://restock.example.test/app")
    monkeypatch.setenv("ZEPTO_OAUTH_CLIENT_ID", "restock-test-client")
    monkeypatch.setenv(
        "RESTOCK_MERCHANT_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii")
    )
    return (
        TestClient(api.app),
        repository,
        {"Authorization": f"Bearer {session_auth.mint(str(user.user_id), SESSION_SECRET)}"},
    )


def test_zepto_connection_is_user_owned_and_starts_pkce(tmp_path, monkeypatch) -> None:
    client, repository, headers = configured_client(tmp_path, monkeypatch)

    initial = client.get("/api/v1/integrations/zepto/connection", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["status"] == "not_connected"
    assert initial.json()["oauth_configured"] is True

    started = client.post("/api/v1/integrations/zepto/connect", headers=headers)
    assert started.status_code == 200
    query = parse_qs(urlsplit(started.json()["authorization_url"]).query)
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["https://restock.example.test/api/v1/integrations/zepto/callback"]
    assert "code_verifier" not in query

    connection = repository.get_merchant_connection(
        user_id=str(demo_user().user_id), provider="zepto"
    )
    assert connection is not None
    assert connection["status"] == "pending"
    assert connection["encrypted_code_verifier"]
    assert "restock-test-client" not in str(connection)


def test_callback_exchanges_once_and_never_exposes_tokens(tmp_path, monkeypatch) -> None:
    client, repository, headers = configured_client(tmp_path, monkeypatch)
    started = client.post("/api/v1/integrations/zepto/connect", headers=headers)
    state = parse_qs(urlsplit(started.json()["authorization_url"]).query)["state"][0]
    token = ZeptoOAuthToken(
        access_token="access-token-should-never-be-json",
        refresh_token="refresh-token-should-never-be-json",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scope="tools:read tools:write",
    )
    monkeypatch.setattr(api, "exchange_authorization_code", lambda **_: token)

    callback = client.get(
        f"/api/v1/integrations/zepto/callback?state={state}&code=one-time-code",
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "https://restock.example.test/app?zepto=connected"
    assert "access-token" not in callback.text
    assert "refresh-token" not in callback.text

    summary = client.get("/api/v1/integrations/zepto/connection", headers=headers)
    assert summary.json()["status"] == "connected"
    assert "encrypted_tokens" not in summary.json()
    connection = repository.get_merchant_connection(
        user_id=str(demo_user().user_id), provider="zepto"
    )
    assert connection is not None
    assert "access-token" not in str(connection["encrypted_tokens"])
    assert connection["authorization_state_hash"] is None
    assert connection["encrypted_code_verifier"] is None


def test_unconnected_user_cannot_read_shared_zepto_addresses(tmp_path, monkeypatch) -> None:
    client, _, headers = configured_client(tmp_path, monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(
        api.zepto_checkout,
        "list_saved_address_summaries",
        lambda **_: calls.append("unexpected") or [],
    )

    response = client.get("/api/v1/integrations/zepto/addresses", headers=headers)
    assert response.status_code == 409
    assert "connect your Zepto account" in response.json()["detail"]
    assert calls == []


def test_history_returns_suggestions_without_creating_items(tmp_path, monkeypatch) -> None:
    client, repository, headers = configured_client(tmp_path, monkeypatch)
    started = client.post("/api/v1/integrations/zepto/connect", headers=headers)
    state = parse_qs(urlsplit(started.json()["authorization_url"]).query)["state"][0]
    token = ZeptoOAuthToken(
        access_token="access", refresh_token="refresh",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1), scope="tools:read"
    )
    monkeypatch.setattr(api, "exchange_authorization_code", lambda **_: token)
    client.get(
        f"/api/v1/integrations/zepto/callback?state={state}&code=code",
        follow_redirects=False,
    )

    class FakeClient:
        def get_past_order_items(self):
            return {
                "items": [
                    {"productVariantId": "coffee-500", "name": "Coffee 500 g"},
                    {"productVariantId": "coffee-500", "name": "Coffee 500 g"},
                    {"productVariantId": "milk-1l", "name": "Milk 1 L"},
                ]
            }

    monkeypatch.setattr(api, "_user_zepto_client", lambda **_: FakeClient())
    response = client.get("/api/v1/integrations/zepto/history/suggestions", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "suggestions": [
            {"merchant_sku_id": "coffee-500", "name": "Coffee 500 g", "search_query": "Coffee 500 g"},
            {"merchant_sku_id": "milk-1l", "name": "Milk 1 L", "search_query": "Milk 1 L"},
        ]
    }
    assert repository.list_items(str(demo_user().user_id)) == []


def test_zepto_callback_rejects_expired_or_replayed_state(tmp_path, monkeypatch) -> None:
    client, _, headers = configured_client(tmp_path, monkeypatch)
    started = client.post("/api/v1/integrations/zepto/connect", headers=headers)
    state = parse_qs(urlsplit(started.json()["authorization_url"]).query)["state"][0]
    token = ZeptoOAuthToken(
        access_token="access", refresh_token="refresh",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1), scope="tools:read"
    )
    monkeypatch.setattr(api, "exchange_authorization_code", lambda **_: token)
    first = client.get(
        f"/api/v1/integrations/zepto/callback?state={state}&code=code",
        follow_redirects=False,
    )
    second = client.get(
        f"/api/v1/integrations/zepto/callback?state={state}&code=code",
        follow_redirects=False,
    )
    assert first.headers["location"].endswith("zepto=connected")
    assert second.headers["location"].endswith("zepto=expired")
