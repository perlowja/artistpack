"""initial schema

Implements every entity from ``docs/database-schema.md`` §Entities, plus
indexes called out in §Indexes worth calling out now (not exhaustive).

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-14 00:00:00
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    json_type = sa.JSON().with_variant(
        __import__("sqlalchemy.dialects.postgresql", fromlist=["JSONB"]).JSONB(),
        "postgresql",
    )

    uuid_type = sa.String(length=36).with_variant(
        __import__("sqlalchemy.dialects.postgresql", fromlist=["UUID"]).UUID(as_uuid=True),
        "postgresql",
    )

    op.create_table(
        "users",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column(
            "role",
            sa.Enum("user", "artist", "moderator", "administrator", name="user_role"),
            nullable=False,
            server_default="user",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "oauth_accounts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("user_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])

    op.create_table(
        "artists",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("owner_user_id", uuid_type, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("avatar_key", sa.Text(), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("patreon", sa.Text(), nullable=True),
        sa.Column("support_url", sa.Text(), nullable=True),
        sa.Column("socials", json_type, nullable=True),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("public_id", name="uq_artists_public_id"),
    )
    op.create_index("ix_artists_owner_user_id", "artists", ["owner_user_id"])

    op.create_table(
        "artist_links",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("artist_id", uuid_type, sa.ForeignKey("artists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("artist_id", "kind", "url", name="uq_artist_link_unique"),
    )
    op.create_index("ix_artist_links_artist_id", "artist_links", ["artist_id"])

    op.create_table(
        "packs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("artist_id", uuid_type, sa.ForeignKey("artists.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_draft_version_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("public_id", name="uq_packs_public_id"),
        sa.UniqueConstraint("current_draft_version_id", name="uq_packs_current_draft_version_id"),
        sa.ForeignKeyConstraint(
            ["current_draft_version_id"],
            ["pack_versions.id"],
            name="fk_packs_current_draft_version",
            ondelete="SET NULL",
            use_alter=True,
        ),
    )
    op.create_index("ix_packs_artist_id", "packs", ["artist_id"])

    op.create_table(
        "pack_versions",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("pack_id", uuid_type, sa.ForeignKey("packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("manifest", json_type, nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "pending_review", "published", "rejected", "suspended", name="pack_version_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("pack_id", "version", name="uq_pack_version"),
        sa.CheckConstraint(
            "status IN ('draft','pending_review','published','rejected','suspended')",
            name="ck_pack_version_status",
        ),
    )
    op.create_index("ix_pack_versions_pack_id", "pack_versions", ["pack_id"])
    op.create_index(
        "ix_pack_versions_status_published_at",
        "pack_versions",
        ["status", "published_at"],
    )

    op.create_table(
        "licenses",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("spdx_or_custom_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("spdx_or_custom_id", name="uq_licenses_spdx_or_custom_id"),
    )

    op.create_table(
        "artworks",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("pack_version_id", uuid_type, sa.ForeignKey("pack_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("original_file", sa.Text(), nullable=False),
        sa.Column("original_sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("orientation", sa.String(length=16), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=16), nullable=False),
        sa.Column("license_id", uuid_type, sa.ForeignKey("licenses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attribution_name", sa.Text(), nullable=False),
        sa.Column("attribution_url", sa.Text(), nullable=True),
        sa.Column("display", json_type, nullable=True),
        sa.Column("palette", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("pack_version_id", "public_id", name="uq_artwork_in_version"),
        sa.CheckConstraint(
            "orientation IN ('landscape','portrait','square')",
            name="ck_artwork_orientation",
        ),
    )
    op.create_index(
        "ix_artworks_filter",
        "artworks",
        ["pack_version_id", "orientation", "aspect_ratio"],
    )

    op.create_table(
        "artwork_variants",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("artwork_id", uuid_type, sa.ForeignKey("artworks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.UniqueConstraint("artwork_id", "width", "height", name="uq_variant_dimensions"),
    )
    op.create_index("ix_artwork_variants_artwork_id", "artwork_variants", ["artwork_id"])

    op.create_table(
        "tags",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="artwork"),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("kind", "slug", name="uq_tag_kind_slug"),
    )

    op.create_table(
        "artwork_tags",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("artwork_id", uuid_type, sa.ForeignKey("artworks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", uuid_type, sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("artwork_id", "tag_id", name="uq_artwork_tag"),
    )
    op.create_index("ix_artwork_tags_artwork_id", "artwork_tags", ["artwork_id"])
    op.create_index("ix_artwork_tags_tag_id", "artwork_tags", ["tag_id"])

    op.create_table(
        "feeds",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("public_id", name="uq_feeds_public_id"),
    )

    op.create_table(
        "feed_items",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("feed_id", uuid_type, sa.ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pack_version_id", uuid_type, sa.ForeignKey("pack_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("feed_id", "pack_version_id", name="uq_feed_item_pack_version"),
    )
    op.create_index("ix_feed_items_feed_id", "feed_items", ["feed_id"])
    op.create_index("ix_feed_items_pack_version_id", "feed_items", ["pack_version_id"])

    op.create_table(
        "provenance_records",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("artwork_id", uuid_type, sa.ForeignKey("artworks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manifest_file", sa.Text(), nullable=False),
        sa.Column("signed_by", sa.Text(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "verification_status",
            sa.Enum("pending", "verified", "failed", name="provenance_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("detail", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("artwork_id", name="uq_provenance_artwork"),
        sa.CheckConstraint(
            "verification_status IN ('pending','verified','failed')",
            name="ck_provenance_status",
        ),
        sa.CheckConstraint(
            "signed_by IN ('artist-provided','artistpack-signing-service')",
            name="ck_provenance_signed_by",
        ),
    )

    op.create_table(
        "publishing_jobs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("pack_version_id", uuid_type, sa.ForeignKey("pack_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "failed", "complete", name="publishing_job_status"),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("error", json_type, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "status IN ('queued','running','failed','complete')",
            name="ck_publishing_job_status",
        ),
    )
    op.create_index("ix_publishing_jobs_pack_version_id", "publishing_jobs", ["pack_version_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("actor_user_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", uuid_type, nullable=False),
        sa.Column("detail", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_audit_log_actor_user_id", "audit_log", ["actor_user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_target", "audit_log", ["target_type", "target_id"])

    # Full-text search vectors for the GET /api/v1/search endpoint (Postgres-only;
    # SQLite FTS5 is wired up via raw SQL at runtime if/when we test it).
    if is_pg:
        op.execute(
            "ALTER TABLE packs ADD COLUMN search_vector tsvector "
            "GENERATED ALWAYS AS ("
            "  setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
            "  setweight(to_tsvector('simple', coalesce(description, '')), 'B')"
            ") STORED"
        )
        op.execute(
            "ALTER TABLE artworks ADD COLUMN search_vector tsvector "
            "GENERATED ALWAYS AS ("
            "  setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
            "  setweight(to_tsvector('simple', coalesce(description, '')), 'B')"
            ") STORED"
        )
        op.create_index("ix_packs_search", "packs", ["search_vector"], postgresql_using="gin")
        op.create_index("ix_artworks_search", "artworks", ["search_vector"], postgresql_using="gin")


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute("ALTER TABLE packs DROP COLUMN IF EXISTS search_vector")
        op.execute("ALTER TABLE artworks DROP COLUMN IF EXISTS search_vector")

    op.drop_table("audit_log")
    op.drop_table("publishing_jobs")
    op.drop_table("provenance_records")
    op.drop_table("feed_items")
    op.drop_table("feeds")
    op.drop_table("artwork_tags")
    op.drop_table("tags")
    op.drop_table("artwork_variants")
    op.drop_table("artworks")
    op.drop_table("licenses")
    op.drop_table("pack_versions")
    op.drop_table("packs")
    op.drop_table("artist_links")
    op.drop_table("artists")
    op.drop_table("oauth_accounts")
    op.drop_table("users")
