"""Milestone 1 foundation: datasets, users, registry, sources, pages, jobs, audit.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None

dataset_kind = postgresql.ENUM("real", "fixture", name="dataset_kind", create_type=False)
user_role = postgresql.ENUM("analyst", "reviewer", "administrator", name="user_role", create_type=False)
jurisdiction_kind = postgresql.ENUM("state", "union_territory", name="jurisdiction_kind", create_type=False)
source_state = postgresql.ENUM(
    "uploaded",
    "inventoried",
    "triaged",
    "parsed",
    "localised",
    "gridded",
    "extracted",
    "validated",
    "awaiting_review",
    "published",
    "failed",
    "cancelled",
    "rejected",
    "superseded",
    "needs_reprocessing",
    name="source_state",
    create_type=False,
)
job_status = postgresql.ENUM(
    "queued", "leased", "succeeded", "failed", "cancelled", name="job_status", create_type=False
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    for enum in (dataset_kind, user_role, jurisdiction_kind, source_state, job_status):
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", dataset_kind, nullable=False),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200)),
        sa.Column("role", user_role, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "jurisdictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", jurisdiction_kind, nullable=False),
        sa.Column("aliases", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "commissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("jurisdiction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jurisdictions.id"), nullable=False),
        sa.Column("aliases", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "utilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("commission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("commissions.id"), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("licensed_area", sa.Text),
        sa.Column("aliases", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("active_reading_profile", sa.String(120)),
        sa.Column("active_reading_profile_version", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "source_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False, server_default="application/pdf"),
        sa.Column("provenance_url", sa.Text),
        sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("uploaded_by", sa.String(320), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("state", source_state, nullable=False, server_default="uploaded"),
        sa.Column("state_reason", sa.Text),
        sa.Column("page_count", sa.Integer),
        sa.Column("pdf_version", sa.String(16)),
        sa.Column("producer", sa.String(300)),
        sa.Column("creator", sa.String(300)),
        sa.Column("is_encrypted", sa.Boolean),
        sa.Column("is_tagged", sa.Boolean),
        sa.Column("fonts_total", sa.Integer),
        sa.Column("fonts_not_embedded", postgresql.JSONB),
        sa.Column("pages_with_text", sa.Integer),
        sa.Column("pages_without_text", sa.Integer),
        sa.Column("inventory_tool", sa.String(80)),
        sa.Column("inventory_tool_version", sa.String(40)),
        sa.Column("inventoried_at", sa.DateTime(timezone=True)),
        sa.Column("golden_id", sa.String(80)),
        sa.Column("manifest_check", postgresql.JSONB),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_documents.id")),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "source_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("printed_label", sa.String(40)),
        sa.Column("width_pt", sa.Float),
        sa.Column("height_pt", sa.Float),
        sa.Column("rotation", sa.Integer, nullable=False, server_default="0"),
        sa.Column("text_chars", sa.Integer, nullable=False, server_default="0"),
        sa.Column("has_text_layer", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("image_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("drawing_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("page_class", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("page_role", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("quality_flags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_id", "page_index", name="uq_source_page"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("idempotency_key", sa.String(300), nullable=False, unique=True),
        sa.Column("status", job_status, nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_owner", sa.String(200)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("stage", sa.String(80)),
        sa.Column("checkpoint", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("progress", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("cancel_requested", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("error_type", sa.String(80)),
        sa.Column("error_message", sa.Text),
        sa.Column(
            "source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_documents.id", ondelete="SET NULL")
        ),
        sa.Column("created_by", sa.String(320)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_jobs_claim", "jobs", ["status", "available_at", "priority"])
    op.create_index("ix_jobs_source", "jobs", ["source_id"])
    op.create_table(
        "job_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("worker", sa.String(200)),
        sa.Column("detail", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_job_events_job", "job_events", ["job_id", "at"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(320), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=False),
        sa.Column("before", postgresql.JSONB),
        sa.Column("after", postgresql.JSONB),
        sa.Column("reason", sa.Text),
        sa.Column("request_id", sa.String(64)),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_entity", "audit_events", ["entity_type", "entity_id"])
    op.create_table(
        "idempotency_records",
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("actor", sa.String(320), primary_key=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False),
        sa.Column("response_body", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Audit events are append-only: no UPDATE or DELETE from any role.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER audit_events_no_update BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();
        """
    )
    # Fixture/real isolation: a utility's dataset kind and a source's dataset kind are
    # enforced by dataset_id foreign keys; the datasets table holds exactly one row per kind.
    op.execute("CREATE UNIQUE INDEX uq_datasets_kind ON datasets (kind)")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_immutable")
    for t in (
        "idempotency_records",
        "audit_events",
        "job_events",
        "jobs",
        "source_pages",
        "source_documents",
        "utilities",
        "commissions",
        "jurisdictions",
        "users",
        "datasets",
    ):
        op.drop_table(t)
    for enum in (job_status, source_state, jurisdiction_kind, user_role, dataset_kind):
        enum.drop(op.get_bind(), checkfirst=True)
