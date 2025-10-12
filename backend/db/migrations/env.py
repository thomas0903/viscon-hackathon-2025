from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy import create_engine
from alembic import context

# Try to make both repository-root (host) and container (/app) layouts importable
HERE = Path(__file__).resolve()
ROOT_CANDIDATES = [HERE.parents[3] if len(HERE.parents) > 3 else None, HERE.parents[2]]
for candidate in ROOT_CANDIDATES:
    if candidate and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import Base and URL helper; support both 'backend.db' and 'db'
try:
    from backend.db.base import Base, make_sync_url  # type: ignore
except ModuleNotFoundError:
    from db.base import Base, make_sync_url  # type: ignore

target_metadata = Base.metadata


def _abs_sqlite_url(url: str) -> str:
    # Resolve relative sqlite path against the directory of the alembic.ini file
    if url.startswith("sqlite") and ":///" in url:
        path = url.split(":///", 1)[1]
        if not path.startswith("/"):
            cfg_dir = Path(config.config_file_name).resolve().parent if config.config_file_name else Path.cwd()
            return url.split(":///", 1)[0] + ":///" + (cfg_dir / path).as_posix()
    return url


def get_url() -> str:
    url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    url = _abs_sqlite_url(url)
    return make_sync_url(url)


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        get_url(),
        poolclass=pool.NullPool,
        connect_args={"check_same_thread": False},
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")

        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
