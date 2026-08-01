from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from storage import Database, RestockRepository
from storage.schema import (
    AuthIdentityRow,
    TransactionRow,
    UserRow,
    WaitlistLeadRow,
)
from ui import api


SUCCESS = {"status": "joined", "message": "You're on the list."}


def configured_repository(tmp_path, monkeypatch) -> RestockRepository:
    repository = RestockRepository(
        Database(f"sqlite:///{tmp_path / 'waitlist.db'}")
    )
    repository.create_schema()
    monkeypatch.setattr(api, "REPOSITORY", repository)
    monkeypatch.setenv("RESTOCK_ENV", "development")
    monkeypatch.setenv("RESTOCK_WAITLIST_MIN_SUBMIT_SECONDS", "1")
    monkeypatch.setenv("RESTOCK_WAITLIST_RATE_LIMIT_PER_10_MINUTES", "12")
    monkeypatch.setenv(
        "RESTOCK_WAITLIST_PRIVACY_NOTICE_VERSION", "waitlist-2026-07-30"
    )
    api._WAITLIST_REQUESTS.clear()
    return repository


def payload(email: str = "Priya@example.com") -> dict:
    return {
        "email": email,
        "client_started_at": (
            datetime.now(timezone.utc) - timedelta(seconds=3)
        ).isoformat(),
        "company": "",
        "display_name": "Priya",
        "track_interest": "home",
        "first_use_category": "coffee",
        "preferred_channel": "email",
        "research_opt_in": True,
        "landing_variant": "nothing-buys-itself",
        "entry_demo_track": "home",
        "utm_source": "devfolio",
        "utm_medium": "profile",
        "utm_campaign": "controlled-pilot",
        "referrer_host": "example.com",
    }


def test_waitlist_join_normalizes_and_stores_lead_only(
    tmp_path, monkeypatch
) -> None:
    repository = configured_repository(tmp_path, monkeypatch)

    response = TestClient(api.app).post("/api/v1/waitlist", json=payload())

    assert response.status_code == 202
    assert response.json() == SUCCESS
    with repository.database.session() as session:
        lead = session.scalar(select(WaitlistLeadRow))
        assert lead is not None
        assert lead.email_normalized == "priya@example.com"
        assert lead.display_name == "Priya"
        assert lead.track_interest == "home"
        assert lead.first_use_category == "coffee"
        assert lead.research_opt_in is True
        assert lead.privacy_notice_version == "waitlist-2026-07-30"
        assert lead.pilot_email_consent_at is not None
        assert session.scalar(select(func.count()).select_from(UserRow)) == 0
        assert (
            session.scalar(select(func.count()).select_from(AuthIdentityRow))
            == 0
        )
        assert (
            session.scalar(select(func.count()).select_from(TransactionRow))
            == 0
        )


def test_duplicate_returns_identical_success_without_mutating_original(
    tmp_path, monkeypatch
) -> None:
    repository = configured_repository(tmp_path, monkeypatch)
    client = TestClient(api.app)
    first = payload()
    duplicate = payload("  PRIYA@EXAMPLE.COM ")
    duplicate["display_name"] = "Someone else"
    duplicate["research_opt_in"] = False

    first_response = client.post("/api/v1/waitlist", json=first)
    duplicate_response = client.post("/api/v1/waitlist", json=duplicate)

    assert first_response.status_code == duplicate_response.status_code == 202
    assert first_response.json() == duplicate_response.json() == SUCCESS
    with repository.database.session() as session:
        assert (
            session.scalar(select(func.count()).select_from(WaitlistLeadRow))
            == 1
        )
        lead = session.scalar(select(WaitlistLeadRow))
        assert lead is not None
        assert lead.display_name == "Priya"
        assert lead.research_opt_in is True


def test_honeypot_and_too_fast_forms_are_quietly_discarded(
    tmp_path, monkeypatch
) -> None:
    repository = configured_repository(tmp_path, monkeypatch)
    client = TestClient(api.app)
    trapped = payload("bot@example.com")
    trapped["company"] = "Spam Corp"
    fast = payload("fast@example.com")
    fast["client_started_at"] = datetime.now(timezone.utc).isoformat()

    trapped_response = client.post("/api/v1/waitlist", json=trapped)
    fast_response = client.post("/api/v1/waitlist", json=fast)

    assert trapped_response.status_code == fast_response.status_code == 202
    assert trapped_response.json() == fast_response.json() == SUCCESS
    with repository.database.session() as session:
        assert (
            session.scalar(select(func.count()).select_from(WaitlistLeadRow))
            == 0
        )


def test_waitlist_has_dedicated_non_persistent_rate_limit(
    tmp_path, monkeypatch
) -> None:
    configured_repository(tmp_path, monkeypatch)
    monkeypatch.setenv("RESTOCK_WAITLIST_RATE_LIMIT_PER_10_MINUTES", "1")
    client = TestClient(api.app)

    assert (
        client.post("/api/v1/waitlist", json=payload()).status_code == 202
    )
    response = client.post(
        "/api/v1/waitlist", json=payload("second@example.com")
    )

    assert response.status_code == 429
    assert response.json() == {"detail": "please try again later"}


def test_waitlist_rejects_invalid_and_payment_shaped_payloads(
    tmp_path, monkeypatch
) -> None:
    configured_repository(tmp_path, monkeypatch)
    client = TestClient(api.app)
    invalid = payload("not-an-email")
    payment_shaped = payload()
    payment_shaped["card_number"] = "4111111111111111"

    assert (
        client.post("/api/v1/waitlist", json=invalid).status_code == 422
    )
    assert (
        client.post("/api/v1/waitlist", json=payment_shaped).status_code
        == 422
    )


def test_waitlist_storage_failure_is_generic(monkeypatch) -> None:
    class OfflineRepository:
        def join_waitlist(self, **_: object) -> bool:
            raise SQLAlchemyError("database host must not leak")

    monkeypatch.setattr(api, "REPOSITORY", OfflineRepository())
    monkeypatch.setenv("RESTOCK_WAITLIST_MIN_SUBMIT_SECONDS", "1")
    api._WAITLIST_REQUESTS.clear()

    response = TestClient(api.app).post(
        "/api/v1/waitlist", json=payload()
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "waitlist unavailable"}
    assert "database host must not leak" not in response.text


def test_concurrent_duplicate_joins_keep_exactly_one_lead(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'concurrent-waitlist.db'}"
    first = RestockRepository(Database(database_url))
    second = RestockRepository(Database(database_url))
    first.create_schema()
    consented_at = datetime.now(timezone.utc)

    def join(repository: RestockRepository) -> bool:
        return repository.join_waitlist(
            email_normalized="same@example.com",
            display_name="Same Person",
            privacy_notice_version="waitlist-2026-07-30",
            pilot_email_consent_at=consented_at,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(join, (first, second)))

    assert sorted(results) == [False, True]
    with first.database.session() as session:
        assert (
            session.scalar(select(func.count()).select_from(WaitlistLeadRow))
            == 1
        )


def test_public_root_serves_built_waitlist_when_enabled(
    tmp_path, monkeypatch
) -> None:
    waitlist_dist = tmp_path / "waitlist-dist"
    waitlist_dist.mkdir()
    (waitlist_dist / "index.html").write_text(
        "<!doctype html><title>Restock waitlist</title>",
        encoding="utf-8",
    )
    monkeypatch.setattr(api, "WAITLIST_DIST", waitlist_dist)
    monkeypatch.setenv("RESTOCK_SERVE_WAITLIST", "1")

    response = TestClient(api.app).get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Restock waitlist" in response.text
