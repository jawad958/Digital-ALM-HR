"""SQLAlchemy async engine and session factory.

Dialect-neutral: works on SQLite (local dev) and PostgreSQL (Render) without
code changes. The engine is a module-level singleton.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alpago.core.config import settings


def _async_url(url: str) -> str:
    """Normalise the URL to an async driver scheme."""
    # Render injects postgres:// — convert to the psycopg async driver
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    # SQLite already uses sqlite+aiosqlite:// in config
    return url


_engine_kwargs = {"echo": False, "pool_pre_ping": True}
if not settings.is_sqlite:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20

engine = create_async_engine(_async_url(settings.database_url), **_engine_kwargs)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a session scoped to one request."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """For use outside the request lifecycle (workers, scripts, tests)."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
