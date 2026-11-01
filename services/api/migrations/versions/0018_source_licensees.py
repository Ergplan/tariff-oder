"""Combined orders: one source for several licensees (increment 35).  A commission often
decides the ARR of all its state's distribution licensees in one order; the order's
licensees are its primary licensee (``source_documents.utility_id``) and these.

Revision ID: 0018_source_licensees
Revises: 0017_true_up_cases
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_source_licensees"
down_revision = "0017_true_up_cases"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "source_licensees",
        sa.Column("source_id", UUID, sa.ForeignKey("source_documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("utility_id", UUID, sa.ForeignKey("utilities.id"), primary_key=True),
        sa.Column("added_by", sa.String(320), nullable=False),
        sa.Column("reason", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_source_licensees_utility", "source_licensees", ["utility_id"])


def downgrade() -> None:
    op.drop_index("ix_source_licensees_utility", table_name="source_licensees")
    op.drop_table("source_licensees")
