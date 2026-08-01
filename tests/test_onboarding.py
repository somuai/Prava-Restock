from fastapi.testclient import TestClient

from common import session_auth
from common.google_identity import GoogleIdentityClaims
from storage import Database, RestockRepository
from ui import api


SESSION_SECRET = "onboarding-placeholder-session-secret-that-is-long-enough"


def configured_client(tmp_path, monkeypatch) -> tuple[TestClient, RestockRepository, str]:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'onboarding.db'}"))
    repository.create_schema()
    monkeypatch.setattr(api, "REPOSITORY", repository)
    monkeypatch.setenv("RESTOCK_ENV", "development")
    monkeypatch.setenv("RESTOCK_AUTH_MODE", "google")
    monkeypatch.setenv("RESTOCK_SESSION_SECRET", SESSION_SECRET)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "web-client.apps.googleusercontent.com")
    monkeypatch.setattr(
        api,
        "verify_google_identity",
        lambda _: GoogleIdentityClaims(
            subject="onboarding-subject",
            email="starter@example.com",
            display_name="Starter User",
        ),
    )
    response = TestClient(api.app).post(
        "/api/v1/auth/google", json={"credential": "verified-token"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    user_id = session_auth.verify(token, SESSION_SECRET)
    return TestClient(api.app), repository, token


def test_google_user_can_add_selected_starter_pantry_items(tmp_path, monkeypatch) -> None:
    client, repository, token = configured_client(tmp_path, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/onboarding/starter-items",
        headers=headers,
        json={"template_ids": ["coffee", "toothpaste"]},
    )

    assert response.status_code == 201
    assert response.json()["created"] == 2
    items = repository.list_items(response.json()["user_id"])
    assert {item["merchant_sku_id"] for item in items} == {
        "zepto-arabica-coffee-500g",
        "zepto-toothpaste-twin-pack",
    }
    assert all(item["track"] == "home" for item in items)
    assert all(item["user_id"] == response.json()["user_id"] for item in items)


def test_starter_onboarding_is_idempotent_per_user(tmp_path, monkeypatch) -> None:
    client, repository, token = configured_client(tmp_path, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"template_ids": ["coffee", "milk"]}

    first = client.post("/api/v1/onboarding/starter-items", headers=headers, json=payload)
    second = client.post("/api/v1/onboarding/starter-items", headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["created"] == 0
    assert second.json()["existing"] == 2
    assert len(repository.list_items(second.json()["user_id"])) == 2


def test_starter_onboarding_rejects_unknown_or_empty_selection(tmp_path, monkeypatch) -> None:
    client, _, token = configured_client(tmp_path, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}

    unknown = client.post(
        "/api/v1/onboarding/starter-items",
        headers=headers,
        json={"template_ids": ["not-a-template"]},
    )
    empty = client.post(
        "/api/v1/onboarding/starter-items", headers=headers, json={"template_ids": []}
    )

    assert unknown.status_code == 422
    assert empty.status_code == 422
