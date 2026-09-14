"""Milestone 4a: extraction runs, candidates, validator findings, family dispositions.

Revision ID: 0006_candidates
Revises: 0005_gridded
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_candidates"
down_revision = "0005_gridded"
branch_labels = None
depends_on = None


def _src_fk():
    return sa.Column(
        "source_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    for col in (
        sa.Column("extraction_version", sa.String(80)),
        sa.Column("extracted_at", sa.DateTime(timezone=True)),
        sa.Column("extraction_summary", postgresql.JSONB),
        sa.Column("validators_version", sa.String(16)),
        sa.Column("validated_at", sa.DateTime(timezone=True)),
        sa.Column("validation_summary", postgresql.JSONB),
    ):
        op.add_column("source_documents", col)
    op.create_table(
        "extraction_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _src_fk(),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("region_ordinal", sa.Integer, nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(16), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("is_fixture", sa.Boolean, nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("candidates_returned", sa.Integer, nullable=False, server_default="0"),
        sa.Column("artefact_key", sa.String(512)),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_extraction_runs_source", "extraction_runs", ["source_id", "started_at"])
    op.create_table(
        "candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _src_fk(),
        sa.Column("candidate_key", sa.String(400), nullable=False),
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
        sa.Column("record", postgresql.JSONB, nullable=False),
        sa.Column("image_record", postgresql.JSONB),
        sa.Column("channel_agreement", sa.String(16), nullable=False),
        sa.Column("disagreeing_fields", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("confidence", sa.String(8), nullable=False),
        sa.Column("risk_tags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("routing", sa.String(16), nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("is_fixture", sa.Boolean, nullable=False),
        sa.Column("structure_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("image_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("extraction_version", sa.String(80), nullable=False),
        sa.Column("finding_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("blocking_finding_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_candidates_source_family", "candidates", ["source_id", "family"])
    op.create_index("ix_candidates_routing", "candidates", ["routing", "review_status"])
    op.create_table(
        "validator_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _src_fk(),
        sa.Column("validator_id", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("candidate_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("detail", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("validators_version", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_validator_findings_source", "validator_findings", ["source_id", "validator_id"])
    op.create_table(
        "family_dispositions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _src_fk(),
        sa.Column("family", sa.String(32), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("decided_by", sa.String(320), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "family", name="uq_family_disposition"),
    )


def downgrade() -> None:
    op.drop_table("family_dispositions")
    op.drop_index("ix_validator_findings_source", table_name="validator_findings")
    op.drop_table("validator_findings")
    op.drop_index("ix_candidates_routing", table_name="candidates")
    op.drop_index("ix_candidates_source_family", table_name="candidates")
    op.drop_table("candidates")
    op.drop_index("ix_extraction_runs_source", table_name="extraction_runs")
    op.drop_table("extraction_runs")
    for col in (
        "validation_summary",
        "validated_at",
        "validators_version",
        "extraction_summary",
        "extracted_at",
        "extraction_version",
    ):
        op.drop_column("source_documents", col)
