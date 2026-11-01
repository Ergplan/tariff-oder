"""ARR read -> formulate -> file (ADR-0018): ARR candidates in the shared envelope, the ARR
track beside the tariff state machine, ARR chapters, published ARR facts, assumptions,
formulations with their projection lines, and filing drafts (draft is the only state).

Revision ID: 0015_arr_read_formulate_file
Revises: 0014_order_type_licensee_kind
Create Date: 2026-10-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_arr_read_formulate_file"
down_revision = "0014_order_type_licensee_kind"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
NOW = sa.text("now()")


def _id() -> sa.Column:
    return sa.Column("id", UUID, primary_key=True)


def _created() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False)


def upgrade() -> None:
    op.add_column("candidates", sa.Column("payload_kind", sa.String(16), nullable=False, server_default="tariff"))
    op.create_index("ix_candidates_source_payload", "candidates", ["source_id", "payload_kind"])
    op.add_column("source_documents", sa.Column("arr_state", sa.String(24)))
    op.add_column("source_documents", sa.Column("arr_summary", JSONB))

    op.create_table(
        "arr_chapters",
        _id(),
        sa.Column("source_id", UUID, sa.ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("branch", sa.String(32), nullable=False),
        sa.Column("cue_text", sa.String(300), nullable=False),
        sa.Column("cue_page", sa.Integer, nullable=False),
        sa.Column("page_start", sa.Integer, nullable=False),
        sa.Column("page_end", sa.Integer, nullable=False),
        sa.Column("origin", sa.String(16), nullable=False, server_default="detected"),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("mapping_id", sa.String(40), nullable=False),
        sa.Column("mapping_version", sa.Integer, nullable=False),
        sa.Column("decided_by", sa.String(320)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text),
        _created(),
        sa.UniqueConstraint("source_id", "ordinal", name="uq_arr_chapter"),
    )

    op.create_table(
        "arr_facts",
        _id(),
        sa.Column("utility_id", UUID, sa.ForeignKey("utilities.id"), nullable=False),
        sa.Column("source_id", UUID, sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("candidate_id", UUID, sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("line_code", sa.String(64), nullable=False),
        sa.Column("fiscal_year", sa.String(12), nullable=False),
        sa.Column("value_type", sa.String(24), nullable=False),
        sa.Column("category_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("value_state", sa.String(24), nullable=False),
        sa.Column("stated_value", sa.String(40)),
        sa.Column("stated_unit", sa.String(24)),
        sa.Column("column_label", sa.String(200)),
        sa.Column("canonical_value", sa.String(40)),
        sa.Column("canonical_unit", sa.String(24)),
        sa.Column("conversion", sa.String(60)),
        sa.Column("basis", sa.String(16)),
        sa.Column("reason_category", sa.String(24)),
        sa.Column("reasoning_quote", JSONB),
        sa.Column("regulation_clause", JSONB),
        sa.Column("evidence", JSONB, nullable=False),
        sa.Column("record", JSONB, nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False),
        sa.Column("is_fixture", sa.Boolean, nullable=False),
        sa.Column("published_by", sa.String(320), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("superseded_by_id", UUID),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_arr_fact_identity",
        "arr_facts",
        ["utility_id", "line_code", "fiscal_year", "value_type", "source_id", "category_code"],
        unique=True,
        postgresql_where=sa.text("superseded_by_id IS NULL"),
    )
    op.create_index("ix_arr_facts_history", "arr_facts", ["utility_id", "line_code", "fiscal_year"])

    op.create_table(
        "arr_assumption_sets",
        _id(),
        sa.Column("utility_id", UUID, sa.ForeignKey("utilities.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("based_on_id", UUID),
        sa.Column("created_by", sa.String(320), nullable=False),
        _created(),
        sa.Column("frozen_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("utility_id", "name", "version", name="uq_arr_assumption_set"),
        sa.CheckConstraint("status in ('draft', 'frozen')", name="ck_arr_assumption_set_status"),
    )
    op.create_table(
        "arr_assumptions",
        _id(),
        sa.Column("set_id", UUID, sa.ForeignKey("arr_assumption_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("fiscal_year", sa.String(12), nullable=False, server_default=""),
        sa.Column("value", sa.String(40), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("source_kind", sa.String(24), nullable=False),
        sa.Column("clause_ref", JSONB),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("entered_by", sa.String(320), nullable=False),
        _created(),
        sa.UniqueConstraint("set_id", "key", "fiscal_year", name="uq_arr_assumption"),
        sa.CheckConstraint("source_kind in ('user', 'regulation_clause')", name="ck_arr_assumption_source_kind"),
        sa.CheckConstraint(
            "source_kind <> 'regulation_clause' or clause_ref is not null", name="ck_arr_assumption_clause"
        ),
    )

    op.create_table(
        "arr_formulations",
        _id(),
        sa.Column("utility_id", UUID, sa.ForeignKey("utilities.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("base_fy", sa.String(12), nullable=False),
        sa.Column("targets", JSONB, nullable=False),
        sa.Column("plan_id", sa.String(40), nullable=False),
        sa.Column("plan_version", sa.Integer, nullable=False),
        sa.Column("library_version", sa.String(16), nullable=False),
        sa.Column("base_rule", JSONB, nullable=False),
        sa.Column("assumption_set_id", UUID, sa.ForeignKey("arr_assumption_sets.id"), nullable=False),
        sa.Column("inputs", JSONB, nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("summary", JSONB, nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("is_fixture", sa.Boolean, nullable=False),
        sa.Column("created_by", sa.String(320), nullable=False),
        _created(),
        sa.Column("frozen_by", sa.String(320)),
        sa.Column("frozen_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status in ('draft', 'frozen')", name="ck_arr_formulation_status"),
    )
    op.create_table(
        "arr_projection_lines",
        _id(),
        sa.Column("formulation_id", UUID, sa.ForeignKey("arr_formulations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_code", sa.String(64), nullable=False),
        sa.Column("fiscal_year", sa.String(12), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("value", sa.String(40)),
        sa.Column("unit", sa.String(24)),
        sa.Column("formula_id", sa.String(40), nullable=False),
        sa.Column("formula_version", sa.String(16), nullable=False),
        sa.Column("inputs", JSONB, nullable=False),
        sa.Column("regulation_clause", JSONB),
        sa.Column("blocked_reason", sa.Text),
        sa.UniqueConstraint("formulation_id", "line_code", "fiscal_year", name="uq_arr_projection_line"),
        sa.CheckConstraint("status in ('computed', 'blocked')", name="ck_arr_projection_status"),
    )

    op.create_table(
        "filing_drafts",
        _id(),
        sa.Column("formulation_id", UUID, sa.ForeignKey("arr_formulations.id"), nullable=False),
        sa.Column("template_id", sa.String(60), nullable=False),
        sa.Column("template_version", sa.Integer, nullable=False),
        sa.Column("template_status", sa.String(16), nullable=False),
        sa.Column("docx_key", sa.String(512), nullable=False),
        sa.Column("docx_sha256", sa.String(64), nullable=False),
        sa.Column("xlsx_key", sa.String(512), nullable=False),
        sa.Column("xlsx_sha256", sa.String(64), nullable=False),
        sa.Column("trace", JSONB, nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("is_fixture", sa.Boolean, nullable=False),
        sa.Column("generated_by", sa.String(320), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        # a filing draft is never filed: the application has no submission path
        sa.CheckConstraint("status = 'draft'", name="ck_filing_draft_only_draft"),
    )


def downgrade() -> None:
    op.drop_table("filing_drafts")
    op.drop_table("arr_projection_lines")
    op.drop_table("arr_formulations")
    op.drop_table("arr_assumptions")
    op.drop_table("arr_assumption_sets")
    op.drop_index("ix_arr_facts_history", table_name="arr_facts")
    op.drop_index("uq_arr_fact_identity", table_name="arr_facts")
    op.drop_table("arr_facts")
    op.drop_table("arr_chapters")
    op.drop_column("source_documents", "arr_summary")
    op.drop_column("source_documents", "arr_state")
    op.drop_index("ix_candidates_source_payload", table_name="candidates")
    op.drop_column("candidates", "payload_kind")
