"""Milestone 5b: data releases, published facts and evidence.

Revision ID: 0009_publication
Revises: 0008_review
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_publication"
down_revision = "0008_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_documents", sa.Column("publication_summary", postgresql.JSONB))
    op.add_column("candidates", sa.Column("published_release_id", postgresql.UUID(as_uuid=True)))
    op.create_table(
        "data_releases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("release_number", sa.Integer, nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("scope_categories", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("scope_families", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("completeness", sa.String(8), nullable=False),
        sa.Column("gaps", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("published_by", sa.String(320), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source_version", sa.Integer, nullable=False),
        sa.Column("utility", sa.String(40)),
        sa.Column("period", sa.String(80)),
        sa.Column("fact_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("candidates_in_scope", sa.Integer, nullable=False, server_default="0"),
        sa.Column("unresolved_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pending_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("awaiting_second_review_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("checklist_snapshot", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("preview_token", sa.String(64), nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("is_fixture", sa.Boolean, nullable=False),
        sa.Column("request_id", sa.String(64)),
        sa.UniqueConstraint("source_id", "release_number", name="uq_data_release_number"),
    )
    op.create_index("ix_data_releases_current", "data_releases", ["source_id", "is_current"])
    op.create_table(
        "published_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "release_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_releases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("review_status", sa.String(24), nullable=False),
        sa.Column("family", sa.String(32), nullable=False),
        sa.Column("category_code", sa.String(80)),
        sa.Column("component_type", sa.String(24), nullable=False),
        sa.Column("value", sa.String(40)),
        sa.Column("value_state", sa.String(24), nullable=False),
        sa.Column("currency", sa.String(8)),
        sa.Column("per_unit", sa.String(16)),
        sa.Column("frequency", sa.String(16)),
        sa.Column("decision_status", sa.String(40)),
        sa.Column("period", sa.String(80)),
        sa.Column("utility", sa.String(40)),
        sa.Column("applicability", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("conditions", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("derivation", postgresql.JSONB),
        sa.Column("record", postgresql.JSONB, nullable=False),
        sa.Column("is_fixture", sa.Boolean, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("release_id", "candidate_id", name="uq_published_fact_candidate"),
    )
    op.create_index("ix_published_facts_release", "published_facts", ["release_id", "family", "category_code"])
    op.create_table(
        "published_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "fact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("published_facts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("printed_label", sa.String(40)),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("grid_ordinal", sa.Integer),
        sa.Column("row", sa.Integer),
        sa.Column("col", sa.Integer),
        sa.Column("line_no", sa.Integer),
        sa.Column("header_path", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("row_path", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("clause_path", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("excerpt", sa.String(400), nullable=False),
    )
    op.create_index("ix_published_evidence_fact", "published_evidence", ["fact_id", "ordinal"])


def downgrade() -> None:
    op.drop_index("ix_published_evidence_fact", table_name="published_evidence")
    op.drop_table("published_evidence")
    op.drop_index("ix_published_facts_release", table_name="published_facts")
    op.drop_table("published_facts")
    op.drop_index("ix_data_releases_current", table_name="data_releases")
    op.drop_table("data_releases")
    op.drop_column("candidates", "published_release_id")
    op.drop_column("source_documents", "publication_summary")
