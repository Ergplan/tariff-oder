"""API response/request models.  These are the single contract source for the web app
(``packages/contracts`` is generated from the OpenAPI document)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import DatasetKind, JobStatus, SourceState, UserRole


class ErrorResponse(BaseModel):
    error_type: str
    message: str
    next_step: str
    severity: str
    request_id: str | None = None
    detail: str | None = None
    extra: dict[str, Any] | None = None


class Health(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]
    database: dict[str, Any]
    storage: dict[str, Any]
    request_id: str | None = None


class StatusReport(BaseModel):
    service: str
    version: str
    deployment_profile: str
    environment_name: str
    adapters: dict[str, str]
    database: dict[str, Any]
    queue_depth: dict[str, int]
    tool_versions: dict[str, str]
    datasets: dict[str, int]
    limits: dict[str, int]


class Me(BaseModel):
    email: str
    role: UserRole
    provider: str


class DatasetOut(BaseModel):
    id: uuid.UUID
    kind: DatasetKind
    name: str


class SourceSummary(BaseModel):
    id: uuid.UUID
    dataset_kind: DatasetKind
    sha256: str
    size_bytes: int
    original_filename: str
    provenance_url: str | None
    acquired_at: datetime
    uploaded_by: str
    state: SourceState
    state_reason: str | None
    page_count: int | None
    pages_with_text: int | None
    pages_without_text: int | None
    golden_id: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class JobSummary(BaseModel):
    id: uuid.UUID
    job_type: str
    status: JobStatus
    stage: str | None
    attempts: int
    max_attempts: int
    progress: dict[str, Any]
    checkpoint: dict[str, Any]
    error_type: str | None
    error_message: str | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
    run_id: uuid.UUID | None
    source_id: uuid.UUID | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobEventOut(BaseModel):
    id: int
    run_id: uuid.UUID | None
    event: str
    worker: str | None
    detail: dict[str, Any]
    at: datetime


class JobDetail(JobSummary):
    payload: dict[str, Any]
    events: list[JobEventOut]


class StageArtefactOut(BaseModel):
    stage: str
    tool: str
    tool_version: str
    page_index: int
    object_key: str
    content_sha256: str
    size_bytes: int
    created_at: datetime


class TriageSummary(BaseModel):
    triage_version: str | None
    triaged_at: datetime | None
    page_class_counts: dict[str, int]
    label_rule: dict[str, Any] | None
    ocr_recommended_pages: list[int]
    low_quality_pages: list[int]
    label_flagged_pages: list[int]
    unknown_pages: list[int]


class StageRerunRequest(BaseModel):
    job_type: Literal["inventory_source", "triage_source"]


class SourceDetail(SourceSummary):
    content_type: str
    object_key: str
    pdf_version: str | None
    producer: str | None
    creator: str | None
    is_encrypted: bool | None
    is_tagged: bool | None
    fonts_total: int | None
    fonts_not_embedded: list[str] | None
    inventory_tool: str | None
    inventory_tool_version: str | None
    inventoried_at: datetime | None
    manifest_check: dict[str, Any] | None
    superseded_by_id: uuid.UUID | None
    latest_job: JobSummary | None
    text_layer_summary: dict[str, Any] | None
    triage: TriageSummary | None
    artefacts: list[StageArtefactOut]


class SourceRegistration(BaseModel):
    source: SourceSummary
    deduplicated: bool
    job: JobSummary | None
    idempotent_replay: bool = False


class SourcePageOut(BaseModel):
    page_index: int
    printed_label: str | None  # resolved label; see label_source
    label_declared: str | None
    label_observed: str | None
    label_source: str  # observed | rule | declared | none
    width_pt: float | None
    height_pt: float | None
    rotation: int
    text_chars: int
    has_text_layer: bool
    image_count: int
    drawing_count: int
    page_class: str
    page_role: str
    quality_flags: list[Any]
    text_quality: dict[str, Any] | None
    ocr_recommended: bool
    triage_rationale: str | None
    triage_version: str | None
    triaged_at: datetime | None


class InboxObject(BaseModel):
    object_key: str
    size_bytes: int
    updated_at: datetime | None
    registered: bool
    source_id: uuid.UUID | None
    is_content_addressed_copy: bool


class InboxList(BaseModel):
    bucket_role: Literal["sources"] = "sources"
    prefix: str
    total: int
    objects: list[InboxObject]


class IngestRequest(BaseModel):
    """Register a PDF already present in the source bucket (operator uploaded it there)."""

    object_key: str = Field(min_length=1, max_length=512)
    dataset_kind: DatasetKind = DatasetKind.real
    provenance_url: str | None = None


class SourcePageList(BaseModel):
    source_id: uuid.UUID
    total: int
    offset: int
    limit: int
    pages: list[SourcePageOut]


class SourceList(BaseModel):
    total: int
    items: list[SourceSummary]


class JobList(BaseModel):
    total: int
    items: list[JobSummary]


class CancelResult(BaseModel):
    job_id: uuid.UUID
    result: Literal["cancelled", "cancel_requested", "not_cancellable"]


class JurisdictionOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    kind: str
    aliases: list[str]


class CommissionOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    jurisdiction_id: uuid.UUID
    aliases: list[str]


class UtilityOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    commission_id: uuid.UUID
    dataset_kind: DatasetKind
    licensed_area: str | None
    aliases: list[str]
    active_reading_profile: str | None
    active_reading_profile_version: str | None


class UtilityCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=200)
    commission_code: str
    dataset_kind: DatasetKind = DatasetKind.real
    licensed_area: str | None = None
    aliases: list[str] = Field(default_factory=list)


class RegistryOut(BaseModel):
    jurisdictions: list[JurisdictionOut]
    commissions: list[CommissionOut]
    utilities: list[UtilityOut]


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    role: UserRole
    active: bool


class UserUpsert(BaseModel):
    email: str
    display_name: str | None = None
    role: UserRole
    active: bool = True


class AuditEventOut(BaseModel):
    id: int
    actor: str
    action: str
    entity_type: str
    entity_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    request_id: str | None
    at: datetime
