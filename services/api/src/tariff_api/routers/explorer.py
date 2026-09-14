"""Published tariff explorer (Section 9, screens 5 and 6a).  Reads `data_releases`,
`published_facts` and `published_evidence` and nothing else: this module has no import of
the candidate model, by design and by test.  Every number shown here comes with citations
derived from the published evidence rows, a completeness banner, and the fixture flag."""

from __future__ import annotations

import uuid

import pymupdf
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select

from ..adapters.storage import ObjectNotFound, ObjectStore
from ..auth import require_analyst
from ..db import session_scope
from ..errors import AppError
from ..inventory import NotAPdf, open_document
from ..models import DataRelease, PublishedEvidence, PublishedFact, SourceDocument, TableGridRecord
from ..schemas import (
    CitationOut,
    CompletenessBanner,
    ExplorerCategory,
    ExplorerReleaseItem,
    ExplorerReleaseList,
    NetworkExplorer,
    NetworkFamilyView,
    PublishedFactOut,
    ReleaseOut,
    TariffExplorer,
)
from ..tariff_schema import NETWORK_FAMILIES

router = APIRouter(prefix="/explorer", tags=["explorer"], dependencies=[Depends(require_analyst)])

NO_RELEASE = "No published release exists for this source; nothing here is verified. Candidates are never shown."


def _citation(e: PublishedEvidence) -> CitationOut:
    table_id = f"p{e.page_index}-g{e.grid_ordinal}" if e.grid_ordinal is not None else None
    cell = f"r{e.row}c{e.col}" if e.row is not None and e.col is not None else None
    return CitationOut(
        evidence_id=e.id,
        source_id=e.source_id,
        pdf_page=e.page_index,
        printed_page=e.printed_label,
        kind=e.kind,
        table_id=table_id,
        cell=cell,
        line_no=e.line_no,
        header_path=e.header_path,
        row_path=e.row_path,
        clause_path=e.clause_path,
        excerpt=e.excerpt,
    )


def _fact(f: PublishedFact, evidence: list[PublishedEvidence]) -> PublishedFactOut:
    return PublishedFactOut(
        fact_id=f.id,
        release_id=f.release_id,
        candidate_id=f.candidate_id,
        review_status=f.review_status,
        family=f.family,
        category_code=f.category_code,
        component_type=f.component_type,
        value=f.value,
        value_state=f.value_state,
        currency=f.currency,
        per_unit=f.per_unit,
        frequency=f.frequency,
        decision_status=f.decision_status,
        period=f.period,
        utility=f.utility,
        applicability=f.applicability,
        conditions=f.conditions,
        derivation=f.derivation,
        original_text=f.record.get("original_text"),
        reference_target=f.record.get("reference_target"),
        is_fixture=f.is_fixture,
        citations=[_citation(e) for e in sorted(evidence, key=lambda e: e.ordinal)],
    )


def _banner(r: DataRelease) -> CompletenessBanner:
    return CompletenessBanner(
        completeness=r.completeness,
        gaps=r.gaps,
        unresolved=r.unresolved_count,
        pending=r.pending_count,
        awaiting_second_review=r.awaiting_second_review_count,
        release_number=r.release_number,
        published_at=r.published_at,
        is_fixture=r.is_fixture,
    )


def _current(s, source_id: uuid.UUID) -> DataRelease | None:
    return s.execute(
        select(DataRelease).where(DataRelease.source_id == source_id, DataRelease.is_current.is_(True))
    ).scalar_one_or_none()


def _facts_with_evidence(s, release_id: uuid.UUID) -> list[PublishedFactOut]:
    facts = s.execute(select(PublishedFact).where(PublishedFact.release_id == release_id)).scalars().all()
    evidence = s.execute(select(PublishedEvidence).where(PublishedEvidence.release_id == release_id)).scalars().all()
    by_fact: dict[uuid.UUID, list[PublishedEvidence]] = {}
    for e in evidence:
        by_fact.setdefault(e.fact_id, []).append(e)
    return [_fact(f, by_fact.get(f.id, [])) for f in facts]


@router.get("/releases", response_model=ExplorerReleaseList)
def list_current_releases(dataset_kind: str | None = None) -> ExplorerReleaseList:
    """Current releases across sources; fixture releases are counted separately and never
    presented as coverage."""
    with session_scope() as s:
        rows = s.execute(
            select(DataRelease, SourceDocument)
            .join(SourceDocument, SourceDocument.id == DataRelease.source_id)
            .where(DataRelease.is_current.is_(True))
            .order_by(DataRelease.is_fixture, DataRelease.published_at.desc())
        ).all()
        items = [
            ExplorerReleaseItem(
                release=ReleaseOut.model_validate(r, from_attributes=True),
                original_filename=src.original_filename,
                dataset_kind=src.dataset.kind,
                state=src.state,
            )
            for r, src in rows
            if not dataset_kind or src.dataset.kind.value == dataset_kind
        ]
        return ExplorerReleaseList(
            items=items,
            total=len(items),
            real=sum(1 for i in items if not i.release.is_fixture),
            fixture=sum(1 for i in items if i.release.is_fixture),
        )


@router.get("/sources/{source_id}/tariff", response_model=TariffExplorer)
def tariff_explorer(source_id: uuid.UUID, category: str | None = None) -> TariffExplorer:
    """Screen 5: category tree with components, units, value states, applicability,
    conditions and citations, under a completeness banner.  Only published facts."""
    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        if src is None:
            raise AppError("not_found", f"source {source_id} not found")
        r = _current(s, source_id)
        if r is None:
            return TariffExplorer(
                status="coverage_insufficient",
                source_id=source_id,
                release=None,
                completeness=None,
                categories=[],
                general_conditions=[],
                unresolved_items=[],
                message=NO_RELEASE,
            )
        facts = _facts_with_evidence(s, r.id)
        cats: dict[str, ExplorerCategory] = {}
        general: list[str] = []
        for f in facts:
            if f.family != "retail_tariff":
                continue
            code = f.category_code or "(no category)"
            if category and code != category:
                continue
            cat = cats.setdefault(code, ExplorerCategory(category_code=code, components={}, conditions=[], facts=0))
            cat.components.setdefault(f.component_type, []).append(f)
            cat.facts += 1
            for c in f.conditions:
                if c not in cat.conditions:
                    cat.conditions.append(c)
            if f.component_type == "condition" and f.original_text and f.original_text not in general:
                general.append(f.original_text)
        unresolved = [g["key"] for g in r.gaps] if r.completeness == "partial" else []
        return TariffExplorer(
            status="published",
            source_id=source_id,
            release=ReleaseOut.model_validate(r, from_attributes=True),
            completeness=_banner(r),
            categories=[cats[k] for k in sorted(cats)],
            general_conditions=general,
            unresolved_items=unresolved,
        )


@router.get("/sources/{source_id}/network", response_model=NetworkExplorer)
def network_explorer(source_id: uuid.UUID) -> NetworkExplorer:
    """Screen 6a: wheeling, losses by role, CSS with its derivation (computed / cap /
    approved), additional surcharge with decision status, banking, green tariff and
    transmission references, each with citations and review state; families with no
    published fact are `coverage_insufficient` with the reviewed disposition if one exists."""
    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        if src is None:
            raise AppError("not_found", f"source {source_id} not found")
        r = _current(s, source_id)
        if r is None:
            return NetworkExplorer(
                status="coverage_insufficient",
                source_id=source_id,
                release=None,
                completeness=None,
                families=[
                    NetworkFamilyView(
                        family=f, status="coverage_insufficient", disposition=None, facts=[], message=NO_RELEASE
                    )
                    for f in NETWORK_FAMILIES
                ],
                message=NO_RELEASE,
            )
        facts = [f for f in _facts_with_evidence(s, r.id) if f.family != "retail_tariff"]
        dispositions = {g["key"]: g.get("reason") for g in r.gaps if g.get("key") in NETWORK_FAMILIES}
        snapshot_disp = r.checklist_snapshot.get("dispositions", {}) if isinstance(r.checklist_snapshot, dict) else {}
        views = []
        for fam in NETWORK_FAMILIES:
            fs = [f for f in facts if f.family == fam]
            disp = snapshot_disp.get(fam)
            if fs:
                views.append(NetworkFamilyView(family=fam, status="published", disposition=disp, facts=fs))
            else:
                views.append(
                    NetworkFamilyView(
                        family=fam,
                        status="coverage_insufficient",
                        disposition=disp,
                        facts=[],
                        message=(
                            f"reviewed disposition: {disp}"
                            if disp
                            else dispositions.get(fam) or "no published fact for this family in this release"
                        ),
                    )
                )
        return NetworkExplorer(
            status="published",
            source_id=source_id,
            release=ReleaseOut.model_validate(r, from_attributes=True),
            completeness=_banner(r),
            families=views,
        )


@router.get("/facts/{fact_id}", response_model=PublishedFactOut)
def get_fact(fact_id: uuid.UUID) -> PublishedFactOut:
    with session_scope() as s:
        f = s.get(PublishedFact, fact_id)
        if f is None:
            raise AppError("not_found", f"published fact {fact_id} not found")
        ev = s.execute(select(PublishedEvidence).where(PublishedEvidence.fact_id == fact_id)).scalars().all()
        return _fact(f, ev)


@router.get(
    "/facts/{fact_id}/evidence/{ordinal}/image",
    responses={200: {"content": {"image/png": {}}, "description": "the cited page, cited table outlined"}},
)
def fact_evidence_image(fact_id: uuid.UUID, ordinal: int, request: Request, dpi: int = Query(110, ge=50, le=200)):
    """Citation drill-down: the cited page rendered from the immutable source bytes."""
    storage: ObjectStore = request.app.state.adapters.storage
    with session_scope() as s:
        f = s.get(PublishedFact, fact_id)
        if f is None:
            raise AppError("not_found", f"published fact {fact_id} not found")
        e = s.execute(
            select(PublishedEvidence).where(PublishedEvidence.fact_id == fact_id, PublishedEvidence.ordinal == ordinal)
        ).scalar_one_or_none()
        if e is None:
            raise AppError("not_found", f"fact has no evidence ordinal {ordinal}")
        src = s.get(SourceDocument, f.source_id)
        assert src is not None
        object_key = src.object_key
        bbox = None
        if e.grid_ordinal is not None:
            g = s.execute(
                select(TableGridRecord).where(
                    TableGridRecord.source_id == f.source_id,
                    TableGridRecord.page_index == e.page_index,
                    TableGridRecord.ordinal == e.grid_ordinal,
                    TableGridRecord.is_primary.is_(True),
                )
            ).scalar_one_or_none()
            bbox = [float(v) for v in g.bbox] if g is not None and g.bbox and len(g.bbox) == 4 else None
        page_index = e.page_index
    try:
        data = storage.get(ObjectStore.SOURCES, object_key)
        doc = open_document(data)
    except ObjectNotFound as exc:
        raise AppError("storage_unavailable", "object missing for registered source") from exc
    except NotAPdf as exc:
        raise AppError("source_unreadable", str(exc)) from exc
    if page_index < 1 or page_index > doc.page_count:
        raise AppError("validation_failed", f"evidence cites page {page_index}; document has {doc.page_count}")
    page = doc[page_index - 1]
    if bbox:
        shape = page.new_shape()
        shape.draw_rect(pymupdf.Rect(*bbox))
        shape.finish(color=(0.85, 0.1, 0.1), width=2.0)
        shape.commit()
    png = page.get_pixmap(dpi=dpi).tobytes("png")
    doc.close()
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, no-store"})
