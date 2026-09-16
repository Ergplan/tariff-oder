"""Generated category summaries (reviewer context, grounding-checked, never a fact).

Revision ID: 0011_category_summaries
Revises: 0010_region_annotations
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_category_summaries"
down_revision = "0010_region_annotations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "category_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category_code", sa.String(40), nullable=False),
        sa.Column("heading_text", sa.String(300)),
        sa.Column("page_indices", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(16), nullable=False),
        sa.Column("is_fixture", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("grounded", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("unsupported_numbers", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("candidate_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("extraction_version", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "category_code", name="uq_category_summary"),
    )


def downgrade() -> None:
    op.drop_table("category_summaries")
