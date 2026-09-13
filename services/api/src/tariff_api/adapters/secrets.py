"""Secrets adapter.  Same variable names in both profiles; values never logged."""

from __future__ import annotations

import abc
import os


class SecretProvider(abc.ABC):
    name: str = "abstract"

    @abc.abstractmethod
    def get(self, name: str, default: str | None = None) -> str | None: ...


class EnvSecretProvider(SecretProvider):
    """``local`` profile: values come from the process environment (``.env`` outside git)."""

    name = "env"

    def get(self, name: str, default: str | None = None) -> str | None:
        return os.environ.get(name, default)


class SecretManagerProvider(SecretProvider):
    """``gcp`` profile: values are read from Secret Manager by the service identity.

    Secret ids equal the environment variable names so code stays identical.  Values are
    cached for the process lifetime; rotation requires a new revision and a restart.
    """

    name = "secret_manager"

    def __init__(self, project_id: str) -> None:
        from google.cloud import secretmanager

        self._client = secretmanager.SecretManagerServiceClient()
        self._project = project_id
        self._cache: dict[str, str | None] = {}

    def get(self, name: str, default: str | None = None) -> str | None:
        if name in self._cache:
            return self._cache[name] if self._cache[name] is not None else default
        from google.api_core.exceptions import NotFound

        path = f"projects/{self._project}/secrets/{name}/versions/latest"
        try:
            resp = self._client.access_secret_version(request={"name": path})
            value: str | None = resp.payload.data.decode("utf-8")
        except NotFound:
            value = None
        self._cache[name] = value
        return value if value is not None else default
