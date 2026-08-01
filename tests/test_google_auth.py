from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from common import google_identity, password_auth, session_auth
from common.google_identity import GoogleIdentityClaims, GoogleIdentityError
from demo.seed_reset import demo_user
from scripts.validate_service_env import validate
from storage import Database, RestockRepository
from storage.schema import AuthIdentityRow, UserRow
from ui import api


PLACEHOLDER_SESSION_SIGNING_VALUE = (
    "google-auth-placeholder-secret-that-is-at-least-32-characters"
)


def configured_repository(tmp_path, monkeypatch) -> RestockRepository:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'google-auth.db'}"))
    repository.create_schema()
    monkeypatch.setattr(api, "REPOSITORY", repository)
    monkeypatch.setenv("RESTOCK_ENV", "development")
    monkeypatch.setenv("RESTOCK_AUTH_MODE", "google")
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", PLACEHOLDER_SESSION_SIGNING_VALUE)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "web-client.apps.googleusercontent.com")
    api._AUTH_REQUESTS.clear()
    return repository


def claims(
    *,
    subject: str = "google-subject-1",
    email: str = "person@example.com",
    display_name: str = "Priya User",
) -> GoogleIdentityClaims:
    return GoogleIdentityClaims(
        subject=subject,
        email=email,
        display_name=display_name,
    )


def token_user(response) -> str:
    assert response.status_code == 200
    return session_auth.verify(
        response.json()["access_token"], PLACEHOLDER_SESSION_SIGNING_VALUE
    )


def test_google_login_provisions_new_subject_exactly_once(tmp_path, monkeypatch) -> None:
    repository = configured_repository(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "verify_google_identity", lambda _: claims())
    client = TestClient(api.app)

    first_user = token_user(
        client.post("/api/v1/auth/google", json={"credential": "first"})
    )
    second_user = token_user(
        client.post("/api/v1/auth/google", json={"credential": "second"})
    )

    assert first_user == second_user
    with repository.database.session() as session:
        assert session.scalar(select(func.count()).select_from(UserRow)) == 1
        assert session.scalar(select(func.count()).select_from(AuthIdentityRow)) == 1
        user = session.get(UserRow, first_user)
        assert user is not None
        assert user.prava_account_ref == "unlinked"
        assert Decimal(str(user.monthly_cap)) == Decimal("5000.00")
        assert Decimal(str(user.per_item_cap)) == Decimal("1000.00")

    token = client.post(
        "/api/v1/auth/google", json={"credential": "third"}
    ).json()["access_token"]
    current_user = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert current_user.status_code == 200
    assert current_user.json()["auth_providers"] == ["google"]


def test_same_subject_survives_changed_email_and_updates_metadata(
    tmp_path, monkeypatch
) -> None:
    repository = configured_repository(tmp_path, monkeypatch)
    current = {"value": claims()}
    monkeypatch.setattr(api, "verify_google_identity", lambda _: current["value"])
    client = TestClient(api.app)
    user_id = token_user(
        client.post("/api/v1/auth/google", json={"credential": "original"})
    )
    current["value"] = claims(email="new-address@example.com")

    repeated_user = token_user(
        client.post("/api/v1/auth/google", json={"credential": "changed"})
    )

    assert repeated_user == user_id
    identity = repository.get_auth_identity(
        provider="google", subject="google-subject-1"
    )
    assert identity is not None
    assert identity["email"] == "new-address@example.com"


def test_same_email_with_different_subject_is_not_auto_linked(
    tmp_path, monkeypatch
) -> None:
    repository = configured_repository(tmp_path, monkeypatch)
    current = {"value": claims(subject="subject-a")}
    monkeypatch.setattr(api, "verify_google_identity", lambda _: current["value"])
    client = TestClient(api.app)
    first_user = token_user(
        client.post("/api/v1/auth/google", json={"credential": "subject-a"})
    )
    current["value"] = claims(subject="subject-b")

    second_user = token_user(
        client.post("/api/v1/auth/google", json={"credential": "subject-b"})
    )

    assert second_user != first_user
    with repository.database.session() as session:
        assert session.scalar(select(func.count()).select_from(UserRow)) == 2
        assert session.scalar(select(func.count()).select_from(AuthIdentityRow)) == 2


def test_authenticated_owner_can_explicitly_link_google_identity(
    tmp_path, monkeypatch
) -> None:
    repository = configured_repository(tmp_path, monkeypatch)
    repository.upsert_user(demo_user())
    monkeypatch.setenv("RESTOCK_AUTH_MODE", "hybrid")
    monkeypatch.setattr(api, "verify_google_identity", lambda _: claims())
    owner_id = str(demo_user().user_id)
    owner_token = session_auth.mint(owner_id, PLACEHOLDER_SESSION_SIGNING_VALUE)

    linked = TestClient(api.app).post(
        "/api/v1/auth/google/link",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"credential": "verified-google-token"},
    )

    assert linked.status_code == 200
    assert linked.json() == {"status": "linked", "provider": "google"}
    identity = repository.get_auth_identity(
        provider="google", subject="google-subject-1"
    )
    assert identity is not None
    assert identity["user_id"] == owner_id
    # A subsequent Google login resolves to the deliberately linked owner.
    signed_in = TestClient(api.app).post(
        "/api/v1/auth/google", json={"credential": "same-verified-token"}
    )
    assert token_user(signed_in) == owner_id


def test_google_verifier_rejects_unverified_or_incomplete_claims(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "web-client.apps.googleusercontent.com")
    monkeypatch.setattr(
        google_identity.id_token,
        "verify_oauth2_token",
        lambda *_args, **_kwargs: {
            "sub": "subject",
            "email": "person@example.com",
            "email_verified": False,
            "name": "Person",
        },
    )

    with pytest.raises(GoogleIdentityError, match="verified claims"):
        google_identity.verify_google_identity("credential")

    monkeypatch.setattr(
        google_identity.id_token,
        "verify_oauth2_token",
        lambda *_args, **_kwargs: {
            "sub": "subject",
            "email": "person@example.com",
            "email_verified": True,
        },
    )
    verified = google_identity.verify_google_identity("credential")
    assert verified.display_name == "person"


def test_auth_mode_gates_password_and_google_methods(tmp_path, monkeypatch) -> None:
    configured_repository(tmp_path, monkeypatch)
    client = TestClient(api.app)
    monkeypatch.setenv("RESTOCK_AUTH_MODE", "solo")
    assert client.post(
        "/api/v1/auth/google", json={"credential": "credential"}
    ).status_code == 404

    monkeypatch.setenv("RESTOCK_AUTH_MODE", "google")
    assert client.post(
        "/api/v1/auth/login", json={"password": "password"}
    ).status_code == 404

    monkeypatch.setenv("RESTOCK_AUTH_MODE", "hybrid")
    encoded = password_auth.hash_password(
        "password", salt=b"google-auth-test"
    )
    user = demo_user()
    api.REPOSITORY.upsert_user(user)
    monkeypatch.setenv("RESTOCK_SOLO_PASSWORD_HASH", encoded)
    monkeypatch.setenv("RESTOCK_SOLO_USER_ID", str(user.user_id))
    response = client.post(
        "/api/v1/auth/login", json={"password": "password"}
    )
    assert response.status_code == 200


def test_google_cookie_is_secure_httponly_and_supports_logout(
    tmp_path, monkeypatch
) -> None:
    configured_repository(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "verify_google_identity", lambda _: claims())
    client = TestClient(api.app)

    signed_in = client.post(
        "/api/v1/auth/google", json={"credential": "credential"}
    )

    cookie = signed_in.headers["set-cookie"]
    assert "restock_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    user_id = token_user(signed_in)
    cookie_token = signed_in.json()["access_token"]
    current_user = client.get(
        "/api/v1/me",
        headers={"Cookie": f"restock_session={cookie_token}"},
    )
    assert current_user.status_code == 200
    assert current_user.json()["user_id"] == user_id

    signed_out = client.post(
        "/api/v1/auth/logout", headers={"Origin": "http://testserver"}
    )
    assert signed_out.status_code == 200
    assert signed_out.json() == {"status": "signed_out"}
    deletion = signed_out.headers["set-cookie"]
    assert "restock_session=" in deletion
    assert "Max-Age=0" in deletion
    assert "HttpOnly" in deletion
    assert "Secure" in deletion
    assert "SameSite=lax" in deletion


def test_google_auth_cors_csp_and_conditional_environment_contract(
    monkeypatch,
) -> None:
    response = TestClient(api.app).options(
        "/api/v1/auth/google",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers["access-control-allow-credentials"] == "true"
    health = TestClient(api.app).get("/health")
    assert "https://accounts.google.com/gsi/client" in health.headers[
        "content-security-policy"
    ]
    assert health.headers["cross-origin-opener-policy"] == "same-origin-allow-popups"
    assert health.headers["referrer-policy"] == "strict-origin-when-cross-origin"

    base = {
        "DATABASE_URL": "postgresql://restock:secret@postgres/restock",
        "PRAVA_API_KEY": "sk_test_placeholder",
        "PRAVA_API_URL": "https://sandbox.api.prava.space",
        "RESTOCK_ENV": "production",
        "RESTOCK_DEMO_MODE": "0",
        "RESTOCK_SESSION_SECRET": PLACEHOLDER_SESSION_SIGNING_VALUE,
        "RESTOCK_SLACK_SERVICE_TOKEN": "slack-service-placeholder-over-32-characters",
        "RESTOCK_WORKER_SERVICE_TOKEN": "worker-service-placeholder-over-32-characters",
    }
    google_only = {
        **base,
        "RESTOCK_AUTH_MODE": "google",
        "GOOGLE_CLIENT_ID": "web-client.apps.googleusercontent.com",
    }
    assert validate("api", google_only) == []
    assert validate("api", {**google_only, "GOOGLE_CLIENT_ID": ""}) == [
        "GOOGLE_CLIENT_ID"
    ]
    assert validate("api", {**google_only, "GOOGLE_CLIENT_ID": "not-a-web-client"}) == [
        "GOOGLE_CLIENT_ID_INVALID"
    ]


def test_capabilities_publish_only_the_enabled_public_google_client_id(
    monkeypatch,
) -> None:
    client = TestClient(api.app)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "web-client.apps.googleusercontent.com")
    monkeypatch.setenv("RESTOCK_AUTH_MODE", "hybrid")

    hybrid = client.get("/capabilities").json()
    assert hybrid["google_auth_configured"] is True
    assert hybrid["google_client_id"] == "web-client.apps.googleusercontent.com"

    monkeypatch.setenv("RESTOCK_AUTH_MODE", "solo")
    solo = client.get("/capabilities").json()
    assert solo["google_auth_configured"] is True
    assert solo["google_client_id"] == ""
