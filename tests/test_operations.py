from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

import pytest

from demo.seed_reset import demo_user
from storage import Database, RestockRepository
from storage.backup import (
    backup_postgres,
    backup_sqlite,
    restore_postgres,
    restore_sqlite,
    verify_sqlite,
)
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


def test_sqlite_backup_refuses_to_overwrite_source(tmp_path) -> None:
    database_path = tmp_path / "source.db"
    repository = RestockRepository(Database(f"sqlite:///{database_path}"))
    repository.create_schema()

    with pytest.raises(ValueError, match="must differ"):
        backup_sqlite(f"sqlite:///{database_path}", database_path)


def test_sqlite_restore_refuses_to_overwrite_backup(tmp_path) -> None:
    backup_path = tmp_path / "backup.db"
    repository = RestockRepository(Database(f"sqlite:///{backup_path}"))
    repository.create_schema()

    with pytest.raises(ValueError, match="must differ"):
        restore_sqlite(backup_path, f"sqlite:///{backup_path}")


def test_postgres_backup_keeps_credentials_out_of_process_arguments(tmp_path, monkeypatch) -> None:
    destination = tmp_path / "restock.dump"
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        destination.write_bytes(b"valid-dump")

    monkeypatch.setattr("storage.backup.subprocess.run", fake_run)
    backup_postgres(
        "postgresql://restock:private-password@db.example/restock",
        destination,
    )

    assert "private-password" not in " ".join(captured["command"])
    assert captured["environment"]["PGHOST"] == "db.example"
    assert captured["environment"]["PGUSER"] == "restock"
    assert captured["environment"]["PGPASSWORD"] == "private-password"
    assert captured["environment"]["PGDATABASE"] == "restock"


def test_failed_postgres_backup_removes_partial_file(tmp_path, monkeypatch) -> None:
    destination = tmp_path / "partial.dump"
    destination.write_bytes(b"partial")

    def fail_run(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["pg_dump"], stderr="client/server version mismatch")

    monkeypatch.setattr("storage.backup.subprocess.run", fail_run)
    with pytest.raises(RuntimeError, match="version mismatch"):
        backup_postgres("postgresql://restock:secret@db/restock", destination)
    assert not destination.exists()


def test_postgres_restore_rejects_empty_backup(tmp_path) -> None:
    backup_path = tmp_path / "empty.dump"
    backup_path.touch()

    with pytest.raises(ValueError, match="missing or empty"):
        restore_postgres(backup_path, "postgresql://restock:secret@db/restock")


def test_postgres_restore_uses_database_name_without_password_argument(tmp_path, monkeypatch) -> None:
    backup_path = tmp_path / "restock.dump"
    backup_path.write_bytes(b"valid-dump")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]

    monkeypatch.setattr("storage.backup.subprocess.run", fake_run)
    restore_postgres(
        backup_path,
        "postgresql://restock:private-password@db.example/restored",
    )

    assert captured["command"][-2:] == ["restored", str(backup_path)]
    assert "private-password" not in " ".join(captured["command"])
    assert captured["environment"]["PGPASSWORD"] == "private-password"


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
