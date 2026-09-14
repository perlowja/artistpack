"""Shared pytest fixtures.

We use SQLite + ``StaticPool`` for tests so we get a real database
without needing Postgres running. The publish-gate tests use real
files (no DB-specific features) so they pass identically on either
backend in CI.

Setup philosophy: tests are *async* (pytest-asyncio with
``asyncio_mode = "auto"``). The DB engine is shared across the whole
process via a ``StaticPool`` so all sessions see the same in-memory
SQLite database.
"""

from __future__ import annotations

import io
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
TEST_STORAGE = Path(os.environ.get("ARTISTPACK_TEST_STORAGE") or "/tmp/ap-tests-storage")


def _configure_settings_for_tests() -> None:
    os.environ["ARTISTPACK_DATABASE_URL"] = TEST_DB_URL
    os.environ["ARTISTPACK_STORAGE_DIR"] = str(TEST_STORAGE)
    os.environ["ARTISTPACK_ENVIRONMENT"] = "test"
    os.environ["ARTISTPACK_SKIP_INIT"] = "1"


_configure_settings_for_tests()


@pytest.fixture(scope="session", autouse=True)
def _ensure_storage_dir() -> None:
    TEST_STORAGE.mkdir(parents=True, exist_ok=True)


@pytest_asyncio.fixture
async def app_engine() -> AsyncIterator[tuple[Any, Any, Any]]:
    """Per-test isolated in-memory SQLite engine wired into the app."""

    from app.core.config import settings
    from app.db import Base
    import app.db.models  # noqa: F401

    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    import app.db as appdb

    appdb._engine = engine
    appdb._sessionmaker = SessionLocal

    from app.storage import LocalDiskStorage, reset_storage_for_tests

    reset_storage_for_tests(LocalDiskStorage(TEST_STORAGE))

    # Create schema + seed licenses.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        from app.services.licenses import seed_licenses
        await seed_licenses(s)

    from app.main import app

    yield app, engine, SessionLocal

    await engine.dispose()


@pytest.fixture
def client(app_engine) -> Iterator[TestClient]:
    app, _, _ = app_engine
    with TestClient(app) as c:
        yield c


# --- Async helpers -----------------------------------------------------------

@pytest_asyncio.fixture
async def db_session(app_engine):
    """Yield an async session scoped to the test's engine."""

    _, _, SessionLocal = app_engine
    async with SessionLocal() as s:
        yield s


# --- Factories ---------------------------------------------------------------

@pytest_asyncio.fixture
async def make_user(db_session):
    """Create a user + return ``{user_id, token, email}``."""

    from app.db.models import User
    from app.auth.oauth import issue_session_token

    async def _make(*, role: str = "user", email: str | None = None) -> dict[str, Any]:
        u = User(
            email=email or f"{uuid.uuid4().hex[:8]}@example.com",
            display_name="Test User",
            role=role,
        )
        db_session.add(u)
        await db_session.flush()
        return {
            "user_id": str(u.id),
            "token": issue_session_token(str(u.id)),
            "email": u.email,
        }

    return _make


@pytest.fixture
def auth_headers():
    def _h(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _h


@pytest.fixture
def png_bytes() -> bytes:
    img = Image.new("RGB", (4, 3), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def jpeg_bytes() -> bytes:
    img = Image.new("RGB", (640, 480), (0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

