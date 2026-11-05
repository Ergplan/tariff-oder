"""Petition workbooks (increment 151): a case's formats workbooks — the inputs a petitioner
uploads, and the workbook the rule engine fills from them (``tariff_api.arr.petition_fill``),
with the fill's summary.  A filled workbook is a working draft from draft rules: the schema
allows no status that files anything.

Revision ID: 0022_petition_workbooks
Revises: 0021_acceptance_records
Create Date: 2026-11-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_petition_workbooks"
down_revision = "0021_acceptance_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "petition_workbooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("arr_cases.id"), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),  # inputs | filled
        sa.Column("package", sa.String(120), nullable=False),  # the reference filing giving the layout
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        sa.Column("inputs_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("petition_workbooks.id"), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("summary", postgresql.JSONB, nullable=True),
        sa.Column("report_key", sa.String(512), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role in ('inputs', 'filled')", name="ck_petition_workbook_role"),
        sa.CheckConstraint(
            "status in ('stored', 'queued', 'running', 'filled', 'failed')", name="ck_petition_workbook_status"
        ),
        sa.CheckConstraint("role = 'inputs' or inputs_id is not null", name="ck_petition_workbook_filled_from"),
    )
    op.create_index("ix_petition_workbooks_case_id", "petition_workbooks", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_petition_workbooks_case_id", table_name="petition_workbooks")
    op.drop_table("petition_workbooks")
