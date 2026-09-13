from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select

from .. import __version__
from ..auth import require_analyst
from ..db import check_database, get_engine, session_scope
from ..inventory import TOOL_NAME, TOOL_VERSION
from ..models import Dataset, SourceDocument
from ..queue import queue_depth
from ..schemas import Health, Readiness, StatusReport
from ..telemetry import request_id_var

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)


@router.get("/healthz", response_model=Health)
def healthz(request: Request) -> Health:
    return Health(status="ok", service=request.app.state.settings.service_name, version=__version__)


@router.get("/readyz", response_model=Readiness, responses={503: {"model": Readiness}})
def readyz(request: Request, response: Response) -> Readiness:
    db: dict = {}
    try:
        db = {"ok": True, **check_database(get_engine())}
    except Exception as e:  # noqa: BLE001
        log.error("readiness: database check failed", extra={"error": type(e).__name__})
        db = {"ok": False, "error": type(e).__name__}
    storage = request.app.state.adapters.storage.health()
    ready = bool(db.get("ok")) and bool(storage.get("ok"))
    response.status_code = 200 if ready else 503
    return Readiness(
        status="ready" if ready else "not_ready", database=db, storage=storage, request_id=request_id_var.get()
    )


@router.get("/status", response_model=StatusReport, dependencies=[Depends(require_analyst)])
def status(request: Request) -> StatusReport:
    settings = request.app.state.settings
    with session_scope() as s:
        depth = queue_depth(s)
        rows = s.execute(
            select(Dataset.name, func.count(SourceDocument.id))
            .join(SourceDocument, SourceDocument.dataset_id == Dataset.id, isouter=True)
            .group_by(Dataset.name)
        ).all()
    return StatusReport(
        service=settings.service_name,
        version=__version__,
        deployment_profile=settings.deployment_profile.value,
        environment_name=settings.environment_name,
        adapters=request.app.state.adapters.describe(),
        database=check_database(get_engine()),
        queue_depth=depth,
        tool_versions={"inventory": f"{TOOL_NAME}@{TOOL_VERSION}"},
        datasets={name: int(n) for name, n in rows},
        limits={
            "max_upload_bytes": settings.max_upload_bytes,
            "max_pages_per_job": settings.max_pages_per_job,
            "job_lease_seconds": settings.job_lease_seconds,
            "job_max_attempts": settings.job_max_attempts,
        },
    )
