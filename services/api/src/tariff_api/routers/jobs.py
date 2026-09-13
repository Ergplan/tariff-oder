from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from ..adapters.identity import Principal
from ..auth import require_admin, require_analyst
from ..db import session_scope
from ..errors import AppError
from ..models import Job, JobEvent, JobStatus
from ..queue import request_cancel
from ..schemas import CancelResult, JobDetail, JobEventOut, JobList, JobSummary

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobList, dependencies=[Depends(require_analyst)])
def list_jobs(
    status: JobStatus | None = None,
    source_id: uuid.UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> JobList:
    with session_scope() as s:
        q = select(Job)
        if status is not None:
            q = q.where(Job.status == status)
        if source_id is not None:
            q = q.where(Job.source_id == source_id)
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        rows = s.execute(q.order_by(Job.created_at.desc()).offset(offset).limit(limit)).scalars().all()
        return JobList(total=total, items=[JobSummary.model_validate(r, from_attributes=True) for r in rows])


@router.get("/{job_id}", response_model=JobDetail, dependencies=[Depends(require_analyst)])
def get_job(job_id: uuid.UUID) -> JobDetail:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job is None:
            raise AppError("not_found", f"job {job_id} not found")
        events = (
            s.execute(select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.at, JobEvent.id))
            .scalars()
            .all()
        )
        base = JobSummary.model_validate(job, from_attributes=True).model_dump()
        return JobDetail(
            **base, payload=job.payload, events=[JobEventOut.model_validate(e, from_attributes=True) for e in events]
        )


@router.post("/{job_id}/cancel", response_model=CancelResult)
def cancel_job(job_id: uuid.UUID, principal: Principal = Depends(require_admin)) -> CancelResult:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job is None:
            raise AppError("not_found", f"job {job_id} not found")
        result = request_cancel(s, job, actor=principal.email)
        if result == "not_cancellable":
            raise AppError("job_not_cancellable")
        return CancelResult(job_id=job.id, result=result)
