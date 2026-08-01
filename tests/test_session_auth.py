import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import hashlib

from common import password_auth
from common import session_auth
from demo.seed_reset import demo_user
from ui import api
from storage import Database, RestockRepository


SECRET = "a-production-shape-secret-that-is-long-enough"


def test_signed_session_round_trip() -> None:
    token = session_auth.mint("user-1", SECRET)
    assert session_auth.verify(token, SECRET) == "user-1"


def test_tampered_and_expired_sessions_are_rejected() -> None:
    token = session_auth.mint("user-1", SECRET)
    with pytest.raises(ValueError, match="invalid or expired"):
        session_auth.verify(token + "x", SECRET)
    expired = session_auth.mint("user-1", SECRET, ttl_seconds=-1)
    with pytest.raises(ValueError, match="invalid or expired"):
        session_auth.verify(expired, SECRET)


def test_scrypt_password_hash_round_trip_and_wrong_password() -> None:
    encoded = password_auth.hash_password("correct horse", salt=b"0123456789abcdef")

    assert encoded.startswith("scrypt$16384$8$1$")
    assert password_auth.verify_password("correct horse", encoded) is True
    assert password_auth.verify_password("wrong horse", encoded) is False
    assert password_auth.verify_password("correct horse", "malformed") is False


def test_solo_login_mints_existing_signed_session(monkeypatch) -> None:
    user_id = "00000000-0000-0000-0000-000000000001"
    encoded = password_auth.hash_password("login-password", salt=b"1234567890abcdef")
    monkeypatch.setenv("RESTOCK_SOLO_PASSWORD_HASH", encoded)
    monkeypatch.setenv("RESTOCK_SOLO_USER_ID", user_id)
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", SECRET)
    monkeypatch.setenv("RESTOCK_SESSION_TTL_SECONDS", "900")
    monkeypatch.setattr(
        api,
        "get_repository",
        lambda: SimpleNamespace(get_user=lambda configured: {"user_id": configured}),
    )
    api._AUTH_REQUESTS.clear()

    response = TestClient(api.app).post(
        "/api/v1/auth/login", json={"password": "login-password"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert session_auth.verify(body["access_token"], SECRET) == user_id


def test_temporary_reviewer_login_uses_isolated_user_and_expiring_session(
    monkeypatch,
) -> None:
    reviewer_id = "00000000-0000-0000-0000-000000000099"
    encoded = password_auth.hash_password(
        "reviewer-password", salt=b"reviewer-salt-123"
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=20)
    monkeypatch.setenv("RESTOCK_REVIEWER_PASSWORD_HASH", encoded)
    monkeypatch.setenv("RESTOCK_REVIEWER_USER_ID", reviewer_id)
    monkeypatch.setenv("RESTOCK_REVIEWER_EXPIRES_AT", expires_at.isoformat())
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", SECRET)
    monkeypatch.setenv("RESTOCK_SESSION_TTL_SECONDS", "3600")
    monkeypatch.delenv("RESTOCK_SOLO_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("RESTOCK_SOLO_USER_ID", raising=False)
    monkeypatch.setattr(
        api,
        "get_repository",
        lambda: SimpleNamespace(get_user=lambda configured: {"user_id": configured}),
    )
    api._AUTH_REQUESTS.clear()

    response = TestClient(api.app).post(
        "/api/v1/auth/login", json={"password": "reviewer-password"}
    )

    assert response.status_code == 200
    body = response.json()
    assert 60 <= body["expires_in"] <= 20 * 60
    assert session_auth.verify(body["access_token"], SECRET) == reviewer_id


def test_expired_reviewer_password_is_rejected_generically(monkeypatch) -> None:
    encoded = password_auth.hash_password(
        "reviewer-password", salt=b"reviewer-salt-456"
    )
    monkeypatch.setenv("RESTOCK_REVIEWER_PASSWORD_HASH", encoded)
    monkeypatch.setenv(
        "RESTOCK_REVIEWER_USER_ID", "00000000-0000-0000-0000-000000000099"
    )
    monkeypatch.setenv(
        "RESTOCK_REVIEWER_EXPIRES_AT",
        (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    )
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", SECRET)
    monkeypatch.delenv("RESTOCK_SOLO_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("RESTOCK_SOLO_USER_ID", raising=False)
    monkeypatch.setattr(
        api,
        "get_repository",
        lambda: SimpleNamespace(get_user=lambda configured: {"user_id": configured}),
    )
    api._AUTH_REQUESTS.clear()

    response = TestClient(api.app).post(
        "/api/v1/auth/login", json={"password": "reviewer-password"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}


def test_cookie_authenticated_unsafe_requests_require_trusted_origin(monkeypatch) -> None:
    monkeypatch.setenv(
        "RESTOCK_ALLOWED_ORIGINS",
        "https://app.restock.example,http://localhost:5173",
    )
    token = session_auth.mint("user-1", SECRET)

    missing_client = TestClient(api.app)
    missing_client.cookies.set(api.SESSION_COOKIE_NAME, token)
    missing = missing_client.post("/api/v1/auth/logout")
    cross_site_client = TestClient(api.app)
    cross_site_client.cookies.set(api.SESSION_COOKIE_NAME, token)
    cross_site = cross_site_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://attacker.example"},
    )
    allowed_client = TestClient(api.app)
    allowed_client.cookies.set(api.SESSION_COOKIE_NAME, token)
    allowed = allowed_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://app.restock.example"},
    )
    same_origin_client = TestClient(api.app)
    same_origin_client.cookies.set(api.SESSION_COOKIE_NAME, token)
    same_origin = same_origin_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver"},
    )

    assert missing.status_code == 403
    assert missing.json() == {"detail": "untrusted request origin"}
    assert cross_site.status_code == 403
    assert cross_site.json() == {"detail": "untrusted request origin"}
    assert allowed.status_code == 200
    assert same_origin.status_code == 200


def test_origin_check_does_not_block_safe_or_bearer_authenticated_requests(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", SECRET)
    token = session_auth.mint("user-1", SECRET)
    cross_site = {"Origin": "https://attacker.example"}

    safe_client = TestClient(api.app)
    safe_client.cookies.set(api.SESSION_COOKIE_NAME, token)
    safe = safe_client.get("/health", headers=cross_site)
    bearer_client = TestClient(api.app)
    bearer_client.cookies.set(api.SESSION_COOKIE_NAME, token)
    bearer = bearer_client.post(
        "/api/v1/auth/logout",
        headers={**cross_site, "Authorization": f"Bearer {token}"},
    )

    assert safe.status_code == 200
    assert bearer.status_code == 200


def test_production_cookie_origin_does_not_trust_spoofed_host(monkeypatch) -> None:
    monkeypatch.setenv("RESTOCK_ENV", "production")
    monkeypatch.setenv("RESTOCK_ALLOWED_ORIGINS", "https://app.restock.example")
    token = session_auth.mint("user-1", SECRET)
    client = TestClient(api.app)
    client.cookies.set(api.SESSION_COOKIE_NAME, token)

    response = client.post(
        "/api/v1/auth/logout",
        headers={
            "Host": "attacker.example",
            "Origin": "http://attacker.example",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "untrusted request origin"}


def test_malformed_bearer_never_falls_back_to_cookie_or_bypasses_origin(
    tmp_path, monkeypatch
) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'csrf.db'}"))
    repository.create_schema()
    user = demo_user()
    repository.upsert_user(user)
    user_id = str(user.user_id)
    baseline_tenant_ids = {
        tenant["tenant_id"] for tenant in repository.list_tenants(user_id)
    }
    token = session_auth.mint(user_id, SECRET)
    monkeypatch.setattr(api, "REPOSITORY", repository)
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", SECRET)
    monkeypatch.setenv("RESTOCK_ALLOWED_ORIGINS", "https://app.restock.example")

    cross_site = TestClient(api.app)
    cross_site.cookies.set(api.SESSION_COOKIE_NAME, token)
    blocked = cross_site.post(
        "/api/v1/tenants",
        headers={
            "Origin": "https://attacker.example",
            "Authorization": f"bearer {token}",
        },
        json={"name": "Must not exist", "kind": "household"},
    )
    assert blocked.status_code == 403

    trusted_origin = TestClient(api.app)
    trusted_origin.cookies.set(api.SESSION_COOKIE_NAME, token)
    rejected = trusted_origin.post(
        "/api/v1/tenants",
        headers={
            "Origin": "https://app.restock.example",
            "Authorization": f"bearer {token}",
        },
        json={"name": "Still must not exist", "kind": "household"},
    )
    assert rejected.status_code == 401
    assert rejected.json() == {"detail": "invalid API token"}
    assert {
        tenant["tenant_id"] for tenant in repository.list_tenants(user_id)
    } == baseline_tenant_ids

    invalid_bearer = TestClient(api.app)
    invalid_bearer.cookies.set(api.SESSION_COOKIE_NAME, token)
    invalid_blocked = invalid_bearer.post(
        "/api/v1/tenants",
        headers={
            "Origin": "https://attacker.example",
            "Authorization": "Bearer invalid-session-token",
        },
        json={"name": "Invalid token must not exist", "kind": "household"},
    )
    assert invalid_blocked.status_code == 403

    invalid_trusted = invalid_bearer.post(
        "/api/v1/tenants",
        headers={
            "Origin": "https://app.restock.example",
            "Authorization": "Bearer invalid-session-token",
        },
        json={"name": "Invalid token still must not exist", "kind": "household"},
    )
    assert invalid_trusted.status_code == 401
    assert invalid_trusted.json() == {"detail": "invalid or expired session"}
    assert {
        tenant["tenant_id"] for tenant in repository.list_tenants(user_id)
    } == baseline_tenant_ids

    bearer_client = TestClient(api.app)
    created = bearer_client.post(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "My household", "kind": "household"},
    )
    assert created.status_code == 201
    assert created.json()["name"] == "My household"


def test_solo_login_failure_is_generic_and_does_not_echo_password(monkeypatch, caplog) -> None:
    encoded = password_auth.hash_password("expected-password", salt=b"2345678901abcdef")
    monkeypatch.setenv("RESTOCK_SOLO_PASSWORD_HASH", encoded)
    monkeypatch.setenv("RESTOCK_SOLO_USER_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", SECRET)
    caplog.set_level("INFO", logger="restock.api")
    api._AUTH_REQUESTS.clear()

    response = TestClient(api.app).post(
        "/api/v1/auth/login", json={"password": "never-echo-this-password"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}
    assert "never-echo-this-password" not in response.text
    assert "never-echo-this-password" not in caplog.text


def test_solo_login_missing_configuration_is_generic(monkeypatch) -> None:
    for name in (
        "RESTOCK_SOLO_PASSWORD_HASH",
        "RESTOCK_SOLO_USER_ID",
        "RESTOCK_SESSION_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    api._AUTH_REQUESTS.clear()

    response = TestClient(api.app).post(
        "/api/v1/auth/login", json={"password": "irrelevant"}
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "authentication unavailable"}


def test_solo_login_requires_configured_owner_to_exist(monkeypatch) -> None:
    user_id = "00000000-0000-0000-0000-000000000001"
    encoded = password_auth.hash_password("expected-password", salt=b"4567890123abcdef")
    monkeypatch.setenv("RESTOCK_SOLO_PASSWORD_HASH", encoded)
    monkeypatch.setenv("RESTOCK_SOLO_USER_ID", user_id)
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", SECRET)
    monkeypatch.setattr(
        api, "get_repository", lambda: SimpleNamespace(get_user=lambda _: None)
    )
    api._AUTH_REQUESTS.clear()

    response = TestClient(api.app).post(
        "/api/v1/auth/login", json={"password": "expected-password"}
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "authentication unavailable"}


def test_solo_login_is_rate_limited_by_source(monkeypatch) -> None:
    encoded = password_auth.hash_password("expected-password", salt=b"3456789012abcdef")
    monkeypatch.setenv("RESTOCK_SOLO_PASSWORD_HASH", encoded)
    monkeypatch.setenv("RESTOCK_SOLO_USER_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", SECRET)
    monkeypatch.setenv("RESTOCK_AUTH_RATE_LIMIT_PER_MINUTE", "1")
    api._AUTH_REQUESTS.clear()
    client = TestClient(api.app)

    assert client.post("/api/v1/auth/login", json={"password": "wrong"}).status_code == 401
    response = client.post("/api/v1/auth/login", json={"password": "wrong"})

    assert response.status_code == 429
    assert response.json() == {"detail": "too many login attempts"}


def test_login_throttle_survives_restart_and_is_shared_by_instances(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'auth-throttle.db'}"
    first = RestockRepository(Database(database_url))
    first.create_schema()
    source_hash = hashlib.sha256(b"stable-test-source").hexdigest()
    now = datetime.now(timezone.utc)

    assert first.consume_login_attempt(
        source_hash=source_hash, limit=1, now=now
    ) is True

    restarted = RestockRepository(Database(database_url))
    assert restarted.consume_login_attempt(
        source_hash=source_hash, limit=1, now=now + timedelta(seconds=1)
    ) is False
    assert restarted.consume_login_attempt(
        source_hash=source_hash, limit=1, now=now + timedelta(seconds=61)
    ) is True


def test_production_login_fails_closed_without_postgres(monkeypatch, tmp_path) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'unsafe.db'}"))
    repository.create_schema()
    encoded = password_auth.hash_password("expected-password", salt=b"5678901234abcdef")
    monkeypatch.setenv("RESTOCK_ENV", "production")
    monkeypatch.setenv("RESTOCK_SOLO_PASSWORD_HASH", encoded)
    monkeypatch.setenv("RESTOCK_SOLO_USER_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", SECRET)
    monkeypatch.setattr(api, "get_repository", lambda: repository)

    response = TestClient(api.app).post(
        "/api/v1/auth/login", json={"password": "expected-password"}
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "authentication unavailable"}
