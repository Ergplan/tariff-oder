"""The mapping workbench (increment 39): a reviewer's decisions on a commission's unplaced row
labels, kept until they are written into the next version of the commission's mapping file.

Revision ID: 0019_mapping_decisions
Revises: 0018_source_licensees
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_mapping_decisions"
down_revision = "0018_source_licensees"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mapping_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("commission_code", sa.String(32), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),  # normalised, as the placer compares it
        sa.Column("example", sa.Text, nullable=True),  # one printed form, with its page
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("code", sa.String(40), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("decided_by", sa.String(320), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("commission_code", "label", name="uq_mapping_decision"),
        sa.CheckConstraint("kind in ('alias', 'not_a_line')", name="ck_mapping_decision_kind"),
        sa.CheckConstraint("kind <> 'alias' or code is not null", name="ck_mapping_decision_alias_code"),
    )


def downgrade() -> None:
    op.drop_table("mapping_decisions")
