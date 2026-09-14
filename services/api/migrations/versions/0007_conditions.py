"""Milestone 4b: condition records.

Revision ID: 0007_conditions
Revises: 0006_candidates
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_conditions"
down_revision = "0006_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "condition_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("line_no", sa.Integer, nullable=False, server_default="0"),
        sa.Column("number", sa.String(16)),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("scope_codes", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("interpretation_status", sa.String(16), nullable=False, server_default="verbatim_only"),
        sa.Column("extraction_version", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "page_index", "line_no", "kind", "text_hash", name="uq_condition_record"),
    )
    op.create_index("ix_condition_records_source", "condition_records", ["source_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_condition_records_source", table_name="condition_records")
    op.drop_table("condition_records")
