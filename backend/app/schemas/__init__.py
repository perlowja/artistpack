"""Pydantic schemas for the public artist / pack / artwork / feed surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ErrorBody, ErrorEnvelope, HealthResponse, Page

# Re-exports so callers can ``from app.schemas import Page``.
__all__ = [
    "Page",
    "ErrorBody",
    "ErrorEnvelope",
    "HealthResponse",
    # Domain models:
    "ArtistLinkOut",
    "ArtistSummary",
    "ArtistOut",
    "ArtistCreateIn",
    "ArtistLinkIn",
    "ArtistPatchIn",
    "PackSummary",
    "PackOut",
    "PackCreateIn",
    "PackPatchIn",
    "ArtworkVariantOut",
    "ArtworkOut",
    "ArtworkPatchIn",
    "FeedSummary",
    "FeedOut",
    "FeedCreateIn",
    "SearchResults",
    "MeOut",
    "MePatchIn",
    "OAuthCallbackIn",
    "OAuthCallbackOut",
    "PublishError",
    "PublishValidationOut",
    "PublishOut",
    "ReportIn",
    "ReportOut",
    "AuditLogOut",
    "SuspendOut",
]


# --- Artists ------------------------------------------------------------------

class ArtistLinkOut(BaseModel):
    kind: str
    url: str


class ArtistSummary(BaseModel):
    """The artist summary embedded in pack / artwork / feed responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    public_id: str
    name: str
    avatar_url: str | None = None
    website: str | None = None


class ArtistOut(BaseModel):
    """Full artist profile returned by ``GET /api/v1/artists/{artist_id}``."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    public_id: str
    name: str
    bio: str | None = None
    avatar_url: str | None = None
    website: str | None = None
    patreon: str | None = None
    support_url: str | None = None
    socials: dict[str, str | None] | None = None
    links: list[ArtistLinkOut] = Field(default_factory=list)
    manifest_url: str
    created_at: datetime
    updated_at: datetime


class ArtistCreateIn(BaseModel):
    public_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=128)
    name: str = Field(..., min_length=1, max_length=200)
    bio: str | None = None
    website: str | None = None
    patreon: str | None = None
    support_url: str | None = None
    socials: dict[str, str | None] | None = None
    links: list[ArtistLinkIn] | None = None


class ArtistLinkIn(BaseModel):
    kind: str = Field(..., pattern=r"^(website|patreon|social:[a-z0-9-]+)$")
    url: str = Field(..., min_length=1, max_length=2048)


class ArtistPatchIn(BaseModel):
    name: str | None = None
    bio: str | None = None
    website: str | None = None
    patreon: str | None = None
    support_url: str | None = None
    socials: dict[str, str | None] | None = None


# --- Packs --------------------------------------------------------------------

class PackSummary(BaseModel):
    """Pack embedded in artist / list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    public_id: str
    title: str
    description: str | None = None
    current_version: str | None = None
    status: str | None = None
    manifest_url: str
    artist: ArtistSummary


class PackOut(BaseModel):
    """Full pack response. ``manifest_url`` is the always-present
    canonical URL (per ``docs/api-design.md`` §Conventions)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    public_id: str
    title: str
    description: str | None = None
    current_version: str | None = None
    status: str | None = None
    manifest_url: str
    manifest_sha256: str | None = None
    artist: ArtistSummary
    created_at: datetime
    updated_at: datetime


class PackCreateIn(BaseModel):
    public_id: str = Field(..., pattern=r"^[a-z0-9.][a-z0-9.-]*$", max_length=256)
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


class PackPatchIn(BaseModel):
    title: str | None = None
    description: str | None = None


# --- Artworks -----------------------------------------------------------------

class ArtworkVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file: str
    sha256: str
    width: int
    height: int
    mime_type: str | None = None
    url: str


class ArtworkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    public_id: str
    title: str
    description: str | None = None
    original_file: str
    original_sha256: str
    width: int
    height: int
    mime_type: str
    orientation: str
    aspect_ratio: str
    license: str | None = None
    attribution_name: str
    attribution_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    variants: list[ArtworkVariantOut] = Field(default_factory=list)
    pack_id: str
    pack_public_id: str
    manifest_url: str
    display: dict[str, Any] | None = None
    palette: dict[str, Any] | None = None
    created_at: datetime


class ArtworkPatchIn(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    attribution_url: str | None = None


# --- Feeds --------------------------------------------------------------------

class FeedSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    public_id: str
    title: str
    description: str | None = None
    updated_at: datetime


class FeedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    public_id: str
    title: str
    description: str | None = None
    updated_at: datetime
    manifest_url: str
    items: list[PackSummary]


class FeedCreateIn(BaseModel):
    public_id: str = Field(..., pattern=r"^[a-z0-9.][a-z0-9.-]*$", max_length=256)
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


# --- Search -------------------------------------------------------------------

class SearchResults(BaseModel):
    """``GET /api/v1/search`` returns a flat mixed list of packs + artworks."""

    items: list[dict[str, Any]] = Field(default_factory=list)
    next_cursor: str | None = None


# --- /me ----------------------------------------------------------------------

class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str | None
    display_name: str | None
    role: str
    artists: list[ArtistSummary] = Field(default_factory=list)


class MePatchIn(BaseModel):
    display_name: str | None = None


# --- OAuth callback -----------------------------------------------------------

class OAuthCallbackIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=4096)
    state: str = Field(..., min_length=1, max_length=4096)
    redirect_uri: str = Field(..., min_length=1, max_length=2048)


class OAuthCallbackOut(BaseModel):
    user: MeOut
    token: str
    expires_in: int


# --- Publish gate -------------------------------------------------------------

class PublishError(BaseModel):
    path: str
    message: str


class PublishValidationOut(BaseModel):
    """Response shape for ``GET /api/v1/packs/{pack_id}/validation``."""

    pack_id: str
    version: str
    errors: list[PublishError]


class PublishOut(BaseModel):
    pack_id: str
    version: str
    status: str
    published_at: datetime
    manifest_sha256: str


# --- Moderation ---------------------------------------------------------------

class ReportIn(BaseModel):
    target_type: str = Field(..., pattern=r"^(pack|artwork|artist)$")
    target_id: str
    reason: str = Field(..., min_length=1, max_length=2000)
    detail: dict[str, Any] | None = None


class ReportOut(BaseModel):
    id: int
    target_type: str
    target_id: str
    reason: str
    created_at: datetime


class AuditLogOut(BaseModel):
    id: int
    actor_user_id: str | None
    action: str
    target_type: str
    target_id: str
    detail: dict[str, Any] | None
    created_at: datetime


class SuspendOut(BaseModel):
    pack_id: str
    status: str
    reason: str | None = None
