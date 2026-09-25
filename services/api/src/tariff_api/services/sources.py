"""Source registration: upload -> hash -> deduplicate -> store -> enqueue inventory."""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import golden
from ..adapters.storage import ObjectNotFound, ObjectStore
from ..config import Settings
from ..errors import AppError
from ..inventory import NotAPdf, open_document
from ..models import (
    SOURCE_TRANSITIONS,
    AuditEvent,
    Dataset,
    DatasetKind,
    Job,
    JobStatus,
    SourceDocument,
    SourceState,
    Utility,
)
from ..queue import enqueue, request_cancel
from ..telemetry import request_id_var

INVENTORY_JOB = "inventory_source"

# Keys the store writes itself for registered sources.
_CONTENT_KEY = re.compile(r"[0-9a-f]{64}\.pdf")


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


def resolve_utility(session: Session, code: str) -> Utility:
    u = session.execute(select(Utility).where(Utility.code == code.strip().upper())).scalar_one_or_none()
    if u is None:
        raise AppError("validation_failed", f"unknown utility {code!r}; add it to the registry first")
    return u


def apply_utility(source: SourceDocument, utility: Utility, *, actor: str) -> None:
    """The order belongs to this utility: bind the utility's active reading profile (latest
    version) and inherit the commission's reviewer.  Nothing is detected or guessed."""
    from ..profiles import latest_version

    source.utility_id = utility.id
    pid = utility.active_reading_profile
    if pid and source.reading_profile_id is None:
        v = utility.active_reading_profile_version or latest_version(pid)
        if v is not None:
            source.reading_profile_id = pid
            source.reading_profile_version = v
            source.reading_profile_source = "utility"
            source.reading_profile_rationale = (
                f"utility {utility.code} uses {pid} v{v} (set at registration by {actor})"
            )
    if source.assigned_to is None and utility.commission is not None and utility.commission.assigned_to:
        source.assigned_to = utility.commission.assigned_to


def register_from_object(
    session: Session,
    storage: ObjectStore,
    settings: Settings,
    *,
    object_key: str,
    dataset_kind: DatasetKind,
    provenance_url: str | None,
    actor: str,
    utility_code: str | None = None,
    order_type: str | None = None,
    decides: list[dict[str, str]] | None = None,
) -> tuple[SourceDocument, bool, Job | None]:
    """Register a PDF that an operator already placed in the source bucket.

    The bytes are read back and hashed here — the object's name, size or any metadata on it
    are never trusted as identity.  Registration then follows exactly the same path as an
    upload, so dedup, golden-manifest verification and the inventory job are identical.
    """
    if not object_key or object_key.endswith("/"):
        # The console creates a zero-byte placeholder object named `inbox/` when a folder is
        # made by hand; it is not a document and must not reach the hash-and-register path.
        raise AppError("validation_failed", f"{object_key!r} names a folder placeholder, not an object")
    listing = {o.key: o for o in storage.list(ObjectStore.SOURCES, prefix=object_key, limit=1)}
    info = listing.get(object_key)
    if info is None:
        raise AppError("not_found", f"no object {object_key!r} in the source bucket")
    if info.size_bytes > settings.max_upload_bytes:
        raise AppError("source_too_large", f"{info.size_bytes} bytes > {settings.max_upload_bytes}")
    try:
        data = storage.get(ObjectStore.SOURCES, object_key)
    except ObjectNotFound as e:
        raise AppError("not_found", f"no object {object_key!r} in the source bucket") from e
    return register_upload(
        session,
        storage,
        settings,
        data=data,
        filename=object_key.rsplit("/", 1)[-1],
        dataset_kind=dataset_kind,
        provenance_url=provenance_url or f"gs://<source-bucket>/{object_key}",
        actor=actor,
        utility_code=utility_code,
        order_type=order_type,
        decides=decides,
    )


def list_inbox(session: Session, storage: ObjectStore, *, prefix: str = "", limit: int = 200) -> list[dict[str, Any]]:
    """Objects in the source bucket with their registration status.

    Content-addressed keys (``<sha256>.pdf``) are the store's own copies of registered
    sources and are listed as ``registered``; anything else is a candidate for ingestion.
    """
    objects = storage.list(ObjectStore.SOURCES, prefix=prefix, limit=limit)
    known = {row.object_key: row for row in session.execute(select(SourceDocument)).scalars().all()}
    out: list[dict[str, Any]] = []
    for o in objects:
        if o.key.endswith("/"):
            continue  # console-made folder placeholder (`inbox/`, 0 bytes): not a candidate
        src = known.get(o.key)
        out.append(
            {
                "object_key": o.key,
                "size_bytes": o.size_bytes,
                "updated_at": o.updated_at,
                "registered": src is not None,
                "source_id": src.id if src else None,
                "is_content_addressed_copy": _CONTENT_KEY.fullmatch(o.key) is not None,
            }
        )
    return out


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
    utility_code: str | None = None,
    order_type: str | None = None,
    decides: list[dict[str, str]] | None = None,
) -> tuple[SourceDocument, bool, Job | None]:
    """Register bytes as a source.  Returns (source, deduplicated, inventory_job).  With a
    utility code the order belongs to that utility: its active reading profile binds now
    (no detection, no CLI) and the commission's reviewer is inherited."""
    utility = resolve_utility(session, utility_code) if utility_code else None
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
    if utility is not None:
        apply_utility(source, utility, actor=actor)
    # what the instrument is and which years it decides: stated by the person registering
    # it (ARR spec section 5), never inferred from the file
    source.order_type = order_type or None
    source.decides = decides or None
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


STAGE_JOBS = {
    "inventory_source": SourceState.uploaded,
    "triage_source": SourceState.inventoried,
    "parse_source": SourceState.triaged,
    "localise_source": SourceState.parsed,
    "grid_source": SourceState.localised,
    "extract_source": SourceState.gridded,
    "validate_source": SourceState.extracted,
}


def enqueue_stage(session: Session, settings: Settings, source: SourceDocument, job_type: str, *, actor: str) -> Job:
    """Queue a reading stage for a source.  Idempotent per (job, source, series): a stage that is
    already queued or running is not queued twice; a finished one gets a new series."""
    prior = session.execute(select(Job).where(Job.source_id == source.id, Job.job_type == job_type)).scalars().all()
    for j in prior:
        if j.status in (JobStatus.queued, JobStatus.leased):
            return j
    job, _ = enqueue(
        session,
        job_type=job_type,
        payload={"source_id": str(source.id), "sha256": source.sha256},
        idempotency_key=f"{job_type}:{source.sha256}:{len(prior) + 1}",
        source_id=source.id,
        max_attempts=settings.job_max_attempts,
        created_by=actor,
    )
    return job


def request_stage_rerun(
    session: Session, settings: Settings, source: SourceDocument, job_type: str, *, actor: str
) -> Job:
    """Re-run one reading stage (for example after a rules-version bump).  The source must be
    at or past the stage's input state; it is moved back to that state through the transition
    table so the audit trail shows the re-run."""
    if job_type not in STAGE_JOBS:
        raise AppError("validation_failed", f"unknown stage job {job_type!r}")
    input_state = STAGE_JOBS[job_type]
    order = list(SourceState)
    if source.state in (SourceState.failed, SourceState.needs_reprocessing):
        pass
    elif order.index(source.state) < order.index(input_state) and source.state != input_state:
        raise AppError("invalid_transition", f"source is {source.state.value}; {job_type} needs {input_state.value}")
    if source.state != input_state:
        if input_state not in SOURCE_TRANSITIONS[source.state]:
            transition(session, source, SourceState.needs_reprocessing, actor=actor, reason=f"rerun {job_type}")
        transition(session, source, input_state, actor=actor, reason=f"rerun {job_type}")
    # A re-run invalidates the stages that followed: a queued downstream job (e.g. the parse
    # that triage chained) would otherwise run first against the rolled-back state and fail.
    # The re-run stage chains its successors again when it completes.
    stage_rank = {jt: order.index(st) for jt, st in STAGE_JOBS.items()}
    pending = (
        session.execute(
            select(Job).where(
                Job.source_id == source.id,
                Job.status.in_([JobStatus.queued, JobStatus.leased]),
                Job.job_type.in_(list(STAGE_JOBS)),
            )
        )
        .scalars()
        .all()
    )
    for j in pending:
        if stage_rank[j.job_type] >= stage_rank[job_type]:
            request_cancel(session, j, actor=f"{actor} (rerun {job_type})")
    session.flush()
    return enqueue_stage(session, settings, source, job_type, actor=actor)


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
