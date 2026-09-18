"""Authentication and role enforcement (backend-only, both profiles)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy import select

from .adapters.identity import Principal
from .db import session_scope
from .errors import AppError
from .models import User, UserRole
from .telemetry import actor_var

ROLE_RANK = {UserRole.analyst: 1, UserRole.reviewer: 2, UserRole.administrator: 3}


def _role_lookup(email: str) -> UserRole | None:
    with session_scope() as s:
        user = s.execute(select(User).where(User.email == email, User.active.is_(True))).scalar_one_or_none()
        return user.role if user else None


def current_principal(request: Request) -> Principal:
    adapters = request.app.state.adapters
    if adapters.identity is None:
        raise AppError("unauthenticated", "this process has no identity provider")
    principal = adapters.identity.authenticate(request.headers, _role_lookup)
    if principal is None:
        # Names of the identity headers present (never their values) plus the adapter, so an
        # operator can tell "no assertion arrived" from "assertion rejected" in the logs.
        present = [
            h
            for h in (
                "x-goog-iap-jwt-assertion",
                "x-forwarded-iap-assertion",
                "x-user-id-token",
                "authorization",
                "x-local-user",
            )
            if h in request.headers
        ]
        logging.getLogger(__name__).warning(
            "unauthenticated request",
            extra={"identity_headers": present, "adapter": adapters.identity.description, "path": request.url.path},
        )
        raise AppError("unauthenticated")
    if principal.provider.endswith(":unregistered"):
        raise AppError("permission_denied", "authenticated user is not registered in this workspace")
    actor_var.set(principal.email)
    request.state.principal = principal
    return principal


def require_role(minimum: UserRole) -> Callable[[Principal], Principal]:
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if ROLE_RANK[principal.role] < ROLE_RANK[minimum]:
            raise AppError(
                "permission_denied",
                f"requires role {minimum.value} or higher; you have {principal.role.value}",
            )
        return principal

    return dependency


require_analyst = require_role(UserRole.analyst)
require_reviewer = require_role(UserRole.reviewer)
require_admin = require_role(UserRole.administrator)


def known_role(session, settings, email: str) -> UserRole | None:
    """The role an email holds: the users table (every profile), else the local
    allow-list when the deployment is not `gcp`.  None when the email is unknown."""
    from sqlalchemy import select

    from .models import User

    email = (email or "").strip().lower()
    if not email:
        return None
    user = session.execute(select(User).where(User.email == email, User.active.is_(True))).scalar_one_or_none()
    if user is not None:
        return user.role
    if settings.deployment_profile != "gcp":
        entry = settings.allowlist_entries().get(email)
        return UserRole(entry) if entry else None
    return None
