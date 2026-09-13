"""PostgreSQL-backed durable job queue.

Semantics (identical in both profiles):

* ``enqueue`` is idempotent on ``idempotency_key``.
* ``claim`` uses ``SELECT ... FOR UPDATE SKIP LOCKED`` and takes either a queued job or a
  leased job whose lease expired (worker death).  Every claim starts a new ``run_id``.
* ``heartbeat``/``checkpoint``/``complete``/``fail`` are fenced by ``(job_id, run_id)``: a
  worker whose lease was taken over gets ``LeaseLost`` and must stop.
* Attempts are bounded; the final failure carries ``retries_exhausted``.
* ``request_cancel`` sets a flag the handler observes at its next checkpoint.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from .models import Job, JobEvent, JobStatus


class LeaseLost(Exception):
    """Raised when a fenced write affected zero rows."""


class CancelRequested(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue(
    session: Session,
    *,
    job_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
    source_id: uuid.UUID | None = None,
    priority: int = 0,
    max_attempts: int = 3,
    created_by: str | None = None,
) -> tuple[Job, bool]:
    """Insert a job unless one with the same idempotency key exists.  Returns (job, created)."""
    existing = session.execute(select(Job).where(Job.idempotency_key == idempotency_key)).scalar_one_or_none()
    if existing is not None:
        return existing, False
    job = Job(
        job_type=job_type,
        payload=payload,
        idempotency_key=idempotency_key,
        source_id=source_id,
        priority=priority,
        max_attempts=max_attempts,
        created_by=created_by,
    )
    session.add(job)
    session.flush()
    session.add(JobEvent(job_id=job.id, event="enqueued", detail={"job_type": job_type}))
    session.flush()
    return job, True


_CLAIM_SQL = text(
    """
    WITH candidate AS (
        SELECT id, status, run_id, attempts, max_attempts
        FROM jobs
        WHERE (status = 'queued' AND available_at <= now())
           OR (status = 'leased' AND lease_expires_at < now())
        ORDER BY priority DESC, created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    UPDATE jobs j
       SET status = 'leased',
           lease_owner = :worker,
           lease_expires_at = now() + make_interval(secs => :lease_seconds),
           heartbeat_at = now(),
           attempts = j.attempts + 1,
           run_id = :run_id,
           started_at = COALESCE(j.started_at, now())
      FROM candidate c
     WHERE j.id = c.id
    RETURNING j.id, c.status AS previous_status, c.run_id AS previous_run_id, j.attempts, j.max_attempts
    """
)


def claim(session: Session, *, worker: str, lease_seconds: int) -> Job | None:
    """Claim one job.  Expired leases are reclaimed and recorded as ``lease_expired_reclaimed``.
    A job whose attempts exceed ``max_attempts`` is failed with ``retries_exhausted`` instead
    of being run again."""
    run_id = uuid.uuid4()
    row = session.execute(_CLAIM_SQL, {"worker": worker, "lease_seconds": lease_seconds, "run_id": run_id}).first()
    if row is None:
        return None
    job = session.get(Job, row.id)
    assert job is not None
    if row.previous_status == "leased":
        session.add(
            JobEvent(
                job_id=job.id,
                run_id=run_id,
                event="lease_expired_reclaimed",
                worker=worker,
                detail={"previous_run_id": str(row.previous_run_id), "attempt": row.attempts},
            )
        )
    if row.attempts > row.max_attempts:
        job.status = JobStatus.failed
        job.error_type = "retries_exhausted"
        job.error_message = f"attempt {row.attempts} exceeds max_attempts {row.max_attempts}"
        job.finished_at = _now()
        job.lease_owner = None
        job.lease_expires_at = None
        session.add(
            JobEvent(
                job_id=job.id, run_id=run_id, event="failed", worker=worker, detail={"error_type": "retries_exhausted"}
            )
        )
        session.flush()
        return None
    session.add(
        JobEvent(
            job_id=job.id,
            run_id=run_id,
            event="claimed",
            worker=worker,
            detail={"attempt": row.attempts, "checkpoint": job.checkpoint},
        )
    )
    session.flush()
    session.refresh(job)
    return job


def _fenced(session: Session, job_id: uuid.UUID, run_id: uuid.UUID, **values: Any) -> None:
    """Update a leased job only if ``run_id`` still owns it.  Callers pass ids, never ORM
    objects, so no autoflush can write a stale run id back before the fence is checked."""
    result = session.execute(
        update(Job).where(Job.id == job_id, Job.run_id == run_id, Job.status == JobStatus.leased).values(**values)
    )
    if result.rowcount != 1:
        raise LeaseLost(f"job {job_id} run {run_id}")


def heartbeat(session: Session, job_id: uuid.UUID, run_id: uuid.UUID, *, lease_seconds: int) -> bool:
    """Extend the lease.  Returns ``cancel_requested`` so the handler can stop cleanly."""
    _fenced(
        session,
        job_id,
        run_id,
        heartbeat_at=_now(),
        lease_expires_at=_now() + timedelta(seconds=lease_seconds),
    )
    flag = session.execute(select(Job.cancel_requested).where(Job.id == job_id)).scalar_one()
    return bool(flag)


def checkpoint(
    session: Session,
    job_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    worker: str,
    stage: str,
    checkpoint: dict[str, Any],
    progress: dict[str, Any],
) -> None:
    _fenced(session, job_id, run_id, stage=stage, checkpoint=checkpoint, progress=progress, heartbeat_at=_now())
    session.add(
        JobEvent(
            job_id=job_id,
            run_id=run_id,
            event="checkpoint",
            worker=worker,
            detail={"stage": stage, "checkpoint": checkpoint},
        )
    )


def complete(
    session: Session, job_id: uuid.UUID, run_id: uuid.UUID, *, worker: str, result: dict[str, Any] | None = None
) -> None:
    progress = session.execute(select(Job.progress).where(Job.id == job_id)).scalar_one() or {}
    _fenced(
        session,
        job_id,
        run_id,
        status=JobStatus.succeeded,
        finished_at=_now(),
        lease_owner=None,
        lease_expires_at=None,
        progress={**progress, **(result or {})},
    )
    session.add(JobEvent(job_id=job_id, run_id=run_id, event="succeeded", worker=worker, detail=result or {}))


def fail(
    session: Session,
    job_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    worker: str,
    error_type: str,
    message: str,
    retry: bool,
    retry_delay_seconds: int = 5,
) -> None:
    """Record a failure.  ``retry=True`` re-queues with a delay unless attempts are exhausted."""
    row = session.execute(select(Job.attempts, Job.max_attempts).where(Job.id == job_id)).one()
    exhausted = row.attempts >= row.max_attempts
    if retry and not exhausted:
        _fenced(
            session,
            job_id,
            run_id,
            status=JobStatus.queued,
            lease_owner=None,
            lease_expires_at=None,
            available_at=_now() + timedelta(seconds=retry_delay_seconds),
            error_type=error_type,
            error_message=message[:4000],
        )
        event = "retry_scheduled"
    else:
        _fenced(
            session,
            job_id,
            run_id,
            status=JobStatus.failed,
            finished_at=_now(),
            lease_owner=None,
            lease_expires_at=None,
            error_type="retries_exhausted" if (retry and exhausted) else error_type,
            error_message=message[:4000],
        )
        event = "failed"
    session.add(
        JobEvent(
            job_id=job_id,
            run_id=run_id,
            event=event,
            worker=worker,
            detail={"error_type": error_type, "message": message[:500]},
        )
    )


def cancel_from_worker(session: Session, job_id: uuid.UUID, run_id: uuid.UUID, *, worker: str) -> None:
    _fenced(
        session, job_id, run_id, status=JobStatus.cancelled, finished_at=_now(), lease_owner=None, lease_expires_at=None
    )
    session.add(JobEvent(job_id=job_id, run_id=run_id, event="cancelled", worker=worker, detail={}))


def request_cancel(session: Session, job: Job, *, actor: str) -> str:
    """Cancel a queued job immediately; ask a leased job to stop at its next checkpoint."""
    if job.status == JobStatus.queued:
        job.status = JobStatus.cancelled
        job.finished_at = _now()
        session.add(JobEvent(job_id=job.id, event="cancelled", detail={"by": actor}))
        return "cancelled"
    if job.status == JobStatus.leased:
        job.cancel_requested = True
        session.add(JobEvent(job_id=job.id, run_id=job.run_id, event="cancel_requested", detail={"by": actor}))
        return "cancel_requested"
    return "not_cancellable"


def queue_depth(session: Session) -> dict[str, int]:
    rows = session.execute(text("select status, count(*) from jobs group by status")).all()
    depth = {s.value: 0 for s in JobStatus}
    for status, count in rows:
        depth[str(status)] = int(count)
    expired = session.execute(
        text("select count(*) from jobs where status='leased' and lease_expires_at < now()")
    ).scalar_one()
    depth["leased_expired"] = int(expired)
    return depth
