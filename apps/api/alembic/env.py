"""Alembic environment — reads DATABASE_URL from env, converts to sync for migrations."""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

from alpago.core.config import settings
from alpago.models import Base  # core models (users, roles, approvals, ...)

# Register domain module tables with Base.metadata BEFORE autogenerate reads it.
# These imports MUST stay here, not in models/__init__.py, to avoid a cycle:
#   modules.hiring  → api.deps  → models.__init__  → modules.hiring
from alpago.modules import hiring as _hiring_models      # noqa: F401
from alpago.modules import candidates as _candidate_models  # noqa: F401
from alpago.modules import interviews as _interview_models  # noqa: F401
from alpago.modules import offers as _offer_models       # noqa: F401
from alpago.modules import employees as _employee_models  # noqa: F401
from alpago.modules import documents as _document_models  # noqa: F401
from alpago.modules import forms as _form_models          # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    url = settings.database_url
    return url.replace("postgresql://", "postgresql+psycopg://", 1) if url.startswith("postgresql://") else url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(_url(), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
