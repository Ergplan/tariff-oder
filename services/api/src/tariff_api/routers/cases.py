"""ARR cases (ADR-0019): a client organisation's ARR process for a licensee — create, see
what is ready and missing, enter assumptions, formulate, freeze, draft the petition, revise.
Every case is private to its organisation; another organisation's case is not found."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from .. import workspace as ws
from ..adapters.storage import ObjectStore
from ..auth import Principal, require_analyst
from ..db import session_scope
from ..errors import AppError
from ..models import ArrCase, Organisation, Utility
from ..schemas import (
    ArrAssumptionIn,
    ArrAssumptionOut,
    ArrCaseCreate,
    ArrCaseOut,
    ArrCaseUpdate,
    ArrFormulationOut,
    FilingDraftOut,
)

router = APIRouter(prefix="/cases", tags=["arr cases"])


def _out(s, case: ArrCase, *, with_readiness: bool = False) -> ArrCaseOut:
    from ..arr.cases import readiness

    u = s.get(Utility, case.utility_id)
    org = s.get(Organisation, case.organisation_id)
    return ArrCaseOut(
        id=case.id,
        organisation_id=case.organisation_id,
        organisation=org.code,
        utility=u.code,
        utility_name=u.name,
        commission=u.commission.code,
        title=case.title,
        filing_kind=case.filing_kind,
        base_fy=case.base_fy,
        targets=case.targets,
        status=case.status,
        assumption_set_id=case.assumption_set_id,
        formulation_id=case.formulation_id,
        draft_id=case.draft_id,
        notes=case.notes,
        created_by=case.created_by,
        created_at=case.created_at,
        updated_at=case.updated_at,
        readiness=readiness(s, case) if with_readiness else None,
    )


def _case(s, case_id: uuid.UUID, principal: Principal, need: ws.Need = "read") -> ArrCase:
    case = s.get(ArrCase, case_id)
    if case is None:
        raise AppError("not_found", "case not found")
    ws.require(s, principal, case.organisation_id, need, what="case")
    return case


@router.post("", response_model=ArrCaseOut, status_code=201)
def create_case(body: ArrCaseCreate, principal: Principal = Depends(require_analyst)) -> ArrCaseOut:
    from ..arr import cases
    from ..arr.service import utility_by_code

    with session_scope() as s:
        org = s.get(Organisation, body.organisation_id)
        if org is None or not org.active:
            raise AppError("not_found", "organisation not found")
        ws.require(s, principal, org.id, "write", what="case")
        case = cases.create_case(
            s,
            organisation=org,
            utility=utility_by_code(s, body.utility_code),
            title=body.title,
            filing_kind=body.filing_kind,
            base_fy=body.base_fy,
            target_years=body.target_years,
            copy_from=body.copy_assumptions_from,
            notes=body.notes,
            actor=principal.email,
        )
        s.flush()
        s.refresh(case)
        return _out(s, case, with_readiness=True)


@router.get("", response_model=list[ArrCaseOut])
def list_cases(
    organisation_id: uuid.UUID | None = None, principal: Principal = Depends(require_analyst)
) -> list[ArrCaseOut]:
    with session_scope() as s:
        q = select(ArrCase).order_by(ArrCase.updated_at.desc())
        orgs = ws.visible_orgs(s, principal)
        if orgs is not None:
            q = q.where(ArrCase.organisation_id.in_(orgs or [uuid.UUID(int=0)]))
        if organisation_id is not None:
            q = q.where(ArrCase.organisation_id == organisation_id)
        return [_out(s, c) for c in s.execute(q).scalars()]


@router.get("/{case_id}", response_model=ArrCaseOut)
def get_case(case_id: uuid.UUID, principal: Principal = Depends(require_analyst)) -> ArrCaseOut:
    with session_scope() as s:
        return _out(s, _case(s, case_id, principal), with_readiness=True)


@router.patch("/{case_id}", response_model=ArrCaseOut)
def update_case(case_id: uuid.UUID, body: ArrCaseUpdate, principal: Principal = Depends(require_analyst)) -> ArrCaseOut:
    with session_scope() as s:
        case = _case(s, case_id, principal, "write")
        if body.title is not None:
            case.title = body.title
        if body.notes is not None:
            case.notes = body.notes
        if body.status == "closed":
            case.status = "closed"
        s.flush()
        return _out(s, case, with_readiness=True)


@router.post("/{case_id}/assumptions", response_model=ArrAssumptionOut, status_code=201)
def add_assumption(
    case_id: uuid.UUID, body: ArrAssumptionIn, request: Request, principal: Principal = Depends(require_analyst)
) -> ArrAssumptionOut:
    from ..arr import cases

    storage: ObjectStore = request.app.state.adapters.storage
    with session_scope() as s:
        a = cases.add_assumption(
            s, storage, _case(s, case_id, principal, "write"), actor=principal.email, **body.model_dump()
        )
        s.flush()
        s.refresh(a)
        return ArrAssumptionOut.model_validate(a, from_attributes=True)


@router.delete("/{case_id}/assumptions/{assumption_id}", status_code=204)
def remove_assumption(
    case_id: uuid.UUID, assumption_id: uuid.UUID, principal: Principal = Depends(require_analyst)
) -> Response:
    from ..arr import cases

    with session_scope() as s:
        cases.remove_assumption(s, _case(s, case_id, principal, "write"), assumption_id, actor=principal.email)
    return Response(status_code=204)


def _formulation_out(s, f) -> ArrFormulationOut:
    from .arr import _formulation_out as fo

    return fo(s, f)


@router.post("/{case_id}/formulate", response_model=ArrFormulationOut, status_code=201)
def formulate(case_id: uuid.UUID, principal: Principal = Depends(require_analyst)) -> ArrFormulationOut:
    from ..arr import cases

    with session_scope() as s:
        f = cases.formulate(s, _case(s, case_id, principal, "write"), actor=principal.email)
        s.flush()
        s.refresh(f)
        return _formulation_out(s, f)


@router.post("/{case_id}/freeze", response_model=ArrFormulationOut)
def freeze(case_id: uuid.UUID, principal: Principal = Depends(require_analyst)) -> ArrFormulationOut:
    from ..arr import cases

    with session_scope() as s:
        f = cases.freeze(s, _case(s, case_id, principal, "write"), actor=principal.email)
        s.flush()
        return _formulation_out(s, f)


@router.post("/{case_id}/draft", response_model=FilingDraftOut, status_code=201)
def draft(case_id: uuid.UUID, request: Request, principal: Principal = Depends(require_analyst)) -> FilingDraftOut:
    from ..arr import cases
    from .arr import _draft_out

    storage: ObjectStore = request.app.state.adapters.storage
    with session_scope() as s:
        d = cases.draft(s, storage, _case(s, case_id, principal, "write"), actor=principal.email)
        s.flush()
        s.refresh(d)
        return _draft_out(d)


@router.post("/{case_id}/revise", response_model=ArrCaseOut)
def revise(case_id: uuid.UUID, principal: Principal = Depends(require_analyst)) -> ArrCaseOut:
    from ..arr import cases

    with session_scope() as s:
        case = cases.revise(s, _case(s, case_id, principal, "write"), actor=principal.email)
        s.flush()
        return _out(s, case, with_readiness=True)
