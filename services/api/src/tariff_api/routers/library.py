"""The regulatory library (ADR-0019): coverage of every state's tariff orders, true-ups, MYT
orders, ARR/MYT petitions and regulations by licensee and year, and the desk's tools to seed
expected slots, record official URLs and acquire documents.  Clients read; the desk writes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from ..auth import Principal, require_admin, require_analyst
from ..db import session_scope
from ..errors import AppError
from ..models import Commission, LibraryEntry, Utility
from ..schemas import (
    CoverageOut,
    JobSummary,
    LibraryDiscoverRequest,
    LibraryEntryIn,
    LibraryEntryOut,
    LibraryProposal,
    LibrarySeedOut,
    LibrarySeedRequest,
)

router = APIRouter(prefix="/library", tags=["library"])


def _out(s, e: LibraryEntry, *, level: bool = True) -> LibraryEntryOut:
    from ..library import reading_level

    c = s.get(Commission, e.commission_id)
    u = s.get(Utility, e.utility_id) if e.utility_id else None
    return LibraryEntryOut(
        id=e.id,
        commission=c.code,
        utility=u.code if u else None,
        document_kind=e.document_kind,
        fiscal_year=e.fiscal_year,
        title=e.title,
        url=e.url,
        status=e.status,
        origin=e.origin,
        source_id=e.source_id,
        attempts=e.attempts,
        last_error=e.last_error,
        last_attempt_at=e.last_attempt_at,
        note=e.note,
        updated_by=e.updated_by,
        updated_at=e.updated_at,
        reading=reading_level(s, e) if level else None,
    )


@router.get("/coverage", response_model=CoverageOut, dependencies=[Depends(require_analyst)])
def coverage(fiscal_years: str = "", kinds: str = "") -> CoverageOut:
    from ..library import coverage as cov
    from ..models import LIBRARY_KINDS

    with session_scope() as s:
        fys = [f for f in fiscal_years.split(",") if f] or sorted(
            {fy for (fy,) in s.execute(select(LibraryEntry.fiscal_year).distinct()) if fy}
        )
        ks = [k for k in kinds.split(",") if k] or list(LIBRARY_KINDS)
        return CoverageOut(**cov(s, fiscal_years=fys, kinds=ks))


@router.get("/entries", response_model=list[LibraryEntryOut], dependencies=[Depends(require_analyst)])
def list_entries(
    commission: str | None = None,
    utility: str | None = None,
    kind: str | None = None,
    fiscal_year: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[LibraryEntryOut]:
    with session_scope() as s:
        q = select(LibraryEntry).order_by(LibraryEntry.fiscal_year.desc(), LibraryEntry.document_kind)
        if commission:
            q = q.join(Commission, Commission.id == LibraryEntry.commission_id).where(Commission.code == commission)
        if utility:
            q = q.join(Utility, Utility.id == LibraryEntry.utility_id).where(Utility.code == utility)
        if kind:
            q = q.where(LibraryEntry.document_kind == kind)
        if fiscal_year is not None:
            q = q.where(LibraryEntry.fiscal_year == fiscal_year)
        if status:
            q = q.where(LibraryEntry.status == status)
        return [_out(s, e) for e in s.execute(q.limit(min(limit, 2000))).scalars()]


@router.post("/seed", response_model=LibrarySeedOut)
def seed(body: LibrarySeedRequest, principal: Principal = Depends(require_admin)) -> LibrarySeedOut:
    from ..library import seed as do_seed

    with session_scope() as s:
        return LibrarySeedOut(**do_seed(s, actor=principal.email, **body.model_dump()))


@router.post("/reconcile", response_model=LibrarySeedOut)
def reconcile(principal: Principal = Depends(require_admin)) -> LibrarySeedOut:
    from ..library import reconcile as do

    with session_scope() as s:
        return LibrarySeedOut(created=0, existing=0, linked=do(s, actor=principal.email))


@router.put("/entries", response_model=LibraryEntryOut)
def upsert_entry(body: LibraryEntryIn, principal: Principal = Depends(require_admin)) -> LibraryEntryOut:
    """Record (or update) a document slot, typically with the official URL it is published at."""
    from ..library import upsert_entry as do

    with session_scope() as s:
        e = do(s, actor=principal.email, **body.model_dump())
        return _out(s, e)


@router.post("/entries/bulk", response_model=list[LibraryEntryOut])
def bulk_upsert(body: list[LibraryEntryIn], principal: Principal = Depends(require_admin)) -> list[LibraryEntryOut]:
    from ..library import upsert_entry as do

    if len(body) > 2000:
        raise AppError("validation_failed", "at most 2000 entries per request")
    with session_scope() as s:
        return [_out(s, do(s, actor=principal.email, **b.model_dump()), level=False) for b in body]


@router.post("/entries/{entry_id}/acquire", response_model=JobSummary, status_code=202)
def acquire(entry_id: uuid.UUID, request: Request, principal: Principal = Depends(require_admin)) -> JobSummary:
    from ..library import request_acquisition

    with session_scope() as s:
        e = s.get(LibraryEntry, entry_id)
        if e is None:
            raise AppError("not_found", "library entry not found")
        job = request_acquisition(s, request.app.state.settings, e, actor=principal.email)
        s.flush()
        return JobSummary.model_validate(job, from_attributes=True)


@router.post("/discover", response_model=list[LibraryProposal])
def discover(body: LibraryDiscoverRequest, principal: Principal = Depends(require_admin)) -> list[LibraryProposal]:
    """Proposals from a commission's listing page (fetched, or pasted when the list sits behind
    a search form).  Nothing is recorded: the desk confirms proposals with ``/entries/bulk``."""
    from ..library import discover as do

    with session_scope() as s:
        return [LibraryProposal(**p) for p in do(s, **body.model_dump())]
