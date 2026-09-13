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
from .identity import IapIdentityProvider, IdentityProvider, LocalIdentityProvider
from .secrets import EnvSecretProvider, SecretManagerProvider, SecretProvider
from .storage import FilesystemObjectStore, GcsObjectStore, ObjectStore


@dataclass
class Adapters:
    storage: ObjectStore
    secrets: SecretProvider
    identity: IdentityProvider

    def describe(self) -> dict[str, str]:
        return {
            "storage": self.storage.name,
            "secrets": self.secrets.name,
            "identity": self.identity.name,
        }


def build_adapters(settings: Settings) -> Adapters:
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

    if settings.identity_backend == IdentityBackend.local:
        identity: IdentityProvider = LocalIdentityProvider(
            profile=settings.deployment_profile.value,
            allowlist=settings.allowlist_entries(),
        )
    else:
        identity = IapIdentityProvider(audience=settings.iap_audience)

    return Adapters(storage=storage, secrets=secrets, identity=identity)


__all__ = [
    "Adapters",
    "build_adapters",
    "ObjectStore",
    "SecretProvider",
    "IdentityProvider",
]
