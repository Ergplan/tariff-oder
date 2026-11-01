"""Independent sign-off of a reference filing's reproduction (milestone 13, R-ACC-2): a named
checker's acceptance of the whole filing, a petition column or a finding's treatment, pinned to
the reproduction's SHA-256.  Append-only.

Revision ID: 0021_acceptance_records
Revises: 0020_mapping_conventions
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_acceptance_records"
down_revision = "0020_mapping_conventions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "acceptance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("filing_id", sa.String(120), nullable=False),
        sa.Column("scope", sa.String(120), nullable=False),  # filing | column:<fy>|<voice> | finding:<id>
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("reproduction_sha256", sa.String(64), nullable=False),
        sa.Column("independent", sa.Boolean, nullable=False),
        sa.Column("signed_by", sa.String(320), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "decision in ('accepted', 'accepted_with_reservations', 'rejected')", name="ck_acceptance_decision"
        ),
        sa.CheckConstraint("decision = 'accepted' or note is not null", name="ck_acceptance_note"),
        sa.CheckConstraint("independent", name="ck_acceptance_independent"),
    )
    op.create_index("ix_acceptance_records_filing_id", "acceptance_records", ["filing_id"])


def downgrade() -> None:
    op.drop_index("ix_acceptance_records_filing_id", table_name="acceptance_records")
    op.drop_table("acceptance_records")
