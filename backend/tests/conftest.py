"""Shared test fixtures.

Tests run against an in-memory SQLite database with the ORM metadata created
from `app.core.database.Base`. This gives us a real `AsyncSession` so the
broker adapter's DB interactions are exercised end-to-end without needing a
running Postgres.
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import settings as _settings  # noqa: F401 — ensure tables are registered
from app.models import sync as _sync  # noqa: F401
from app.models import user as _user  # noqa: F401
from app.models import stock as _stock  # noqa: F401
from app.models import account as _account  # noqa: F401


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
def user_id() -> str:
    return "user-test-1"
