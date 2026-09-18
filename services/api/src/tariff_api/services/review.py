"""Reviewer workflow (Section 7.2) over candidates.

Everything here is a human boundary: the rules never decide.  A decision needs the reviewer
to have had the cited evidence rendered (an ``EvidenceView`` written by the image endpoint
for this reviewer and this candidate), the candidate version they decided on, a rationale
for anything but approval, a cause tag and an evidence selection for a correction, and a
second reviewer where the policy says so.  Decisions are append-only and reversible only by
undo, which restores the candidate from the decision's own ``before`` snapshot.  Nothing
here publishes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pymupdf
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..adapters.storage import ObjectNotFound, ObjectStore
from ..config import Settings
from ..errors import AppError
from ..inventory import NotAPdf, open_document
from ..models import (
    AuditEvent,
    CandidateRecord,
    ConditionRecordRow,
    DocumentHeading,
    EvidenceView,
    FamilyDisposition,
    LocalisationRegion,
    ReviewDecision,
    SourceDocument,
    SourceState,
    TableGridRecord,
)
from ..profiles import load_profile
from ..schemas import ReviewDecisionRequest
from ..tariff_schema import NETWORK_FAMILIES, Candidate
from ..telemetry import request_id_var
from .sources import enqueue_stage

CAUSE_TAGS = ("wrong_table", "header_misbound", "unit", "ocr", "footnote_missed", "cross_reference", "other")
OUTCOMES = ("approve", "correct", "reject", "unresolved")
OPEN_STATUSES = ("pending", "awaiting_second_review")
FINAL_STATUSES = ("approved", "corrected", "rejected", "unresolved")
CORRECTABLE_FIELDS = frozenset(
    {
        "category_code",
        "component_type",
        "value",
        "value_state",
        "original_text",
        "currency",
        "per_unit",
        "frequency",
        "billing_basis",
        "adjustment",
        "adjustment_base",
        "sign",
        "applicability",
        "period",
        "utility",
        "decision_status",
        "reference_target",
        "conditions",
        "derivation",
        "notes",
    }
)
_CONF_RANK = {"low": 0, "medium": 1, "high": 2}
# document order: the schedule first, then the open-access chapter's families as an order
# prints them (wheeling, losses, CSS, additional surcharge, banking, green, transmission)
_FAMILY_ORDER = {
    "retail_tariff": 0,
    "wheeling_charge": 10,
    "oa_loss": 11,
    "distribution_loss_approved": 12,
    "cross_subsidy_surcharge": 13,
    "additional_surcharge": 14,
    "banking_rule": 15,
    "green_tariff": 16,
    "transmission_reference": 17,
}
_COMPONENT_ORDER = {
    "fixed": 0,
    "demand": 1,
    "energy": 2,
    "minimum": 3,
    "tod_adjustment": 4,
    "rebate": 5,
    "surcharge": 6,
    "subsidy": 7,
    "green_premium": 8,
    "charge": 9,
    "loss": 10,
    "condition": 11,
    "cross_reference": 12,
}


# ------------------------------------------------------------------ policy


def second_review_reasons(cand: CandidateRecord, record: Candidate, *, outcome: str, settings: Settings) -> list[str]:
    """Why a first-round approval or correction needs a second reviewer (Section 7.2).  An
    empty list means the first decision is final."""
    reasons: list[str] = []
    if settings.second_review_material:
        if record.component_type == "condition":
            reasons.append("material_condition")
        if record.value_state == "formula" or (
            record.component_type == "tod_adjustment" and record.adjustment == "percent_of"
        ):
            reasons.append("formula_component")
        if outcome == "correct" and cand.channel_agreement == "disagree":
            reasons.append("corrected_channel_disagreement")
    if settings.second_review_first_order and "new_profile" in (cand.risk_tags or []):
        reasons.append("first_order_from_utility")
    return reasons


# ------------------------------------------------------------------ queue and checklist


def _primary_page(rec: dict) -> int | None:
    ev = rec.get("evidence") or []
    return ev[0].get("page_index") if ev else None


def ordered_queue(
    session: Session,
    source: SourceDocument,
    *,
    category: str | None = None,
    component: str | None = None,
    family: str | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    risk: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    order: str = "risk",
) -> list[tuple[CandidateRecord, dict[str, Any]]]:
    """Pending candidates in review order.  ``document`` (default): the retail schedule first,
    category by category in the order the schedule prints them, fixed charge before energy
    charge, then the open-access and network families in page order — the way a reviewer
    reads the order.  ``risk``: blocking findings, findings, channel disagreement, risk tags,
    then coverage impact, then confidence (low first).  Filters of Section 7.2."""
    rows = session.execute(select(CandidateRecord).where(CandidateRecord.source_id == source.id)).scalars().all()
    approved_categories = {
        r.category_code for r in rows if r.review_status in ("approved", "corrected") and r.category_code
    }
    out: list[tuple[CandidateRecord, dict[str, Any]]] = []
    for r in rows:
        if status:
            if r.review_status != status:
                continue
        elif r.review_status not in OPEN_STATUSES:
            continue
        if category and r.category_code != category:
            continue
        if component and r.component_type != component:
            continue
        if family and r.family != family:
            continue
        if risk and risk not in (r.risk_tags or []):
            continue
        if channel and r.channel_agreement != channel:
            continue
        page = _primary_page(r.effective_record)
        if page_start is not None and (page is None or page < page_start):
            continue
        if page_end is not None and (page is None or page > page_end):
            continue
        no_approved_fact = bool(r.category_code) and r.category_code not in approved_categories
        if order == "risk":
            rank: tuple = (
                -r.blocking_finding_count,
                -r.finding_count,
                0 if r.channel_agreement == "disagree" else 1,
                -len(r.risk_tags or []),
                0 if no_approved_fact else 1,
                _CONF_RANK.get(r.confidence, 1),
                r.family,
                r.category_code or "",
                r.candidate_key,
            )
        else:
            ev = (r.effective_record.get("evidence") or [{}])[0]
            rank = (
                _FAMILY_ORDER.get(r.family, 50),
                page or 0,
                ev.get("grid_ordinal") or 0,
                r.category_code or "",
                _COMPONENT_ORDER.get(r.component_type, 50),
                ev.get("row") or 0,
                ev.get("col") or 0,
                ev.get("line_no") or 0,
                r.candidate_key,
            )
        out.append(
            (
                r,
                {
                    "rank": rank,
                    "page_index": page,
                    "coverage_impact": no_approved_fact,
                    "reason": _reason(r, no_approved_fact),
                },
            )
        )
    out.sort(key=lambda t: t[1]["rank"])
    for pos, (_, meta) in enumerate(out, start=1):
        meta["position"] = pos
        del meta["rank"]
    return out


def _reason(r: CandidateRecord, no_approved_fact: bool) -> str:
    if r.blocking_finding_count:
        return f"{r.blocking_finding_count} blocking validator finding(s)"
    if r.channel_agreement == "disagree":
        return "channels disagree on " + (", ".join(r.disagreeing_fields or []) or "the record")
    if r.finding_count:
        return f"{r.finding_count} validator finding(s)"
    if r.risk_tags:
        return "risk: " + ", ".join(r.risk_tags)
    if no_approved_fact:
        return "category has no approved fact yet"
    return f"{r.confidence} confidence"


def _item_status(statuses: list[str]) -> str:
    if not statuses:
        return "not_started"
    if any(s == "unresolved" for s in statuses):
        return "unresolved"
    if all(s in OPEN_STATUSES for s in statuses):
        return "not_started"
    if any(s in OPEN_STATUSES for s in statuses):
        return "in_progress"
    if any(s == "corrected" for s in statuses):
        return "corrected"
    if any(s == "approved" for s in statuses):
        return "approved"
    return "rejected"


def checklist(session: Session, source: SourceDocument) -> dict[str, Any]:
    """Completeness checklist derived from the inventory (Section 7.2): every expected
    category and component, every charge family and every material condition with its
    status.  ``expected_from`` says whether the inventory or only the extraction expects
    the item; an inventory category with no candidate is a visible gap, never silence."""
    rows = session.execute(select(CandidateRecord).where(CandidateRecord.source_id == source.id)).scalars().all()
    inventory: list[str] = []
    if source.reading_profile_id:
        profile = load_profile(source.reading_profile_id, source.reading_profile_version)
        inventory = sorted(
            {
                h.code_canonical
                for h in session.execute(
                    select(DocumentHeading).where(DocumentHeading.source_id == source.id)
                ).scalars()
                if h.kind == profile.schedule_heading_kind and h.code_canonical
            }
        )
    dispositions = {
        d.family: d.disposition
        for d in session.execute(select(FamilyDisposition).where(FamilyDisposition.source_id == source.id)).scalars()
    }
    # regions a reviewer excluded at the localisation checkpoint, by the family they covered:
    # the note explains why the family has no candidate and informs the disposition
    excluded_notes: dict[str, list[str]] = {}
    for reg in session.execute(
        select(LocalisationRegion).where(
            LocalisationRegion.source_id == source.id, LocalisationRegion.excluded.is_(True)
        )
    ).scalars():
        if reg.sub_role:
            excluded_notes.setdefault(reg.sub_role, []).append(
                f"pages {reg.page_start}–{reg.page_end} excluded by {reg.annotated_by}: {reg.reviewer_note}"
            )
    items: list[dict[str, Any]] = []
    groups: dict[tuple[str, str], list[CandidateRecord]] = {}
    for r in rows:
        if r.family == "retail_tariff":
            groups.setdefault((r.category_code or "(no category)", r.component_type), []).append(r)
    seen_categories = {k[0] for k in groups}
    for code in inventory:
        if code not in seen_categories:
            items.append(
                {
                    "kind": "category",
                    "key": code,
                    "category_code": code,
                    "component_type": None,
                    "expected_from": "inventory",
                    "candidates": 0,
                    "status": "not_started",
                    "counts": {},
                    "note": "rate schedule heading in the inventory; no candidate was extracted",
                }
            )
    for (code, comp), rs in sorted(groups.items()):
        statuses = [r.review_status for r in rs]
        items.append(
            {
                "kind": "category_component",
                "key": f"{code}|{comp}",
                "category_code": code,
                "component_type": comp,
                "expected_from": "inventory" if code in inventory else "extraction",
                "candidates": len(rs),
                "status": _item_status(statuses),
                "counts": _count(statuses),
                "note": None,
            }
        )
    for fam in NETWORK_FAMILIES:
        rs = [r for r in rows if r.family == fam]
        statuses = [r.review_status for r in rs]
        disp = dispositions.get(fam)
        items.append(
            {
                "kind": "family",
                "key": fam,
                "category_code": None,
                "component_type": None,
                "expected_from": "spec",
                "candidates": len(rs),
                "status": _item_status(statuses) if rs else (f"disposition:{disp}" if disp else "not_started"),
                "counts": _count(statuses),
                "note": "; ".join(
                    ([] if rs or disp else ["no candidate and no reviewed disposition"]) + excluded_notes.get(fam, [])
                )
                or None,
            }
        )
    conditions = session.execute(
        select(func.count()).select_from(ConditionRecordRow).where(ConditionRecordRow.source_id == source.id)
    ).scalar_one()
    condition_cands = [r for r in rows if r.component_type == "condition"]
    summary = _count([i["status"] for i in items])
    return {
        "items": items,
        "summary": summary,
        "inventory_categories": inventory,
        "condition_records": conditions,
        "condition_candidates": _count([r.review_status for r in condition_cands]),
        "candidates": _count([r.review_status for r in rows]),
        "awaiting_second_review": sum(1 for r in rows if r.review_status == "awaiting_second_review"),
        "unresolved": sum(1 for r in rows if r.review_status == "unresolved"),
    }


def _count(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


# ------------------------------------------------------------------ evidence


def get_candidate(session: Session, candidate_id: uuid.UUID) -> CandidateRecord:
    row = session.get(CandidateRecord, candidate_id)
    if row is None:
        raise AppError("not_found", f"candidate {candidate_id} not found")
    return row


def render_evidence(
    session: Session,
    storage: ObjectStore,
    settings: Settings,
    cand: CandidateRecord,
    evidence_index: int,
    *,
    viewer: str,
) -> tuple[bytes, EvidenceView, dict[str, Any]]:
    """Render the cited page with the cited table outlined and record that this viewer saw
    it.  The view row is the only thing a decision can cite as evidence viewed."""
    record = Candidate.model_validate(cand.effective_record)
    if evidence_index < 0 or evidence_index >= len(record.evidence):
        raise AppError("not_found", f"candidate has {len(record.evidence)} evidence reference(s)")
    ref = record.evidence[evidence_index]
    src = session.get(SourceDocument, cand.source_id)
    assert src is not None
    try:
        data = storage.get(ObjectStore.SOURCES, src.object_key)
    except ObjectNotFound as e:
        raise AppError("storage_unavailable", "object missing for registered source") from e
    try:
        doc = open_document(data)
    except NotAPdf as e:
        raise AppError("source_unreadable", str(e)) from e
    if ref.page_index < 1 or ref.page_index > doc.page_count:
        raise AppError("validation_failed", f"evidence cites page {ref.page_index}; document has {doc.page_count}")
    page = doc[ref.page_index - 1]
    highlighted = False
    bbox: list[float] | None = None
    if ref.kind == "cell" and ref.grid_ordinal is not None:
        grid = session.execute(
            select(TableGridRecord).where(
                TableGridRecord.source_id == cand.source_id,
                TableGridRecord.page_index == ref.page_index,
                TableGridRecord.ordinal == ref.grid_ordinal,
                TableGridRecord.is_primary.is_(True),
            )
        ).scalar_one_or_none()
        if grid is not None and grid.bbox and len(grid.bbox) == 4:
            bbox = [float(v) for v in grid.bbox]
            shape = page.new_shape()
            shape.draw_rect(pymupdf.Rect(*bbox))
            shape.finish(color=(0.85, 0.1, 0.1), width=2.0)
            shape.commit()
            highlighted = True
    png = page.get_pixmap(dpi=settings.evidence_render_dpi).tobytes("png")
    doc.close()
    view = EvidenceView(
        source_id=cand.source_id,
        candidate_id=cand.id,
        evidence_index=evidence_index,
        page_index=ref.page_index,
        viewer=viewer,
        dpi=settings.evidence_render_dpi,
        highlighted=highlighted,
    )
    session.add(view)
    session.flush()
    meta = {
        "page_index": ref.page_index,
        "kind": ref.kind,
        "grid_ordinal": ref.grid_ordinal,
        "row": ref.row,
        "col": ref.col,
        "line_no": ref.line_no,
        "header_path": ref.header_path,
        "row_path": ref.row_path,
        "clause_path": ref.clause_path,
        "excerpt": ref.excerpt,
        "table_bbox": bbox,
        "highlighted": highlighted,
    }
    return png, view, meta


def render_page_for(
    session: Session,
    storage: ObjectStore,
    settings: Settings,
    source: SourceDocument,
    page_index: int,
    cands: list[CandidateRecord],
    *,
    viewer: str,
) -> tuple[bytes, dict[str, str], list[str]]:
    """Render one page once with every cited table outlined and record a view for each
    candidate whose primary evidence is on that page — the tariff-table screen shows a
    reviewer the page for a whole block before they approve its values.  Returns the PNG,
    `{candidate_id: view_id}` and the ids of candidates skipped because their primary
    evidence is on another page (those need their own render)."""
    try:
        data = storage.get(ObjectStore.SOURCES, source.object_key)
    except ObjectNotFound as e:
        raise AppError("storage_unavailable", "object missing for registered source") from e
    try:
        doc = open_document(data)
    except NotAPdf as e:
        raise AppError("source_unreadable", str(e)) from e
    if page_index < 1 or page_index > doc.page_count:
        raise AppError("validation_failed", f"page {page_index} is outside the document ({doc.page_count} pages)")
    page = doc[page_index - 1]
    grids = {
        g.ordinal: g
        for g in session.execute(
            select(TableGridRecord).where(
                TableGridRecord.source_id == source.id,
                TableGridRecord.page_index == page_index,
                TableGridRecord.is_primary.is_(True),
            )
        ).scalars()
    }
    outlined: set[int] = set()
    views: dict[str, str] = {}
    skipped: list[str] = []
    shape = page.new_shape()
    for cand in cands:
        record = Candidate.model_validate(cand.effective_record)
        ref = record.evidence[0]
        if ref.page_index != page_index:
            skipped.append(str(cand.id))
            continue
        highlighted = False
        if ref.kind == "cell" and ref.grid_ordinal is not None and ref.grid_ordinal in grids:
            g = grids[ref.grid_ordinal]
            if g.bbox and len(g.bbox) == 4:
                if ref.grid_ordinal not in outlined:
                    shape.draw_rect(pymupdf.Rect(*[float(v) for v in g.bbox]))
                    outlined.add(ref.grid_ordinal)
                highlighted = True
        view = EvidenceView(
            source_id=source.id,
            candidate_id=cand.id,
            evidence_index=0,
            page_index=page_index,
            viewer=viewer,
            dpi=settings.evidence_render_dpi,
            highlighted=highlighted,
        )
        session.add(view)
        session.flush()
        views[str(cand.id)] = str(view.id)
    if outlined:
        shape.finish(color=(0.85, 0.1, 0.1), width=2.0)
        shape.commit()
    png = page.get_pixmap(dpi=settings.evidence_render_dpi).tobytes("png")
    doc.close()
    return png, views, skipped


def views_for(session: Session, cand: CandidateRecord, viewer: str) -> list[EvidenceView]:
    return (
        session.execute(
            select(EvidenceView)
            .where(EvidenceView.candidate_id == cand.id, EvidenceView.viewer == viewer)
            .order_by(EvidenceView.rendered_at)
        )
        .scalars()
        .all()
    )


# ------------------------------------------------------------------ decisions


def _snapshot(cand: CandidateRecord) -> dict[str, Any]:
    return {
        "review_status": cand.review_status,
        "reviewed_record": cand.reviewed_record,
        "candidate_key": cand.candidate_key,
        "reviewed_by": cand.reviewed_by,
        "reviewed_at": cand.reviewed_at.isoformat() if cand.reviewed_at else None,
        "first_reviewer": cand.first_reviewer,
        "second_review": cand.second_review,
        "version": cand.version,
    }


def _restore(cand: CandidateRecord, snap: dict[str, Any]) -> None:
    cand.review_status = snap["review_status"]
    cand.reviewed_record = snap["reviewed_record"]
    cand.candidate_key = snap["candidate_key"]
    cand.reviewed_by = snap["reviewed_by"]
    cand.reviewed_at = datetime.fromisoformat(snap["reviewed_at"]) if snap["reviewed_at"] else None
    cand.first_reviewer = snap["first_reviewer"]
    cand.second_review = snap["second_review"]


def _check_views(
    session: Session, settings: Settings, cand: CandidateRecord, view_ids: list[uuid.UUID], *, actor: str
) -> tuple[list[EvidenceView], int | None]:
    """The views a decision cites must be this reviewer's, for this candidate, recent, and
    must include the primary evidence (index 0).  Otherwise the approve control is, in
    effect, disabled: the API refuses."""
    if not view_ids:
        raise AppError(
            "validation_failed",
            "the cited evidence has not been rendered to you; open the evidence before deciding",
            extra={"evidence_required": [0]},
        )
    views = (
        session.execute(
            select(EvidenceView).where(
                EvidenceView.id.in_(view_ids), EvidenceView.candidate_id == cand.id, EvidenceView.viewer == actor
            )
        )
        .scalars()
        .all()
    )
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.evidence_view_max_age_seconds)
    fresh = [v for v in views if v.rendered_at >= cutoff]
    if len(fresh) != len(set(view_ids)):
        raise AppError(
            "validation_failed",
            "one or more evidence views are not yours, not for this candidate, or too old; re-open the evidence",
            extra={"evidence_required": [0]},
        )
    if not any(v.evidence_index == 0 for v in fresh):
        raise AppError(
            "validation_failed",
            "the primary evidence (index 0) has not been rendered to you",
            extra={"evidence_required": [0]},
        )
    first = min(v.rendered_at for v in fresh)
    return fresh, int((datetime.now(UTC) - first).total_seconds() * 1000)


def _build_correction(cand: CandidateRecord, body: ReviewDecisionRequest) -> tuple[dict[str, Any], list[str]]:
    base = dict(cand.effective_record)
    patch = body.correction or {}
    unknown = sorted(set(patch) - CORRECTABLE_FIELDS)
    if unknown:
        raise AppError("validation_failed", f"fields cannot be corrected: {', '.join(unknown)}")
    if not patch and not body.evidence and not body.evidence_indices:
        raise AppError("validation_failed", "a correction must change at least one field or the evidence selection")
    merged = {**base, **patch}
    if body.evidence:
        merged["evidence"] = [e.model_dump() for e in body.evidence]
    elif body.evidence_indices:
        refs = base.get("evidence") or []
        bad = [i for i in body.evidence_indices if i < 0 or i >= len(refs)]
        if bad:
            raise AppError("validation_failed", f"evidence indices out of range: {bad}")
        merged["evidence"] = [refs[i] for i in body.evidence_indices]
    else:
        raise AppError("validation_failed", "a correction must select its evidence (evidence_indices or evidence)")
    try:
        record = Candidate.model_validate(merged)
    except ValidationError as e:
        raise AppError(
            "validation_failed",
            "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()),
        ) from e
    corrected = record.model_dump(mode="json")
    changed = sorted(k for k in corrected if corrected.get(k) != base.get(k))
    return corrected, changed


def decide(
    session: Session,
    settings: Settings,
    cand: CandidateRecord,
    body: ReviewDecisionRequest,
    *,
    actor: str,
    idempotency_key: str | None = None,
) -> ReviewDecision:
    src = session.get(SourceDocument, cand.source_id)
    assert src is not None
    if src.state not in (SourceState.awaiting_review, SourceState.published):
        raise AppError("invalid_transition", f"source is {src.state.value}; decisions are taken while it awaits review")
    if cand.published_release_id is not None:
        raise AppError("invalid_transition", "this candidate is published; its decision is no longer changeable")
    if cand.review_status not in OPEN_STATUSES:
        raise AppError(
            "invalid_transition",
            f"candidate is already {cand.review_status}; undo the last decision to decide again",
        )
    if body.expected_version != cand.version:
        raise AppError(
            "conflict_stale_version",
            f"candidate is at version {cand.version}, you decided on {body.expected_version}",
            extra={
                "current_version": cand.version,
                "current_status": cand.review_status,
                "reviewed_by": cand.reviewed_by,
            },
        )
    review_round = 2 if cand.review_status == "awaiting_second_review" else 1
    if review_round == 2 and cand.first_reviewer == actor:
        raise AppError(
            "validation_failed",
            "second review must be by a different reviewer",
            extra={"first_reviewer": cand.first_reviewer},
        )
    if body.outcome != "approve" and not (body.rationale and body.rationale.strip()):
        raise AppError("validation_failed", f"{body.outcome} needs a rationale")
    views: list[EvidenceView] = []
    view_ms: int | None = None
    if body.outcome in ("approve", "correct"):
        views, view_ms = _check_views(session, settings, cand, body.evidence_view_ids, actor=actor)
    corrected: dict[str, Any] | None = None
    changed: list[str] = []
    if body.outcome == "correct":
        if body.cause_tag not in CAUSE_TAGS:
            raise AppError("validation_failed", f"a correction needs a cause tag: one of {', '.join(CAUSE_TAGS)}")
        corrected, changed = _build_correction(cand, body)

    before = _snapshot(cand)
    record = Candidate.model_validate(corrected or cand.effective_record)
    reasons: list[str] = []
    if body.outcome in ("approve", "correct"):
        if review_round == 1:
            reasons = second_review_reasons(cand, record, outcome=body.outcome, settings=settings)
            if reasons:
                new_status = "awaiting_second_review"
                cand.second_review = "pending"
                cand.first_reviewer = actor
            else:
                new_status = "approved" if body.outcome == "approve" else "corrected"
        else:
            new_status = "approved" if body.outcome == "approve" else "corrected"
            cand.second_review = "done"
    else:
        new_status = "rejected" if body.outcome == "reject" else "unresolved"
        if review_round == 2:
            cand.second_review = "done"
    if corrected is not None:
        cand.reviewed_record = corrected
        cand.candidate_key = record.key()[:400]
    now = datetime.now(UTC)
    cand.review_status = new_status
    cand.reviewed_by = actor
    cand.reviewed_at = now
    cand.decision_count += 1
    cand.version += 1
    seq = cand.decision_count
    revalidation_job = None
    if corrected is not None:
        revalidation_job = enqueue_stage(session, settings, src, "validate_source", actor=actor)
    after = _snapshot(cand)
    after["second_review_reasons"] = reasons
    after["revalidation_job_id"] = str(revalidation_job.id) if revalidation_job else None
    decision = ReviewDecision(
        source_id=cand.source_id,
        candidate_id=cand.id,
        sequence=seq,
        review_round=review_round,
        outcome=body.outcome,
        reviewer=actor,
        candidate_version=body.expected_version,
        rationale=body.rationale,
        cause_tag=body.cause_tag if body.outcome == "correct" else None,
        corrected_record=corrected,
        corrected_fields=changed,
        evidence_view_ids=[str(v.id) for v in views],
        evidence_viewed=bool(views),
        time_spent_ms=body.time_spent_ms,
        view_to_decision_ms=view_ms,
        before=before,
        after=after,
        idempotency_key=idempotency_key,
        request_id=request_id_var.get(),
    )
    session.add(decision)
    session.add(
        AuditEvent(
            actor=actor,
            action=f"candidate.{body.outcome}",
            entity_type="candidate",
            entity_id=str(cand.id),
            before=before,
            after=after,
            reason=body.rationale,
            request_id=request_id_var.get(),
        )
    )
    session.flush()
    return decision


def undo(session: Session, decision: ReviewDecision, *, actor: str) -> ReviewDecision:
    """Reverse the latest decision on a candidate (Section 7.2: undo within the session before
    publication).  Only its reviewer may undo it; the decision row stays, marked undone."""
    cand = get_candidate(session, decision.candidate_id)
    src = session.get(SourceDocument, cand.source_id)
    assert src is not None
    if decision.undone:
        raise AppError("invalid_transition", "this decision is already undone")
    if decision.reviewer != actor:
        raise AppError("permission_denied", "only the reviewer who took a decision can undo it")
    if cand.published_release_id is not None:
        raise AppError("invalid_transition", "the candidate is published; its decision is no longer reversible")
    latest = session.execute(
        select(func.max(ReviewDecision.sequence)).where(
            ReviewDecision.candidate_id == cand.id, ReviewDecision.undone.is_(False)
        )
    ).scalar_one()
    if latest != decision.sequence:
        raise AppError("invalid_transition", "only the latest decision on a candidate can be undone")
    before = _snapshot(cand)
    _restore(cand, decision.before)
    cand.version += 1
    decision.undone = True
    decision.undone_by = actor
    decision.undone_at = datetime.now(UTC)
    session.add(
        AuditEvent(
            actor=actor,
            action="candidate.undo",
            entity_type="candidate",
            entity_id=str(cand.id),
            before=before,
            after=_snapshot(cand),
            reason=f"undo decision {decision.id} ({decision.outcome})",
            request_id=request_id_var.get(),
        )
    )
    session.flush()
    return decision


def batch_eligible(cand: CandidateRecord) -> str | None:
    """Why a candidate may not be batch-approved (Section 6.10): only high confidence with no
    risk tags and no findings, still pending, and never a real-source candidate flagged
    for individual review."""
    if cand.review_status != "pending":
        return f"candidate is {cand.review_status}"
    if cand.routing != "batch":
        return "routed to individual review"
    if cand.risk_tags:
        return "carries risk tags: " + ", ".join(cand.risk_tags)
    if cand.confidence != "high":
        return f"confidence is {cand.confidence}"
    if cand.finding_count:
        return "has validator findings"
    return None


# ------------------------------------------------------------------ telemetry (Section 7.6)


def telemetry(session: Session, source_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Interaction telemetry without document text: review time per candidate by risk tag,
    correction rate by cause tag and by utility, outcomes, undo count, second reviews."""
    q = select(ReviewDecision, CandidateRecord).join(CandidateRecord, CandidateRecord.id == ReviewDecision.candidate_id)
    if source_id is not None:
        q = q.where(ReviewDecision.source_id == source_id)
    rows = session.execute(q).all()
    by_tag: dict[str, list[int]] = {}
    outcomes: dict[str, int] = {}
    cause: dict[str, int] = {}
    by_utility: dict[str, dict[str, int]] = {}
    undone = 0
    second = 0
    for d, c in rows:
        if d.undone:
            undone += 1
            continue
        outcomes[d.outcome] = outcomes.get(d.outcome, 0) + 1
        if d.review_round == 2:
            second += 1
        if d.view_to_decision_ms is not None:
            for tag in c.risk_tags or ["none"]:
                by_tag.setdefault(tag, []).append(d.view_to_decision_ms)
        util = c.utility or "(unknown)"
        u = by_utility.setdefault(util, {"decisions": 0, "corrections": 0})
        u["decisions"] += 1
        if d.outcome == "correct":
            u["corrections"] += 1
            cause[d.cause_tag or "other"] = cause.get(d.cause_tag or "other", 0) + 1
    decisions = sum(outcomes.values())
    return {
        "decisions": decisions,
        "outcomes": dict(sorted(outcomes.items())),
        "undone": undone,
        "second_reviews": second,
        "correction_rate": round(outcomes.get("correct", 0) / decisions, 4) if decisions else None,
        "corrections_by_cause": dict(sorted(cause.items())),
        "by_utility": {
            k: {**v, "correction_rate": round(v["corrections"] / v["decisions"], 4) if v["decisions"] else None}
            for k, v in sorted(by_utility.items())
        },
        "review_ms_by_risk_tag": {
            k: {"n": len(v), "mean_ms": int(sum(v) / len(v)), "max_ms": max(v)} for k, v in sorted(by_tag.items())
        },
    }
