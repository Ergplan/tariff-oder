"""Client organisations and their members (ADR-0019).  A platform administrator creates an
organisation with its first owner; owners add and remove members.  A member who is not yet a
registered user is registered as a platform ``analyst`` (read-only on the shared corpus):
their organisation role, not a platform role, is what lets them work."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from .. import workspace as ws
from ..auth import Principal, require_admin, require_analyst
from ..db import session_scope
from ..errors import AppError
from ..models import AuditEvent, Organisation, OrganisationMember, User, UserRole
from ..schemas import (
    OrganisationCreate,
    OrganisationMemberIn,
    OrganisationMemberOut,
    OrganisationOut,
)
from ..telemetry import request_id_var

router = APIRouter(prefix="/organisations", tags=["organisations"])


def _audit(s, actor: str, action: str, entity_id: str, **kw) -> None:
    s.add(
        AuditEvent(
            actor=actor,
            action=action,
            entity_type="organisation",
            entity_id=entity_id,
            request_id=request_id_var.get(),
            **kw,
        )
    )


def _ensure_user(s, email: str) -> None:
    if s.execute(select(User).where(User.email == email)).scalar_one_or_none() is None:
        s.add(User(email=email, role=UserRole.analyst, active=True))


def _out(s, org: Organisation, principal: Principal, *, members: bool = True) -> OrganisationOut:
    rows = (
        s.execute(
            select(OrganisationMember)
            .where(OrganisationMember.organisation_id == org.id)
            .order_by(OrganisationMember.role, OrganisationMember.email)
        )
        .scalars()
        .all()
    )
    mine = next((m.role for m in rows if m.email == principal.email.lower()), None)
    return OrganisationOut(
        id=org.id,
        code=org.code,
        name=org.name,
        active=org.active,
        created_at=org.created_at,
        my_role=mine,
        members=[OrganisationMemberOut.model_validate(m, from_attributes=True) for m in rows] if members else [],
    )


def _org(s, org_id: uuid.UUID, principal: Principal, need: ws.Need) -> Organisation:
    org = s.get(Organisation, org_id)
    if org is None:
        raise AppError("not_found", "organisation not found")
    ws.require(s, principal, org.id, need, what="organisation")
    return org


@router.post("", response_model=OrganisationOut, status_code=201)
def create_organisation(body: OrganisationCreate, principal: Principal = Depends(require_admin)) -> OrganisationOut:
    owner = body.owner_email.strip().lower()
    with session_scope() as s:
        if s.execute(select(Organisation).where(Organisation.code == body.code)).scalar_one_or_none():
            raise AppError("validation_failed", f"organisation {body.code} already exists")
        org = Organisation(code=body.code, name=body.name, created_by=principal.email)
        s.add(org)
        s.flush()
        _ensure_user(s, owner)
        s.add(OrganisationMember(organisation_id=org.id, email=owner, role="owner", added_by=principal.email))
        _audit(s, principal.email, "organisation.created", str(org.id), after={"code": body.code, "owner": owner})
        s.flush()
        s.refresh(org)
        return _out(s, org, principal)


@router.get("", response_model=list[OrganisationOut])
def list_organisations(principal: Principal = Depends(require_analyst)) -> list[OrganisationOut]:
    with session_scope() as s:
        q = select(Organisation).order_by(Organisation.name)
        orgs = ws.visible_orgs(s, principal)
        if orgs is not None:
            q = q.where(Organisation.id.in_(orgs or [uuid.UUID(int=0)]))
        return [_out(s, o, principal, members=False) for o in s.execute(q).scalars()]


@router.get("/{org_id}", response_model=OrganisationOut)
def get_organisation(org_id: uuid.UUID, principal: Principal = Depends(require_analyst)) -> OrganisationOut:
    with session_scope() as s:
        return _out(s, _org(s, org_id, principal, "read"), principal)


@router.post("/{org_id}/members", response_model=OrganisationOut)
def add_member(
    org_id: uuid.UUID, body: OrganisationMemberIn, principal: Principal = Depends(require_analyst)
) -> OrganisationOut:
    email = body.email.strip().lower()
    with session_scope() as s:
        org = s.get(Organisation, org_id)
        if org is None:
            raise AppError("not_found", "organisation not found")
        if principal.role != UserRole.administrator:
            ws.require(s, principal, org.id, "manage", what="organisation members")
        m = s.execute(
            select(OrganisationMember).where(
                OrganisationMember.organisation_id == org.id, OrganisationMember.email == email
            )
        ).scalar_one_or_none()
        before = {"role": m.role} if m else None
        if m is None:
            _ensure_user(s, email)
            s.add(OrganisationMember(organisation_id=org.id, email=email, role=body.role, added_by=principal.email))
        else:
            if m.role == "owner" and body.role != "owner" and _owners(s, org.id) == 1:
                raise AppError("validation_failed", "an organisation keeps at least one owner")
            m.role = body.role
        _audit(
            s,
            principal.email,
            "organisation.member_set",
            str(org.id),
            before=before,
            after={"email": email, "role": body.role},
        )
        s.flush()
        return _out(s, org, principal)


def _owners(s, org_id: uuid.UUID) -> int:
    return s.execute(
        select(func.count()).where(OrganisationMember.organisation_id == org_id, OrganisationMember.role == "owner")
    ).scalar_one()


@router.delete("/{org_id}/members/{email}", response_model=OrganisationOut)
def remove_member(org_id: uuid.UUID, email: str, principal: Principal = Depends(require_analyst)) -> OrganisationOut:
    email = email.strip().lower()
    with session_scope() as s:
        org = s.get(Organisation, org_id)
        if org is None:
            raise AppError("not_found", "organisation not found")
        if principal.role != UserRole.administrator:
            ws.require(s, principal, org.id, "manage", what="organisation members")
        m = s.execute(
            select(OrganisationMember).where(
                OrganisationMember.organisation_id == org.id, OrganisationMember.email == email
            )
        ).scalar_one_or_none()
        if m is None:
            raise AppError("not_found", f"{email} is not a member")
        if m.role == "owner" and _owners(s, org.id) == 1:
            raise AppError("validation_failed", "an organisation keeps at least one owner")
        s.delete(m)
        _audit(s, principal.email, "organisation.member_removed", str(org.id), before={"email": email, "role": m.role})
        s.flush()
        return _out(s, org, principal)
