"""Milestone 3b: structure integrity — grid cells with header/row paths and unit bindings,
clause-outline values, source structure summary.

Revision ID: 0005_gridded
Revises: 0004_localise
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_gridded"
down_revision = "0004_localise"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_documents", sa.Column("structure_version", sa.String(40)))
    op.add_column("source_documents", sa.Column("gridded_at", sa.DateTime(timezone=True)))
    op.add_column("source_documents", sa.Column("structure_summary", postgresql.JSONB))
    op.create_table(
        "structure_cells",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("region_role", sa.String(32), nullable=False),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("grid_ordinal", sa.Integer, nullable=False),
        sa.Column("row", sa.Integer, nullable=False),
        sa.Column("col", sa.Integer, nullable=False),
        sa.Column("raw", sa.String(300), nullable=False),
        sa.Column("header_path", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("row_path", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("normalised", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("value_state", sa.String(24), nullable=False),
        sa.Column("currency", sa.String(8)),
        sa.Column("per_unit", sa.String(16)),
        sa.Column("frequency", sa.String(16)),
        sa.Column("unit_source", sa.String(24)),
        sa.Column("flags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("footnotes", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("slab", postgresql.JSONB),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("rules_version", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "page_index", "grid_ordinal", "row", "col", name="uq_structure_cell"),
    )
    op.create_index("ix_structure_cells_source_page", "structure_cells", ["source_id", "page_index"])
    op.create_table(
        "clause_values",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("region_role", sa.String(32), nullable=False),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("category_code", sa.String(80)),
        sa.Column("clause_path", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("connector", sa.String(16)),
        sa.Column("alternative", sa.Integer, nullable=False, server_default="0"),
        sa.Column("line_text", sa.String(400), nullable=False),
        sa.Column("normalised", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("dimension", postgresql.JSONB),
        sa.Column("slab", postgresql.JSONB),
        sa.Column("time_window", sa.String(24)),
        sa.Column("sign", sa.Integer),
        sa.Column("parameters", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("rules_version", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "page_index", "line_no", "ordinal", name="uq_clause_value"),
    )
    op.create_index("ix_clause_values_source_category", "clause_values", ["source_id", "category_code"])


def downgrade() -> None:
    op.drop_index("ix_clause_values_source_category", table_name="clause_values")
    op.drop_table("clause_values")
    op.drop_index("ix_structure_cells_source_page", table_name="structure_cells")
    op.drop_table("structure_cells")
    for col in ("structure_summary", "gridded_at", "structure_version"):
        op.drop_column("source_documents", col)
