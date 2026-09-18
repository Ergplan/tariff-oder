"""Authoritative relational model (Milestone 1 scope of Section 5.2).

This module is the single schema definition; Alembic migrations under
``services/api/migrations`` are the only way the schema changes.  Later milestones add
regulatory orders, schedule versions, categories, components, candidates, facts, review
decisions and evidence spans; nothing here anticipates them beyond stable identities.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class DatasetKind(str, enum.Enum):
    """Fixture and real data are isolated (working agreement 12)."""

    real = "real"
    fixture = "fixture"


class UserRole(str, enum.Enum):
    analyst = "analyst"
    reviewer = "reviewer"
    administrator = "administrator"


class JurisdictionKind(str, enum.Enum):
    state = "state"
    union_territory = "union_territory"


class SourceState(str, enum.Enum):
    """Pipeline state machine of Section 6.2.  Milestone 1 uses uploaded -> inventoried."""

    uploaded = "uploaded"
    inventoried = "inventoried"
    triaged = "triaged"
    parsed = "parsed"
    localised = "localised"
    gridded = "gridded"
    extracted = "extracted"
    validated = "validated"
    awaiting_review = "awaiting_review"
    published = "published"
    failed = "failed"
    cancelled = "cancelled"
    rejected = "rejected"
    superseded = "superseded"
    needs_reprocessing = "needs_reprocessing"


# Allowed transitions.  A transition not listed here raises ``invalid_transition``.
SOURCE_TRANSITIONS: dict[SourceState, set[SourceState]] = {
    SourceState.uploaded: {SourceState.inventoried, SourceState.failed, SourceState.cancelled},
    SourceState.inventoried: {
        SourceState.triaged,
        SourceState.failed,
        SourceState.needs_reprocessing,
        SourceState.superseded,
    },
    SourceState.triaged: {
        SourceState.parsed,
        SourceState.failed,
        SourceState.needs_reprocessing,
        SourceState.superseded,
    },
    SourceState.parsed: {
        SourceState.localised,
        SourceState.failed,
        SourceState.needs_reprocessing,
        SourceState.superseded,
    },
    SourceState.localised: {
        SourceState.gridded,
        SourceState.failed,
        SourceState.needs_reprocessing,
        SourceState.superseded,
    },
    SourceState.gridded: {
        SourceState.extracted,
        SourceState.failed,
        SourceState.needs_reprocessing,
        SourceState.superseded,
    },
    SourceState.extracted: {
        SourceState.validated,
        SourceState.failed,
        SourceState.needs_reprocessing,
        SourceState.superseded,
    },
    SourceState.validated: {
        SourceState.awaiting_review,
        SourceState.failed,
        SourceState.needs_reprocessing,
        SourceState.superseded,
    },
    SourceState.awaiting_review: {
        SourceState.published,
        SourceState.rejected,
        SourceState.needs_reprocessing,
        SourceState.superseded,
    },
    SourceState.published: {SourceState.superseded, SourceState.needs_reprocessing},
    SourceState.failed: {SourceState.uploaded, SourceState.needs_reprocessing, SourceState.cancelled},
    SourceState.needs_reprocessing: {
        SourceState.uploaded,
        SourceState.inventoried,
        SourceState.triaged,
        SourceState.parsed,
        SourceState.localised,
        SourceState.gridded,
        SourceState.extracted,
        SourceState.cancelled,
    },
    SourceState.cancelled: set(),
    SourceState.rejected: {SourceState.needs_reprocessing},
    SourceState.superseded: set(),
}


class JobStatus(str, enum.Enum):
    queued = "queued"
    leased = "leased"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    kind: Mapped[DatasetKind] = mapped_column(Enum(DatasetKind, name="dataset_kind"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[JurisdictionKind] = mapped_column(Enum(JurisdictionKind, name="jurisdiction_kind"), nullable=False)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    commissions: Mapped[list[Commission]] = relationship(back_populates="jurisdiction")


class Commission(Base):
    __tablename__ = "commissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jurisdictions.id"), nullable=False)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    jurisdiction: Mapped[Jurisdiction] = relationship(back_populates="commissions")
    utilities: Mapped[list[Utility]] = relationship(back_populates="commission")


class Utility(Base):
    __tablename__ = "utilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    commission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("commissions.id"), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    licensed_area: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    active_reading_profile: Mapped[str | None] = mapped_column(String(120))
    active_reading_profile_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    commission: Mapped[Commission] = relationship(back_populates="utilities")
    dataset: Mapped[Dataset] = relationship()


class SourceDocument(Base):
    """An immutable uploaded file identified by its content hash."""

    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="application/pdf")
    provenance_url: Mapped[str | None] = mapped_column(Text)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(320), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[SourceState] = mapped_column(
        Enum(SourceState, name="source_state"), nullable=False, default=SourceState.uploaded
    )
    state_reason: Mapped[str | None] = mapped_column(Text)

    # Document-level inventory (filled by the inventory stage; null until then)
    page_count: Mapped[int | None] = mapped_column(Integer)
    pdf_version: Mapped[str | None] = mapped_column(String(16))
    producer: Mapped[str | None] = mapped_column(String(300))
    creator: Mapped[str | None] = mapped_column(String(300))
    is_encrypted: Mapped[bool | None] = mapped_column(Boolean)
    is_tagged: Mapped[bool | None] = mapped_column(Boolean)
    fonts_total: Mapped[int | None] = mapped_column(Integer)
    fonts_not_embedded: Mapped[list | None] = mapped_column(JSONB)
    pages_with_text: Mapped[int | None] = mapped_column(Integer)
    pages_without_text: Mapped[int | None] = mapped_column(Integer)
    inventory_tool: Mapped[str | None] = mapped_column(String(80))
    inventory_tool_version: Mapped[str | None] = mapped_column(String(40))
    inventoried_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Triage (Milestone 2a): the printed-label rule as explicit segments, class histogram, provenance
    label_rule: Mapped[dict | None] = mapped_column(JSONB)
    page_class_counts: Mapped[dict | None] = mapped_column(JSONB)
    triage_version: Mapped[str | None] = mapped_column(String(16))
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Parse (Milestone 2b): heading inventory and table/agreement summary
    parse_version: Mapped[str | None] = mapped_column(String(16))
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heading_inventory: Mapped[dict | None] = mapped_column(JSONB)
    table_summary: Mapped[dict | None] = mapped_column(JSONB)
    # Milestone 3a: reading profile binding and localisation (Sections 6.5, 6.11)
    reading_profile_id: Mapped[str | None] = mapped_column(String(64))
    reading_profile_version: Mapped[int | None] = mapped_column(Integer)
    reading_profile_source: Mapped[str | None] = mapped_column(String(16))  # detected | assigned
    reading_profile_rationale: Mapped[str | None] = mapped_column(Text)
    localisation_version: Mapped[str | None] = mapped_column(String(16))
    localised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Milestone 3b: structure integrity (Section 6.6)
    structure_version: Mapped[str | None] = mapped_column(String(40))
    gridded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    structure_summary: Mapped[dict | None] = mapped_column(JSONB)
    # Milestone 4a: candidate extraction and validation (Sections 6.8-6.10)
    # Review assignment (increment 19): the reviewer responsible for this order; the queue
    # filters by it and the source page shows it.  Not an access control: any reviewer may
    # still decide, and the second-review policy still needs a different reviewer.
    assigned_to: Mapped[str | None] = mapped_column(String(320))
    extraction_version: Mapped[str | None] = mapped_column(String(80))
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_summary: Mapped[dict | None] = mapped_column(JSONB)
    validators_version: Mapped[str | None] = mapped_column(String(16))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_summary: Mapped[dict | None] = mapped_column(JSONB)
    # Milestone 5b: the current data release, denormalised for the detail page
    publication_summary: Mapped[dict | None] = mapped_column(JSONB)

    # Golden-corpus reconciliation (tests/golden/manifest.json); never copied, always re-verified
    golden_id: Mapped[str | None] = mapped_column(String(80))
    manifest_check: Mapped[dict | None] = mapped_column(JSONB)

    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_documents.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # optimistic concurrency
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    dataset: Mapped[Dataset] = relationship()
    pages: Mapped[list[SourcePage]] = relationship(
        back_populates="source", cascade="all, delete-orphan", order_by="SourcePage.page_index"
    )


class SourcePage(Base):
    __tablename__ = "source_pages"
    __table_args__ = (UniqueConstraint("source_id", "page_index", name="uq_source_page"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based PDF index
    # The label a human reads.  Inventory sets it to what the PDF declares; triage resolves it
    # from the printed footer and the document-wide rule, recording where it came from.
    printed_label: Mapped[str | None] = mapped_column(String(40))
    label_declared: Mapped[str | None] = mapped_column(String(40))  # PDF page-label dictionary
    label_observed: Mapped[str | None] = mapped_column(String(40))  # read from the page footer
    label_source: Mapped[str] = mapped_column(String(16), nullable=False, default="none")  # observed|rule|declared|none
    width_pt: Mapped[float | None] = mapped_column()
    height_pt: Mapped[float | None] = mapped_column()
    rotation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_text_layer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drawing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_class: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unknown"
    )  # Section 6.3, assigned in M2
    page_role: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")  # Section 6.5, assigned in M3
    quality_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    text_quality: Mapped[dict | None] = mapped_column(JSONB)  # glyph coverage, dictionary hit rate, reading order
    ocr_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    triage_rationale: Mapped[str | None] = mapped_column(Text)
    triage_version: Mapped[str | None] = mapped_column(String(16))
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Parse (Milestone 2b): OCR provenance and outcome; `ocr_agreement` compares OCR with the
    # text layer when both exist (a low value on a page that *has* a text layer is a finding).
    ocr_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ocr_engine: Mapped[str | None] = mapped_column(String(80))
    ocr_confidence: Mapped[float | None] = mapped_column()
    ocr_word_count: Mapped[int | None] = mapped_column(Integer)
    ocr_text_chars: Mapped[int | None] = mapped_column(Integer)
    ocr_agreement: Mapped[float | None] = mapped_column()
    parse_version: Mapped[str | None] = mapped_column(String(16))
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[SourceDocument] = relationship(back_populates="pages")


class TableGridRecord(Base):
    """One reader's grid for one table on one page, with its agreement against the other
    reader (Section 6.4).  The full grid lives in the artefact at ``object_key``."""

    __tablename__ = "table_grids"
    __table_args__ = (
        UniqueConstraint("source_id", "page_index", "reader", "reader_version", "ordinal", name="uq_table_grid"),
        Index("ix_table_grids_source_page", "source_id", "page_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    reader: Mapped[str] = mapped_column(String(40), nullable=False)
    reader_version: Mapped[str] = mapped_column(String(40), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(String(16), nullable=False)
    bbox: Mapped[list] = mapped_column(JSONB, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    col_count: Mapped[int] = mapped_column(Integer, nullable=False)
    header_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    is_empty: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False)
    agreement_class: Mapped[str | None] = mapped_column(String(40))
    agreement_score: Mapped[float | None] = mapped_column()
    paired_ordinal: Mapped[int | None] = mapped_column(Integer)
    disagreeing_cells: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DocumentHeading(Base):
    """Document-wide heading inventory (`tariff_api.headings`), the expectation localisation
    reconciles against in Milestone 3."""

    __tablename__ = "document_headings"
    __table_args__ = (
        UniqueConstraint("source_id", "page_index", "line_no", "kind", "rules_version", name="uq_document_heading"),
        Index("ix_document_headings_source", "source_id", "ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    code_raw: Mapped[str | None] = mapped_column(String(80))
    code_canonical: Mapped[str | None] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    text_source: Mapped[str] = mapped_column(String(16), nullable=False)  # text_layer | ocr
    rules_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StageArtefact(Base):
    """Index of immutable per-stage artefacts in object storage (Section 6.2).  The object key
    embeds source hash, stage and tool version, so a tool upgrade produces new artefacts beside
    the old ones rather than overwriting them."""

    __tablename__ = "stage_artefacts"
    __table_args__ = (
        UniqueConstraint("source_id", "stage", "tool_version", "page_index", name="uq_stage_artefact"),
        Index("ix_stage_artefacts_source_stage", "source_id", "stage"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    tool: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(160), nullable=False)  # composite for multi-tool stages
    page_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 = document-level
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Job(Base):
    """PostgreSQL-backed durable queue (Section 4)."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "status", "available_at", "priority"),
        Index("ix_jobs_source", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), nullable=False, default=JobStatus.queued
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    stage: Mapped[str | None] = mapped_column(String(80))
    checkpoint: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    progress: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_type: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_documents.id", ondelete="SET NULL"))
    created_by: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job", "job_id", "at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    worker: Mapped[str | None] = mapped_column(String(200))
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditEvent(Base):
    """Immutable audit trail (Section 5.2: publication/audit event)."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(320), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IdempotencyRecord(Base):
    """Stored responses for client idempotency keys (Section 7.1, principle 8)."""

    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    actor: Mapped[str] = mapped_column(String(320), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LocalisationRecord(Base):
    """Where the binding schedule is (Section 6.5), one record per source.  ``status`` is
    ``proposed`` (rules ran, reviewer must confirm), ``ambiguous`` (rules halted: several or no
    approved-schedule candidates; reviewer must correct), ``confirmed`` or ``corrected`` (a
    reviewer decided; extraction may proceed).  The rules' own output is kept in the stage
    artefact; the regions table holds the current, possibly reviewer-edited, set."""

    __tablename__ = "localisation_records"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(16), nullable=False)
    profile_ref: Mapped[str] = mapped_column(String(80), nullable=False)  # <id>@<version>
    findings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    extraction_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decided_by: Mapped[str | None] = mapped_column(String(320))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_rationale: Mapped[str | None] = mapped_column(Text)
    decision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    artefact_key: Mapped[str | None] = mapped_column(String(512))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LocalisationRegion(Base):
    """One classified page span with the textual cue that justified it.  ``origin`` says
    whether the rules or a reviewer placed it."""

    __tablename__ = "localisation_regions"
    __table_args__ = (
        UniqueConstraint("source_id", "ordinal", name="uq_localisation_region"),
        Index("ix_localisation_regions_source_role", "source_id", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    sub_role: Mapped[str | None] = mapped_column(String(32))
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    cue_text: Mapped[str] = mapped_column(String(300), nullable=False)
    cue_page: Mapped[int] = mapped_column(Integer, nullable=False)
    cue_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # locator | page_class | reviewer
    utility: Mapped[str | None] = mapped_column(String(40))
    period: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="detected")  # detected | reviewer
    grid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Reviewer annotation (Section 6.5): a comment on what this region is, and whether the
    # stages must leave it alone.  An excluded region is skipped by the structure and
    # extraction stages and its note is shown wherever the family it covers is reported.
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    annotated_by: Mapped[str | None] = mapped_column(String(320))
    annotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StructureCell(Base):
    """One numeric-ish cell of a confirmed approved-region grid with its header path, row
    path, unit binding and flags (Section 6.6).  A candidate cites a cell, never a page."""

    __tablename__ = "structure_cells"
    __table_args__ = (
        UniqueConstraint("source_id", "page_index", "grid_ordinal", "row", "col", name="uq_structure_cell"),
        Index("ix_structure_cells_source_page", "source_id", "page_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    region_role: Mapped[str] = mapped_column(String(32), nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    grid_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    row: Mapped[int] = mapped_column(Integer, nullable=False)
    col: Mapped[int] = mapped_column(Integer, nullable=False)
    raw: Mapped[str] = mapped_column(String(300), nullable=False)
    header_path: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    row_path: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    normalised: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    value_state: Mapped[str] = mapped_column(String(24), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(8))
    per_unit: Mapped[str | None] = mapped_column(String(16))
    frequency: Mapped[str | None] = mapped_column(String(16))
    unit_source: Mapped[str | None] = mapped_column(String(24))
    flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    footnotes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    slab: Mapped[dict | None] = mapped_column(JSONB)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rules_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ClauseValueRecord(Base):
    """One value line of a clause-outline schedule with its clause path, role and unit
    (Section 6.6, GERC shape)."""

    __tablename__ = "clause_values"
    __table_args__ = (
        UniqueConstraint("source_id", "page_index", "line_no", "ordinal", name="uq_clause_value"),
        Index("ix_clause_values_source_category", "source_id", "category_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    region_role: Mapped[str] = mapped_column(String(32), nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)  # several values on one line
    category_code: Mapped[str | None] = mapped_column(String(80))
    clause_path: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    connector: Mapped[str | None] = mapped_column(String(16))
    alternative: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_text: Mapped[str] = mapped_column(String(400), nullable=False)
    normalised: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    dimension: Mapped[dict | None] = mapped_column(JSONB)
    slab: Mapped[dict | None] = mapped_column(JSONB)
    time_window: Mapped[str | None] = mapped_column(String(24))
    sign: Mapped[int | None] = mapped_column(Integer)
    parameters: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    rules_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExtractionRun(Base):
    """One provider call for one channel over one region (Section 6.8): provider, model,
    prompt and schema versions, input hash, token usage and cost, and whether it was a
    fixture.  Fixture runs are never mixed with real runs: the flag is on every row."""

    __tablename__ = "extraction_runs"
    __table_args__ = (Index("ix_extraction_runs_source", "source_id", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    region_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # structure | image
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # succeeded | failed
    error: Mapped[str | None] = mapped_column(Text)
    candidates_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    artefact_key: Mapped[str | None] = mapped_column(String(512))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CandidateRecord(Base):
    """A proposed fact (Section 5.2: candidate).  Separate from published facts; no tool of
    Section 8 ever reads this table."""

    __tablename__ = "candidates"
    __table_args__ = (
        Index("ix_candidates_source_family", "source_id", "family"),
        Index("ix_candidates_routing", "routing", "review_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    candidate_key: Mapped[str] = mapped_column(String(400), nullable=False)
    family: Mapped[str] = mapped_column(String(32), nullable=False)
    category_code: Mapped[str | None] = mapped_column(String(80))
    component_type: Mapped[str] = mapped_column(String(24), nullable=False)
    value: Mapped[str | None] = mapped_column(String(40))
    value_state: Mapped[str] = mapped_column(String(24), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(8))
    per_unit: Mapped[str | None] = mapped_column(String(16))
    frequency: Mapped[str | None] = mapped_column(String(16))
    decision_status: Mapped[str | None] = mapped_column(String(40))
    period: Mapped[str | None] = mapped_column(String(80))
    utility: Mapped[str | None] = mapped_column(String(40))
    record: Mapped[dict] = mapped_column(JSONB, nullable=False)  # the full Candidate (structure or only channel)
    image_record: Mapped[dict | None] = mapped_column(JSONB)  # the image channel's version, when it exists
    channel_agreement: Mapped[str] = mapped_column(String(16), nullable=False)
    disagreeing_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)
    risk_tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    routing: Mapped[str] = mapped_column(String(16), nullable=False)  # individual | batch
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False)
    structure_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    image_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    extraction_version: Mapped[str] = mapped_column(String(80), nullable=False)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Milestone 5a: review state.  ``record`` stays what the extractor produced; a correction
    # writes ``reviewed_record`` (the effective proposal) and never overwrites the original.
    # review_status: pending | awaiting_second_review | approved | corrected | rejected | unresolved
    reviewed_record: Mapped[dict | None] = mapped_column(JSONB)
    reviewed_by: Mapped[str | None] = mapped_column(String(320))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_reviewer: Mapped[str | None] = mapped_column(String(320))
    second_review: Mapped[str] = mapped_column(String(16), nullable=False, default="not_required")
    decision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Milestone 5b: set by the first release that published this candidate; decisions on a
    # published candidate are no longer reversible
    published_release_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @property
    def effective_record(self) -> dict:
        return self.reviewed_record or self.record


class ValidatorFindingRecord(Base):
    """A validator finding (Section 6.9) attached to candidates or to the source."""

    __tablename__ = "validator_findings"
    __table_args__ = (Index("ix_validator_findings_source", "source_id", "validator_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    validator_id: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    validators_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FamilyDisposition(Base):
    """A reviewer's disposition for a charge family the order does not decide
    (``absent_in_source``, ``out_of_scope``), needed for the completeness validator."""

    __tablename__ = "family_dispositions"
    __table_args__ = (UniqueConstraint("source_id", "family", name="uq_family_disposition"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    family: Mapped[str] = mapped_column(String(32), nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str] = mapped_column(String(320), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CategorySummary(Base):
    """A generated summary of what the schedule says about one category — reviewer context,
    never a fact.  Grounding is checked deterministically: every number in the text must be
    a candidate value or appear in the category's pages; failures are stored, flagged and
    listed, never hidden."""

    __tablename__ = "category_summaries"
    __table_args__ = (UniqueConstraint("source_id", "category_code", name="uq_category_summary"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False)
    heading_text: Mapped[str | None] = mapped_column(String(300))
    page_indices: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(16), nullable=False)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    grounded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unsupported_numbers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    extraction_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ConditionRecordRow(Base):
    """A condition / rule (Section 5.2): verbatim source text, the category codes it names as
    scope, and an interpretation status.  Structured interpretation is a reviewer's job
    (Milestone 5); until then every record is ``verbatim_only``."""

    __tablename__ = "condition_records"
    __table_args__ = (
        UniqueConstraint("source_id", "page_index", "line_no", "kind", "text_hash", name="uq_condition_record"),
        Index("ix_condition_records_source", "source_id", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    number: Mapped[str | None] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # general_provision | footnote | clause_condition
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    interpretation_status: Mapped[str] = mapped_column(String(16), nullable=False, default="verbatim_only")
    extraction_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EvidenceView(Base):
    """Proof that the cited evidence of a candidate was rendered to a named reviewer (Section
    7.2: the approve control is disabled until the evidence has been rendered).  The API
    writes one row when it serves the page image; a decision must cite views made by the
    deciding reviewer for that candidate.  Nothing else can create one."""

    __tablename__ = "evidence_views"
    __table_args__ = (Index("ix_evidence_views_candidate", "candidate_id", "viewer"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    evidence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    viewer: Mapped[str] = mapped_column(String(320), nullable=False)
    dpi: Mapped[int] = mapped_column(Integer, nullable=False)
    highlighted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rendered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReviewDecision(Base):
    """One reviewer decision on one candidate (Section 5.2: review decision).  Append-only:
    an undo marks the row undone and restores the candidate from ``before``; nothing is
    deleted, so the correction history stays intact."""

    __tablename__ = "review_decisions"
    __table_args__ = (
        Index("ix_review_decisions_candidate", "candidate_id", "sequence"),
        Index("ix_review_decisions_source", "source_id", "created_at"),
        UniqueConstraint("reviewer", "idempotency_key", name="uq_review_decision_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)  # per candidate, 1-based
    review_round: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 = first review, 2 = second
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)  # approve | correct | reject | unresolved
    reviewer: Mapped[str] = mapped_column(String(320), nullable=False)
    candidate_version: Mapped[int] = mapped_column(Integer, nullable=False)  # the version decided on
    rationale: Mapped[str | None] = mapped_column(Text)
    cause_tag: Mapped[str | None] = mapped_column(String(24))
    corrected_record: Mapped[dict | None] = mapped_column(JSONB)
    corrected_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_view_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_viewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    time_spent_ms: Mapped[int | None] = mapped_column(Integer)  # client-reported
    view_to_decision_ms: Mapped[int | None] = mapped_column(Integer)  # server-measured from the first view
    before: Mapped[dict] = mapped_column(JSONB, nullable=False)
    after: Mapped[dict] = mapped_column(JSONB, nullable=False)
    undone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    undone_by: Mapped[str | None] = mapped_column(String(320))
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DataRelease(Base):
    """A publication transaction over a declared scope (Section 7.2, publication).  Releases
    are cumulative snapshots per source: the current one carries every published fact; an
    earlier one stays readable as history and is marked superseded.  Partial releases are
    labelled partial everywhere and list their gaps."""

    __tablename__ = "data_releases"
    __table_args__ = (
        UniqueConstraint("source_id", "release_number", name="uq_data_release_number"),
        Index("ix_data_releases_current", "source_id", "is_current"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    release_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # whole_schedule | subset
    scope_categories: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    scope_families: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    completeness: Mapped[str] = mapped_column(String(8), nullable=False)  # complete | partial
    gaps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    published_by: Mapped[str] = mapped_column(String(320), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    utility: Mapped[str | None] = mapped_column(String(40))
    period: Mapped[str | None] = mapped_column(String(80))
    fact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidates_in_scope: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    awaiting_second_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checklist_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    preview_token: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))


class PublishedFact(Base):
    """A published fact (Section 5.2: the database is the source of truth for published
    answers).  Separate table, separate routes from candidates; the explorer and every tool
    of Section 8 read this and only this."""

    __tablename__ = "published_facts"
    __table_args__ = (
        UniqueConstraint("release_id", "candidate_id", name="uq_published_fact_candidate"),
        Index("ix_published_facts_release", "release_id", "family", "category_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_releases.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    review_status: Mapped[str] = mapped_column(String(24), nullable=False)  # approved | corrected
    family: Mapped[str] = mapped_column(String(32), nullable=False)
    category_code: Mapped[str | None] = mapped_column(String(80))
    component_type: Mapped[str] = mapped_column(String(24), nullable=False)
    value: Mapped[str | None] = mapped_column(String(40))
    value_state: Mapped[str] = mapped_column(String(24), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(8))
    per_unit: Mapped[str | None] = mapped_column(String(16))
    frequency: Mapped[str | None] = mapped_column(String(16))
    decision_status: Mapped[str | None] = mapped_column(String(40))
    period: Mapped[str | None] = mapped_column(String(80))
    utility: Mapped[str | None] = mapped_column(String(40))
    applicability: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    derivation: Mapped[dict | None] = mapped_column(JSONB)
    record: Mapped[dict] = mapped_column(JSONB, nullable=False)  # the effective record at publication
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PublishedEvidence(Base):
    """Evidence span of a published fact (Section 5.2): the citation is derived from this row
    by backend code; no model ever produces a page number that reaches a user."""

    __tablename__ = "published_evidence"
    __table_args__ = (Index("ix_published_evidence_fact", "fact_id", "ordinal"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("published_facts.id", ondelete="CASCADE"), nullable=False)
    release_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    printed_label: Mapped[str | None] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    grid_ordinal: Mapped[int | None] = mapped_column(Integer)
    row: Mapped[int | None] = mapped_column(Integer)
    col: Mapped[int | None] = mapped_column(Integer)
    line_no: Mapped[int | None] = mapped_column(Integer)
    header_path: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    row_path: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    clause_path: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    excerpt: Mapped[str] = mapped_column(String(400), nullable=False)
