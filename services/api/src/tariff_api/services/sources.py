"""Source registration: upload -> hash -> deduplicate -> store -> enqueue inventory."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import golden
from ..adapters.storage import ObjectStore
from ..config import Settings
from ..errors import AppError
from ..inventory import NotAPdf, open_document
from ..models import (
    SOURCE_TRANSITIONS,
    AuditEvent,
    Dataset,
    DatasetKind,
    Job,
    SourceDocument,
    SourceState,
)
from ..queue import enqueue
from ..telemetry import request_id_var

INVENTORY_JOB = "inventory_source"


def get_or_create_dataset(session: Session, kind: DatasetKind) -> Dataset:
    name = "real" if kind == DatasetKind.real else "fixture"
    ds = session.execute(select(Dataset).where(Dataset.name == name)).scalar_one_or_none()
    if ds is None:
        ds = Dataset(kind=kind, name=name)
        session.add(ds)
        session.flush()
    return ds


def transition(
    session: Session, source: SourceDocument, to: SourceState, *, actor: str, reason: str | None = None
) -> None:
    if to not in SOURCE_TRANSITIONS[source.state]:
        raise AppError("invalid_transition", f"{source.state.value} -> {to.value} is not allowed")
    before = source.state.value
    source.state = to
    source.state_reason = reason
    source.version += 1
    session.add(
        AuditEvent(
            actor=actor,
            action="source.transition",
            entity_type="source_document",
            entity_id=str(source.id),
            before={"state": before},
            after={"state": to.value},
            reason=reason,
            request_id=request_id_var.get(),
        )
    )


def inventory_idempotency_key(sha256: str, attempt_series: int = 1) -> str:
    return f"{INVENTORY_JOB}:{sha256}:{attempt_series}"


def register_upload(
    session: Session,
    storage: ObjectStore,
    settings: Settings,
    *,
    data: bytes,
    filename: str,
    dataset_kind: DatasetKind,
    provenance_url: str | None,
    actor: str,
) -> tuple[SourceDocument, bool, Job | None]:
    """Register bytes as a source.  Returns (source, deduplicated, inventory_job)."""
    if len(data) > settings.max_upload_bytes:
        raise AppError("source_too_large", f"{len(data)} bytes > {settings.max_upload_bytes}")
    if not data.startswith(b"%PDF"):
        raise AppError("source_unreadable", "file does not start with a PDF header")
    try:
        doc = open_document(data)
        page_count_probe = doc.page_count
        doc.close()
    except NotAPdf as e:
        raise AppError("source_unreadable", str(e)) from e
    if page_count_probe > settings.max_pages_per_job:
        raise AppError(
            "page_limit_exceeded", f"{page_count_probe} pages > MAX_PAGES_PER_JOB={settings.max_pages_per_job}"
        )

    sha = hashlib.sha256(data).hexdigest()
    existing = session.execute(select(SourceDocument).where(SourceDocument.sha256 == sha)).scalar_one_or_none()
    if existing is not None:
        session.add(
            AuditEvent(
                actor=actor,
                action="source.deduplicated",
                entity_type="source_document",
                entity_id=str(existing.id),
                after={"sha256": sha, "filename": filename, "existing_dataset_id": str(existing.dataset_id)},
                request_id=request_id_var.get(),
            )
        )
        job = (
            session.execute(select(Job).where(Job.source_id == existing.id).order_by(Job.created_at.desc()))
            .scalars()
            .first()
        )
        return existing, True, job

    dataset = get_or_create_dataset(session, dataset_kind)
    object_key = f"{sha}.pdf"
    storage.put(ObjectStore.SOURCES, object_key, data, "application/pdf")

    source = SourceDocument(
        dataset_id=dataset.id,
        sha256=sha,
        size_bytes=len(data),
        original_filename=filename[:512],
        provenance_url=provenance_url,
        uploaded_by=actor,
        object_key=object_key,
        state=SourceState.uploaded,
    )
    entry = golden.find_by_sha256(settings.golden_manifest_path, sha)
    if entry:
        source.golden_id = entry["id"]
        source.manifest_check = golden.compare_inventory(entry, {"size_bytes": len(data)})
    session.add(source)
    session.flush()
    session.add(
        AuditEvent(
            actor=actor,
            action="source.registered",
            entity_type="source_document",
            entity_id=str(source.id),
            after={"sha256": sha, "filename": filename, "dataset": dataset.name, "size_bytes": len(data)},
            request_id=request_id_var.get(),
        )
    )
    job, _ = enqueue(
        session,
        job_type=INVENTORY_JOB,
        payload={"source_id": str(source.id), "sha256": sha},
        idempotency_key=inventory_idempotency_key(sha),
        source_id=source.id,
        max_attempts=settings.job_max_attempts,
        created_by=actor,
    )
    return source, False, job


def request_reprocess(session: Session, settings: Settings, source: SourceDocument, *, actor: str) -> Job:
    """Enqueue a fresh inventory run for a failed or reprocessable source."""
    if source.state not in (SourceState.failed, SourceState.needs_reprocessing, SourceState.inventoried):
        raise AppError("invalid_transition", f"cannot reprocess a source in state {source.state.value}")
    series = (
        1
        + session.execute(select(Job).where(Job.source_id == source.id, Job.job_type == INVENTORY_JOB))
        .scalars()
        .all()
        .__len__()
    )
    if source.state != SourceState.uploaded:
        # failed/needs_reprocessing/inventoried -> uploaded (allowed by the transition table)
        transition(session, source, SourceState.uploaded, actor=actor, reason="reprocess requested")
    job, _ = enqueue(
        session,
        job_type=INVENTORY_JOB,
        payload={"source_id": str(source.id), "sha256": source.sha256},
        idempotency_key=inventory_idempotency_key(source.sha256, series),
        source_id=source.id,
        max_attempts=settings.job_max_attempts,
        created_by=actor,
    )
    return job


def summarise(source: SourceDocument) -> dict[str, Any]:
    return {
        "id": str(source.id),
        "sha256": source.sha256,
        "state": source.state.value,
        "page_count": source.page_count,
        "pages_with_text": source.pages_with_text,
        "pages_without_text": source.pages_without_text,
    }


def get_source(session: Session, source_id: uuid.UUID) -> SourceDocument:
    src = session.get(SourceDocument, source_id)
    if src is None:
        raise AppError("not_found", f"source {source_id} not found")
    return src
