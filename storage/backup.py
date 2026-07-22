"""Operator-controlled backup/restore helpers for SQLite and Postgres."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import subprocess

from storage.database import normalize_database_url


def _sqlite_path(url: str) -> Path:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise ValueError("not a SQLite URL")
    return Path(url.removeprefix(prefix)).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_sqlite(database_url: str, destination: Path) -> str:
    source_path = _sqlite_path(database_url)
    if source_path == destination.resolve():
        raise ValueError("backup destination must differ from the source database")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    verify_sqlite(destination)
    return sha256(destination)


def restore_sqlite(backup_path: Path, destination_url: str) -> str:
    verify_sqlite(backup_path)
    destination_path = _sqlite_path(destination_url)
    if backup_path.resolve() == destination_path:
        raise ValueError("restore destination must differ from the backup file")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup_path) as source, sqlite3.connect(destination_path) as target:
        source.backup(target)
    verify_sqlite(destination_path)
    return sha256(destination_path)


def verify_sqlite(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    if result != ("ok",):
        raise RuntimeError(f"SQLite integrity check failed: {result}")


def backup_postgres(database_url: str, destination: Path) -> None:
    normalized = normalize_database_url(database_url).replace("postgresql+psycopg://", "postgresql://")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pg_dump", "--format=custom", "--no-owner", "--file", str(destination), normalized],
        check=True,
    )


def restore_postgres(backup_path: Path, destination_url: str) -> None:
    normalized = normalize_database_url(destination_url).replace("postgresql+psycopg://", "postgresql://")
    subprocess.run(
        ["pg_restore", "--clean", "--if-exists", "--no-owner", "--dbname", normalized, str(backup_path)],
        check=True,
    )
