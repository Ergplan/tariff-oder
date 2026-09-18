"""Reviewer assignment on sources (increment 19).

Revision ID: 0012_review_assignment
Revises: 0011_category_summaries
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_review_assignment"
down_revision = "0011_category_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_documents", sa.Column("assigned_to", sa.String(320)))
    op.create_index("ix_source_documents_assigned_to", "source_documents", ["assigned_to"])


def downgrade() -> None:
    op.drop_index("ix_source_documents_assigned_to", table_name="source_documents")
    op.drop_column("source_documents", "assigned_to")
