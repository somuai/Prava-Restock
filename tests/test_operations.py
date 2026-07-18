from datetime import datetime, timedelta, timezone
from pathlib import Path

from demo.seed_reset import demo_user
from storage import Database, RestockRepository
from storage.backup import backup_sqlite, restore_sqlite, verify_sqlite
from storage.schema import AuditRow


def test_sqlite_backup_restore_round_trip(tmp_path) -> None:
    source_url = f"sqlite:///{tmp_path / 'source.db'}"
    repository = RestockRepository(Database(source_url))
    repository.create_schema()
    repository.upsert_user(demo_user())
    backup_path = tmp_path / "backup.db"
    digest = backup_sqlite(source_url, backup_path)
    assert len(digest) == 64
    verify_sqlite(backup_path)

    restored_url = f"sqlite:///{tmp_path / 'restored.db'}"
    assert restore_sqlite(backup_path, restored_url) == digest
    restored = RestockRepository(Database(restored_url))
    assert restored.get_user(str(demo_user().user_id))["display_name"] == demo_user().display_name


def test_retention_deletes_old_audit_but_preserves_recent(tmp_path) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'retention.db'}"))
    repository.create_schema()
    user = demo_user()
    repository.upsert_user(user)
    old = repository.audit(
        user_id=str(user.user_id),
        event_type="old",
        payload={},
        modes={"mode": "test"},
    )
    repository.audit(
        user_id=str(user.user_id),
        event_type="recent",
        payload={},
        modes={"mode": "test"},
    )
    with repository.database.session() as session:
        session.get(AuditRow, old["audit_id"]).created_at = datetime.now(timezone.utc) - timedelta(days=400)
    result = repository.enforce_retention(before=datetime.now(timezone.utc) - timedelta(days=365))
    assert result["audit_entries"] == 1
    assert [entry["event_type"] for entry in repository.list_audit(str(user.user_id))] == ["recent"]
