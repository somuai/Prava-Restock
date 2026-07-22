import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import hashlib

from common import password_auth
from common import session_auth
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
