"""Operator-controlled backup/restore helpers for SQLite and Postgres."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
from urllib.parse import parse_qs, unquote, urlsplit

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


def _postgres_environment(database_url: str) -> dict[str, str]:
    normalized = normalize_database_url(database_url).replace(
        "postgresql+psycopg://", "postgresql://"
    )
    parsed = urlsplit(normalized)
    if parsed.scheme != "postgresql" or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("invalid Postgres database URL")
    environment = {
        **os.environ,
        "PGHOST": parsed.hostname,
        "PGPORT": str(parsed.port or 5432),
        "PGDATABASE": unquote(parsed.path.lstrip("/")),
    }
    if parsed.username:
        environment["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        environment["PGPASSWORD"] = unquote(parsed.password)
    query = parse_qs(parsed.query)
    if query.get("sslmode"):
        environment["PGSSLMODE"] = query["sslmode"][-1]
    return environment


def backup_postgres(database_url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    environment = _postgres_environment(database_url)
    command = [
        os.getenv("PG_DUMP_BIN", "pg_dump"),
        "--format=custom",
        "--no-owner",
        "--file",
        str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, env=environment)
    except (OSError, subprocess.CalledProcessError) as exc:
        destination.unlink(missing_ok=True)
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise RuntimeError(f"Postgres backup failed: {detail}") from exc


def restore_postgres(backup_path: Path, destination_url: str) -> None:
    if not backup_path.is_file() or backup_path.stat().st_size == 0:
        raise ValueError("Postgres backup file is missing or empty")
    environment = _postgres_environment(destination_url)
    command = [
        os.getenv("PG_RESTORE_BIN", "pg_restore"),
        "--clean",
        "--if-exists",
        "--no-owner",
        "--dbname",
        environment["PGDATABASE"],
        str(backup_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, env=environment)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise RuntimeError(f"Postgres restore failed: {detail}") from exc
