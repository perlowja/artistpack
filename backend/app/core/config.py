"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the ArtistPack backend.

    All values are pulled from environment variables with the
    ``ARTISTPACK_`` prefix; see ``docs/tech-decisions.md`` for the
    technology choices that hang off these.
    """

    model_config = SettingsConfigDict(
        env_prefix="ARTISTPACK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ArtistPack backend"
    environment: Literal["dev", "test", "staging", "prod"] = "dev"
    debug: bool = False

    database_url: str = Field(
        default="sqlite+aiosqlite:///./artistpack.db",
        description="SQLAlchemy URL. Prod should be postgresql+psycopg://...",
    )
    storage_dir: Path = Field(
        default=Path("./storage"),
        description="Local-disk storage root. S3-compatible backend comes later.",
    )

    schema_dir: Path = Field(
        default=Path(__file__).resolve().parents[3] / "schema",
        description="Path to the JSON Schema files (schema/pack.schema.json etc.).",
    )

    oauth_jwt_secret: str = Field(
        default="dev-only-not-for-prod-please-rotate",
        description="HMAC secret for the session token returned by the OAuth callback.",
    )
    oauth_session_ttl_seconds: int = 60 * 60 * 24 * 14  # 14 days

    manifest_max_bytes: int = 1_048_576  # 1 MiB cap on pack.yaml / feed.yaml uploads
    artwork_max_bytes: int = 50 * 1024 * 1024  # 50 MiB per original artwork
    artwork_max_pixels: int = 100_000_000  # decompression-bomb guard

    api_v1_prefix: str = "/api/v1"


def get_settings() -> Settings:
    """Return the cached ``Settings`` for this process.

    Tests monkeypatch ``app.core.config.settings`` directly, so this
    mostly exists for the FastAPI dependency-injection flow.
    """
    return settings


# Module-level cache so settings are parsed once. Tests can still replace this.
settings = Settings()


def configure_for_tests(database_url: str, storage_dir: Path | None = None) -> Settings:
    """Reset ``settings`` for test runs. Idempotent — safe to call repeatedly."""

    os.environ["ARTISTPACK_DATABASE_URL"] = database_url
    os.environ["ARTISTPACK_ENVIRONMENT"] = "test"
    global settings
    settings = Settings()
    if storage_dir is not None:
        settings.storage_dir = storage_dir
    return settings
