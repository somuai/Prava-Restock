from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
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
    monkeypatch.setenv("RESTOCK_WAITLIST_EMAIL_MODE", "disabled")
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


def test_waitlist_only_enqueues_welcome_for_a_genuinely_new_lead(
    tmp_path, monkeypatch
) -> None:
    configured_repository(tmp_path, monkeypatch)
    monkeypatch.setattr(
        api,
        "send_waitlist_welcome",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("public join must not perform outbound email")
        ),
        raising=False,
    )
    client = TestClient(api.app)

    first_response = client.post("/api/v1/waitlist", json=payload())
    duplicate_response = client.post(
        "/api/v1/waitlist", json=payload("PRIYA@example.com")
    )
    trapped = payload("bot@example.com")
    trapped["company"] = "Spam Corp"
    trapped_response = client.post("/api/v1/waitlist", json=trapped)

    assert first_response.status_code == 202
    assert duplicate_response.status_code == 202
    assert trapped_response.status_code == 202
    with api.REPOSITORY.database.session() as session:
        deliveries = session.execute(
            text(
                "SELECT status, attempts, last_error, sent_at "
                "FROM waitlist_welcome_emails"
            )
        ).all()
    assert len(deliveries) == 1
    assert deliveries[0].status == "pending"
    assert deliveries[0].attempts == 0
    assert deliveries[0].last_error is None
    assert deliveries[0].sent_at is None


def test_welcome_worker_persists_failure_without_logging_sensitive_values(
    tmp_path, monkeypatch, caplog
) -> None:
    repository = configured_repository(tmp_path, monkeypatch)
    secret = "resend-secret-that-must-not-appear"
    response = TestClient(api.app).post("/api/v1/waitlist", json=payload())

    waitlist_email = __import__(
        "common.waitlist_email", fromlist=["retry_waitlist_welcome_emails"]
    )

    def fail_delivery(email: str, display_name: str | None = None) -> bool:
        raise RuntimeError(f"provider failed for {email} using {secret}")

    with caplog.at_level(logging.ERROR):
        summary = waitlist_email.retry_waitlist_welcome_emails(
            repository, max_attempts=3, limit=10, sender=fail_delivery
        )

    assert response.status_code == 202
    assert response.json() == SUCCESS
    assert summary == {
        "eligible": 1,
        "sent": 0,
        "failed": 1,
        "disabled": 0,
        "lost_lease": 0,
    }
    with repository.database.session() as session:
        assert (
            session.scalar(select(func.count()).select_from(WaitlistLeadRow))
            == 1
        )
        delivery = session.execute(
            text(
                "SELECT status, attempts, last_error, sent_at "
                "FROM waitlist_welcome_emails"
            )
        ).one()
        assert delivery.status == "failed"
        assert delivery.attempts == 1
        assert delivery.last_error == "delivery_failed"
        assert delivery.sent_at is None
    assert "priya@example.com" not in caplog.text
    assert secret not in caplog.text


def test_failed_welcome_email_is_retried_to_sent_with_bounded_attempts(
    tmp_path, monkeypatch
) -> None:
    repository = configured_repository(tmp_path, monkeypatch)
    response = TestClient(api.app).post("/api/v1/waitlist", json=payload())
    assert response.status_code == 202

    waitlist_email = __import__(
        "common.waitlist_email", fromlist=["retry_waitlist_welcome_emails"]
    )
    sent: list[str] = []

    def succeeds(email: str, display_name: str | None = None) -> bool:
        sent.append(email)
        return True

    first = waitlist_email.retry_waitlist_welcome_emails(
        repository,
        max_attempts=3,
        limit=10,
        sender=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("temporary outage")
        ),
    )
    summary = waitlist_email.retry_waitlist_welcome_emails(
        repository, max_attempts=3, limit=10, sender=succeeds
    )

    assert first == {
        "eligible": 1,
        "sent": 0,
        "failed": 1,
        "disabled": 0,
        "lost_lease": 0,
    }
    assert summary == {
        "eligible": 1,
        "sent": 1,
        "failed": 0,
        "disabled": 0,
        "lost_lease": 0,
    }
    assert sent == ["priya@example.com"]
    with repository.database.session() as session:
        delivery = session.execute(
            text(
                "SELECT status, attempts, last_error, sent_at "
                "FROM waitlist_welcome_emails"
            )
        ).one()
        assert delivery.status == "sent"
        assert delivery.attempts == 2
        assert delivery.last_error is None
        assert delivery.sent_at is not None

    # Sent rows and exhausted failed rows are never selected again.
    assert waitlist_email.retry_waitlist_welcome_emails(
        repository, max_attempts=2, limit=10, sender=succeeds
    ) == {
        "eligible": 0,
        "sent": 0,
        "failed": 0,
        "disabled": 0,
        "lost_lease": 0,
    }


def test_failed_welcome_retries_stop_at_configured_attempt_limit(
    tmp_path, monkeypatch
) -> None:
    repository = configured_repository(tmp_path, monkeypatch)
    waitlist_email = __import__(
        "common.waitlist_email", fromlist=["retry_waitlist_welcome_emails"]
    )
    delivery_calls = 0

    def fails(*_args, **_kwargs) -> bool:
        nonlocal delivery_calls
        delivery_calls += 1
        raise RuntimeError("provider unavailable")

    assert TestClient(api.app).post(
        "/api/v1/waitlist", json=payload()
    ).status_code == 202

    first_retry = waitlist_email.retry_waitlist_welcome_emails(
        repository, max_attempts=2, limit=10, sender=fails
    )
    second_retry = waitlist_email.retry_waitlist_welcome_emails(
        repository, max_attempts=2, limit=10, sender=fails
    )
    exhausted_retry = waitlist_email.retry_waitlist_welcome_emails(
        repository, max_attempts=2, limit=10, sender=fails
    )

    assert first_retry == {
        "eligible": 1,
        "sent": 0,
        "failed": 1,
        "disabled": 0,
        "lost_lease": 0,
    }
    assert second_retry == {
        "eligible": 1,
        "sent": 0,
        "failed": 1,
        "disabled": 0,
        "lost_lease": 0,
    }
    assert exhausted_retry == {
        "eligible": 0,
        "sent": 0,
        "failed": 0,
        "disabled": 0,
        "lost_lease": 0,
    }
    assert delivery_calls == 2
    with repository.database.session() as session:
        assert session.execute(
            text("SELECT attempts FROM waitlist_welcome_emails")
        ).scalar_one() == 2


def test_concurrent_welcome_workers_claim_and_send_exactly_once(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'concurrent-email.db'}"
    first = RestockRepository(Database(database_url))
    second = RestockRepository(Database(database_url))
    first.create_schema()
    first.join_waitlist(
        email_normalized="one@example.com",
        display_name="One",
        privacy_notice_version="v1",
        pilot_email_consent_at=datetime.now(timezone.utc),
    )
    waitlist_email = __import__(
        "common.waitlist_email", fromlist=["retry_waitlist_welcome_emails"]
    )
    barrier = threading.Barrier(2)
    send_lock = threading.Lock()
    sends: list[str] = []

    def sender(email: str, _display_name: str | None = None) -> bool:
        with send_lock:
            sends.append(email)
        return True

    def run(repository: RestockRepository) -> dict[str, int]:
        barrier.wait()
        return waitlist_email.retry_waitlist_welcome_emails(
            repository,
            max_attempts=3,
            limit=10,
            lease_seconds=60,
            sender=sender,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        summaries = list(executor.map(run, (first, second)))

    assert sum(summary["eligible"] for summary in summaries) == 1
    assert sum(summary["sent"] for summary in summaries) == 1
    assert sends == ["one@example.com"]
    with first.database.session() as session:
        row = session.execute(
            text(
                "SELECT status, attempts, claim_owner, lease_expires_at "
                "FROM waitlist_welcome_emails"
            )
        ).one()
        assert row.status == "sent"
        assert row.attempts == 1
        assert row.claim_owner is None
        assert row.lease_expires_at is None


def test_stale_welcome_lease_is_recovered_and_only_new_owner_can_finalize(
    tmp_path,
) -> None:
    repository = RestockRepository(
        Database(f"sqlite:///{tmp_path / 'stale-email.db'}")
    )
    repository.create_schema()
    repository.join_waitlist(
        email_normalized="stale@example.com",
        display_name=None,
        privacy_notice_version="v1",
        pilot_email_consent_at=datetime.now(timezone.utc),
    )
    first_claim = repository.claim_waitlist_welcome_deliveries(
        owner_id="worker-one",
        max_attempts=3,
        limit=1,
        lease_seconds=60,
    )
    assert len(first_claim) == 1
    delivery_id = first_claim[0]["delivery_id"]
    with repository.database.session() as session:
        session.execute(
            text(
                "UPDATE waitlist_welcome_emails "
                "SET lease_expires_at = :expired WHERE delivery_id = :delivery_id"
            ),
            {
                "expired": datetime.now(timezone.utc) - timedelta(seconds=1),
                "delivery_id": delivery_id,
            },
        )

    second_claim = repository.claim_waitlist_welcome_deliveries(
        owner_id="worker-two",
        max_attempts=3,
        limit=1,
        lease_seconds=60,
    )

    assert len(second_claim) == 1
    assert second_claim[0]["attempts"] == 2
    assert repository.finalize_waitlist_welcome_delivery(
        delivery_id=delivery_id,
        owner_id="worker-one",
        status="sent",
    ) is False
    assert repository.finalize_waitlist_welcome_delivery(
        delivery_id=delivery_id,
        owner_id="worker-two",
        status="sent",
    ) is True


def test_sender_decline_requeues_without_consuming_reserved_attempt(
    tmp_path,
) -> None:
    repository = RestockRepository(
        Database(f"sqlite:///{tmp_path / 'declined-email.db'}")
    )
    repository.create_schema()
    repository.join_waitlist(
        email_normalized="declined@example.com",
        privacy_notice_version="v1",
        pilot_email_consent_at=datetime.now(timezone.utc),
    )
    waitlist_email = __import__(
        "common.waitlist_email", fromlist=["retry_waitlist_welcome_emails"]
    )

    summary = waitlist_email.retry_waitlist_welcome_emails(
        repository,
        max_attempts=3,
        limit=1,
        sender=lambda *_args, **_kwargs: False,
    )

    assert summary == {
        "eligible": 1,
        "sent": 0,
        "failed": 0,
        "disabled": 1,
        "lost_lease": 0,
    }
    with repository.database.session() as session:
        row = session.execute(
            text(
                "SELECT status, attempts, claim_owner, lease_expires_at "
                "FROM waitlist_welcome_emails"
            )
        ).one()
        assert row.status == "pending"
        assert row.attempts == 0
        assert row.claim_owner is None
        assert row.lease_expires_at is None


@pytest.mark.parametrize("sender", [lambda *_: True, lambda *_: (_ for _ in ()).throw(RuntimeError())])
def test_lost_lease_is_explicit_and_never_reported_as_sent(
    tmp_path,
    sender,
) -> None:
    repository = RestockRepository(
        Database(f"sqlite:///{tmp_path / 'lost-lease.db'}")
    )
    repository.create_schema()
    repository.join_waitlist(
        email_normalized="lease@example.com",
        privacy_notice_version="v1",
        pilot_email_consent_at=datetime.now(timezone.utc),
    )
    delivery = repository.claim_waitlist_welcome_deliveries(
        owner_id="actual-owner",
        max_attempts=3,
        limit=1,
        lease_seconds=60,
    )[0]
    waitlist_email = __import__(
        "common.waitlist_email", fromlist=["attempt_waitlist_welcome_email"]
    )

    with pytest.raises(waitlist_email.WaitlistEmailLeaseLost):
        waitlist_email.attempt_waitlist_welcome_email(
            repository,
            delivery,
            owner_id="wrong-owner",
            sender=sender,
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
