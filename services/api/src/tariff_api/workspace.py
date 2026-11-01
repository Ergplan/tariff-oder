"""Who may see and change what (ADR-0019), decided in one place.

- A **desk object** (``organisation_id`` null): any platform analyst reads; a platform
  reviewer or administrator writes (Increment A behaviour).
- An **organisation object**: its members read (viewer), write (editor) or manage (owner);
  a platform administrator may read it for support.  Anyone else gets ``not_found``: an id
  from another organisation must not even confirm that the object exists.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .adapters.identity import Principal
from .errors import AppError
from .models import ORG_ROLES, Organisation, OrganisationMember, UserRole

Need = Literal["read", "write", "manage"]
_NEED_RANK = {"read": 0, "write": 1, "manage": 2}
_PLATFORM_RANK = {UserRole.analyst: 1, UserRole.reviewer: 2, UserRole.administrator: 3}


def memberships(session: Session, email: str) -> dict[uuid.UUID, str]:
    rows = session.execute(
        select(OrganisationMember.organisation_id, OrganisationMember.role)
        .join(Organisation, Organisation.id == OrganisationMember.organisation_id)
        .where(OrganisationMember.email == email.lower(), Organisation.active.is_(True))
    ).all()
    return {org: role for org, role in rows}


def can(session: Session, principal: Principal, organisation_id: uuid.UUID | None, need: Need) -> bool:
    if organisation_id is None:
        if need == "read":
            return True
        return _PLATFORM_RANK[principal.role] >= _PLATFORM_RANK[UserRole.reviewer]
    if principal.role == UserRole.administrator and need == "read":
        return True
    role = memberships(session, principal.email).get(organisation_id)
    return role is not None and ORG_ROLES.index(role) >= _NEED_RANK[need]


def require(
    session: Session, principal: Principal, organisation_id: uuid.UUID | None, need: Need, *, what: str
) -> None:
    if can(session, principal, organisation_id, need):
        return
    # reading is refused as "not found"; a member who may read but not write is told why
    if organisation_id is not None and can(session, principal, organisation_id, "read"):
        raise AppError("permission_denied", f"your role in this organisation does not allow changing {what}")
    if organisation_id is None and need != "read":
        raise AppError("permission_denied", f"changing a desk {what} needs the reviewer role")
    raise AppError("not_found", f"{what} not found")


def visible_orgs(session: Session, principal: Principal) -> set[uuid.UUID] | None:
    """The organisations whose objects this principal may list; None means all (platform
    administrator)."""
    if principal.role == UserRole.administrator:
        return None
    return set(memberships(session, principal.email))
