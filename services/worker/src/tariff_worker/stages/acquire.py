"""``acquire_library_entry`` (ADR-0019): fetch a library entry's official URL and register the
PDF exactly as an upload (hash, dedup, golden manifest, licensee, order type), then link it.
A failure — blocked network, HTTP error, not a PDF — is recorded on the entry and not
retried automatically: a person re-requests it, typically from a host with open egress."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from tariff_api import library
from tariff_api.db import session_scope
from tariff_api.errors import AppError
from tariff_api.models import LibraryEntry

from ..runner import JobContext, JobFailure


def acquire_library_entry(ctx: JobContext) -> dict:
    entry_id = uuid.UUID(ctx.payload["entry_id"])
    with session_scope() as s:
        e = s.get(LibraryEntry, entry_id)
        if e is None:
            raise JobFailure("not_found", "library entry no longer exists", retry=False)
        if e.status == "acquired":
            return {"status": "already acquired", "source_id": str(e.source_id)}
        url = e.url
        if not url:
            raise JobFailure("validation_failed", "the entry has no URL", retry=False)
        twin = library.link_acquired_twin(s, e)
        if twin is not None:
            return {"status": "linked to the copy already acquired from the same URL", "source_id": str(twin.id)}
        e.attempts += 1
        e.last_attempt_at = datetime.now(UTC)
    try:
        data, final_url = library.fetch(url)
    except Exception as exc:  # noqa: BLE001 - every failure is recorded on the entry
        with session_scope() as s:
            e = s.get(LibraryEntry, entry_id)
            e.status, e.last_error = "failed", f"{type(exc).__name__}: {exc}"[:1000]
        raise JobFailure("provider_unavailable", f"could not fetch {url}: {exc}", retry=False) from exc
    with session_scope() as s:
        e = s.get(LibraryEntry, entry_id)
        try:
            src = library.acquire(s, ctx.adapters.storage, ctx.settings, e, data, final_url)
        except AppError as exc:
            e.status, e.last_error = "failed", f"{exc.error_type}: {exc}"[:1000]
            raise JobFailure(exc.error_type, str(exc), retry=False) from exc
        return {"status": "acquired", "source_id": str(src.id), "bytes": len(data)}
