"""Database engine and session handling (SQLite for local use)."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
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
        self._add_missing_columns()

    def _add_missing_columns(self) -> None:
        """Add nullable columns introduced after a table was created.

        A minimal stand-in for migrations while the app runs locally. It only adds
        columns; it never changes or drops anything. Use Alembic before hosting.
        """
        inspector = inspect(self.engine)
        with self.engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                existing = {column["name"] for column in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name not in existing and column.nullable:
                        column_type = column.type.compile(dialect=self.engine.dialect)
                        connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'))

    def session(self) -> Iterator[Session]:
        with self._sessions() as session:
            yield session
