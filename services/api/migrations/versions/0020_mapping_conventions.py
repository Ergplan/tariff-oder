"""Mapping conventions (increment 44): a reviewer's decision on how a commission composes its
printed totals — the gap convention, or a line printed inclusive of others — kept beside the
label decisions until written into the next version of the mapping file.

Revision ID: 0020_mapping_conventions
Revises: 0019_mapping_decisions
Create Date: 2026-11-01
"""

from __future__ import annotations

from alembic import op

revision = "0020_mapping_conventions"
down_revision = "0019_mapping_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_mapping_decision_kind", "mapping_decisions", type_="check")
    op.create_check_constraint(
        "ck_mapping_decision_kind", "mapping_decisions", "kind in ('alias', 'not_a_line', 'convention')"
    )
    op.create_check_constraint(
        "ck_mapping_decision_convention_value", "mapping_decisions", "kind <> 'convention' or code is not null"
    )


def downgrade() -> None:
    op.execute("DELETE FROM mapping_decisions WHERE kind = 'convention'")
    op.drop_constraint("ck_mapping_decision_convention_value", "mapping_decisions", type_="check")
    op.drop_constraint("ck_mapping_decision_kind", "mapping_decisions", type_="check")
    op.create_check_constraint("ck_mapping_decision_kind", "mapping_decisions", "kind in ('alias', 'not_a_line')")
