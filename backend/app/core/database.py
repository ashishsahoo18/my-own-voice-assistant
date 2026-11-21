"""Database engine, base model, and session dependency using SQLAlchemy 2.x."""

from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import settings

# Parse the URL once to determine dialect reliably (avoids fragile string prefix matching).
_db_url = make_url(settings.DATABASE_URL)
_dialect = _db_url.get_dialect().name  # e.g. "sqlite", "postgresql"

# Build engine keyword arguments conditionally on dialect.
# SQLite must NOT receive pool_size / max_overflow / pool_recycle (StaticPool used internally).
# PostgreSQL benefits from explicit pool tuning and a fast connect timeout.
_engine_kwargs: dict = {"pool_pre_ping": True, "echo": False}

if _dialect == "sqlite":
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif _dialect == "postgresql":
    _engine_kwargs.update(
        {
            "pool_size": 5,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_recycle": 1800,
            "connect_args": {"connect_timeout": 10},
        }
    )
# Unknown dialects: pass no extra kwargs; _verify_startup_schema() will reject them at startup.

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)

# Enforce foreign key constraints for SQLite (PostgreSQL enforces FKs natively).
if _dialect == "sqlite":
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for scoped database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

