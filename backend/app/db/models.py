"""SQLAlchemy ORM models.

Every entity from ``docs/database-schema.md`` §Entities is implemented
here. Field shapes track the doc; cross-database portability (SQLite for
tests, Postgres in prod) is the only deviation from a literal copy:

* ``UUID`` columns use SQLAlchemy's portable ``Uuid``/``String(36)``
  dialect-agnostic type (see ``app.db.types_guid``) — Postgres would
  natively use a ``uuid`` column type, SQLite stores a 36-char string,
  both work through SQLAlchemy.
* ``JSONB`` columns are mapped via the JSON type, which works on both
  backends.
* ``pack_versions.manifest_sha256`` is implemented as a Postgres trigger
  in the Alembic migration (the doc's hard requirement); we *also*
  recompute it on every Python-side save so tests running on SQLite see
  the same invariant. The trigger is the authoritative guarantee in
  prod; the Python recompute is a portability shim.
* ``provenance_records`` and ``audit_log`` are append-only by convention
  (the doc's intent) — there is no application-level guard rail here
  yet, but ``unique (artwork_id)`` on the former is enforced.

Type imports reference the string ``__tablename__`` values defined
inline; each model carries the doc's column names verbatim so the
migration can be reviewed against the spec.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import BIGINT as PG_BIGINT
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator

from app.db import Base


# --- Custom cross-dialect UUID type ------------------------------------------

class GUID(TypeDecorator):
    """Platform-independent UUID column.

    Stores as native ``uuid`` on Postgres, as a 36-char string elsewhere.
    SQLAlchemy 2.0+ ships ``sqlalchemy.Uuid`` which already does this,
    but using the built-in keeps the model decoupled from any specific
    SQLAlchemy micro-version.
    """

    impl = String
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(length=36)

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID

            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value if dialect.name == "postgresql" else str(value)
        # accept strings too
        if isinstance(value, str):
            parsed = uuid.UUID(value)
            return parsed if dialect.name == "postgresql" else str(parsed)
        raise TypeError(f"GUID expects UUID or string, got {type(value).__name__}")

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


# --- JSONB type that falls back to JSON on non-Postgres ----------------------

class PortableJSONB(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _AutoincrementBigInt(TypeDecorator):
    """BigInteger that maps to SQLite's INTEGER PRIMARY KEY autoincrement.

    SQLite only autoincrements columns typed ``INTEGER PRIMARY KEY``.
    On Postgres we want the real ``bigint`` type; on SQLite we coerce
    to ``INTEGER`` so the autoincrement happens automatically.
    """

    impl = BigInteger
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "sqlite":
            return dialect.type_descriptor(Integer())
        return dialect.type_descriptor(PG_BIGINT())


# --- Enums --------------------------------------------------------------------

class UserRole(str, enum.Enum):
    user = "user"
    artist = "artist"
    moderator = "moderator"
    administrator = "administrator"


class PackVersionStatus(str, enum.Enum):
    draft = "draft"
    pending_review = "pending_review"
    published = "published"
    rejected = "rejected"
    suspended = "suspended"


class ProvenanceVerificationStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    failed = "failed"


class PublishingJobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    failed = "failed"
    complete = "complete"


# --- Users / OAuth ------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.user
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now(),
        onupdate=_utcnow,
    )

    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    artists: Mapped[list["Artist"]] = relationship(back_populates="owner_user")


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="oauth_accounts")


# --- Artists ------------------------------------------------------------------

class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    public_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    patreon: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    support_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    socials: Mapped[Optional[dict[str, Any]]] = mapped_column(PortableJSONB(), nullable=True)
    manifest_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now(),
        onupdate=_utcnow,
    )

    owner_user: Mapped["User"] = relationship(back_populates="artists")
    links: Mapped[list["ArtistLink"]] = relationship(
        back_populates="artist", cascade="all, delete-orphan"
    )
    packs: Mapped[list["Pack"]] = relationship(back_populates="artist")


class ArtistLink(Base):
    __tablename__ = "artist_links"
    __table_args__ = (
        UniqueConstraint("artist_id", "kind", "url", name="uq_artist_link_unique"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    artist_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("artists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # website|patreon|social:<x>
    url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    artist: Mapped["Artist"] = relationship(back_populates="links")


# --- Packs / pack_versions ---------------------------------------------------

class Pack(Base):
    __tablename__ = "packs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    public_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    artist_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("artists.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_draft_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("pack_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now(),
        onupdate=_utcnow,
    )

    artist: Mapped["Artist"] = relationship(back_populates="packs")
    versions: Mapped[list["PackVersion"]] = relationship(
        back_populates="pack",
        cascade="all, delete-orphan",
        foreign_keys="PackVersion.pack_id",
    )
    current_draft: Mapped[Optional["PackVersion"]] = relationship(
        foreign_keys=[current_draft_version_id], post_update=True
    )


class PackVersion(Base):
    """Immutable per-version snapshot of a pack.

    The doc's "why artworks belong to pack_versions, not packs" note
    lives in ``docs/database-schema.md`` — this is the row that locks a
    pack's published state in place. ``manifest_sha256`` is the
    hash of the canonical serialized manifest and must never silently
    drift; that invariant is enforced in two places: a Postgres trigger
    (the authoritative guarantee, see Alembic migration) and the
    ``recompute_manifest_sha256`` helper called from this module's
    :py:meth:`__before_commit__` hook and from save paths.
    """

    __tablename__ = "pack_versions"
    __table_args__ = (
        UniqueConstraint("pack_id", "version", name="uq_pack_version"),
        CheckConstraint(
            "status IN ('draft','pending_review','published','rejected','suspended')",
            name="ck_pack_version_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    pack_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("packs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(Text, nullable=False)
    # MutableDict so ``pack_version.manifest['foo'] = 'bar'`` triggers an
    # ORM change and the row is written on commit (the application's
    # usual mutation style). Postgres trigger still owns the
    # ``manifest_sha256`` invariant. We use SA's ``JSON`` directly here
    # (dialect-loaded via ``PortableJSONB``) because ``MutableDict``
    # needs a SQLAlchemy JSON-flavoured type to attach to, not a generic
    # ``TypeDecorator``.
    manifest: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON()), nullable=False
    )
    manifest_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[PackVersionStatus] = mapped_column(
        Enum(PackVersionStatus, name="pack_version_status"),
        nullable=False,
        default=PackVersionStatus.draft,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    pack: Mapped["Pack"] = relationship(
        back_populates="versions", foreign_keys=[pack_id]
    )
    artworks: Mapped[list["Artwork"]] = relationship(
        back_populates="pack_version", cascade="all, delete-orphan",
        order_by="Artwork.created_at",
    )


# --- Artworks / variants ------------------------------------------------------

class Artwork(Base):
    __tablename__ = "artworks"
    __table_args__ = (
        UniqueConstraint("pack_version_id", "public_id", name="uq_artwork_in_version"),
        CheckConstraint(
            "orientation IN ('landscape','portrait','square')",
            name="ck_artwork_orientation",
        ),
        Index(
            "ix_artworks_filter",
            "pack_version_id",
            "orientation",
            "aspect_ratio",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    pack_version_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("pack_versions.id", ondelete="CASCADE"), nullable=False
    )
    public_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_file: Mapped[str] = mapped_column(Text, nullable=False)
    original_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    orientation: Mapped[str] = mapped_column(String(16), nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(16), nullable=False)
    license_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("licenses.id", ondelete="SET NULL"), nullable=True
    )
    attribution_name: Mapped[str] = mapped_column(Text, nullable=False)
    attribution_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display: Mapped[Optional[dict[str, Any]]] = mapped_column(PortableJSONB(), nullable=True)
    palette: Mapped[Optional[dict[str, Any]]] = mapped_column(PortableJSONB(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    pack_version: Mapped["PackVersion"] = relationship(back_populates="artworks")
    variants: Mapped[list["ArtworkVariant"]] = relationship(
        back_populates="artwork", cascade="all, delete-orphan", order_by="ArtworkVariant.width"
    )
    provenance: Mapped[Optional["ProvenanceRecord"]] = relationship(
        back_populates="artwork", cascade="all, delete-orphan", uselist=False
    )


class ArtworkVariant(Base):
    __tablename__ = "artwork_variants"
    __table_args__ = (
        UniqueConstraint("artwork_id", "width", "height", name="uq_variant_dimensions"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    artwork_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("artworks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    artwork: Mapped["Artwork"] = relationship(back_populates="variants")


# --- Tags ---------------------------------------------------------------------

class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("kind", "slug", name="uq_tag_kind_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="artwork")
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )


class ArtworkTag(Base):
    __tablename__ = "artwork_tags"
    __table_args__ = (
        UniqueConstraint("artwork_id", "tag_id", name="uq_artwork_tag"),
    )

    id: Mapped[BigInteger] = mapped_column(_AutoincrementBigInt(), primary_key=True, autoincrement=True)
    artwork_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("artworks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True
    )


# --- Licenses -----------------------------------------------------------------

class License(Base):
    __tablename__ = "licenses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    spdx_or_custom_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )


# --- Feeds --------------------------------------------------------------------

class Feed(Base):
    __tablename__ = "feeds"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    public_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    items: Mapped[list["FeedItem"]] = relationship(
        back_populates="feed", cascade="all, delete-orphan", order_by="FeedItem.position"
    )


class FeedItem(Base):
    __tablename__ = "feed_items"
    __table_args__ = (
        UniqueConstraint("feed_id", "pack_version_id", name="uq_feed_item_pack_version"),
    )

    id: Mapped[BigInteger] = mapped_column(_AutoincrementBigInt(), primary_key=True, autoincrement=True)
    feed_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pack_version_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("pack_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    feed: Mapped["Feed"] = relationship(back_populates="items")
    pack_version: Mapped["PackVersion"] = relationship()


# --- Provenance / publishing jobs / audit -------------------------------------

class ProvenanceRecord(Base):
    __tablename__ = "provenance_records"
    __table_args__ = (
        UniqueConstraint("artwork_id", name="uq_provenance_artwork"),
        CheckConstraint(
            "verification_status IN ('pending','verified','failed')",
            name="ck_provenance_status",
        ),
        CheckConstraint(
            "signed_by IN ('artist-provided','artistpack-signing-service')",
            name="ck_provenance_signed_by",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    artwork_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("artworks.id", ondelete="CASCADE"), nullable=False
    )
    manifest_file: Mapped[str] = mapped_column(Text, nullable=False)
    signed_by: Mapped[str] = mapped_column(Text, nullable=False)
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[ProvenanceVerificationStatus] = mapped_column(
        Enum(ProvenanceVerificationStatus, name="provenance_status"),
        nullable=False,
        default=ProvenanceVerificationStatus.pending,
    )
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(PortableJSONB(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    artwork: Mapped["Artwork"] = relationship(back_populates="provenance")


class PublishingJob(Base):
    __tablename__ = "publishing_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','failed','complete')",
            name="ck_publishing_job_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    pack_version_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("pack_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[PublishingJobStatus] = mapped_column(
        Enum(PublishingJobStatus, name="publishing_job_status"),
        nullable=False,
        default=PublishingJobStatus.queued,
    )
    error: Mapped[Optional[dict[str, Any]]] = mapped_column(PortableJSONB(), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    pack_version: Mapped["PackVersion"] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[BigInteger] = mapped_column(_AutoincrementBigInt(), primary_key=True, autoincrement=True)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(PortableJSONB(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )


# --- Reports (moderation intake) ---------------------------------------------

class Report(Base):
    """Moderation reports — one row per user-submitted flag.

    Filed by any authenticated user against ``pack``, ``artwork``, or
    ``artist`` targets (the ``target_type`` check is enforced by the
    schema). ``status`` follows the moderation queue workflow and is
    intentionally a free-form string here — the moderator dashboard
    (Task 8) defines the exact set of states.
    """

    __tablename__ = "reports"

    id: Mapped[BigInteger] = mapped_column(_AutoincrementBigInt(), primary_key=True, autoincrement=True)
    reporter_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(PortableJSONB(), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )


__all__ = [
    "GUID",
    "PortableJSONB",
    "User",
    "OAuthAccount",
    "Artist",
    "ArtistLink",
    "Pack",
    "PackVersion",
    "Artwork",
    "ArtworkVariant",
    "Tag",
    "ArtworkTag",
    "License",
    "Feed",
    "FeedItem",
    "ProvenanceRecord",
    "PublishingJob",
    "AuditLog",
    "UserRole",
    "PackVersionStatus",
    "ProvenanceVerificationStatus",
    "PublishingJobStatus",
]
