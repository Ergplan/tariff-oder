"""The client application (ADR-0019): organisations and their members, organisation-owned
ARR objects, ARR cases, and the regulatory library of expected and acquired documents.

Revision ID: 0016_client_application
Revises: 0015_arr_read_formulate_file
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_client_application"
down_revision = "0015_arr_read_formulate_file"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )
    op.create_table(
        "organisation_members",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organisation_id", UUID, sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("added_by", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.UniqueConstraint("organisation_id", "email", name="uq_organisation_member"),
        sa.CheckConstraint("role in ('owner', 'editor', 'viewer')", name="ck_organisation_member_role"),
    )
    op.create_index("ix_organisation_members_email", "organisation_members", ["email"])
    for table in ("arr_assumption_sets", "arr_formulations"):
        op.add_column(table, sa.Column("organisation_id", UUID, sa.ForeignKey("organisations.id")))
        op.create_index(f"ix_{table}_organisation", table, ["organisation_id"])
    # set names are per owner: two organisations may each have "Base case" v1
    op.drop_constraint("uq_arr_assumption_set", "arr_assumption_sets", type_="unique")
    op.create_index(
        "uq_arr_assumption_set_owner",
        "arr_assumption_sets",
        [
            "utility_id",
            sa.text("coalesce(organisation_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "name",
            "version",
        ],
        unique=True,
    )

    op.create_table(
        "arr_cases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organisation_id", UUID, sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("utility_id", UUID, sa.ForeignKey("utilities.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("filing_kind", sa.String(16), nullable=False),
        sa.Column("base_fy", sa.String(12), nullable=False),
        sa.Column("targets", JSONB, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="setup"),
        sa.Column("assumption_set_id", UUID, sa.ForeignKey("arr_assumption_sets.id"), nullable=False),
        sa.Column("formulation_id", UUID, sa.ForeignKey("arr_formulations.id")),
        sa.Column("draft_id", UUID, sa.ForeignKey("filing_drafts.id")),
        sa.Column("notes", sa.Text),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("filing_kind in ('annual_arr', 'myt')", name="ck_arr_case_kind"),
        sa.CheckConstraint(
            "status in ('setup', 'assumptions', 'formulated', 'frozen', 'drafted', 'closed')",
            name="ck_arr_case_status",
        ),
    )
    op.create_index("ix_arr_cases_organisation", "arr_cases", ["organisation_id", "status"])

    op.create_table(
        "library_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("commission_id", UUID, sa.ForeignKey("commissions.id"), nullable=False),
        sa.Column("utility_id", UUID, sa.ForeignKey("utilities.id")),
        sa.Column("document_kind", sa.String(32), nullable=False),
        sa.Column("fiscal_year", sa.String(12), nullable=False, server_default=""),
        sa.Column("title", sa.String(300)),
        sa.Column("url", sa.Text),
        sa.Column("status", sa.String(12), nullable=False, server_default="expected"),
        sa.Column("origin", sa.String(12), nullable=False, server_default="seeded"),
        sa.Column("source_id", UUID, sa.ForeignKey("source_documents.id")),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text),
        sa.Column("updated_by", sa.String(320)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("status in ('expected', 'located', 'acquired', 'failed')", name="ck_library_entry_status"),
    )
    # one slot per (commission, licensee or none, kind, year)
    op.create_index(
        "uq_library_entry_slot",
        "library_entries",
        [
            "commission_id",
            sa.text("coalesce(utility_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "document_kind",
            "fiscal_year",
        ],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_library_entry_slot", table_name="library_entries")
    op.drop_table("library_entries")
    op.drop_index("ix_arr_cases_organisation", table_name="arr_cases")
    op.drop_table("arr_cases")
    op.drop_index("uq_arr_assumption_set_owner", table_name="arr_assumption_sets")
    op.create_unique_constraint("uq_arr_assumption_set", "arr_assumption_sets", ["utility_id", "name", "version"])
    for table in ("arr_formulations", "arr_assumption_sets"):
        op.drop_index(f"ix_{table}_organisation", table_name=table)
        op.drop_column(table, "organisation_id")
    op.drop_index("ix_organisation_members_email", table_name="organisation_members")
    op.drop_table("organisation_members")
    op.drop_table("organisations")
