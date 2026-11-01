"""ARR (ARR spec, ADR-0017, ADR-0018): the taxonomy and commission mappings as the app sees
them; the ARR reading track of an order (chapters, candidates, identity findings,
publication); the reviewed ARR history of a licensee; assumption sets, formulations and
filing drafts.  Facts, assumptions and projections are separate resources and every
response names its kind.  Nothing here approves a candidate or files a petition."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import or_, select

from .. import workspace as ws
from ..adapters.storage import ObjectNotFound, ObjectStore
from ..auth import Principal, require_admin, require_analyst, require_reviewer
from ..db import session_scope
from ..errors import AppError
from ..models import ArrAssumptionSet, ArrFormulation, FilingDraft, SourceDocument, Utility
from ..schemas import (
    ARR_VALUE_TYPES,
    ArrAssumptionIn,
    ArrAssumptionOut,
    ArrAssumptionSetCreate,
    ArrAssumptionSetOut,
    ArrBenchmarksOut,
    ArrChapterDecision,
    ArrChapterOut,
    ArrChapterUpdate,
    ArrFormulationCreate,
    ArrFormulationOut,
    ArrHistoryOut,
    ArrMappingOut,
    ArrProjectionLineOut,
    ArrPublishOut,
    ArrReadingOut,
    ArrReproduceOut,
    ArrTaxonomyOut,
    CandidateList,
    CandidateOut,
    FilingDraftOut,
    FindingOut,
    JobSummary,
    MappingConventionIn,
    MappingDecisionIn,
)

router = APIRouter(tags=["arr"])


@router.get("/arr/taxonomy", response_model=ArrTaxonomyOut, dependencies=[Depends(require_analyst)])
def get_taxonomy() -> ArrTaxonomyOut:
    from ..arr.taxonomy import load_taxonomy, mapping_files

    t = load_taxonomy()
    return ArrTaxonomyOut(
        id=t.id,
        version=t.version,
        status=t.status,
        canonical_units=t.canonical_units,
        value_types=[c.model_dump() for c in t.value_types],
        reason_categories=[c.model_dump() for c in t.reason_categories],
        line_items=[i.model_dump() for i in t.line_items],
        identities=[i.model_dump() for i in t.identities],
        mappings={k: [v for v, _ in sorted(paths)] for k, paths in mapping_files().items()},
    )


@router.get("/arr/mappings/{commission}", response_model=ArrMappingOut, dependencies=[Depends(require_analyst)])
def get_mapping(commission: str, version: int | None = None) -> ArrMappingOut:
    from ..arr.taxonomy import load_mapping

    try:
        m = load_mapping(commission, version)
    except (FileNotFoundError, StopIteration) as e:
        raise AppError("not_found", f"no ARR mapping for {commission}") from e
    d: dict[str, Any] = m.model_dump()
    return ArrMappingOut(**d)


# ------------------------------------------------------------------ reading track of an order


def _source(s, source_id: uuid.UUID) -> SourceDocument:
    src = s.get(SourceDocument, source_id)
    if src is None:
        raise AppError("not_found", f"source {source_id} not found")
    return src


def _reading(s, src: SourceDocument) -> ArrReadingOut:
    from ..arr import service as arr
    from ..services.review import arr_mapping_confirmed

    ok, why = arr_mapping_confirmed(s, src)
    counts = Counter(c.review_status for c in arr.arr_candidates(s, src.id))
    return ArrReadingOut(
        source_id=src.id,
        arr_state=src.arr_state,
        arr_summary=src.arr_summary,
        chapters=[ArrChapterOut.model_validate(c, from_attributes=True) for c in arr.chapters(s, src.id)],
        candidates_by_status=dict(counts),
        findings=[FindingOut.model_validate(f, from_attributes=True) for f in arr.arr_findings(s, src.id)],
        mapping_confirmed=ok,
        mapping_note=why or "confirmed",
        commission=src.utility.commission.code if src.utility and src.utility.commission else None,
    )


@router.post("/sources/{source_id}/arr/read", response_model=JobSummary, status_code=202)
def read_arr(source_id: uuid.UUID, request: Request, principal: Principal = Depends(require_admin)) -> JobSummary:
    from ..arr import service as arr

    with session_scope() as s:
        src = _source(s, source_id)
        job = arr.start_reading(s, request.app.state.settings, src, actor=principal.email)
        s.flush()
        return JobSummary.model_validate(job, from_attributes=True)


@router.get("/sources/{source_id}/arr", response_model=ArrReadingOut, dependencies=[Depends(require_analyst)])
def get_reading(source_id: uuid.UUID) -> ArrReadingOut:
    with session_scope() as s:
        return _reading(s, _source(s, source_id))


@router.put("/sources/{source_id}/arr/chapters/{chapter_id}", response_model=ArrChapterOut)
def update_chapter(
    source_id: uuid.UUID,
    chapter_id: uuid.UUID,
    body: ArrChapterUpdate,
    principal: Principal = Depends(require_reviewer),
) -> ArrChapterOut:
    from ..arr import service as arr

    with session_scope() as s:
        src = _source(s, source_id)
        ch = arr.update_chapter(s, src, chapter_id, actor=principal.email, **body.model_dump())
        s.flush()
        return ArrChapterOut.model_validate(ch, from_attributes=True)


@router.post("/sources/{source_id}/arr/chapters/decision", response_model=ArrReadingOut)
def confirm_chapters(
    source_id: uuid.UUID, body: ArrChapterDecision, request: Request, principal: Principal = Depends(require_reviewer)
) -> ArrReadingOut:
    from ..arr import service as arr

    with session_scope() as s:
        src = _source(s, source_id)
        arr.confirm_chapters(s, request.app.state.settings, src, actor=principal.email, rationale=body.rationale)
        s.flush()
        return _reading(s, src)


@router.get(
    "/sources/{source_id}/arr/candidates", response_model=CandidateList, dependencies=[Depends(require_analyst)]
)
def list_arr_candidates(source_id: uuid.UUID) -> CandidateList:
    from ..arr import service as arr

    with session_scope() as s:
        _source(s, source_id)
        rows = arr.arr_candidates(s, source_id)
        return CandidateList(
            candidates=[CandidateOut.model_validate(r, from_attributes=True) for r in rows],
            total=len(rows),
            limit=len(rows),
            offset=0,
        )


@router.post("/sources/{source_id}/arr/publish", response_model=ArrPublishOut)
def publish_arr(source_id: uuid.UUID, principal: Principal = Depends(require_reviewer)) -> ArrPublishOut:
    from ..arr import service as arr

    with session_scope() as s:
        out = arr.publish(s, _source(s, source_id), actor=principal.email)
        return ArrPublishOut(**out)


# ------------------------------------------------------------------ licensee: history, assumptions, formulations


def _utility(s, code: str) -> Utility:
    from ..arr.service import utility_by_code

    return utility_by_code(s, code)


@router.get("/arr/readings", response_model=dict, dependencies=[Depends(require_analyst)])
def arr_readings() -> dict:
    """Every order whose ARR is being read, by state and commission, with its preview, its
    review counts and the next human step (increment 49).  Read-only."""
    from ..arr import board

    with session_scope() as s:
        return board.readings(s)


@router.get("/arr/mappings/{commission}/workbench", response_model=dict, dependencies=[Depends(require_analyst)])
def mapping_workbench(commission: str) -> dict:
    """What the commission's mapping does not place yet, across its read orders, with the
    reviewer's decisions and word-overlap suggestions (increment 39)."""
    from ..arr import workbench as wb

    with session_scope() as s:
        return wb.unplaced(s, commission.upper())


@router.put("/arr/mappings/{commission}/decisions", response_model=dict)
def mapping_decide(commission: str, body: MappingDecisionIn, principal: Principal = Depends(require_reviewer)) -> dict:
    from ..arr import workbench as wb

    with session_scope() as s:
        d = wb.decide(s, commission.upper(), actor=principal.email, **body.model_dump())
        return {"label": d.label, "kind": d.kind, "code": d.code, "note": d.note, "decided_by": d.decided_by}


@router.put("/arr/mappings/{commission}/conventions", response_model=dict)
def mapping_convention(
    commission: str, body: MappingConventionIn, principal: Principal = Depends(require_reviewer)
) -> dict:
    """A reviewer's answer to one convention question (increment 44); written into the next
    mapping version by the draft, never applied to the identities until that file is committed."""
    from ..arr import workbench as wb

    with session_scope() as s:
        d = wb.decide_convention(s, commission.upper(), actor=principal.email, **body.model_dump())
        return {"key": d.label, "value": d.code, "note": d.note, "decided_by": d.decided_by}


@router.delete("/arr/mappings/{commission}/decisions", status_code=204)
def mapping_withdraw(commission: str, label: str, principal: Principal = Depends(require_reviewer)) -> Response:
    from ..arr import workbench as wb

    with session_scope() as s:
        wb.withdraw(s, commission.upper(), label, actor=principal.email)
    return Response(status_code=204)


@router.get(
    "/arr/mappings/{commission}/draft",
    dependencies=[Depends(require_analyst)],
    responses={200: {"description": "the next version of the mapping file with the decisions, status draft"}},
)
def mapping_draft(commission: str) -> Response:
    import json as _json

    from ..arr import workbench as wb

    with session_scope() as s:
        data = wb.draft(s, commission.upper())
    name = f"{data['id']}.v{data['version']}.json"
    return Response(
        _json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        media_type="application/json",
        headers={"Content-Disposition": _disposition(name)},
    )


@router.get("/arr/benchmarks", response_model=ArrBenchmarksOut, dependencies=[Depends(require_analyst)])
def benchmarks(
    fiscal_year: str, value_type: str = "approved", include_fixtures: bool = False, commission: str | None = None
) -> ArrBenchmarksOut:
    """Ratios across licensees for one year and voice, each with the facts it is computed from."""
    from ..arr import benchmarks as bm
    from ..arr.formulate import FY_RE

    if not FY_RE.match(fiscal_year):
        raise AppError("validation_failed", "fiscal_year must look like FY2025-26")
    if value_type not in ARR_VALUE_TYPES:
        raise AppError("validation_failed", f"value_type is one of {', '.join(ARR_VALUE_TYPES)}")
    with session_scope() as s:
        return ArrBenchmarksOut(
            **bm.compute(
                s,
                fiscal_year=fiscal_year,
                value_type=value_type,
                include_fixtures=include_fixtures,
                commission=commission,
            )
        )


@router.get("/arr/utilities/{code}/history", response_model=ArrHistoryOut, dependencies=[Depends(require_analyst)])
def history(code: str) -> ArrHistoryOut:
    from ..arr import service as arr

    with session_scope() as s:
        return ArrHistoryOut(**arr.history(s, _utility(s, code)))


@router.get(
    "/arr/utilities/{code}/history.xlsx",
    dependencies=[Depends(require_analyst)],
    responses={200: {"description": "the licensee's reviewed ARR facts as a workbook, each with its order and page"}},
)
def history_xlsx(code: str) -> Response:
    from ..arr import service as arr

    with session_scope() as s:
        u = _utility(s, code)
        body = arr.history_workbook(s, u)
        name = f"ARR-history-{u.code}.xlsx"
    return Response(
        body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _disposition(name)},
    )


def _set_out(s, aset: ArrAssumptionSet) -> ArrAssumptionSetOut:
    from ..arr import service as arr

    u = s.get(Utility, aset.utility_id)
    return ArrAssumptionSetOut(
        id=aset.id,
        utility=u.code,
        organisation_id=aset.organisation_id,
        name=aset.name,
        version=aset.version,
        status=aset.status,
        based_on_id=aset.based_on_id,
        created_by=aset.created_by,
        created_at=aset.created_at,
        frozen_at=aset.frozen_at,
        assumptions=[ArrAssumptionOut.model_validate(a, from_attributes=True) for a in arr.assumptions_of(s, aset.id)],
    )


def _visible(s, principal: Principal, column):
    """A filter for listing: desk objects plus the principal's organisations' objects."""
    orgs = ws.visible_orgs(s, principal)
    if orgs is None:
        return True
    return or_(column.is_(None), column.in_(orgs)) if orgs else column.is_(None)


@router.post("/arr/utilities/{code}/assumption-sets", response_model=ArrAssumptionSetOut, status_code=201)
def create_assumption_set(
    code: str, body: ArrAssumptionSetCreate, principal: Principal = Depends(require_analyst)
) -> ArrAssumptionSetOut:
    from ..arr import service as arr

    with session_scope() as s:
        ws.require(s, principal, body.organisation_id, "write", what="assumption set")
        aset = arr.create_assumption_set(
            s,
            _utility(s, code),
            body.name,
            actor=principal.email,
            based_on=body.based_on_id,
            organisation_id=body.organisation_id,
        )
        s.flush()
        s.refresh(aset)
        return _set_out(s, aset)


@router.get("/arr/utilities/{code}/assumption-sets", response_model=list[ArrAssumptionSetOut])
def list_assumption_sets(code: str, principal: Principal = Depends(require_analyst)) -> list[ArrAssumptionSetOut]:
    with session_scope() as s:
        u = _utility(s, code)
        rows = s.execute(
            select(ArrAssumptionSet)
            .where(ArrAssumptionSet.utility_id == u.id, _visible(s, principal, ArrAssumptionSet.organisation_id))
            .order_by(ArrAssumptionSet.name, ArrAssumptionSet.version.desc())
        ).scalars()
        return [_set_out(s, a) for a in rows]


def _aset(s, set_id: uuid.UUID, principal: Principal, need: ws.Need = "read") -> ArrAssumptionSet:
    aset = s.get(ArrAssumptionSet, set_id)
    if aset is None:
        raise AppError("not_found", f"assumption set {set_id} not found")
    ws.require(s, principal, aset.organisation_id, need, what="assumption set")
    return aset


@router.get("/arr/assumption-sets/{set_id}", response_model=ArrAssumptionSetOut)
def get_assumption_set(set_id: uuid.UUID, principal: Principal = Depends(require_analyst)) -> ArrAssumptionSetOut:
    with session_scope() as s:
        return _set_out(s, _aset(s, set_id, principal))


@router.post("/arr/assumption-sets/{set_id}/assumptions", response_model=ArrAssumptionOut, status_code=201)
def add_assumption(
    set_id: uuid.UUID, body: ArrAssumptionIn, request: Request, principal: Principal = Depends(require_analyst)
) -> ArrAssumptionOut:
    from ..arr import service as arr

    storage: ObjectStore = request.app.state.adapters.storage
    with session_scope() as s:
        a = arr.add_assumption(
            s, storage, _aset(s, set_id, principal, "write"), actor=principal.email, **body.model_dump()
        )
        s.flush()
        s.refresh(a)
        return ArrAssumptionOut.model_validate(a, from_attributes=True)


def _formulation_out(s, f: ArrFormulation, *, with_lines: bool = True) -> ArrFormulationOut:
    from ..arr import service as arr

    u = s.get(Utility, f.utility_id)
    lines = (
        [ArrProjectionLineOut.model_validate(p, from_attributes=True) for p in arr.projection_lines(s, f.id)]
        if with_lines
        else []
    )
    d = {c: getattr(f, c) for c in ArrFormulationOut.model_fields if hasattr(f, c) and c not in ("lines", "kind")}
    return ArrFormulationOut(**{**d, "utility": u.code, "lines": lines})


def _formulation(s, formulation_id: uuid.UUID, principal: Principal, need: ws.Need = "read") -> ArrFormulation:
    f = s.get(ArrFormulation, formulation_id)
    if f is None:
        raise AppError("not_found", f"formulation {formulation_id} not found")
    ws.require(s, principal, f.organisation_id, need, what="formulation")
    return f


@router.post("/arr/utilities/{code}/formulations", response_model=ArrFormulationOut, status_code=201)
def create_formulation(
    code: str, body: ArrFormulationCreate, principal: Principal = Depends(require_analyst)
) -> ArrFormulationOut:
    from ..arr import service as arr

    with session_scope() as s:
        aset = _aset(s, body.assumption_set_id, principal, "write")
        f = arr.create_formulation(
            s,
            _utility(s, code),
            name=body.name,
            base_fy=body.base_fy,
            targets=[t.model_dump() for t in body.targets],
            assumption_set_id=aset.id,
            actor=principal.email,
        )
        s.flush()
        s.refresh(f)
        return _formulation_out(s, f)


@router.get("/arr/utilities/{code}/formulations", response_model=list[ArrFormulationOut])
def list_formulations(code: str, principal: Principal = Depends(require_analyst)) -> list[ArrFormulationOut]:
    with session_scope() as s:
        u = _utility(s, code)
        rows = s.execute(
            select(ArrFormulation)
            .where(ArrFormulation.utility_id == u.id, _visible(s, principal, ArrFormulation.organisation_id))
            .order_by(ArrFormulation.created_at.desc())
        ).scalars()
        return [_formulation_out(s, f, with_lines=False) for f in rows]


@router.get("/arr/formulations/{formulation_id}", response_model=ArrFormulationOut)
def get_formulation(formulation_id: uuid.UUID, principal: Principal = Depends(require_analyst)) -> ArrFormulationOut:
    with session_scope() as s:
        return _formulation_out(s, _formulation(s, formulation_id, principal))


@router.post("/arr/formulations/{formulation_id}/freeze", response_model=ArrFormulationOut)
def freeze_formulation(formulation_id: uuid.UUID, principal: Principal = Depends(require_analyst)) -> ArrFormulationOut:
    from ..arr import service as arr

    with session_scope() as s:
        f = arr.freeze_formulation(s, _formulation(s, formulation_id, principal, "write"), actor=principal.email)
        s.flush()
        return _formulation_out(s, f)


@router.post("/arr/formulations/{formulation_id}/reproduce", response_model=ArrReproduceOut)
def reproduce_formulation(
    formulation_id: uuid.UUID, principal: Principal = Depends(require_analyst)
) -> ArrReproduceOut:
    from ..arr import service as arr

    with session_scope() as s:
        return ArrReproduceOut(**arr.reproduce(s, _formulation(s, formulation_id, principal)))


# ------------------------------------------------------------------ filing drafts


def _draft_out(d: FilingDraft) -> FilingDraftOut:
    from ..arr.filing import WATERMARK

    return FilingDraftOut(
        **{c: getattr(d, c) for c in FilingDraftOut.model_fields if c != "watermark"}, watermark=WATERMARK
    )


@router.post("/arr/formulations/{formulation_id}/drafts", response_model=FilingDraftOut, status_code=201)
def generate_draft(
    formulation_id: uuid.UUID, request: Request, principal: Principal = Depends(require_analyst)
) -> FilingDraftOut:
    from ..arr import service as arr

    storage: ObjectStore = request.app.state.adapters.storage
    with session_scope() as s:
        d = arr.generate_draft(s, storage, _formulation(s, formulation_id, principal, "write"), actor=principal.email)
        s.flush()
        s.refresh(d)
        return _draft_out(d)


@router.get("/arr/formulations/{formulation_id}/drafts", response_model=list[FilingDraftOut])
def list_drafts(formulation_id: uuid.UUID, principal: Principal = Depends(require_analyst)) -> list[FilingDraftOut]:
    with session_scope() as s:
        _formulation(s, formulation_id, principal)
        rows = s.execute(
            select(FilingDraft)
            .where(FilingDraft.formulation_id == formulation_id)
            .order_by(FilingDraft.generated_at.desc())
        ).scalars()
        return [_draft_out(d) for d in rows]


def _draft(s, draft_id: uuid.UUID, principal: Principal) -> FilingDraft:
    d = s.get(FilingDraft, draft_id)
    if d is None:
        raise AppError("not_found", f"filing draft {draft_id} not found")
    if d.formulation_id is not None:
        _formulation(s, d.formulation_id, principal)  # a draft is visible to whoever sees its formulation
    else:
        # a true-up or APR draft is visible to whoever sees its case (ADR-0020)
        from .. import workspace as ws
        from ..models import ArrCase

        case = s.get(ArrCase, d.case_id)
        if case is None:
            raise AppError("not_found", f"filing draft {draft_id} not found")
        ws.require(s, principal, case.organisation_id, "read", what="filing draft")
    return d


@router.get("/arr/drafts/{draft_id}", response_model=FilingDraftOut)
def get_draft(draft_id: uuid.UUID, principal: Principal = Depends(require_analyst)) -> FilingDraftOut:
    with session_scope() as s:
        return _draft_out(_draft(s, draft_id, principal))


def _disposition(name: str) -> str:
    """An attachment header any client accepts: an ASCII fallback name plus the UTF-8 name
    (RFC 6266 / 5987); formulation names carry dashes and non-Latin characters."""
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")[:120] or "draft"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name[:160])}"


_FILES = {
    "petition.docx": ("docx_key", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "formats.xlsx": ("xlsx_key", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


@router.get(
    "/arr/drafts/{draft_id}/{filename}",
    responses={200: {"description": "the draft's DOCX narrative or XLSX formats"}},
)
def draft_file(
    draft_id: uuid.UUID, filename: str, request: Request, principal: Principal = Depends(require_analyst)
) -> Response:
    if filename not in _FILES:
        raise AppError("not_found", "petition.docx or formats.xlsx")
    attr, ctype = _FILES[filename]
    storage: ObjectStore = request.app.state.adapters.storage
    with session_scope() as s:
        d = _draft(s, draft_id, principal)
        key = getattr(d, attr)
        if d.formulation_id is not None:
            name = s.get(ArrFormulation, d.formulation_id).name
        else:
            from ..models import ArrCase

            name = s.get(ArrCase, d.case_id).title
    try:
        data = storage.get(ObjectStore.ARTEFACTS, key)
    except ObjectNotFound as e:
        raise AppError("storage_unavailable", "the draft's file is missing") from e
    return Response(
        content=data,
        media_type=ctype,
        headers={"Content-Disposition": _disposition(f"DRAFT-{name}-{filename}")},
    )
