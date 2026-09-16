"""Candidates, validator findings, extraction runs, the review queue and family dispositions
(Sections 6.8-6.10).  Candidates are proposals: this router is the only way to read them and
no query tool of Section 8 ever does.  Nothing here approves or publishes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, func, select

from ..adapters.identity import Principal
from ..auth import require_analyst, require_reviewer
from ..db import session_scope
from ..errors import AppError
from ..models import (
    AuditEvent,
    CandidateRecord,
    CategorySummary,
    ConditionRecordRow,
    ExtractionRun,
    FamilyDisposition,
    SourceDocument,
    SourceState,
    ValidatorFindingRecord,
)
from ..schemas import (
    CandidateList,
    CandidateOut,
    CategorySummaryList,
    CategorySummaryOut,
    ConditionList,
    ConditionOut,
    DispositionOut,
    DispositionRequest,
    ExtractionRunList,
    ExtractionRunOut,
    FindingList,
    FindingOut,
    ReviewQueue,
    ReviewQueueItem,
)
from ..services import sources as svc
from ..tariff_schema import FAMILIES
from ..telemetry import request_id_var

router = APIRouter(tags=["candidates"])


@router.get("/sources/{source_id}/candidates", response_model=CandidateList, dependencies=[Depends(require_analyst)])
def list_candidates(
    source_id: uuid.UUID,
    family: str | None = None,
    category: str | None = None,
    routing: str | None = None,
    confidence: str | None = None,
    risk: str | None = None,
    review_status: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> CandidateList:
    with session_scope() as s:
        svc.get_source(s, source_id)
        q = select(CandidateRecord).where(CandidateRecord.source_id == source_id)
        if family:
            q = q.where(CandidateRecord.family == family)
        if category:
            q = q.where(CandidateRecord.category_code == category)
        if routing:
            q = q.where(CandidateRecord.routing == routing)
        if confidence:
            q = q.where(CandidateRecord.confidence == confidence)
        if risk:
            q = q.where(CandidateRecord.risk_tags.contains([risk]))
        if review_status:
            q = q.where(CandidateRecord.review_status == review_status)
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        rows = (
            s.execute(
                q.order_by(CandidateRecord.family, CandidateRecord.category_code, CandidateRecord.candidate_key)
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        return CandidateList(
            candidates=[CandidateOut.model_validate(r, from_attributes=True) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )


@router.get("/candidates/{candidate_id}", response_model=CandidateOut, dependencies=[Depends(require_analyst)])
def get_candidate(candidate_id: uuid.UUID) -> CandidateOut:
    with session_scope() as s:
        row = s.get(CandidateRecord, candidate_id)
        if row is None:
            raise AppError("not_found", f"candidate {candidate_id} not found")
        return CandidateOut.model_validate(row, from_attributes=True)


@router.get(
    "/sources/{source_id}/summaries", response_model=CategorySummaryList, dependencies=[Depends(require_analyst)]
)
def list_summaries(source_id: uuid.UUID) -> CategorySummaryList:
    """Generated category summaries: reviewer context with a grounding flag; never facts."""
    with session_scope() as s:
        svc.get_source(s, source_id)
        rows = (
            s.execute(
                select(CategorySummary)
                .where(CategorySummary.source_id == source_id)
                .order_by(CategorySummary.category_code)
            )
            .scalars()
            .all()
        )
        return CategorySummaryList(
            source_id=source_id,
            summaries=[CategorySummaryOut.model_validate(r, from_attributes=True) for r in rows],
            total=len(rows),
        )


@router.get("/sources/{source_id}/findings", response_model=FindingList, dependencies=[Depends(require_analyst)])
def list_findings(source_id: uuid.UUID, severity: str | None = None, validator: str | None = None) -> FindingList:
    with session_scope() as s:
        svc.get_source(s, source_id)
        q = select(ValidatorFindingRecord).where(ValidatorFindingRecord.source_id == source_id)
        if severity:
            q = q.where(ValidatorFindingRecord.severity == severity)
        if validator:
            q = q.where(ValidatorFindingRecord.validator_id == validator)
        rows = (
            s.execute(q.order_by(ValidatorFindingRecord.validator_id, ValidatorFindingRecord.created_at))
            .scalars()
            .all()
        )
        return FindingList(findings=[FindingOut.model_validate(r, from_attributes=True) for r in rows], total=len(rows))


@router.get(
    "/sources/{source_id}/extraction-runs", response_model=ExtractionRunList, dependencies=[Depends(require_analyst)]
)
def list_runs(source_id: uuid.UUID) -> ExtractionRunList:
    """Provider telemetry per run: provider, model, prompt and schema versions, tokens, cost;
    fixture and real runs are counted separately and never summed together."""
    with session_scope() as s:
        svc.get_source(s, source_id)
        rows = (
            s.execute(
                select(ExtractionRun).where(ExtractionRun.source_id == source_id).order_by(ExtractionRun.started_at)
            )
            .scalars()
            .all()
        )
        real = [r for r in rows if not r.is_fixture]
        return ExtractionRunList(
            runs=[ExtractionRunOut.model_validate(r, from_attributes=True) for r in rows],
            total_cost_usd=round(sum(r.cost_usd for r in real), 6),
            fixture_runs=len(rows) - len(real),
            real_runs=len(real),
        )


@router.get("/review/queue", response_model=ReviewQueue, dependencies=[Depends(require_analyst)])
def review_queue(dataset_kind: str | None = None) -> ReviewQueue:
    """Sources with pending candidates, with the individual / batch split (Section 6.10).
    Fixture sources are listed with their flag and never mixed into real counts."""
    with session_scope() as s:
        q = (
            select(
                CandidateRecord.source_id,
                func.count().label("pending"),
                func.sum(func.cast(CandidateRecord.routing == "individual", type_=Integer)).label("individual"),
                func.sum(func.cast(CandidateRecord.routing == "batch", type_=Integer)).label("batch"),
                func.sum(func.cast(CandidateRecord.blocking_finding_count > 0, type_=Integer)).label("blocked"),
                func.bool_or(CandidateRecord.is_fixture).label("is_fixture"),
            )
            .where(CandidateRecord.review_status.in_(["pending", "awaiting_second_review"]))
            .group_by(CandidateRecord.source_id)
        )
        items = []
        total = 0
        for row in s.execute(q).all():
            src = s.get(SourceDocument, row.source_id)
            if src is None or src.state != SourceState.awaiting_review:
                continue
            if dataset_kind and src.dataset.kind.value != dataset_kind:
                continue
            items.append(
                ReviewQueueItem(
                    source_id=src.id,
                    original_filename=src.original_filename,
                    dataset_kind=src.dataset.kind,
                    state=src.state,
                    pending=int(row.pending),
                    individual=int(row.individual or 0),
                    batch=int(row.batch or 0),
                    blocked=int(row.blocked or 0),
                    is_fixture=bool(row.is_fixture),
                )
            )
            total += int(row.pending)
        items.sort(key=lambda i: (i.is_fixture, i.original_filename))
        return ReviewQueue(items=items, total_pending=total)


@router.get(
    "/sources/{source_id}/dispositions", response_model=list[DispositionOut], dependencies=[Depends(require_analyst)]
)
def list_dispositions(source_id: uuid.UUID) -> list[DispositionOut]:
    with session_scope() as s:
        svc.get_source(s, source_id)
        rows = s.execute(select(FamilyDisposition).where(FamilyDisposition.source_id == source_id)).scalars().all()
        return [DispositionOut.model_validate(r, from_attributes=True) for r in rows]


@router.put("/sources/{source_id}/dispositions", response_model=DispositionOut)
def set_disposition(
    source_id: uuid.UUID, body: DispositionRequest, principal: Principal = Depends(require_reviewer)
) -> DispositionOut:
    """A reviewer records that a charge family is not decided by this order (Section 6.9,
    network-charge completeness).  Audited; the next validation run reads it."""
    if body.family not in FAMILIES:
        raise AppError("validation_failed", f"unknown charge family {body.family!r}")
    if not body.pages_viewed:
        raise AppError("validation_failed", "record a disposition only after looking at the order (pages_viewed)")
    with session_scope() as s:
        svc.get_source(s, source_id)
        row = s.execute(
            select(FamilyDisposition).where(
                FamilyDisposition.source_id == source_id, FamilyDisposition.family == body.family
            )
        ).scalar_one_or_none()
        before = {"disposition": row.disposition, "rationale": row.rationale} if row else None
        if row is None:
            row = FamilyDisposition(
                source_id=source_id,
                family=body.family,
                disposition=body.disposition,
                rationale=body.rationale,
                decided_by=principal.email,
            )
            s.add(row)
        else:
            row.disposition, row.rationale, row.decided_by = body.disposition, body.rationale, principal.email
        s.flush()
        s.add(
            AuditEvent(
                actor=principal.email,
                action="family_disposition.set",
                entity_type="source_document",
                entity_id=str(source_id),
                before=before,
                after={"family": body.family, "disposition": body.disposition},
                reason=body.rationale,
                request_id=request_id_var.get(),
            )
        )
        return DispositionOut.model_validate(row, from_attributes=True)


@router.get("/sources/{source_id}/conditions", response_model=ConditionList, dependencies=[Depends(require_analyst)])
def list_conditions(source_id: uuid.UUID, kind: str | None = None) -> ConditionList:
    """Condition records: verbatim general provisions, footnotes and clause conditions with
    the category codes they name.  All `verbatim_only` until a reviewer interprets them."""
    with session_scope() as s:
        svc.get_source(s, source_id)
        q = select(ConditionRecordRow).where(ConditionRecordRow.source_id == source_id)
        if kind:
            q = q.where(ConditionRecordRow.kind == kind)
        rows = s.execute(q.order_by(ConditionRecordRow.page_index, ConditionRecordRow.line_no)).scalars().all()
        return ConditionList(
            conditions=[ConditionOut.model_validate(r, from_attributes=True) for r in rows], total=len(rows)
        )
