"""Order type and the years an order decides; the kind of licensee (ARR spec section 5).

Revision ID: 0014_order_type_licensee_kind
Revises: 0013_utility_on_sources
Create Date: 2026-09-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_order_type_licensee_kind"
down_revision = "0013_utility_on_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "utilities",
        sa.Column("licensee_kind", sa.String(20), nullable=False, server_default="distribution"),
    )
    op.add_column("source_documents", sa.Column("order_type", sa.String(32), nullable=True))
    op.add_column("source_documents", sa.Column("decides", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("source_documents", "decides")
    op.drop_column("source_documents", "order_type")
    op.drop_column("utilities", "licensee_kind")
