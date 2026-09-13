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
from ..auth import require_admin, require_analyst
from ..db import session_scope
from ..errors import AppError
from ..models import (
    DatasetKind,
    IdempotencyRecord,
    Job,
    SourceDocument,
    SourcePage,
    SourceState,
)
from ..schemas import (
    JobSummary,
    SourceDetail,
    SourceList,
    SourcePageList,
    SourcePageOut,
    SourceRegistration,
    SourceSummary,
)
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
        )


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
) -> SourcePageList:
    with session_scope() as s:
        svc.get_source(s, source_id)
        q = select(SourcePage).where(SourcePage.source_id == source_id)
        if text_layer is not None:
            q = q.where(SourcePage.has_text_layer.is_(text_layer))
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        rows = s.execute(q.order_by(SourcePage.page_index).offset(offset).limit(limit)).scalars().all()
        return SourcePageList(
            source_id=source_id,
            total=total,
            offset=offset,
            limit=limit,
            pages=[SourcePageOut.model_validate(r, from_attributes=True) for r in rows],
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


@router.post("/{source_id}/reprocess", response_model=JobSummary, status_code=202)
def reprocess(source_id: uuid.UUID, request: Request, principal: Principal = Depends(require_admin)) -> JobSummary:
    settings = request.app.state.settings
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        job = svc.request_reprocess(s, settings, src, actor=principal.email)
        s.flush()
        s.refresh(job)
        return JobSummary.model_validate(job, from_attributes=True)
