"""SQLAlchemy engine and session setup.

This module centralizes DB configuration for both sync and async usage.
We set consistent naming for constraints (better Alembic diffs), enable
SQLite PRAGMAs (WAL, timeouts, FKs), and expose session factories.
"""

import os
import pathlib
from typing import Generator

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker


# Consistent names for PK/FK/IX/UQ to make Alembic diffs stable
naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=naming_convention)
Base = declarative_base(metadata=metadata)


# Default SQLite file relative to the backend working dir
# This matches backend/alembic.ini (sqlite:///var/data/app.db)
DEFAULT_DB_PATH = os.path.join("var", "data", "app.db")
DEFAULT_ASYNC_URL = f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}"


def _ensure_db_dir(db_url: str) -> None:
    """Create the parent directory of the SQLite DB file if needed."""
    if db_url.startswith("sqlite"):
        path_part = db_url.split("///", 1)[-1]
        db_path = pathlib.Path(path_part)
        db_path.parent.mkdir(parents=True, exist_ok=True)


def _apply_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # type: ignore[no-redef]
    """Enable WAL, timeouts, and FK enforcement on every SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")  # better read/write concurrency
    cursor.execute("PRAGMA synchronous=NORMAL;")  # balance safety/perf
    cursor.execute("PRAGMA busy_timeout=5000;")  # reduce 'database is locked'
    cursor.execute("PRAGMA foreign_keys=ON;")  # enforce FKs
    cursor.close()


def make_sync_url(url: str) -> str:
    """Convert an async SQLite URL to sync (e.g., for Alembic)."""
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    return url


def get_database_url() -> str:
    """Resolve DB URL with a sensible default for local dev."""
    return os.getenv("DATABASE_URL", DEFAULT_ASYNC_URL)


def get_engine() -> Engine:
    """Synchronous engine (CLI/migrations/scripts)."""
    url = make_sync_url(get_database_url())
    _ensure_db_dir(url)
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},  # allow use across threads
        future=True,
    )
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _apply_sqlite_pragmas)
    return engine


def get_async_engine() -> AsyncEngine:
    """Async engine (FastAPI handlers)."""
    url = get_database_url()
    _ensure_db_dir(url)
    aengine = create_async_engine(url, future=True)
    if url.startswith("sqlite+aiosqlite"):
        # Ensure PRAGMAs on the underlying sync engine
        event.listen(aengine.sync_engine, "connect", _apply_sqlite_pragmas)
    return aengine


# Session factories (sync for scripts/tests, async for web handlers)
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=get_async_engine(), autoflush=False, expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    """Yield a sync Session. Useful in scripts/CLI tools."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> Generator[AsyncSession, None, None]:
    """Yield an AsyncSession. Use with FastAPI Depends."""
    async with AsyncSessionLocal() as session:
        yield session
