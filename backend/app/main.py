"""FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import artists, artworks, auth, feeds, moderation, packs, search
from app.core.config import settings
from app.core.errors import (
    APIError,
    api_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.db import init_models
from app.schemas.common import HealthResponse
from app.storage import get_storage


# SQLite needs this for any FK we declared with ondelete=...
@event.listens_for(Engine, "connect")
def _sqlite_pragma_on_connect(dbapi_connection, connection_record):
    if "sqlite" in str(dbapi_connection.__class__):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # First-boot convenience: ``init_models`` creates tables via SQLAlchemy
    # metadata. Production uses Alembic (``alembic upgrade head``); tests
    # either use the same or call ``init_models`` directly.
    if os.getenv("ARTISTPACK_SKIP_INIT") != "1":
        await init_models()
        # Seed licenses once at startup. Idempotent.
        from app.services.licenses import seed_licenses
        from app.db import session_scope

        async with session_scope() as session:
            await seed_licenses(session)
    yield


app = FastAPI(
    title="ArtistPack backend",
    version="0.1.0",
    description=(
        "Minimal FastAPI backend (Task 7 of docs/mvp-plan.md). "
        "Implements the REST surface in docs/api-design.md against the "
        "Postgres schema in docs/database-schema.md."
    ),
    lifespan=lifespan,
)

# --- Error handlers (envelope shape) ----------------------------------------
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


# --- Health ------------------------------------------------------------------
@app.get("/healthz", response_model=HealthResponse, tags=["meta"])
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version="0.1.0")


# --- Routers -----------------------------------------------------------------
prefix = settings.api_v1_prefix
app.include_router(auth.router, prefix=prefix)
app.include_router(artists.router, prefix=prefix)
app.include_router(packs.router, prefix=prefix)
app.include_router(artworks.router, prefix=prefix)
app.include_router(feeds.public_router, prefix=prefix)
app.include_router(feeds.admin_router, prefix=prefix)
app.include_router(moderation.router, prefix=prefix)
app.include_router(search.router, prefix=prefix)


# --- Local-disk storage download endpoint -----------------------------------
# The local-disk backend serves uploaded files at ``/storage/<key>`` so the
# public read endpoints can return real URLs. S3 replaces this in Phase 2.
@app.get("/storage/{key:path}", tags=["storage"])
async def serve_storage(key: str) -> FileResponse:
    storage = get_storage()
    if not storage.exists(key):
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Storage key not found.", "details": {"key": key}}},
        )
    path: Path = storage.absolute_path(key)
    # Pick a content type from extension as a best-effort; storage backend
    # doesn't track content type for the local FS impl yet.
    suffix = path.suffix.lower()
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".c2pa": "application/c2pa",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media_type)


__all__ = ["app"]
