"""Milestone 2a: page triage — classification, text quality, printed-label maps, stage artefacts.

Revision ID: 0002_triage
Revises: 0001_foundation
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_triage"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `printed_label` becomes the *resolved* label; where it came from is now explicit.
    op.add_column("source_pages", sa.Column("label_declared", sa.String(40)))
    op.add_column("source_pages", sa.Column("label_observed", sa.String(40)))
    op.add_column("source_pages", sa.Column("label_source", sa.String(16), nullable=False, server_default="none"))
    op.add_column("source_pages", sa.Column("text_quality", postgresql.JSONB))
    op.add_column("source_pages", sa.Column("ocr_recommended", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("source_pages", sa.Column("triage_rationale", sa.Text))
    op.add_column("source_pages", sa.Column("triage_version", sa.String(16)))
    op.add_column("source_pages", sa.Column("triaged_at", sa.DateTime(timezone=True)))
    # Inventory only ever recorded what the PDF declared; carry that forward honestly.
    op.execute(
        "UPDATE source_pages SET label_declared = printed_label, label_source = 'declared' "
        "WHERE printed_label IS NOT NULL"
    )

    op.add_column("source_documents", sa.Column("label_rule", postgresql.JSONB))
    op.add_column("source_documents", sa.Column("page_class_counts", postgresql.JSONB))
    op.add_column("source_documents", sa.Column("triage_version", sa.String(16)))
    op.add_column("source_documents", sa.Column("triaged_at", sa.DateTime(timezone=True)))

    # Immutable per-stage artefacts (Section 6.2), keyed by source hash, stage and tool version.
    op.create_table(
        "stage_artefacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("tool", sa.String(80), nullable=False),
        sa.Column("tool_version", sa.String(40), nullable=False),
        sa.Column("page_index", sa.Integer, nullable=False, server_default="0"),  # 0 = document-level
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "stage", "tool_version", "page_index", name="uq_stage_artefact"),
    )
    op.create_index("ix_stage_artefacts_source_stage", "stage_artefacts", ["source_id", "stage"])


def downgrade() -> None:
    op.drop_index("ix_stage_artefacts_source_stage", table_name="stage_artefacts")
    op.drop_table("stage_artefacts")
    for col in ("triaged_at", "triage_version", "page_class_counts", "label_rule"):
        op.drop_column("source_documents", col)
    for col in (
        "triaged_at",
        "triage_version",
        "triage_rationale",
        "ocr_recommended",
        "text_quality",
        "label_source",
        "label_observed",
        "label_declared",
    ):
        op.drop_column("source_pages", col)
