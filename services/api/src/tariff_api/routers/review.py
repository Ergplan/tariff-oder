"""Reviewer workflow endpoints (Section 7.2): the per-order queue in review order, the
completeness checklist, evidence rendering that records the view, decisions with
stale-version and evidence-viewed enforcement, batch approval, undo and telemetry.
Reviewer or administrator only for anything that decides; analysts read."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select

from ..adapters.identity import Principal
from ..adapters.storage import ObjectStore
from ..auth import require_analyst, require_reviewer
from ..db import session_scope
from ..errors import AppError
from ..models import CandidateRecord, IdempotencyRecord, ReviewDecision
from ..schemas import (
    BatchApproveRequest,
    BatchApproveResult,
    BatchItemResult,
    CandidateEvidenceOut,
    CandidateOut,
    ChecklistItem,
    DecisionList,
    DecisionResult,
    EvidenceViewOut,
    ReviewChecklist,
    ReviewDecisionOut,
    ReviewDecisionRequest,
    ReviewQueueCandidate,
    ReviewQueueDetail,
    ReviewTelemetry,
)
from ..services import review as rv
from ..services import sources as svc
from ..tariff_schema import Candidate

router = APIRouter(tags=["review"])


def _cand(row: CandidateRecord) -> CandidateOut:
    return CandidateOut.model_validate(row, from_attributes=True)


def _decision(row: ReviewDecision) -> ReviewDecisionOut:
    return ReviewDecisionOut.model_validate(row, from_attributes=True)


@router.get(
    "/sources/{source_id}/review/queue", response_model=ReviewQueueDetail, dependencies=[Depends(require_analyst)]
)
def review_queue_detail(
    source_id: uuid.UUID,
    category: str | None = None,
    component: str | None = None,
    family: str | None = None,
    page_start: int | None = Query(None, ge=1),
    page_end: int | None = Query(None, ge=1),
    risk: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    order: str = Query("risk", pattern="^(document|risk)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> ReviewQueueDetail:
    """Pending candidates of one order in review order: ``document`` (default) follows the
    order as printed — schedule categories first, then the network families; ``risk`` puts
    blocking findings, disagreements and low confidence first (Section 7.2).  Every item
    says why it sits where it does."""
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        ordered = rv.ordered_queue(
            s,
            src,
            category=category,
            component=component,
            family=family,
            page_start=page_start,
            page_end=page_end,
            risk=risk,
            channel=channel,
            status=status,
            order=order,
        )
        page = ordered[offset : offset + limit]
        return ReviewQueueDetail(
            source_id=source_id,
            items=[
                ReviewQueueCandidate(
                    position=meta["position"],
                    candidate=_cand(row),
                    page_index=meta["page_index"],
                    coverage_impact=meta["coverage_impact"],
                    reason=meta["reason"],
                )
                for row, meta in page
            ],
            total=len(ordered),
            limit=limit,
            offset=offset,
            filters={
                k: v
                for k, v in {
                    "category": category,
                    "component": component,
                    "family": family,
                    "page_start": page_start,
                    "page_end": page_end,
                    "risk": risk,
                    "channel": channel,
                    "status": status,
                }.items()
                if v is not None
            },
        )


@router.get(
    "/sources/{source_id}/review/checklist", response_model=ReviewChecklist, dependencies=[Depends(require_analyst)]
)
def review_checklist(source_id: uuid.UUID, request: Request) -> ReviewChecklist:
    settings = request.app.state.settings
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        c = rv.checklist(s, src)
        return ReviewChecklist(
            source_id=source_id,
            items=[ChecklistItem(**i) for i in c["items"]],
            summary=c["summary"],
            inventory_categories=c["inventory_categories"],
            condition_records=c["condition_records"],
            condition_candidates=c["condition_candidates"],
            candidates=c["candidates"],
            awaiting_second_review=c["awaiting_second_review"],
            unresolved=c["unresolved"],
            second_review_policy={
                "material": settings.second_review_material,
                "first_order": settings.second_review_first_order,
            },
        )


@router.get("/candidates/{candidate_id}/evidence", response_model=CandidateEvidenceOut)
def candidate_evidence(
    candidate_id: uuid.UUID, principal: Principal = Depends(require_analyst)
) -> CandidateEvidenceOut:
    """The candidate's evidence references and the views already issued to the caller."""
    with session_scope() as s:
        cand = rv.get_candidate(s, candidate_id)
        record = Candidate.model_validate(cand.effective_record)
        views = rv.views_for(s, cand, principal.email)
        return CandidateEvidenceOut(
            candidate_id=cand.id,
            version=cand.version,
            review_status=cand.review_status,
            evidence=record.evidence,
            views=[EvidenceViewOut.model_validate(v, from_attributes=True) for v in views],
            viewed_required=any(v.evidence_index == 0 for v in views),
        )


@router.get(
    "/candidates/{candidate_id}/evidence/{evidence_index}/image",
    responses={200: {"content": {"image/png": {}}, "description": "rendered page with the cited table outlined"}},
)
def candidate_evidence_image(
    candidate_id: uuid.UUID, evidence_index: int, request: Request, principal: Principal = Depends(require_reviewer)
):
    """Render the cited page to the reviewer and record the view.  The response header
    ``X-Evidence-View-Id`` is what a decision cites; it is issued only here, only to the
    reviewer who receives the bytes."""
    storage: ObjectStore = request.app.state.adapters.storage
    with session_scope() as s:
        cand = rv.get_candidate(s, candidate_id)
        png, view, meta = rv.render_evidence(
            s, storage, request.app.state.settings, cand, evidence_index, viewer=principal.email
        )
        view_id = str(view.id)
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "X-Evidence-View-Id": view_id,
            "X-Evidence-Page": str(meta["page_index"]),
            "X-Evidence-Highlighted": "1" if meta["highlighted"] else "0",
            "X-Evidence-Meta": json.dumps(meta, default=str),
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/candidates/{candidate_id}/decision", response_model=DecisionResult)
def decide_candidate(
    candidate_id: uuid.UUID,
    body: ReviewDecisionRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    principal: Principal = Depends(require_reviewer),
) -> DecisionResult:
    """One of the four outcomes (Section 7.2).  Refused without the rendered evidence, with a
    stale version, without a rationale (except approve), without a cause tag and evidence
    selection for a correction, or by the first reviewer at second review.  An
    ``Idempotency-Key`` replays the original result for the same request."""
    fingerprint = hashlib.sha256((str(candidate_id) + "|" + body.model_dump_json()).encode()).hexdigest()
    with session_scope() as s:
        if idempotency_key:
            rec = s.get(IdempotencyRecord, {"key": idempotency_key, "actor": principal.email})
            if rec is not None:
                if rec.request_fingerprint != fingerprint:
                    raise AppError("idempotency_conflict")
                replay = dict(rec.response_body)
                replay["idempotent_replay"] = True
                response.status_code = rec.response_status
                return DecisionResult.model_validate(replay)
        cand = rv.get_candidate(s, candidate_id)
        decision = rv.decide(
            s, request.app.state.settings, cand, body, actor=principal.email, idempotency_key=idempotency_key
        )
        result = DecisionResult(decision=_decision(decision), candidate=_cand(cand))
        if idempotency_key:
            s.add(
                IdempotencyRecord(
                    key=idempotency_key,
                    actor=principal.email,
                    request_fingerprint=fingerprint,
                    response_status=200,
                    response_body=json.loads(result.model_dump_json()),
                )
            )
        return result


@router.get(
    "/candidates/{candidate_id}/decisions", response_model=DecisionList, dependencies=[Depends(require_analyst)]
)
def candidate_decisions(candidate_id: uuid.UUID) -> DecisionList:
    """Correction history, undone decisions included: nothing is deleted."""
    with session_scope() as s:
        rv.get_candidate(s, candidate_id)
        rows = (
            s.execute(
                select(ReviewDecision)
                .where(ReviewDecision.candidate_id == candidate_id)
                .order_by(ReviewDecision.sequence, ReviewDecision.created_at)
            )
            .scalars()
            .all()
        )
        return DecisionList(decisions=[_decision(r) for r in rows], total=len(rows))


@router.get("/sources/{source_id}/decisions", response_model=DecisionList, dependencies=[Depends(require_analyst)])
def source_decisions(source_id: uuid.UUID, outcome: str | None = None, reviewer: str | None = None) -> DecisionList:
    with session_scope() as s:
        svc.get_source(s, source_id)
        q = select(ReviewDecision).where(ReviewDecision.source_id == source_id)
        if outcome:
            q = q.where(ReviewDecision.outcome == outcome)
        if reviewer:
            q = q.where(ReviewDecision.reviewer == reviewer)
        rows = s.execute(q.order_by(ReviewDecision.created_at)).scalars().all()
        return DecisionList(decisions=[_decision(r) for r in rows], total=len(rows))


@router.post("/review/decisions/{decision_id}/undo", response_model=DecisionResult)
def undo_decision(decision_id: uuid.UUID, principal: Principal = Depends(require_reviewer)) -> DecisionResult:
    with session_scope() as s:
        decision = s.get(ReviewDecision, decision_id)
        if decision is None:
            raise AppError("not_found", f"decision {decision_id} not found")
        rv.undo(s, decision, actor=principal.email)
        cand = rv.get_candidate(s, decision.candidate_id)
        return DecisionResult(decision=_decision(decision), candidate=_cand(cand))


@router.post("/review/batch", response_model=BatchApproveResult)
def batch_approve(
    body: BatchApproveRequest, request: Request, principal: Principal = Depends(require_reviewer)
) -> BatchApproveResult:
    """Batch approval (Section 6.10): only high-confidence, no-risk, finding-free candidates
    routed to batch, each still with its own rendered evidence and version.  Items are
    decided one by one; a refused item never blocks the others and says why."""
    settings = request.app.state.settings
    results: list[BatchItemResult] = []
    approved = 0
    for item in body.items:
        try:
            with session_scope() as s:
                cand = rv.get_candidate(s, item.candidate_id)
                why = rv.batch_eligible(cand)
                if why:
                    raise AppError("validation_failed", f"not batch-eligible: {why}")
                req = ReviewDecisionRequest(
                    outcome="approve",
                    expected_version=item.expected_version,
                    evidence_view_ids=item.evidence_view_ids,
                    time_spent_ms=item.time_spent_ms,
                )
                rv.decide(s, settings, cand, req, actor=principal.email)
                results.append(BatchItemResult(candidate_id=cand.id, ok=True, review_status=cand.review_status))
                approved += 1
        except AppError as e:
            results.append(
                BatchItemResult(candidate_id=item.candidate_id, ok=False, error_type=e.error_type, message=str(e))
            )
    return BatchApproveResult(results=results, approved=approved, refused=len(results) - approved)


@router.get("/review/telemetry", response_model=ReviewTelemetry, dependencies=[Depends(require_analyst)])
def review_telemetry(source_id: uuid.UUID | None = None) -> ReviewTelemetry:
    """Section 7.6: review time by risk tag, correction rate by cause and utility, outcomes.
    No document text, ever."""
    with session_scope() as s:
        data: dict[str, Any] = rv.telemetry(s, source_id)
        return ReviewTelemetry(**data)
