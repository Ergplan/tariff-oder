"""True-up and APR cases (ADR-0020): a case kind that sets the licensee's actuals of a past
or current year against the commission's approval, each actual with its source, and drafts
from a frozen variance statement.

Revision ID: 0017_true_up_cases
Revises: 0016_client_application
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_true_up_cases"
down_revision = "0016_client_application"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
NOW = sa.text("now()")


def upgrade() -> None:
    op.drop_constraint("ck_arr_case_kind", "arr_cases", type_="check")
    op.create_check_constraint(
        "ck_arr_case_kind", "arr_cases", "filing_kind in ('annual_arr', 'myt', 'true_up', 'apr')"
    )
    # the frozen (or last computed) variance statement of a true-up or APR case
    op.add_column("arr_cases", sa.Column("statement", JSONB, nullable=True))

    op.create_table(
        "arr_actuals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("case_id", UUID, sa.ForeignKey("arr_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_code", sa.String(40), nullable=False),
        sa.Column("fiscal_year", sa.String(12), nullable=False),
        sa.Column("stated_value", sa.String(40), nullable=False),
        sa.Column("stated_unit", sa.String(24), nullable=False),
        sa.Column("canonical_value", sa.String(40), nullable=True),
        sa.Column("canonical_unit", sa.String(24), nullable=True),
        sa.Column("conversion", sa.String(80), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("fact_id", UUID, sa.ForeignKey("arr_facts.id"), nullable=True),
        sa.Column("source_id", UUID, sa.ForeignKey("source_documents.id"), nullable=True),
        sa.Column("page_index", sa.Integer, nullable=True),
        sa.Column("excerpt", sa.Text, nullable=True),
        sa.Column("document_name", sa.String(300), nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("entered_by", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.UniqueConstraint("case_id", "line_code", "fiscal_year", name="uq_arr_actual"),
        sa.CheckConstraint(
            "source_kind in ('fact', 'document', 'statement', 'estimate')", name="ck_arr_actual_source_kind"
        ),
        sa.CheckConstraint("source_kind <> 'fact' or fact_id is not null", name="ck_arr_actual_fact"),
        sa.CheckConstraint(
            "source_kind <> 'document' or (source_id is not null and page_index is not null and excerpt is not null)",
            name="ck_arr_actual_document",
        ),
        sa.CheckConstraint(
            "source_kind not in ('statement', 'estimate') or (rationale is not null and document_name is not null)",
            name="ck_arr_actual_statement",
        ),
    )

    # a draft is drafted from a frozen formulation (ARR, MYT) or a frozen case statement
    # (true-up, APR)
    op.alter_column("filing_drafts", "formulation_id", nullable=True)
    op.add_column("filing_drafts", sa.Column("case_id", UUID, sa.ForeignKey("arr_cases.id"), nullable=True))
    op.create_check_constraint(
        "ck_filing_draft_origin", "filing_drafts", "formulation_id is not null or case_id is not null"
    )


def downgrade() -> None:
    op.drop_constraint("ck_filing_draft_origin", "filing_drafts", type_="check")
    op.execute("update arr_cases set draft_id = null where filing_kind in ('true_up', 'apr')")
    op.execute("delete from filing_drafts where formulation_id is null")
    op.drop_column("filing_drafts", "case_id")
    op.alter_column("filing_drafts", "formulation_id", nullable=False)
    op.drop_table("arr_actuals")
    op.drop_column("arr_cases", "statement")
    op.execute("delete from arr_cases where filing_kind in ('true_up', 'apr')")
    op.drop_constraint("ck_arr_case_kind", "arr_cases", type_="check")
    op.create_check_constraint("ck_arr_case_kind", "arr_cases", "filing_kind in ('annual_arr', 'myt')")
