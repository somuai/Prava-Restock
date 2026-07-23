"""Concurrency tests for the SQLite-backed notification and audit stores.

The migration from JSON-file to SQLite was specifically motivated by race
conditions under concurrent writes.  These tests confirm that WAL mode and
the busy-timeout configuration prevent data loss when two writers collide.
"""

import threading
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from common import audit_store, notification_store
from payments.models import AuditLogEntry


@pytest.fixture(autouse=True)
def isolated_stores(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "test_concurrent.db"
    monkeypatch.setattr(
        notification_store, "NOTIFICATION_STORE_PATH", db_path
    )
    monkeypatch.setattr(audit_store, "AUDIT_STORE_PATH", db_path)
    notification_store.reset()
    audit_store.reset()


def _notification_payload(suffix: str = "") -> dict:
    return {
        "item_id": f"concurrent-item-{suffix}",
        "message": f"Concurrent test notification {suffix}",
        "actions": ["approve", "skip"],
    }


def _audit_entry() -> AuditLogEntry:
    return AuditLogEntry(
        log_id=uuid4(),
        user_id=uuid4(),
        event_type="notification_sent",
        payload={"test": True},
        timestamp=datetime.now(timezone.utc),
    )


def test_concurrent_notification_creates_no_data_loss() -> None:
    """Two near-simultaneous creates must both persist — no silent drops."""
    results: list[dict] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2, timeout=5)

    def worker(suffix: str) -> None:
        try:
            barrier.wait()
            result = notification_store.create(_notification_payload(suffix))
            results.append(result)
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("A",)),
        threading.Thread(target=worker, args=("B",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"concurrent creates raised: {errors}"
    assert len(results) == 2
    pending = notification_store.get_pending()
    assert len(pending) == 2
    ids = {n["notification_id"] for n in pending}
    assert ids == {r["notification_id"] for r in results}


def test_concurrent_audit_appends_no_data_loss() -> None:
    """Two near-simultaneous audit appends must both persist."""
    results: list[dict] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2, timeout=5)

    def worker() -> None:
        try:
            barrier.wait()
            result = audit_store.append(_audit_entry())
            results.append(result)
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker),
        threading.Thread(target=worker),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"concurrent appends raised: {errors}"
    assert len(results) == 2
    all_entries = audit_store.get_all()
    assert len(all_entries) == 2
    ids = {e["log_id"] for e in all_entries}
    assert ids == {r["log_id"] for r in results}


def test_concurrent_update_status_is_serialized() -> None:
    """Only one of two simultaneous status updates on the same notification succeeds."""
    created = notification_store.create(_notification_payload("race"))
    nid = created["notification_id"]
    outcomes: list[str] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2, timeout=5)

    def worker(status: str) -> None:
        try:
            barrier.wait()
            notification_store.update_status(nid, status)
            outcomes.append(status)
        except (ValueError, KeyError):
            outcomes.append("blocked")
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("approved",)),
        threading.Thread(target=worker, args=("skipped",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"unexpected errors: {errors}"
    assert len(outcomes) == 2
    # Exactly one succeeds, one gets blocked (terminal status error)
    assert "blocked" in outcomes
    terminal = [o for o in outcomes if o != "blocked"]
    assert len(terminal) == 1
    assert terminal[0] in {"approved", "skipped"}
    assert notification_store.get_pending() == []
