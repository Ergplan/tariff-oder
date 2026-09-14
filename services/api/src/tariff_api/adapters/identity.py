"""Identity adapter.

The adapter only establishes *who* the caller is.  Role checks happen in the backend
(``tariff_api.auth``) for both profiles, so the local adapter can never grant more than the
cloud one.
"""

from __future__ import annotations

import abc
import logging
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

    @property
    def description(self) -> str:
        """What /status shows.  Never hides a degraded state behind the backend name."""
        return self.name

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
            # No load balancer exists yet (no domain), so no assertion can be verified.  Refusing
            # to construct would crash-loop the service; instead start, serve health probes, and
            # refuse every authenticated request.  Fails closed, and says so in logs and /status.
            logging.getLogger(__name__).warning(
                "IAP identity is not configured (IAP_AUDIENCE is empty): every authenticated "
                "request will be refused with `unauthenticated`. Set var.domain, apply, then "
                "copy `terraform output iap_audiences` into var.iap_audiences and apply again."
            )

    @property
    def configured(self) -> bool:
        return bool(self.audiences)

    @property
    def description(self) -> str:
        return self.name if self.configured else f"{self.name} (UNCONFIGURED — all requests refused)"

    def authenticate(self, headers: Mapping[str, str], role_lookup) -> Principal | None:
        if not self.audiences:
            return None
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
            # Diagnostic only: the unverified `aud` tells the operator which audience string
            # IAP actually signs for this deployment (Cloud Run IAP and load-balancer IAP use
            # different forms).  Nothing from an unverified token is ever trusted.
            try:
                from google.auth import jwt as google_jwt

                observed = google_jwt.decode(assertion, verify=False).get("aud")
            except Exception:  # noqa: BLE001
                observed = None
            logging.getLogger(__name__).warning(
                "IAP assertion rejected", extra={"observed_aud": observed, "configured": self.audiences}
            )
            return None
        email = (claims.get("email") or "").lower()
        if not email:
            return None
        role = role_lookup(email)
        if role is None:
            return Principal(email=email, role=UserRole.analyst, provider=self.name + ":unregistered")
        return Principal(email=email, role=role, provider=self.name)


class GoogleIdTokenIdentityProvider(IdentityProvider):
    """``gcp`` profile without a domain: verifies a Google-signed OpenID Connect ID token.

    Cloud Run already authenticates the caller at its front door (no public ingress, invoker
    IAM); this adapter establishes *who* the human is from the same kind of token.  Two
    places to find it: ``X-User-Id-Token`` (the web app forwards the token it received from
    ``gcloud run services proxy`` while using its own service token for the call itself) or,
    for direct API calls, the ``Authorization: Bearer`` header.  The token must be signed by
    Google, unexpired, carry a verified email, and name one of the configured audiences —
    our own service URLs, so a token minted for any other service is refused.  Roles come
    from the users table; a verified but unregistered user gets ``permission_denied``.
    """

    name = "google_id_token"
    USER_HEADER = "x-user-id-token"

    def __init__(self, audiences: str) -> None:
        self.audiences = [a.strip().rstrip("/") for a in audiences.split(",") if a.strip()]
        if not self.audiences:
            logging.getLogger(__name__).warning(
                "google_id_token identity has no audiences (ID_TOKEN_AUDIENCES is empty): every "
                "authenticated request will be refused with `unauthenticated`."
            )

    @property
    def configured(self) -> bool:
        return bool(self.audiences)

    @property
    def description(self) -> str:
        return self.name if self.configured else f"{self.name} (UNCONFIGURED — all requests refused)"

    @staticmethod
    def _extract(headers: Mapping[str, str]) -> str | None:
        token = (headers.get(GoogleIdTokenIdentityProvider.USER_HEADER) or "").strip()
        if token:
            return token
        auth = (headers.get("authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip() or None
        return None

    def verify(self, token: str) -> dict | None:
        """Claims of a Google-signed token whose audience is one of ours, else ``None``.
        Separated so tests can substitute the verifier; production uses google-auth."""
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        request = google_requests.Request()
        for audience in self.audiences:
            try:
                return id_token.verify_oauth2_token(token, request, audience=audience)
            except Exception:  # noqa: BLE001 - any verification failure is "unauthenticated"
                continue
        return None

    def authenticate(self, headers: Mapping[str, str], role_lookup) -> Principal | None:
        if not self.audiences:
            return None
        token = self._extract(headers)
        if not token:
            return None
        claims = self.verify(token)
        if not claims:
            return None
        if claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
            return None
        email = (claims.get("email") or "").lower()
        if not email or not claims.get("email_verified", False):
            return None
        role = role_lookup(email)
        if role is None:
            return Principal(email=email, role=UserRole.analyst, provider=self.name + ":unregistered")
        return Principal(email=email, role=role, provider=self.name, display_name=claims.get("name"))
