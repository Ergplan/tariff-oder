"""Milestone 2b: OCR results, table grids with reader agreement, document heading inventory.

Revision ID: 0003_parse
Revises: 0002_triage
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_parse"
down_revision = "0002_triage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The parse stage records a composite tool version (pymupdf+pdfplumber+tesseract+rules),
    # longer than the 40 characters 0002 allowed for a single tool.
    op.alter_column("stage_artefacts", "tool_version", type_=sa.String(160), existing_type=sa.String(40))

    op.add_column("source_pages", sa.Column("ocr_used", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("source_pages", sa.Column("ocr_engine", sa.String(80)))
    op.add_column("source_pages", sa.Column("ocr_confidence", sa.Float))
    op.add_column("source_pages", sa.Column("ocr_word_count", sa.Integer))
    op.add_column("source_pages", sa.Column("ocr_text_chars", sa.Integer))
    op.add_column("source_pages", sa.Column("ocr_agreement", sa.Float))  # vs the text layer, when both exist
    op.add_column("source_pages", sa.Column("parse_version", sa.String(16)))
    op.add_column("source_pages", sa.Column("parsed_at", sa.DateTime(timezone=True)))

    op.add_column("source_documents", sa.Column("parse_version", sa.String(16)))
    op.add_column("source_documents", sa.Column("parsed_at", sa.DateTime(timezone=True)))
    op.add_column("source_documents", sa.Column("heading_inventory", postgresql.JSONB))
    op.add_column("source_documents", sa.Column("table_summary", postgresql.JSONB))

    op.create_table(
        "table_grids",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("reader", sa.String(40), nullable=False),
        sa.Column("reader_version", sa.String(40), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("strategy", sa.String(16), nullable=False),
        sa.Column("bbox", postgresql.JSONB, nullable=False),
        sa.Column("row_count", sa.Integer, nullable=False),
        sa.Column("col_count", sa.Integer, nullable=False),
        sa.Column("header_rows", sa.Integer, nullable=False),
        sa.Column("is_empty", sa.Boolean, nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False),
        sa.Column("agreement_class", sa.String(40)),
        sa.Column("agreement_score", sa.Float),
        sa.Column("paired_ordinal", sa.Integer),
        sa.Column("disagreeing_cells", sa.Integer, nullable=False, server_default="0"),
        sa.Column("risk_tags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "page_index", "reader", "reader_version", "ordinal", name="uq_table_grid"),
    )
    op.create_index("ix_table_grids_source_page", "table_grids", ["source_id", "page_index"])

    op.create_table(
        "document_headings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),  # document-wide order
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("code_raw", sa.String(80)),
        sa.Column("code_canonical", sa.String(80)),
        sa.Column("text", sa.String(200), nullable=False),
        sa.Column("text_source", sa.String(16), nullable=False),  # text_layer | ocr
        sa.Column("rules_version", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "page_index", "line_no", "kind", "rules_version", name="uq_document_heading"),
    )
    op.create_index("ix_document_headings_source", "document_headings", ["source_id", "ordinal"])


def downgrade() -> None:
    # The parse stage's artefact index rows carry composite tool versions that do not fit the
    # 0002 column; they belong to this revision's feature and go with it (object storage keeps
    # the immutable artefacts themselves).
    op.execute("DELETE FROM stage_artefacts WHERE stage = 'parse' OR length(tool_version) > 40")
    op.alter_column("stage_artefacts", "tool_version", type_=sa.String(40), existing_type=sa.String(160))
    op.drop_index("ix_document_headings_source", table_name="document_headings")
    op.drop_table("document_headings")
    op.drop_index("ix_table_grids_source_page", table_name="table_grids")
    op.drop_table("table_grids")
    for col in ("table_summary", "heading_inventory", "parsed_at", "parse_version"):
        op.drop_column("source_documents", col)
    for col in (
        "parsed_at",
        "parse_version",
        "ocr_agreement",
        "ocr_text_chars",
        "ocr_word_count",
        "ocr_confidence",
        "ocr_engine",
        "ocr_used",
    ):
        op.drop_column("source_pages", col)
