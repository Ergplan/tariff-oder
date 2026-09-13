"""Stage ``inventoried -> triaged`` (Section 6.3).

For every page: extract signals, classify, score the text layer, read the printed label, and
write an immutable per-page artefact.  Then, document-wide: infer the printed-label rule,
resolve every page's label against it, write the document artefact, and record the class
histogram.  Nothing here extracts a number.

Resumable: the checkpoint carries ``next_page``; pages already triaged at this
``TRIAGE_VERSION`` are skipped on resume, and artefact writes are no-ops when the object
already exists.  A tool-version change produces new artefacts beside the old ones — it never
overwrites — and re-triages every page.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from tariff_api.adapters.storage import ObjectNotFound, ObjectStore
from tariff_api.db import session_scope
from tariff_api.inventory import NotAPdf, open_document
from tariff_api.models import SourceDocument, SourcePage, SourceState, StageArtefact
from tariff_api.page_signals import TOOL_NAME, TOOL_VERSION, extract_signals
from tariff_api.services.sources import transition
from tariff_api.triage import (
    TRIAGE_VERSION,
    ObservedLabel,
    classify_page,
    extract_label,
    infer_label_rule,
    resolve_label,
)

from ..runner import JobContext, JobFailure

STAGE = "triage"
STAGE_TOOL_VERSION = f"{TOOL_NAME}@{TOOL_VERSION}+rules@{TRIAGE_VERSION}"


def _artefact_key(sha256: str, page_index: int) -> str:
    name = f"page-{page_index:04d}.json" if page_index else "document.json"
    return f"{sha256}/{STAGE}/{STAGE_TOOL_VERSION}/{name}"


def _write_artefact(
    session, storage: ObjectStore, *, source_id: uuid.UUID, sha256: str, page_index: int, payload: dict[str, Any]
) -> None:
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    key = _artefact_key(sha256, page_index)
    storage.put(ObjectStore.ARTEFACTS, key, body, "application/json")
    session.execute(
        insert(StageArtefact)
        .values(
            id=uuid.uuid4(),
            source_id=source_id,
            stage=STAGE,
            tool=TOOL_NAME,
            tool_version=STAGE_TOOL_VERSION,
            page_index=page_index,
            object_key=key,
            content_sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
        )
        .on_conflict_do_nothing(constraint="uq_stage_artefact")
    )


def triage_source(ctx: JobContext) -> dict:
    source_id = uuid.UUID(ctx.payload["source_id"])
    storage: ObjectStore = ctx.adapters.storage
    settings = ctx.settings

    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        if src is None:
            raise JobFailure("not_found", f"source {source_id} no longer exists", retry=False)
        if src.state == SourceState.triaged and src.triage_version == TRIAGE_VERSION:
            return {"skipped": "already_triaged"}
        if src.state not in (SourceState.inventoried, SourceState.triaged, SourceState.needs_reprocessing):
            raise JobFailure(
                "invalid_transition", f"source in state {src.state.value}; triage needs inventoried", retry=False
            )
        if src.page_count is None:
            raise JobFailure("invalid_transition", "source has no inventory", retry=False)
        object_key, sha, total = src.object_key, src.sha256, src.page_count
        already = {
            row.page_index
            for row in s.execute(
                select(SourcePage.page_index).where(
                    SourcePage.source_id == source_id, SourcePage.triage_version == TRIAGE_VERSION
                )
            ).all()
        }

    try:
        data = storage.get(ObjectStore.SOURCES, object_key)
    except ObjectNotFound as e:
        raise JobFailure("storage_unavailable", f"object {object_key} missing", retry=True) from e
    if hashlib.sha256(data).hexdigest() != sha:
        raise JobFailure("source_unreadable", "stored bytes do not match the registered hash", retry=False)
    try:
        doc = open_document(data)
    except NotAPdf as e:
        raise JobFailure("source_unreadable", str(e), retry=False) from e
    if doc.page_count != total:
        raise JobFailure(
            "validation_failed", f"inventory says {total} pages, document has {doc.page_count}", retry=False
        )

    if not ctx.checkpoint:
        ctx.save_checkpoint(STAGE, {"next_page": 1}, {"pages_done": 0, "pages_total": total})
    page = int(ctx.checkpoint.get("next_page", 1))
    batch = max(1, settings.inventory_checkpoint_every_pages)

    while page <= total:
        end = min(page + batch, total + 1)
        with session_scope() as s:
            for idx in range(page, end):
                if idx in already:
                    continue
                sig = extract_signals(doc[idx - 1])
                result = classify_page(sig)
                observed = extract_label(sig.text)
                declared = doc[idx - 1].get_label() or None
                payload = {
                    "page_index": idx,
                    "signals": {k: v for k, v in sig.__dict__.items() if k not in ("text", "quality")},
                    "text_quality": sig.quality.to_dict() if sig.quality else None,
                    "triage": result.to_dict(),
                    "label_declared": declared,
                    "label_observed": observed.value if observed else None,
                    "tool": TOOL_NAME,
                    "tool_version": TOOL_VERSION,
                    "rules_version": TRIAGE_VERSION,
                }
                _write_artefact(s, storage, source_id=source_id, sha256=sha, page_index=idx, payload=payload)
                row = s.execute(
                    select(SourcePage).where(SourcePage.source_id == source_id, SourcePage.page_index == idx)
                ).scalar_one()
                row.page_class = result.page_class
                row.quality_flags = result.quality_flags
                row.ocr_recommended = result.ocr_recommended
                row.triage_rationale = result.rationale
                row.text_quality = sig.quality.to_dict() if sig.quality else None
                row.label_declared = declared
                row.label_observed = observed.value if observed else None
                row.triage_version = TRIAGE_VERSION
                row.triaged_at = datetime.now(UTC)
        page = end
        ctx.save_checkpoint(STAGE, {"next_page": page}, {"pages_done": page - 1, "pages_total": total})

    doc.close()

    # Document-wide: the printed-label rule, resolution of every page, class histogram.
    with session_scope() as s:
        rows = (
            s.execute(select(SourcePage).where(SourcePage.source_id == source_id).order_by(SourcePage.page_index))
            .scalars()
            .all()
        )
        observations: list[ObservedLabel] = []
        for r in rows:
            if r.label_observed:
                obs = extract_label(r.label_observed)  # re-parse the stored value into number/style
                if obs:
                    obs.page_index = r.page_index
                    observations.append(obs)
        segments = infer_label_rule(observations, total)
        conflicts = 0
        for r in rows:
            obs = next((o for o in observations if o.page_index == r.page_index), None)
            label, source, flags = resolve_label(r.page_index, r.label_declared, obs, segments)
            r.printed_label = label
            r.label_source = source
            if flags:
                r.quality_flags = sorted(set(list(r.quality_flags or []) + flags))
                conflicts += 1
        counts = Counter(r.page_class for r in rows)
        rule = {
            "segments": [seg.to_dict() for seg in segments],
            "observed_pages": len(observations),
            "declared_pages": sum(1 for r in rows if r.label_declared),
            "pages_with_label_flags": conflicts,
            "rules_version": TRIAGE_VERSION,
        }
        src = s.get(SourceDocument, source_id)
        src.label_rule = rule
        src.page_class_counts = dict(counts)
        src.triage_version = TRIAGE_VERSION
        src.triaged_at = datetime.now(UTC)
        _write_artefact(
            s,
            storage,
            source_id=source_id,
            sha256=sha,
            page_index=0,
            payload={"label_rule": rule, "page_class_counts": dict(counts), "pages": total},
        )
        if src.state != SourceState.triaged:
            transition(s, src, SourceState.triaged, actor=ctx.worker, reason=STAGE_TOOL_VERSION)
        summary = {
            "pages_total": total,
            "page_class_counts": dict(counts),
            "ocr_recommended_pages": sum(1 for r in rows if r.ocr_recommended),
            "label_segments": len(segments),
            "pages_with_label_flags": conflicts,
        }
    return summary
