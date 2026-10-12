"""Shared test fixtures.

Uses the same dialect-neutral SQLAlchemy models — so tests work on both the
default SQLite file DB and on Postgres (set DATABASE_URL in the env).

For speed and isolation, the test DB is dropped+recreated once per session,
and each test clears all tables at the end.
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force a dedicated test DB when the user hasn't set one
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./alpago_test.db")
os.environ.setdefault("ENV", "test")

from alpago.core.config import settings  # noqa: E402
from alpago.models import Base, User  # noqa: E402
from alpago.models.user import AuthProvider, UserStatus  # noqa: E402


def _async_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(_async_url(settings.database_url), echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    sm = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with sm() as s:
        yield s
        await s.rollback()
    # Hard clean after each test — delete rows (keep tables)
    async with engine.begin() as conn:
        for t in reversed(Base.metadata.sorted_tables):
            await conn.execute(t.delete())


@pytest_asyncio.fixture
async def make_user(session):
    async def _make(email: str | None = None, name: str = "Test User") -> User:
        u = User(
            email=email or f"user-{uuid4()}@test.alpago",
            name=name,
            status=UserStatus.active,
            auth_provider=AuthProvider.google,
        )
        session.add(u)
        await session.flush()
        return u
    return _make
