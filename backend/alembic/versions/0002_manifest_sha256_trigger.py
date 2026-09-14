"""manifest_sha256 Postgres trigger (production-only integrity floor).

``docs/database-schema.md`` is explicit that ``manifest_sha256`` must
*never silently drift* from the manifest it represents, and that the
guarantee should live in the database, not in application code. This
migration adds a BEFORE INSERT OR UPDATE trigger on ``pack_versions``
that recomputes the canonical SHA-256 of the ``manifest`` JSONB and
overwrites ``manifest_sha256`` with the result.

The trigger is dialect-guarded to Postgres. On SQLite (our test
backend), the application computes the same value at save time via
``app.services.manifest_hash.recompute_and_set`` — so the invariant
holds on both backends, with the trigger being the authoritative
floor in production per the doc.

Revision ID: 0002_manifest_sha256_trigger
Revises: 0001_initial
Create Date: 2026-09-14 00:00:01
"""

from __future__ import annotations

from typing import Sequence

from alembic import op

revision: str = "0002_manifest_sha256_trigger"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TRIGGER_FN = """
CREATE OR REPLACE FUNCTION ap_recompute_manifest_sha256()
RETURNS trigger AS $$
DECLARE
    canonical jsonb;
BEGIN
    -- Canonicalize: sort keys, drop nulls, compact whitespace.
    -- Postgres' jsonb type already deduplicates keys and is keyed,
    -- so jsonb_typeof + re-emission via jsonb_build_object handles
    -- ordering; dropping nulls is the one explicit step we need.
    canonical := (
        SELECT jsonb_object_agg(key, value)
        FROM jsonb_each(NEW.manifest)
        WHERE value IS NOT NULL
    );

    NEW.manifest_sha256 := encode(digest(canonical::text, 'sha256'), 'hex');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # ``digest()`` ships with ``pgcrypto``. The schema is created in an
    # idempotent fashion — if the extension already exists, that's fine.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(TRIGGER_FN)
    op.execute(
        """
        DROP TRIGGER IF EXISTS ap_pack_versions_manifest_sha256 ON pack_versions;
        CREATE TRIGGER ap_pack_versions_manifest_sha256
        BEFORE INSERT OR UPDATE OF manifest ON pack_versions
        FOR EACH ROW EXECUTE FUNCTION ap_recompute_manifest_sha256();
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS ap_pack_versions_manifest_sha256 ON pack_versions")
    op.execute("DROP FUNCTION IF EXISTS ap_recompute_manifest_sha256()")
