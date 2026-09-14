"""Database setup: SQLAlchemy async engine + session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Project-wide declarative base."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        kwargs: dict = {"echo": settings.debug}
        # SQLite + asyncio needs this for cross-session visibility in tests.
        if _is_sqlite(settings.database_url):
            from sqlalchemy.pool import StaticPool

            kwargs["connect_args"] = {"check_same_thread": False}
            kwargs["poolclass"] = StaticPool
        _engine = create_async_engine(settings.database_url, **kwargs)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False, autoflush=False
        )
    return _sessionmaker


def configure_for_tests(database_url: str) -> None:
    """Reset the engine/sessionmaker for tests."""
    global _engine, _sessionmaker
    # Dispose old engine if it exists (best-effort, sync context).
    if _engine is not None:
        try:
            _engine.sync_engine.pool.dispose()
        except Exception:  # pragma: no cover - cleanup is best-effort
            pass
    # Force re-creation against the new URL.
    from app.core.config import configure_for_tests as _configure_settings
    from app.core.config import settings as current_settings

    current_settings.database_url = database_url
    # Reset cached modules so they re-read.
    _configure_settings(database_url)
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a request-scoped session."""
    async with get_sessionmaker()() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context manager for code paths (workers, tests) that aren't request-scoped."""
    async with get_sessionmaker()() as session:
        yield session


async def init_models() -> None:
    """Create tables on first boot (dev convenience). Use Alembic in prod."""
    # Import the models so they register against Base.metadata.
    from app.db import models  # noqa: F401

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
