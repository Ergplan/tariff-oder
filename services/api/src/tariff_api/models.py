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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[SourceDocument] = relationship(back_populates="pages")


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
    tool_version: Mapped[str] = mapped_column(String(40), nullable=False)
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
