"""Add reports table for moderation intake.

The doc's moderation endpoints list ``GET /admin/reports``; we ship a
small ``reports`` table to back it. This is the smallest possible
addition — a ``status`` column with a free-form string so the dashboard
queue (Task 8) can introduce its own workflow without an Alembic
roundtrip.

Revision ID: 0003_reports
Revises: 0002_manifest_sha256_trigger
Create Date: 2026-09-14 00:00:02
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_reports"
down_revision: str | None = "0002_manifest_sha256_trigger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(
        __import__("sqlalchemy.dialects.postgresql", fromlist=["JSONB"]).JSONB(),
        "postgresql",
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("reporter_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("detail", json_type, nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_reports_reporter_user_id", "reports", ["reporter_user_id"])
    op.create_index("ix_reports_target", "reports", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_table("reports")
