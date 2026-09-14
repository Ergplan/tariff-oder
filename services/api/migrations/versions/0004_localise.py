"""Milestone 3a: reading-profile binding and binding-schedule localisation.

Revision ID: 0004_localise
Revises: 0003_parse
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_localise"
down_revision = "0003_parse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_documents", sa.Column("reading_profile_id", sa.String(64)))
    op.add_column("source_documents", sa.Column("reading_profile_version", sa.Integer))
    op.add_column("source_documents", sa.Column("reading_profile_source", sa.String(16)))
    op.add_column("source_documents", sa.Column("reading_profile_rationale", sa.Text))
    op.add_column("source_documents", sa.Column("localisation_version", sa.String(16)))
    op.add_column("source_documents", sa.Column("localised_at", sa.DateTime(timezone=True)))

    op.create_table(
        "localisation_records",
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rules_version", sa.String(16), nullable=False),
        sa.Column("profile_ref", sa.String(80), nullable=False),
        sa.Column("findings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("extraction_allowed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("decided_by", sa.String(320)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_rationale", sa.Text),
        sa.Column("decision_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("artefact_key", sa.String(512)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "localisation_regions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("sub_role", sa.String(32)),
        sa.Column("page_start", sa.Integer, nullable=False),
        sa.Column("page_end", sa.Integer, nullable=False),
        sa.Column("cue_text", sa.String(300), nullable=False),
        sa.Column("cue_page", sa.Integer, nullable=False),
        sa.Column("cue_kind", sa.String(16), nullable=False),
        sa.Column("utility", sa.String(40)),
        sa.Column("period", sa.String(80)),
        sa.Column("note", sa.Text),
        sa.Column("origin", sa.String(16), nullable=False, server_default="detected"),
        sa.Column("grid_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "ordinal", name="uq_localisation_region"),
    )
    op.create_index("ix_localisation_regions_source_role", "localisation_regions", ["source_id", "role"])


def downgrade() -> None:
    op.drop_index("ix_localisation_regions_source_role", table_name="localisation_regions")
    op.drop_table("localisation_regions")
    op.drop_table("localisation_records")
    for col in (
        "localised_at",
        "localisation_version",
        "reading_profile_rationale",
        "reading_profile_source",
        "reading_profile_version",
        "reading_profile_id",
    ):
        op.drop_column("source_documents", col)
