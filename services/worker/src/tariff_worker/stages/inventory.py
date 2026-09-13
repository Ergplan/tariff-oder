"""Stage ``uploaded -> inventoried``: per-page text-layer inventory with page checkpoints.

Resumable: the checkpoint stores ``next_page`` (1-based); completed pages are upserted with
``ON CONFLICT DO NOTHING`` so a retry after a worker death never duplicates rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from tariff_api import golden
from tariff_api.adapters.storage import ObjectNotFound, ObjectStore
from tariff_api.db import session_scope
from tariff_api.inventory import (
    TOOL_NAME,
    TOOL_VERSION,
    NotAPdf,
    document_inventory,
    open_document,
    page_inventory,
)
from tariff_api.models import SourceDocument, SourcePage, SourceState
from tariff_api.services.sources import transition

from ..runner import JobContext, JobFailure

STAGE = "inventory"


def inventory_source(ctx: JobContext) -> dict:
    source_id = uuid.UUID(ctx.payload["source_id"])
    expected_sha = ctx.payload.get("sha256")
    storage: ObjectStore = ctx.adapters.storage
    settings = ctx.settings

    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        if src is None:
            raise JobFailure("not_found", f"source {source_id} no longer exists", retry=False)
        if src.state not in (SourceState.uploaded, SourceState.needs_reprocessing):
            if src.state == SourceState.inventoried:
                return {"skipped": "already_inventoried"}
            raise JobFailure("invalid_transition", f"source in state {src.state.value}", retry=False)
        object_key, sha = src.object_key, src.sha256
    if expected_sha and expected_sha != sha:
        raise JobFailure("validation_failed", "payload hash does not match the registered source", retry=False)

    try:
        data = storage.get(ObjectStore.SOURCES, object_key)
    except ObjectNotFound as e:
        raise JobFailure("storage_unavailable", f"object {object_key} missing", retry=True) from e

    import hashlib

    if hashlib.sha256(data).hexdigest() != sha:
        raise JobFailure("source_unreadable", "stored bytes do not match the registered hash", retry=False)

    try:
        doc = open_document(data)
    except NotAPdf as e:
        with session_scope() as s:
            src = s.get(SourceDocument, source_id)
            transition(s, src, SourceState.failed, actor=ctx.worker, reason=f"source_unreadable: {e}")
        raise JobFailure("source_unreadable", str(e), retry=False) from e

    if doc.page_count > settings.max_pages_per_job:
        with session_scope() as s:
            src = s.get(SourceDocument, source_id)
            transition(s, src, SourceState.failed, actor=ctx.worker, reason="page_limit_exceeded")
        raise JobFailure("page_limit_exceeded", f"{doc.page_count} pages > {settings.max_pages_per_job}", retry=False)

    next_page = int(ctx.checkpoint.get("next_page", 1))
    total = doc.page_count
    if not ctx.checkpoint:
        info = document_inventory(doc)
        with session_scope() as s:
            src = s.get(SourceDocument, source_id)
            src.page_count = info.page_count
            src.pdf_version = info.pdf_version
            src.producer = info.producer
            src.creator = info.creator
            src.is_encrypted = info.is_encrypted
            src.is_tagged = info.is_tagged
            src.fonts_total = info.fonts_total
            src.fonts_not_embedded = info.fonts_not_embedded
            src.inventory_tool = TOOL_NAME
            src.inventory_tool_version = str(TOOL_VERSION)
        ctx.save_checkpoint(
            STAGE, {"next_page": 1, "document_inventory_done": True}, {"pages_done": 0, "pages_total": total}
        )

    batch = max(1, settings.inventory_checkpoint_every_pages)
    page = next_page
    while page <= total:
        rows = []
        for idx in range(page, min(page + batch, total + 1)):
            pi = page_inventory(doc, idx - 1)
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "source_id": source_id,
                    "page_index": pi.page_index,
                    "printed_label": pi.printed_label,
                    "width_pt": pi.width_pt,
                    "height_pt": pi.height_pt,
                    "rotation": pi.rotation,
                    "text_chars": pi.text_chars,
                    "has_text_layer": pi.has_text_layer,
                    "image_count": pi.image_count,
                    "drawing_count": pi.drawing_count,
                }
            )
        with session_scope() as s:
            s.execute(insert(SourcePage).values(rows).on_conflict_do_nothing(constraint="uq_source_page"))
        page = rows[-1]["page_index"] + 1
        ctx.save_checkpoint(
            STAGE, {"next_page": page, "document_inventory_done": True}, {"pages_done": page - 1, "pages_total": total}
        )

    doc.close()
    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        with_text = s.execute(
            select(func.count()).where(SourcePage.source_id == source_id, SourcePage.has_text_layer.is_(True))
        ).scalar_one()
        stored = s.execute(select(func.count()).where(SourcePage.source_id == source_id)).scalar_one()
        if stored != total:
            raise JobFailure("internal_error", f"stored {stored} page rows for {total} pages", retry=True)
        src.pages_with_text = int(with_text)
        src.pages_without_text = total - int(with_text)
        src.inventoried_at = datetime.now(UTC)
        if src.golden_id:
            entry = golden.find_by_sha256(settings.golden_manifest_path, sha)
            if entry:
                src.manifest_check = golden.compare_inventory(
                    entry,
                    {"size_bytes": src.size_bytes, "page_count": total, "pages_without_text": src.pages_without_text},
                )
        transition(s, src, SourceState.inventoried, actor=ctx.worker, reason=f"{TOOL_NAME}@{TOOL_VERSION}")
    return {"pages_total": total, "pages_with_text": int(with_text), "pages_without_text": total - int(with_text)}
