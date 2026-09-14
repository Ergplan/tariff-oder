"""Milestone 5a: review decisions, evidence views, reviewed candidate state.

Revision ID: 0008_review
Revises: 0007_conditions
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_review"
down_revision = "0007_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("reviewed_record", postgresql.JSONB))
    op.add_column("candidates", sa.Column("reviewed_by", sa.String(320)))
    op.add_column("candidates", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.add_column("candidates", sa.Column("first_reviewer", sa.String(320)))
    op.add_column(
        "candidates", sa.Column("second_review", sa.String(16), nullable=False, server_default="not_required")
    )
    op.add_column("candidates", sa.Column("decision_count", sa.Integer, nullable=False, server_default="0"))
    op.create_table(
        "evidence_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_index", sa.Integer, nullable=False),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("viewer", sa.String(320), nullable=False),
        sa.Column("dpi", sa.Integer, nullable=False),
        sa.Column("highlighted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("rendered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_evidence_views_candidate", "evidence_views", ["candidate_id", "viewer"])
    op.create_table(
        "review_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("review_round", sa.Integer, nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("reviewer", sa.String(320), nullable=False),
        sa.Column("candidate_version", sa.Integer, nullable=False),
        sa.Column("rationale", sa.Text),
        sa.Column("cause_tag", sa.String(24)),
        sa.Column("corrected_record", postgresql.JSONB),
        sa.Column("corrected_fields", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("evidence_view_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("evidence_viewed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("time_spent_ms", sa.Integer),
        sa.Column("view_to_decision_ms", sa.Integer),
        sa.Column("before", postgresql.JSONB, nullable=False),
        sa.Column("after", postgresql.JSONB, nullable=False),
        sa.Column("undone", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("undone_by", sa.String(320)),
        sa.Column("undone_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(200)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reviewer", "idempotency_key", name="uq_review_decision_idempotency"),
    )
    op.create_index("ix_review_decisions_candidate", "review_decisions", ["candidate_id", "sequence"])
    op.create_index("ix_review_decisions_source", "review_decisions", ["source_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_review_decisions_source", table_name="review_decisions")
    op.drop_index("ix_review_decisions_candidate", table_name="review_decisions")
    op.drop_table("review_decisions")
    op.drop_index("ix_evidence_views_candidate", table_name="evidence_views")
    op.drop_table("evidence_views")
    for col in ("decision_count", "second_review", "first_reviewer", "reviewed_at", "reviewed_by", "reviewed_record"):
        op.drop_column("candidates", col)
