"""Database engine and session handling (SQLite for local use)."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def create_database_engine(database_url: str) -> Engine:
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        # SQLite ignores foreign key constraints (and ON DELETE CASCADE) unless asked.
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


class Database:
    def __init__(self, database_url: str):
        self.engine = create_database_engine(database_url)
        self._sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_tables(self) -> None:
        from app import models  # noqa: F401  Registers the tables on Base.metadata.

        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        with self._sessions() as session:
            yield session
