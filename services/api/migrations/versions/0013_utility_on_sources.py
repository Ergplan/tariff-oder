"""Sources belong to a utility; commissions carry a responsible reviewer (increment 20).

Revision ID: 0013_utility_on_sources
Revises: 0012_review_assignment
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_utility_on_sources"
down_revision = "0012_review_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column("utility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("utilities.id"), nullable=True),
    )
    op.create_index("ix_source_documents_utility_id", "source_documents", ["utility_id"])
    op.add_column("commissions", sa.Column("assigned_to", sa.String(320)))


def downgrade() -> None:
    op.drop_column("commissions", "assigned_to")
    op.drop_index("ix_source_documents_utility_id", table_name="source_documents")
    op.drop_column("source_documents", "utility_id")
