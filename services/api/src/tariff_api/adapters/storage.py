"""Object storage adapter.

Keys are content-derived and immutable (``sources/<sha256>.pdf``,
``artefacts/<sha256>/<stage>/<tool>@<version>/...``).  Both implementations use the same key
scheme; the only difference is where the bytes live.
"""

from __future__ import annotations

import abc
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path


class ObjectNotFound(Exception):
    pass


class ObjectStore(abc.ABC):
    name: str = "abstract"

    @abc.abstractmethod
    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None: ...

    @abc.abstractmethod
    def get(self, bucket: str, key: str) -> bytes: ...

    @abc.abstractmethod
    def stream(self, bucket: str, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]: ...

    @abc.abstractmethod
    def exists(self, bucket: str, key: str) -> bool: ...

    @abc.abstractmethod
    def health(self) -> dict: ...

    # Logical buckets - the application addresses buckets by role, never by cloud name.
    SOURCES = "sources"
    ARTEFACTS = "artefacts"
    EXPORTS = "exports"


class FilesystemObjectStore(ObjectStore):
    """``local`` profile adapter.  Writes are atomic (temp file + rename) and never overwrite
    an existing key, which mirrors object versioning on the cloud bucket."""

    name = "filesystem"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, bucket: str, key: str) -> Path:
        if ".." in key.split("/") or key.startswith("/"):
            raise ValueError("invalid object key")
        return self.root / bucket / key

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        path = self._path(bucket, key)
        if path.exists():
            return  # immutable content-addressed key
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def get(self, bucket: str, key: str) -> bytes:
        path = self._path(bucket, key)
        if not path.exists():
            raise ObjectNotFound(f"{bucket}/{key}")
        return path.read_bytes()

    def stream(self, bucket: str, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        path = self._path(bucket, key)
        if not path.exists():
            raise ObjectNotFound(f"{bucket}/{key}")
        with path.open("rb") as fh:
            while chunk := fh.read(chunk_size):
                yield chunk

    def exists(self, bucket: str, key: str) -> bool:
        return self._path(bucket, key).exists()

    def health(self) -> dict:
        ok = os.access(self.root, os.W_OK)
        return {"ok": ok, "backend": self.name, "root": str(self.root)}


class GcsObjectStore(ObjectStore):
    """``gcp`` profile adapter over Cloud Storage.  Buckets are private, uniform-access,
    versioned; the application never generates public or signed URLs for sources."""

    name = "gcs"

    def __init__(self, project: str, source_bucket: str, artefact_bucket: str, export_bucket: str) -> None:
        from google.cloud import storage  # imported here so the local profile needs no SDK

        self._client = storage.Client(project=project or None)
        self._buckets = {
            self.SOURCES: source_bucket,
            self.ARTEFACTS: artefact_bucket,
            self.EXPORTS: export_bucket,
        }

    def _blob(self, bucket: str, key: str):
        name = self._buckets.get(bucket)
        if not name:
            raise ValueError(f"unknown logical bucket {bucket!r}")
        return self._client.bucket(name).blob(key)

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        blob = self._blob(bucket, key)
        # if_generation_match=0 refuses to overwrite: content-addressed keys are immutable
        from google.api_core.exceptions import PreconditionFailed

        try:
            blob.upload_from_string(data, content_type=content_type, if_generation_match=0)
        except PreconditionFailed:
            return

    def get(self, bucket: str, key: str) -> bytes:
        from google.api_core.exceptions import NotFound

        try:
            return self._blob(bucket, key).download_as_bytes()
        except NotFound as e:
            raise ObjectNotFound(f"{bucket}/{key}") from e

    def stream(self, bucket: str, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        from google.api_core.exceptions import NotFound

        blob = self._blob(bucket, key)
        try:
            with blob.open("rb") as fh:
                while chunk := fh.read(chunk_size):
                    yield chunk
        except NotFound as e:
            raise ObjectNotFound(f"{bucket}/{key}") from e

    def exists(self, bucket: str, key: str) -> bool:
        return self._blob(bucket, key).exists()

    def health(self) -> dict:
        try:
            for name in self._buckets.values():
                self._client.get_bucket(name)
            return {"ok": True, "backend": self.name, "buckets": list(self._buckets)}
        except Exception as e:  # noqa: BLE001 - reported, not raised, by readiness
            return {"ok": False, "backend": self.name, "error": type(e).__name__}
