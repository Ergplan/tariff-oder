"""Jurisdictions, commissions, utilities, users, audit (administrator workflow, Section 7.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from ..adapters.identity import Principal
from ..auth import require_admin, require_analyst
from ..db import session_scope
from ..errors import AppError
from ..models import AuditEvent, Commission, Jurisdiction, User, Utility
from ..schemas import (
    AuditEventOut,
    CommissionOut,
    JurisdictionOut,
    RegistryOut,
    UserOut,
    UserUpsert,
    UtilityCreate,
    UtilityOut,
)
from ..services.sources import get_or_create_dataset
from ..telemetry import request_id_var

router = APIRouter(tags=["registry"])


def _utility_out(u: Utility) -> UtilityOut:
    return UtilityOut(
        id=u.id,
        code=u.code,
        name=u.name,
        commission_id=u.commission_id,
        dataset_kind=u.dataset.kind,
        licensed_area=u.licensed_area,
        aliases=u.aliases,
        active_reading_profile=u.active_reading_profile,
        active_reading_profile_version=u.active_reading_profile_version,
    )


@router.get("/registry", response_model=RegistryOut, dependencies=[Depends(require_analyst)])
def registry() -> RegistryOut:
    with session_scope() as s:
        js = s.execute(select(Jurisdiction).order_by(Jurisdiction.code)).scalars().all()
        cs = s.execute(select(Commission).order_by(Commission.code)).scalars().all()
        us = s.execute(select(Utility).order_by(Utility.code)).scalars().all()
        return RegistryOut(
            jurisdictions=[JurisdictionOut.model_validate(j, from_attributes=True) for j in js],
            commissions=[CommissionOut.model_validate(c, from_attributes=True) for c in cs],
            utilities=[_utility_out(u) for u in us],
        )


@router.post("/utilities", response_model=UtilityOut, status_code=201)
def create_utility(body: UtilityCreate, principal: Principal = Depends(require_admin)) -> UtilityOut:
    with session_scope() as s:
        commission = s.execute(select(Commission).where(Commission.code == body.commission_code)).scalar_one_or_none()
        if commission is None:
            raise AppError("validation_failed", f"unknown commission {body.commission_code}")
        if s.execute(select(Utility).where(Utility.code == body.code)).scalar_one_or_none():
            raise AppError("validation_failed", f"utility {body.code} already exists")
        ds = get_or_create_dataset(s, body.dataset_kind)
        u = Utility(
            code=body.code,
            name=body.name,
            commission_id=commission.id,
            dataset_id=ds.id,
            licensed_area=body.licensed_area,
            aliases=body.aliases,
        )
        s.add(u)
        s.flush()
        s.add(
            AuditEvent(
                actor=principal.email,
                action="utility.created",
                entity_type="utility",
                entity_id=str(u.id),
                after=body.model_dump(),
                request_id=request_id_var.get(),
            )
        )
        s.refresh(u)
        return _utility_out(u)


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_admin)])
def list_users() -> list[UserOut]:
    with session_scope() as s:
        rows = s.execute(select(User).order_by(User.email)).scalars().all()
        return [UserOut.model_validate(r, from_attributes=True) for r in rows]


@router.put("/users", response_model=UserOut)
def upsert_user(body: UserUpsert, principal: Principal = Depends(require_admin)) -> UserOut:
    """Role changes are audit events (Section 7.4)."""
    email = body.email.strip().lower()
    with session_scope() as s:
        user = s.execute(select(User).where(User.email == email)).scalar_one_or_none()
        before = None
        if user is None:
            user = User(email=email, display_name=body.display_name, role=body.role, active=body.active)
            s.add(user)
            action = "user.created"
        else:
            before = {"role": user.role.value, "active": user.active}
            user.display_name = body.display_name
            user.role = body.role
            user.active = body.active
            action = "user.updated"
        s.flush()
        s.add(
            AuditEvent(
                actor=principal.email,
                action=action,
                entity_type="user",
                entity_id=str(user.id),
                before=before,
                after={"role": user.role.value, "active": user.active},
                request_id=request_id_var.get(),
            )
        )
        s.refresh(user)
        return UserOut.model_validate(user, from_attributes=True)


@router.get("/audit", response_model=list[AuditEventOut], dependencies=[Depends(require_admin)])
def list_audit(
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
) -> list[AuditEventOut]:
    with session_scope() as s:
        q = select(AuditEvent)
        if entity_type:
            q = q.where(AuditEvent.entity_type == entity_type)
        if entity_id:
            q = q.where(AuditEvent.entity_id == entity_id)
        rows = s.execute(q.order_by(AuditEvent.at.desc(), AuditEvent.id.desc()).limit(limit)).scalars().all()
        return [AuditEventOut.model_validate(r, from_attributes=True) for r in rows]
