"""Platform adapters (Section 3.2).

Everything platform-specific lives behind these interfaces.  Application code receives an
:class:`Adapters` bundle and never imports a cloud SDK directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import (
    IdentityBackend,
    SecretsBackend,
    Settings,
    StorageBackend,
)
from .identity import GoogleIdTokenIdentityProvider, IapIdentityProvider, IdentityProvider, LocalIdentityProvider
from .secrets import EnvSecretProvider, SecretManagerProvider, SecretProvider
from .storage import FilesystemObjectStore, GcsObjectStore, ObjectStore


@dataclass
class Adapters:
    storage: ObjectStore
    secrets: SecretProvider
    identity: IdentityProvider | None

    def describe(self) -> dict[str, str]:
        return {
            "storage": self.storage.name,
            "secrets": self.secrets.name,
            "identity": self.identity.description if self.identity else "not built (no request path)",
        }


def build_adapters(settings: Settings, *, include_identity: bool = True) -> Adapters:
    """Build the platform adapters.

    ``include_identity=False`` is for processes that never serve a request — the worker and the
    operational CLI.  They must not require an identity provider to be configurable, and must
    not be able to authenticate anyone.
    """
    settings.validate_profile()

    if settings.object_store_backend == StorageBackend.filesystem:
        storage: ObjectStore = FilesystemObjectStore(settings.object_store_root)
    else:
        storage = GcsObjectStore(
            project=settings.gcp_project_id,
            source_bucket=settings.source_bucket,
            artefact_bucket=settings.artefact_bucket,
            export_bucket=settings.export_bucket or settings.artefact_bucket,
        )

    if settings.secrets_backend == SecretsBackend.env:
        secrets: SecretProvider = EnvSecretProvider()
    else:
        secrets = SecretManagerProvider(settings.gcp_project_id)

    identity: IdentityProvider | None = None
    if include_identity:
        if settings.identity_backend == IdentityBackend.local:
            identity = LocalIdentityProvider(
                profile=settings.deployment_profile.value,
                allowlist=settings.allowlist_entries(),
            )
        else:
            identity = (
                GoogleIdTokenIdentityProvider(audiences=settings.id_token_audiences)
                if settings.identity_backend == IdentityBackend.google_id_token
                else IapIdentityProvider(audience=settings.iap_audience)
            )

    return Adapters(storage=storage, secrets=secrets, identity=identity)


__all__ = [
    "Adapters",
    "build_adapters",
    "ObjectStore",
    "SecretProvider",
    "IdentityProvider",
]
