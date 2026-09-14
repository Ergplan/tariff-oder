"""API response/request models.  These are the single contract source for the web app
(``packages/contracts`` is generated from the OpenAPI document)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import DatasetKind, JobStatus, SourceState, UserRole
from .tariff_schema import EvidenceRef


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


class TableGridOut(BaseModel):
    page_index: int
    reader: str
    reader_version: str
    ordinal: int
    strategy: str
    bbox: list[float]
    row_count: int
    col_count: int
    header_rows: int
    is_empty: bool
    is_primary: bool
    agreement_class: str | None
    agreement_score: float | None
    paired_ordinal: int | None
    disagreeing_cells: int
    risk_tags: list[str]
    object_key: str


class TableGridList(BaseModel):
    source_id: uuid.UUID
    total: int
    grids: list[TableGridOut]


class HeadingOut(BaseModel):
    page_index: int
    line_no: int
    ordinal: int
    kind: str
    code_raw: str | None
    code_canonical: str | None
    text: str
    text_source: str


class HeadingList(BaseModel):
    source_id: uuid.UUID
    total: int
    inventory: dict[str, Any] | None
    headings: list[HeadingOut]


class ParseSummary(BaseModel):
    parse_version: str | None
    parsed_at: datetime | None
    heading_inventory: dict[str, Any] | None
    table_summary: dict[str, Any] | None


class ReadingProfileOut(BaseModel):
    id: str
    version: int
    commission: str
    utilities: list[str]
    schedule_representation: str
    schedule_heading_kind: str
    seeded_from: str


class ReadingProfileList(BaseModel):
    profiles: list[ReadingProfileOut]


class ProfileAssignRequest(BaseModel):
    profile_id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    version: int | None = Field(default=None, ge=1)  # None = latest
    reason: str = Field(min_length=5, max_length=500)


class SourceProfileOut(BaseModel):
    profile_id: str | None
    version: int | None
    source: str | None  # detected | assigned
    rationale: str | None


class LocalisationRegionOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    role: str
    sub_role: str | None
    page_start: int
    page_end: int
    cue_text: str
    cue_page: int
    cue_kind: str
    utility: str | None
    period: str | None
    note: str | None
    origin: str
    grid_count: int


class LocalisationFindingOut(BaseModel):
    code: str
    severity: str
    message: str
    pages: list[int] = Field(default_factory=list)


class LocalisationOut(BaseModel):
    source_id: uuid.UUID
    status: str  # proposed | ambiguous | confirmed | corrected
    rules_version: str
    profile_ref: str
    extraction_allowed: bool
    findings: list[LocalisationFindingOut]
    regions: list[LocalisationRegionOut]
    decided_by: str | None
    decided_at: datetime | None
    decision_rationale: str | None
    decision_count: int
    version: int
    artefact_key: str | None


class LocalisationSummary(BaseModel):
    status: str
    rules_version: str
    profile_ref: str
    extraction_allowed: bool
    region_count: int
    blocking_findings: int
    approved_schedule_pages: list[str]


class RegionEdit(BaseModel):
    role: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    sub_role: str | None = None
    utility: str | None = Field(default=None, max_length=40)
    period: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class LocalisationDecision(BaseModel):
    """A reviewer's checkpoint decision.  ``confirm`` keeps the detected regions; ``correct``
    replaces them with ``regions`` (every region then carries origin=reviewer).  Both need a
    rationale and a statement that the pages were looked at."""

    decision: Literal["confirm", "correct"]
    rationale: str = Field(min_length=5, max_length=2000)
    pages_viewed: bool
    regions: list[RegionEdit] | None = None
    expected_version: int | None = None  # optimistic concurrency on the record


class StructureCellOut(BaseModel):
    id: uuid.UUID
    region_role: str
    page_index: int
    grid_ordinal: int
    row: int
    col: int
    raw: str
    header_path: list[str]
    row_path: list[str]
    value_state: str
    value: str | None
    currency: str | None
    per_unit: str | None
    frequency: str | None
    unit_source: str | None
    flags: list[str]
    footnotes: list[str]
    slab: dict[str, Any] | None
    resolved: bool
    rules_version: str


class StructureCellList(BaseModel):
    cells: list[StructureCellOut]
    total: int
    limit: int
    offset: int


class ClauseValueOut(BaseModel):
    id: uuid.UUID
    region_role: str
    page_index: int
    line_no: int
    ordinal: int
    category_code: str | None
    clause_path: list[str]
    role: str
    kind: str
    connector: str | None
    alternative: int
    line_text: str
    value: str | None
    value_state: str | None
    currency: str | None
    per_unit: str | None
    frequency: str | None
    percent_of: str | None
    reference: str | None
    dimension: dict[str, str] | None
    slab: dict[str, Any] | None
    time_window: str | None
    sign: int | None
    parameters: list[str]
    rules_version: str


class ClauseValueList(BaseModel):
    values: list[ClauseValueOut]
    total: int


class StructureSummary(BaseModel):
    tool_version: str
    representation: str
    regions_read: int
    regions_skipped: int
    regions_without_grids: list[int]
    cells: int
    cells_resolved: int
    cells_unresolved: int
    unresolved_by_flag: dict[str, int]
    flags: dict[str, int]
    unit_sources: dict[str, int]
    continuations: int
    header_inherited_grids: int
    clause_values: int
    clause_cross_references: int
    clause_conditions: int
    clause_categories: list[str]
    clause_option_groups: int
    regions: list[dict[str, Any]]
    gridded_at: datetime | None


class ExtractionSummary(BaseModel):
    extraction_version: str
    provider: str
    model: str
    is_fixture: bool
    prompt_version: str
    schema_version: str
    runs: int
    runs_failed: int
    cost_usd: float
    tokens: int
    candidates: int
    by_family: dict[str, int]
    by_confidence: dict[str, int]
    by_agreement: dict[str, int]
    by_routing: dict[str, int]
    risk_tags: dict[str, int]
    image_channel: bool
    new_profile: bool
    conditions: int = 0
    extracted_at: datetime | None


class ValidationSummary(BaseModel):
    validators_version: str
    findings: int
    by_severity: dict[str, int]
    by_validator: dict[str, int]
    candidates_with_findings: int
    candidates_blocked: int
    source_level_findings: int
    families_without_disposition: list[str]
    routing: dict[str, int]
    confidence: dict[str, int]
    validated_at: datetime | None


class CandidateOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    candidate_key: str
    family: str
    category_code: str | None
    component_type: str
    value: str | None
    value_state: str
    currency: str | None
    per_unit: str | None
    frequency: str | None
    decision_status: str | None
    period: str | None
    utility: str | None
    record: dict[str, Any]
    image_record: dict[str, Any] | None
    channel_agreement: str
    disagreeing_fields: list[str]
    confidence: str
    risk_tags: list[str]
    routing: str
    review_status: str
    is_fixture: bool
    finding_count: int
    blocking_finding_count: int
    extraction_version: str
    version: int
    created_at: datetime
    # Milestone 5a review state
    reviewed_record: dict[str, Any] | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    first_reviewer: str | None = None
    second_review: str = "not_required"
    decision_count: int = 0


class CandidateList(BaseModel):
    candidates: list[CandidateOut]
    total: int
    limit: int
    offset: int


class FindingOut(BaseModel):
    id: uuid.UUID
    validator_id: str
    severity: str
    message: str
    candidate_ids: list[str]
    detail: dict[str, Any]
    validators_version: str


class FindingList(BaseModel):
    findings: list[FindingOut]
    total: int


class ReviewQueueItem(BaseModel):
    source_id: uuid.UUID
    original_filename: str
    dataset_kind: DatasetKind
    state: SourceState
    pending: int
    individual: int
    batch: int
    blocked: int
    is_fixture: bool


class ReviewQueue(BaseModel):
    items: list[ReviewQueueItem]
    total_pending: int


class DispositionRequest(BaseModel):
    family: str
    disposition: Literal["absent_in_source", "out_of_scope", "not_a_tariff_category"]
    rationale: str = Field(min_length=5, max_length=2000)
    pages_viewed: bool


class DispositionOut(BaseModel):
    id: uuid.UUID
    family: str
    disposition: str
    rationale: str
    decided_by: str
    decided_at: datetime


class ExtractionRunOut(BaseModel):
    id: uuid.UUID
    region_ordinal: int
    channel: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    is_fixture: bool
    input_hash: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    status: str
    error: str | None
    candidates_returned: int
    started_at: datetime
    finished_at: datetime | None


class ExtractionRunList(BaseModel):
    runs: list[ExtractionRunOut]
    total_cost_usd: float
    fixture_runs: int
    real_runs: int


class ConditionOut(BaseModel):
    id: uuid.UUID
    page_index: int
    line_no: int
    number: str | None
    kind: str
    text: str
    scope_codes: list[str]
    interpretation_status: str


class ConditionList(BaseModel):
    conditions: list[ConditionOut]
    total: int


class StageRerunRequest(BaseModel):
    job_type: Literal[
        "inventory_source",
        "triage_source",
        "parse_source",
        "localise_source",
        "grid_source",
        "extract_source",
        "validate_source",
    ]


class PublicationSummary(BaseModel):
    id: uuid.UUID
    release_number: int
    scope: str
    completeness: str
    gaps: list[dict[str, Any]]
    fact_count: int
    published_by: str
    published_at: datetime | None
    is_current: bool
    is_fixture: bool
    unresolved: int = 0
    pending: int = 0
    awaiting_second_review: int = 0


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
    parse: ParseSummary | None
    reading_profile: SourceProfileOut
    localisation: LocalisationSummary | None
    structure: StructureSummary | None
    extraction: ExtractionSummary | None
    validation: ValidationSummary | None
    publication: PublicationSummary | None = None
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
    ocr_used: bool
    ocr_engine: str | None
    ocr_confidence: float | None
    ocr_word_count: int | None
    ocr_text_chars: int | None
    ocr_agreement: float | None
    parse_version: str | None
    parsed_at: datetime | None


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


# ------------------------------------------------------------------ Milestone 5a: review workflow


class ReviewDecisionRequest(BaseModel):
    """A reviewer's decision on one candidate (Section 7.2).  ``expected_version`` is the
    candidate version the reviewer looked at; ``evidence_view_ids`` are the views the image
    endpoint issued to this reviewer for this candidate.  A correction is a partial record
    (only the listed fields change), a cause tag and an evidence selection."""

    outcome: Literal["approve", "correct", "reject", "unresolved"]
    expected_version: int
    rationale: str | None = Field(default=None, max_length=4000)
    evidence_view_ids: list[uuid.UUID] = Field(default_factory=list)
    correction: dict[str, Any] | None = None
    evidence_indices: list[int] | None = None
    evidence: list[EvidenceRef] | None = None
    cause_tag: (
        Literal["wrong_table", "header_misbound", "unit", "ocr", "footnote_missed", "cross_reference", "other"] | None
    ) = None
    time_spent_ms: int | None = Field(default=None, ge=0)


class ReviewDecisionOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    candidate_id: uuid.UUID
    sequence: int
    review_round: int
    outcome: str
    reviewer: str
    candidate_version: int
    rationale: str | None
    cause_tag: str | None
    corrected_record: dict[str, Any] | None
    corrected_fields: list[str]
    evidence_view_ids: list[str]
    evidence_viewed: bool
    time_spent_ms: int | None
    view_to_decision_ms: int | None
    before: dict[str, Any]
    after: dict[str, Any]
    undone: bool
    undone_by: str | None
    undone_at: datetime | None
    request_id: str | None
    created_at: datetime


class DecisionResult(BaseModel):
    decision: ReviewDecisionOut
    candidate: CandidateOut
    idempotent_replay: bool = False


class DecisionList(BaseModel):
    decisions: list[ReviewDecisionOut]
    total: int


class EvidenceViewOut(BaseModel):
    id: uuid.UUID
    evidence_index: int
    page_index: int
    viewer: str
    highlighted: bool
    rendered_at: datetime


class CandidateEvidenceOut(BaseModel):
    """The candidate's evidence references with, for the caller, the views already issued.
    ``required_index`` is the evidence a decision must have had rendered."""

    candidate_id: uuid.UUID
    version: int
    review_status: str
    evidence: list[EvidenceRef]
    views: list[EvidenceViewOut]
    required_index: int = 0
    viewed_required: bool


class ReviewQueueCandidate(BaseModel):
    position: int
    candidate: CandidateOut
    page_index: int | None
    coverage_impact: bool
    reason: str


class ReviewQueueDetail(BaseModel):
    source_id: uuid.UUID
    items: list[ReviewQueueCandidate]
    total: int
    limit: int
    offset: int
    filters: dict[str, Any]


class ChecklistItem(BaseModel):
    kind: str  # category | category_component | family
    key: str
    category_code: str | None
    component_type: str | None
    expected_from: str  # inventory | extraction | spec
    candidates: int
    status: str  # not_started | in_progress | approved | corrected | rejected | unresolved | disposition:<x>
    counts: dict[str, int]
    note: str | None


class ReviewChecklist(BaseModel):
    source_id: uuid.UUID
    items: list[ChecklistItem]
    summary: dict[str, int]
    inventory_categories: list[str]
    condition_records: int
    condition_candidates: dict[str, int]
    candidates: dict[str, int]
    awaiting_second_review: int
    unresolved: int
    second_review_policy: dict[str, bool]


class BatchApproveItem(BaseModel):
    candidate_id: uuid.UUID
    expected_version: int
    evidence_view_ids: list[uuid.UUID]
    time_spent_ms: int | None = None


class BatchApproveRequest(BaseModel):
    items: list[BatchApproveItem] = Field(min_length=1, max_length=200)


class BatchItemResult(BaseModel):
    candidate_id: uuid.UUID
    ok: bool
    review_status: str | None = None
    error_type: str | None = None
    message: str | None = None


class BatchApproveResult(BaseModel):
    results: list[BatchItemResult]
    approved: int
    refused: int


class ReviewTelemetry(BaseModel):
    decisions: int
    outcomes: dict[str, int]
    undone: int
    second_reviews: int
    correction_rate: float | None
    corrections_by_cause: dict[str, int]
    by_utility: dict[str, dict[str, Any]]
    review_ms_by_risk_tag: dict[str, dict[str, int]]


# ------------------------------------------------------------------ Milestone 5b: publication and explorer


class PublishGap(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=3, max_length=1000)


class PublishPreviewRequest(BaseModel):
    scope: Literal["whole_schedule", "subset"] = "whole_schedule"
    categories: list[str] | None = None
    families: list[str] | None = None


class PublishPreview(BaseModel):
    """The consequences of a publication over a scope (Section 7.1, principle 5).  The
    token must be presented with the publish request."""

    source_id: uuid.UUID
    scope: str
    categories: list[str]
    families: list[str]
    candidates_in_scope: int
    facts_to_publish: int
    pending: list[str]
    awaiting_second_review: list[str]
    unresolved: list[str]
    blocked_by_findings: list[str]
    missing_for_complete: list[dict[str, str]]
    gap_keys_required_for_partial: list[str]
    dispositions: dict[str, str]
    checklist: ReviewChecklist
    prior_release: PublicationSummary | None
    source_version: int
    preview_token: str


class PublishRequest(BaseModel):
    scope: Literal["whole_schedule", "subset"] = "whole_schedule"
    categories: list[str] | None = None
    families: list[str] | None = None
    completeness: Literal["complete", "partial"]
    gaps: list[PublishGap] = Field(default_factory=list)
    rationale: str = Field(min_length=5, max_length=4000)
    expected_source_version: int
    preview_token: str = Field(min_length=64, max_length=64)
    confirm_consequences: bool


class ReleaseOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    release_number: int
    scope: str
    scope_categories: list[str]
    scope_families: list[str]
    completeness: str
    gaps: list[dict[str, Any]]
    rationale: str
    published_by: str
    published_at: datetime
    source_version: int
    utility: str | None
    period: str | None
    fact_count: int
    candidates_in_scope: int
    unresolved_count: int
    pending_count: int
    awaiting_second_review_count: int
    is_current: bool
    superseded_by_id: uuid.UUID | None
    is_fixture: bool


class ReleaseList(BaseModel):
    releases: list[ReleaseOut]
    total: int


class CitationOut(BaseModel):
    """Derived by backend code from a published evidence row; never model-produced."""

    evidence_id: uuid.UUID
    source_id: uuid.UUID
    pdf_page: int
    printed_page: str | None
    kind: str
    table_id: str | None
    cell: str | None
    line_no: int | None
    header_path: list[str]
    row_path: list[str]
    clause_path: list[str]
    excerpt: str


class PublishedFactOut(BaseModel):
    fact_id: uuid.UUID
    release_id: uuid.UUID
    candidate_id: uuid.UUID
    review_status: str
    family: str
    category_code: str | None
    component_type: str
    value: str | None
    value_state: str
    currency: str | None
    per_unit: str | None
    frequency: str | None
    decision_status: str | None
    period: str | None
    utility: str | None
    applicability: dict[str, Any]
    conditions: list[str]
    derivation: dict[str, Any] | None
    original_text: str | None
    reference_target: str | None
    is_fixture: bool
    citations: list[CitationOut]


class CompletenessBanner(BaseModel):
    completeness: str  # complete | partial
    gaps: list[dict[str, Any]]
    unresolved: int
    pending: int
    awaiting_second_review: int
    release_number: int
    published_at: datetime
    is_fixture: bool


class ExplorerCategory(BaseModel):
    category_code: str
    components: dict[str, list[PublishedFactOut]]
    conditions: list[str]
    facts: int


class TariffExplorer(BaseModel):
    status: Literal["published", "coverage_insufficient"]
    source_id: uuid.UUID
    release: ReleaseOut | None
    completeness: CompletenessBanner | None
    categories: list[ExplorerCategory]
    general_conditions: list[str]
    unresolved_items: list[str]
    message: str | None = None


class NetworkFamilyView(BaseModel):
    family: str
    status: Literal["published", "coverage_insufficient"]
    disposition: str | None
    facts: list[PublishedFactOut]
    message: str | None = None


class NetworkExplorer(BaseModel):
    status: Literal["published", "coverage_insufficient"]
    source_id: uuid.UUID
    release: ReleaseOut | None
    completeness: CompletenessBanner | None
    families: list[NetworkFamilyView]
    message: str | None = None


class ExplorerReleaseItem(BaseModel):
    release: ReleaseOut
    original_filename: str
    dataset_kind: DatasetKind
    state: SourceState


class ExplorerReleaseList(BaseModel):
    items: list[ExplorerReleaseItem]
    total: int
    real: int
    fixture: int
