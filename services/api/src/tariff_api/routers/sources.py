from __future__ import annotations

import hashlib
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from ..adapters.identity import Principal
from ..adapters.storage import ObjectNotFound, ObjectStore
from ..auth import require_admin, require_analyst, require_reviewer
from ..db import session_scope
from ..errors import AppError
from ..models import (
    ClauseValueRecord,
    DatasetKind,
    DocumentHeading,
    IdempotencyRecord,
    Job,
    LocalisationRecord,
    LocalisationRegion,
    SourceDocument,
    SourcePage,
    SourceState,
    StageArtefact,
    StructureCell,
    TableGridRecord,
)
from ..schemas import (
    ClauseValueList,
    ClauseValueOut,
    HeadingList,
    HeadingOut,
    InboxList,
    InboxObject,
    IngestRequest,
    JobSummary,
    LocalisationDecision,
    LocalisationOut,
    LocalisationRegionOut,
    LocalisationSummary,
    ParseSummary,
    ProfileAssignRequest,
    SourceDetail,
    SourceList,
    SourcePageList,
    SourcePageOut,
    SourceProfileOut,
    SourceRegistration,
    SourceSummary,
    StageArtefactOut,
    StageRerunRequest,
    StructureCellList,
    StructureCellOut,
    StructureSummary,
    TableGridList,
    TableGridOut,
    TriageSummary,
)
from ..services import localisation as loc
from ..services import sources as svc

router = APIRouter(prefix="/sources", tags=["sources"])


def _summary(src: SourceDocument) -> SourceSummary:
    return SourceSummary(
        id=src.id,
        dataset_kind=src.dataset.kind,
        sha256=src.sha256,
        size_bytes=src.size_bytes,
        original_filename=src.original_filename,
        provenance_url=src.provenance_url,
        acquired_at=src.acquired_at,
        uploaded_by=src.uploaded_by,
        state=src.state,
        state_reason=src.state_reason,
        page_count=src.page_count,
        pages_with_text=src.pages_with_text,
        pages_without_text=src.pages_without_text,
        golden_id=src.golden_id,
        version=src.version,
        created_at=src.created_at,
        updated_at=src.updated_at,
    )


def job_summary(job: Job | None) -> JobSummary | None:
    if job is None:
        return None
    return JobSummary.model_validate(job, from_attributes=True)


@router.post(
    "", response_model=SourceRegistration, status_code=201, responses={409: {"description": "idempotency conflict"}}
)
def upload_source(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File()],
    dataset_kind: Annotated[DatasetKind, Form()] = DatasetKind.real,
    provenance_url: Annotated[str | None, Form()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    principal: Principal = Depends(require_admin),
) -> SourceRegistration:
    """Register a PDF.  Identical bytes are deduplicated by SHA-256; an ``Idempotency-Key``
    replays the original response for the same request and rejects a different one."""
    settings = request.app.state.settings
    storage: ObjectStore = request.app.state.adapters.storage
    data = file.file.read(settings.max_upload_bytes + 1)
    fingerprint = hashlib.sha256(
        (hashlib.sha256(data).hexdigest() + "|" + dataset_kind.value + "|" + (provenance_url or "")).encode()
    ).hexdigest()

    with session_scope() as s:
        if idempotency_key:
            rec = s.get(IdempotencyRecord, {"key": idempotency_key, "actor": principal.email})
            if rec is not None:
                if rec.request_fingerprint != fingerprint:
                    raise AppError("idempotency_conflict")
                response.status_code = rec.response_status
                body = dict(rec.response_body)
                body["idempotent_replay"] = True
                return SourceRegistration.model_validate(body)

        source, dedup, job = svc.register_upload(
            s,
            storage,
            settings,
            data=data,
            filename=file.filename or "upload.pdf",
            dataset_kind=dataset_kind,
            provenance_url=provenance_url,
            actor=principal.email,
        )
        s.flush()
        s.refresh(source)
        result = SourceRegistration(source=_summary(source), deduplicated=dedup, job=job_summary(job))
        status_code = 200 if dedup else 201
        if idempotency_key:
            s.add(
                IdempotencyRecord(
                    key=idempotency_key,
                    actor=principal.email,
                    request_fingerprint=fingerprint,
                    response_status=status_code,
                    response_body=json.loads(result.model_dump_json()),
                )
            )
        response.status_code = status_code
        return result


@router.get("/inbox", response_model=InboxList, dependencies=[Depends(require_admin)])
def list_inbox(
    request: Request,
    prefix: str = Query("", max_length=512),
    limit: int = Query(200, ge=1, le=1000),
) -> InboxList:
    """List objects in the source bucket and whether each one is registered.

    This is how the three tariff orders reach the system in the cloud: an operator copies
    them into the bucket, then registers each one with POST /sources/ingest.
    """
    storage: ObjectStore = request.app.state.adapters.storage
    with session_scope() as s:
        rows = svc.list_inbox(s, storage, prefix=prefix, limit=limit)
    return InboxList(
        prefix=prefix,
        total=len(rows),
        objects=[InboxObject.model_validate(r) for r in rows],
    )


@router.post("/ingest", response_model=SourceRegistration, status_code=201)
def ingest_source(
    body: IngestRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    principal: Principal = Depends(require_admin),
) -> SourceRegistration:
    """Register an object already in the source bucket.  The bytes are re-read and hashed;
    the object name is never trusted as identity.  Dedup and idempotency behave exactly as
    for a browser upload."""
    settings = request.app.state.settings
    storage: ObjectStore = request.app.state.adapters.storage
    fingerprint = hashlib.sha256(
        f"ingest|{body.object_key}|{body.dataset_kind.value}|{body.provenance_url or ''}".encode()
    ).hexdigest()

    with session_scope() as s:
        if idempotency_key:
            rec = s.get(IdempotencyRecord, {"key": idempotency_key, "actor": principal.email})
            if rec is not None:
                if rec.request_fingerprint != fingerprint:
                    raise AppError("idempotency_conflict")
                response.status_code = rec.response_status
                replay = dict(rec.response_body)
                replay["idempotent_replay"] = True
                return SourceRegistration.model_validate(replay)

        source, dedup, job = svc.register_from_object(
            s,
            storage,
            settings,
            object_key=body.object_key,
            dataset_kind=body.dataset_kind,
            provenance_url=body.provenance_url,
            actor=principal.email,
        )
        s.flush()
        s.refresh(source)
        result = SourceRegistration(source=_summary(source), deduplicated=dedup, job=job_summary(job))
        status_code = 200 if dedup else 201
        if idempotency_key:
            s.add(
                IdempotencyRecord(
                    key=idempotency_key,
                    actor=principal.email,
                    request_fingerprint=fingerprint,
                    response_status=status_code,
                    response_body=json.loads(result.model_dump_json()),
                )
            )
        response.status_code = status_code
        return result


@router.get("", response_model=SourceList, dependencies=[Depends(require_analyst)])
def list_sources(
    dataset_kind: DatasetKind | None = None,
    state: SourceState | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> SourceList:
    with session_scope() as s:
        q = select(SourceDocument).join(SourceDocument.dataset)
        if dataset_kind is not None:
            q = q.where(SourceDocument.dataset.has(kind=dataset_kind))
        if state is not None:
            q = q.where(SourceDocument.state == state)
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        rows = s.execute(q.order_by(SourceDocument.created_at.desc()).offset(offset).limit(limit)).scalars().all()
        return SourceList(total=total, items=[_summary(r) for r in rows])


@router.get("/{source_id}", response_model=SourceDetail, dependencies=[Depends(require_analyst)])
def get_source(source_id: uuid.UUID) -> SourceDetail:
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        job = s.execute(select(Job).where(Job.source_id == src.id).order_by(Job.created_at.desc())).scalars().first()
        text_summary = None
        if src.page_count is not None:
            no_text = (
                s.execute(
                    select(SourcePage.page_index)
                    .where(SourcePage.source_id == src.id, SourcePage.has_text_layer.is_(False))
                    .order_by(SourcePage.page_index)
                )
                .scalars()
                .all()
            )
            rotated = s.execute(
                select(func.count()).where(SourcePage.source_id == src.id, SourcePage.rotation != 0)
            ).scalar_one()
            labelled = s.execute(
                select(func.count()).where(SourcePage.source_id == src.id, SourcePage.printed_label.is_not(None))
            ).scalar_one()
            text_summary = {
                "pages_without_text_layer": _ranges(no_text),
                "pages_without_text_count": len(no_text),
                "rotated_pages": int(rotated),
                "pages_with_pdf_labels": int(labelled),
            }
        triage = None
        if src.triage_version:
            pages = s.execute(
                select(
                    SourcePage.page_index,
                    SourcePage.page_class,
                    SourcePage.ocr_recommended,
                    SourcePage.quality_flags,
                ).where(SourcePage.source_id == src.id)
            ).all()
            triage = TriageSummary(
                triage_version=src.triage_version,
                triaged_at=src.triaged_at,
                page_class_counts=src.page_class_counts or {},
                label_rule=src.label_rule,
                ocr_recommended_pages=sorted(p.page_index for p in pages if p.ocr_recommended),
                low_quality_pages=sorted(p.page_index for p in pages if "low_text_quality" in (p.quality_flags or [])),
                label_flagged_pages=sorted(
                    p.page_index
                    for p in pages
                    if any(f in (p.quality_flags or []) for f in ("label_conflict", "label_off_rule"))
                ),
                unknown_pages=sorted(p.page_index for p in pages if p.page_class == "unknown"),
            )
        artefacts = (
            s.execute(
                select(StageArtefact)
                .where(StageArtefact.source_id == src.id)
                .order_by(StageArtefact.stage, StageArtefact.tool_version, StageArtefact.page_index)
            )
            .scalars()
            .all()
        )
        base = _summary(src).model_dump()
        return SourceDetail(
            **base,
            content_type=src.content_type,
            object_key=src.object_key,
            pdf_version=src.pdf_version,
            producer=src.producer,
            creator=src.creator,
            is_encrypted=src.is_encrypted,
            is_tagged=src.is_tagged,
            fonts_total=src.fonts_total,
            fonts_not_embedded=src.fonts_not_embedded,
            inventory_tool=src.inventory_tool,
            inventory_tool_version=src.inventory_tool_version,
            inventoried_at=src.inventoried_at,
            manifest_check=src.manifest_check,
            superseded_by_id=src.superseded_by_id,
            latest_job=job_summary(job),
            text_layer_summary=text_summary,
            triage=triage,
            parse=ParseSummary(
                parse_version=src.parse_version,
                parsed_at=src.parsed_at,
                heading_inventory=src.heading_inventory,
                table_summary=src.table_summary,
            )
            if src.parse_version
            else None,
            reading_profile=SourceProfileOut(
                profile_id=src.reading_profile_id,
                version=src.reading_profile_version,
                source=src.reading_profile_source,
                rationale=src.reading_profile_rationale,
            ),
            localisation=_localisation_summary(s, src),
            structure=StructureSummary(**src.structure_summary, gridded_at=src.gridded_at)
            if src.structure_summary
            else None,
            artefacts=[StageArtefactOut.model_validate(a, from_attributes=True) for a in artefacts if a.page_index == 0]
            + [
                StageArtefactOut.model_validate(a, from_attributes=True)
                for a in artefacts
                if a.page_index != 0 and a.page_index <= 3
            ],  # document-level artefacts plus a sample; the page table links the rest
        )


def _localisation_summary(s, src: SourceDocument) -> LocalisationSummary | None:
    rec = s.get(LocalisationRecord, src.id)
    if rec is None:
        return None
    regions = s.execute(select(LocalisationRegion).where(LocalisationRegion.source_id == src.id)).scalars().all()
    approved = sorted(
        {i for r in regions if r.role == "approved_schedule" for i in range(r.page_start, r.page_end + 1)}
    )
    return LocalisationSummary(
        status=rec.status,
        rules_version=rec.rules_version,
        profile_ref=rec.profile_ref,
        extraction_allowed=rec.extraction_allowed,
        region_count=len(regions),
        blocking_findings=sum(1 for f in rec.findings if f.get("severity") == "blocking"),
        approved_schedule_pages=_ranges(approved),
    )


def _localisation_out(rec: LocalisationRecord, regions: list[LocalisationRegion]) -> LocalisationOut:
    return LocalisationOut(
        source_id=rec.source_id,
        status=rec.status,
        rules_version=rec.rules_version,
        profile_ref=rec.profile_ref,
        extraction_allowed=rec.extraction_allowed,
        findings=rec.findings,
        regions=[LocalisationRegionOut.model_validate(r, from_attributes=True) for r in regions],
        decided_by=rec.decided_by,
        decided_at=rec.decided_at,
        decision_rationale=rec.decision_rationale,
        decision_count=rec.decision_count,
        version=rec.version,
        artefact_key=rec.artefact_key,
    )


@router.get("/{source_id}/localisation", response_model=LocalisationOut, dependencies=[Depends(require_analyst)])
def get_localisation(source_id: uuid.UUID) -> LocalisationOut:
    with session_scope() as s:
        svc.get_source(s, source_id)
        rec, regions = loc.get_record(s, source_id)
        return _localisation_out(rec, regions)


@router.post("/{source_id}/localisation/decision", response_model=LocalisationOut)
def decide_localisation(
    source_id: uuid.UUID,
    body: LocalisationDecision,
    request: Request,
    principal: Principal = Depends(require_reviewer),
) -> LocalisationOut:
    """The mandatory human checkpoint of Section 6.5.  Reviewer or administrator only; the
    rules never confirm their own result.  A decision queues the structure stage."""
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        rec, regions = loc.decide(s, request.app.state.settings, src, body, actor=principal.email)
        return _localisation_out(rec, regions)


@router.put("/{source_id}/profile", response_model=SourceDetail)
def assign_profile(
    source_id: uuid.UUID, body: ProfileAssignRequest, request: Request, principal: Principal = Depends(require_admin)
) -> SourceDetail:
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        loc.assign_profile(
            s, request.app.state.settings, src, body.profile_id, body.version, actor=principal.email, reason=body.reason
        )
    return get_source(source_id)


def _cell_out(c: StructureCell) -> StructureCellOut:
    return StructureCellOut(
        id=c.id,
        region_role=c.region_role,
        page_index=c.page_index,
        grid_ordinal=c.grid_ordinal,
        row=c.row,
        col=c.col,
        raw=c.raw,
        header_path=c.header_path,
        row_path=c.row_path,
        value_state=c.value_state,
        value=c.normalised.get("value"),
        currency=c.currency,
        per_unit=c.per_unit,
        frequency=c.frequency,
        unit_source=c.unit_source,
        flags=c.flags,
        footnotes=c.footnotes,
        slab=c.slab,
        resolved=c.resolved,
        rules_version=c.rules_version,
    )


@router.get("/{source_id}/structure/cells", response_model=StructureCellList, dependencies=[Depends(require_analyst)])
def list_structure_cells(
    source_id: uuid.UUID,
    page_index: int | None = None,
    unresolved_only: bool = False,
    flag: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> StructureCellList:
    """Every numeric cell of the confirmed approved regions with its header path, row path,
    unit binding and flags (Section 6.6).  ``unresolved_only`` lists what a reviewer must look
    at: cells with no header path, no row path or no unit."""
    with session_scope() as s:
        svc.get_source(s, source_id)
        q = select(StructureCell).where(StructureCell.source_id == source_id)
        if page_index is not None:
            q = q.where(StructureCell.page_index == page_index)
        if unresolved_only:
            q = q.where(StructureCell.resolved.is_(False))
        if flag:
            q = q.where(StructureCell.flags.contains([flag]))
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        rows = (
            s.execute(
                q.order_by(StructureCell.page_index, StructureCell.grid_ordinal, StructureCell.row, StructureCell.col)
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        return StructureCellList(cells=[_cell_out(c) for c in rows], total=total, limit=limit, offset=offset)


@router.get("/{source_id}/structure/clauses", response_model=ClauseValueList, dependencies=[Depends(require_analyst)])
def list_clause_values(source_id: uuid.UUID, category: str | None = None, kind: str | None = None) -> ClauseValueList:
    with session_scope() as s:
        svc.get_source(s, source_id)
        q = select(ClauseValueRecord).where(ClauseValueRecord.source_id == source_id)
        if category:
            q = q.where(ClauseValueRecord.category_code == category)
        if kind:
            q = q.where(ClauseValueRecord.kind == kind)
        rows = (
            s.execute(q.order_by(ClauseValueRecord.page_index, ClauseValueRecord.line_no, ClauseValueRecord.ordinal))
            .scalars()
            .all()
        )
        out = [
            ClauseValueOut(
                id=v.id,
                region_role=v.region_role,
                page_index=v.page_index,
                line_no=v.line_no,
                ordinal=v.ordinal,
                category_code=v.category_code,
                clause_path=v.clause_path,
                role=v.role,
                kind=v.kind,
                connector=v.connector,
                alternative=v.alternative,
                line_text=v.line_text,
                value=v.normalised.get("value"),
                value_state=v.normalised.get("value_state"),
                currency=v.normalised.get("currency"),
                per_unit=v.normalised.get("per_unit"),
                frequency=v.normalised.get("frequency"),
                percent_of=v.normalised.get("percent_of"),
                reference=v.normalised.get("reference"),
                dimension=v.dimension,
                slab=v.slab,
                time_window=v.time_window,
                sign=v.sign,
                parameters=v.parameters,
                rules_version=v.rules_version,
            )
            for v in rows
        ]
        return ClauseValueList(values=out, total=len(out))


def _ranges(indices: list[int]) -> list[str]:
    out: list[str] = []
    start = prev = None
    for i in indices:
        if start is None:
            start = prev = i
        elif i == prev + 1:
            prev = i
        else:
            out.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = i
    if start is not None:
        out.append(f"{start}-{prev}" if start != prev else str(start))
    return out


@router.get("/{source_id}/pages", response_model=SourcePageList, dependencies=[Depends(require_analyst)])
def list_pages(
    source_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    text_layer: bool | None = None,
    page_class: str | None = None,
    ocr_recommended: bool | None = None,
) -> SourcePageList:
    with session_scope() as s:
        svc.get_source(s, source_id)
        q = select(SourcePage).where(SourcePage.source_id == source_id)
        if text_layer is not None:
            q = q.where(SourcePage.has_text_layer.is_(text_layer))
        if page_class is not None:
            q = q.where(SourcePage.page_class == page_class)
        if ocr_recommended is not None:
            q = q.where(SourcePage.ocr_recommended.is_(ocr_recommended))
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        rows = s.execute(q.order_by(SourcePage.page_index).offset(offset).limit(limit)).scalars().all()
        return SourcePageList(
            source_id=source_id,
            total=total,
            offset=offset,
            limit=limit,
            pages=[SourcePageOut.model_validate(r, from_attributes=True) for r in rows],
        )


@router.get("/{source_id}/tables", response_model=TableGridList, dependencies=[Depends(require_analyst)])
def list_tables(
    source_id: uuid.UUID,
    page_index: int | None = None,
    agreement_class: str | None = None,
    primary_only: bool = False,
) -> TableGridList:
    """Table grids from both readers with their agreement class — the routing signal of
    Section 6.4.  The full cell grid is in the artefact at ``object_key``."""
    with session_scope() as s:
        svc.get_source(s, source_id)
        q = select(TableGridRecord).where(TableGridRecord.source_id == source_id)
        if page_index is not None:
            q = q.where(TableGridRecord.page_index == page_index)
        if agreement_class is not None:
            q = q.where(TableGridRecord.agreement_class == agreement_class)
        if primary_only:
            q = q.where(TableGridRecord.is_primary.is_(True))
        rows = (
            s.execute(
                q.order_by(TableGridRecord.page_index, TableGridRecord.is_primary.desc(), TableGridRecord.ordinal)
            )
            .scalars()
            .all()
        )
        return TableGridList(
            source_id=source_id,
            total=len(rows),
            grids=[TableGridOut.model_validate(r, from_attributes=True) for r in rows],
        )


@router.get("/{source_id}/headings", response_model=HeadingList, dependencies=[Depends(require_analyst)])
def list_headings(source_id: uuid.UUID, kind: str | None = None) -> HeadingList:
    """The document-wide heading inventory: the expectation localisation reconciles against."""
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        q = select(DocumentHeading).where(DocumentHeading.source_id == source_id)
        if kind is not None:
            q = q.where(DocumentHeading.kind == kind)
        rows = (
            s.execute(q.order_by(DocumentHeading.ordinal, DocumentHeading.page_index, DocumentHeading.line_no))
            .scalars()
            .all()
        )
        return HeadingList(
            source_id=source_id,
            total=len(rows),
            inventory=src.heading_inventory,
            headings=[HeadingOut.model_validate(r, from_attributes=True) for r in rows],
        )


@router.get("/{source_id}/file", dependencies=[Depends(require_analyst)])
def get_file(source_id: uuid.UUID, request: Request):
    """Authorized access to the immutable bytes.  No signed or public URL exists."""
    storage: ObjectStore = request.app.state.adapters.storage
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        key, filename, size = src.object_key, src.original_filename, src.size_bytes
    if not storage.exists(ObjectStore.SOURCES, key):
        raise AppError("storage_unavailable", "object missing for registered source")
    try:
        stream = storage.stream(ObjectStore.SOURCES, key)
    except ObjectNotFound as e:
        raise AppError("storage_unavailable", "object missing for registered source") from e
    safe_name = filename.replace('"', "")
    return StreamingResponse(
        stream,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
            "Content-Length": str(size),
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{source_id}/stages/rerun", response_model=JobSummary, status_code=202)
def rerun_stage(
    source_id: uuid.UUID, body: StageRerunRequest, request: Request, principal: Principal = Depends(require_admin)
) -> JobSummary:
    """Re-run one reading stage (after a rules-version bump, or to reprocess a failed one).
    Artefacts from earlier tool versions are kept; new ones are written beside them."""
    settings = request.app.state.settings
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        job = svc.request_stage_rerun(s, settings, src, body.job_type, actor=principal.email)
        s.flush()
        s.refresh(job)
        return JobSummary.model_validate(job, from_attributes=True)


@router.post("/{source_id}/reprocess", response_model=JobSummary, status_code=202)
def reprocess(source_id: uuid.UUID, request: Request, principal: Principal = Depends(require_admin)) -> JobSummary:
    settings = request.app.state.settings
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        job = svc.request_reprocess(s, settings, src, actor=principal.email)
        s.flush()
        s.refresh(job)
        return JobSummary.model_validate(job, from_attributes=True)
