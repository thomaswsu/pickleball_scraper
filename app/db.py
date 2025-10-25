"""Database utilities."""

from collections.abc import Generator
from typing import Any, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base model for SQLAlchemy."""


engine_kwargs: dict[str, Any] = {}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def ensure_schema() -> None:
    """Apply lightweight schema migrations for SQLite."""
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        result = conn.exec_driver_sql("PRAGMA table_info('availability_slots')")
        columns = {row[1] for row in result.fetchall()}
        if "duration_minutes" not in columns:
            conn.exec_driver_sql("ALTER TABLE availability_slots ADD COLUMN duration_minutes INTEGER")

def get_session() -> Generator:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
