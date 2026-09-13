"""Identity adapter.

The adapter only establishes *who* the caller is.  Role checks happen in the backend
(``tariff_api.auth``) for both profiles, so the local adapter can never grant more than the
cloud one.
"""

from __future__ import annotations

import abc
from collections.abc import Mapping
from dataclasses import dataclass

from ..models import UserRole


@dataclass(frozen=True)
class Principal:
    email: str
    role: UserRole
    provider: str
    display_name: str | None = None


class IdentityProvider(abc.ABC):
    name: str = "abstract"

    @abc.abstractmethod
    def authenticate(self, headers: Mapping[str, str], role_lookup) -> Principal | None:
        """Return the principal or ``None`` if unauthenticated.

        ``role_lookup(email) -> UserRole | None`` consults the users table; the local adapter
        may instead take roles from its allow-list.
        """


class LocalIdentityProvider(IdentityProvider):
    """Developer/CI adapter.  Trusts an ``X-Local-User`` header only for emails on an explicit
    allow-list.  Refuses to be constructed when the deployment profile is ``gcp``."""

    name = "local"
    HEADER = "x-local-user"

    def __init__(self, profile: str, allowlist: dict[str, str]) -> None:
        if profile == "gcp":
            raise RuntimeError("LocalIdentityProvider refuses to run under DEPLOYMENT_PROFILE=gcp")
        if not allowlist:
            raise RuntimeError(
                "LOCAL_USER_ALLOWLIST is empty; the local identity adapter requires an explicit "
                "allow-list of `email:role` entries"
            )
        self.allowlist = {k.lower(): UserRole(v) for k, v in allowlist.items()}

    def authenticate(self, headers: Mapping[str, str], role_lookup) -> Principal | None:
        email = (headers.get(self.HEADER) or "").strip().lower()
        if not email or email not in self.allowlist:
            return None
        role = self.allowlist[email]
        return Principal(email=email, role=role, provider=self.name)


class IapIdentityProvider(IdentityProvider):
    """``gcp`` profile: verifies the Identity-Aware Proxy JWT assertion header.

    See https://cloud.google.com/iap/docs/signed-headers-howto .  The audience is the
    backend-service audience string of the load balancer.  Roles come from the users table;
    an authenticated user without a row is treated as unauthenticated for role purposes and
    receives ``permission_denied``.
    """

    name = "iap"
    HEADER = "x-goog-iap-jwt-assertion"
    CERTS_URL = "https://www.gstatic.com/iap/verify/public_key"

    def __init__(self, audience: str) -> None:
        # Comma-separated list: the web backend's audience (assertions forwarded by the web app)
        # and the API backend's audience (direct /api/* requests through the load balancer).
        self.audiences = [a.strip() for a in audience.split(",") if a.strip()]
        if not self.audiences:
            raise RuntimeError("IAP_AUDIENCE is required for the iap identity adapter")

    def authenticate(self, headers: Mapping[str, str], role_lookup) -> Principal | None:
        assertion = headers.get(self.HEADER)
        if not assertion:
            return None
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        claims = None
        for audience in self.audiences:
            try:
                claims = id_token.verify_token(
                    assertion,
                    google_requests.Request(),
                    audience=audience,
                    certs_url=self.CERTS_URL,
                )
                break
            except Exception:  # noqa: BLE001 - any verification failure is "unauthenticated"
                continue
        if claims is None:
            return None
        email = (claims.get("email") or "").lower()
        if not email:
            return None
        role = role_lookup(email)
        if role is None:
            return Principal(email=email, role=UserRole.analyst, provider=self.name + ":unregistered")
        return Principal(email=email, role=role, provider=self.name)
