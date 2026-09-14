"""Reviewer annotations on localisation regions: note, exclusion, who and when.

Revision ID: 0010_region_annotations
Revises: 0009_publication
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_region_annotations"
down_revision = "0009_publication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("localisation_regions", sa.Column("reviewer_note", sa.Text))
    op.add_column(
        "localisation_regions",
        sa.Column("excluded", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.add_column("localisation_regions", sa.Column("annotated_by", sa.String(320)))
    op.add_column("localisation_regions", sa.Column("annotated_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    for col in ("annotated_at", "annotated_by", "excluded", "reviewer_note"):
        op.drop_column("localisation_regions", col)
