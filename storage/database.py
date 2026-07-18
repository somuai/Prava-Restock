"""SQLAlchemy database configuration for SQLite development and Postgres production."""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from storage.schema import Base


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = f"sqlite:///{ROOT / 'logs' / 'restock.db'}"


def normalize_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://") and "+" not in value.split(":", 1)[0]:
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


class Database:
    def __init__(self, url: str | None = None) -> None:
        self.url = normalize_database_url(
            url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        )
        connect_args = {"check_same_thread": False} if self.url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(
            self.url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self._sessions = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def reset_schema(self) -> None:
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
