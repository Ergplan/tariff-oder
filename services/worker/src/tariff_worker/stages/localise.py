"""Stage ``parsed -> localised`` (Section 6.5): bind a reading profile, run the localisation
rules over the parsed document, store the classified regions with their cues, and open the
reviewer checkpoint.  The stage never confirms anything: the record it writes is ``proposed``
or ``ambiguous``; only a reviewer's decision sets ``extraction_allowed``.

Inputs per page: the text layer in reading order (or the OCR artefact text where the page was
OCR'd), the triage class, the parse stage's headings and grid count.  Output: one immutable
artefact ``<sha>/localise/rules@<v>+profile@<ref>/document.json`` and the current region rows.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tariff_api.adapters.storage import ObjectNotFound, ObjectStore
from tariff_api.db import session_scope
from tariff_api.inventory import NotAPdf, open_document
from tariff_api.localisation import LOCALISATION_VERSION, PageInfo, localise
from tariff_api.models import (
    DocumentHeading,
    LocalisationRecord,
    LocalisationRegion,
    SourceDocument,
    SourcePage,
    SourceState,
    StageArtefact,
    TableGridRecord,
)
from tariff_api.profiles import detect_profile, latest_version, load_profile
from tariff_api.services.sources import transition

from ..runner import JobContext, JobFailure

STAGE = "localise"


def _ocr_texts(s, storage: ObjectStore, source_id: uuid.UUID) -> dict[int, str]:
    """Text of the OCR artefacts the parse stage wrote, by page index (latest tool version)."""
    rows = (
        s.execute(
            select(StageArtefact)
            .where(StageArtefact.source_id == source_id, StageArtefact.stage == "parse", StageArtefact.tool == "ocr")
            .order_by(StageArtefact.tool_version, StageArtefact.page_index)
        )
        .scalars()
        .all()
    )
    out: dict[int, str] = {}
    for a in rows:
        try:
            body = json.loads(storage.get(ObjectStore.ARTEFACTS, a.object_key))
        except (ObjectNotFound, ValueError):
            continue
        out[a.page_index] = body.get("text", "")
    return out


def localise_source(ctx: JobContext) -> dict:
    source_id = uuid.UUID(ctx.payload["source_id"])
    storage: ObjectStore = ctx.adapters.storage

    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        if src is None:
            raise JobFailure("not_found", f"source {source_id} no longer exists", retry=False)
        if src.state not in (SourceState.parsed, SourceState.localised, SourceState.needs_reprocessing):
            raise JobFailure(
                "invalid_transition", f"source in state {src.state.value}; localise needs parsed", retry=False
            )
        if src.parse_version is None or src.page_count is None:
            raise JobFailure("invalid_transition", "source has not been parsed", retry=False)
        rec = s.get(LocalisationRecord, source_id)
        if (
            src.state == SourceState.localised
            and rec is not None
            and rec.rules_version == LOCALISATION_VERSION
            and rec.profile_ref == f"{src.reading_profile_id}@{src.reading_profile_version}"
        ):
            return {"skipped": "already_localised", "status": rec.status}

        # 1. profile: assigned by an administrator, else detected from the heading inventory
        if src.reading_profile_id is None:
            counts = (src.heading_inventory or {}).get("counts", {})
            pid, why = detect_profile(counts)
            if pid is None:
                total = src.page_count
                ctx.save_checkpoint("localise", {"pages_read": 0}, {"pages_done": total, "pages_total": total})
                _write_record(
                    s,
                    src,
                    status="ambiguous",
                    profile_ref="none",
                    findings=[
                        {
                            "code": "no_reading_profile",
                            "severity": "blocking",
                            "message": f"no reading profile detected ({why}); an administrator must assign one",
                            "pages": [],
                        }
                    ],
                    regions=[],
                    artefact_key=None,
                )
                if src.state != SourceState.localised:
                    transition(s, src, SourceState.localised, actor=ctx.worker, reason="no reading profile")
                return {"status": "ambiguous", "profile": None}
            src.reading_profile_id = pid
            src.reading_profile_version = latest_version(pid)
            src.reading_profile_source = "detected"
            src.reading_profile_rationale = why
        profile = load_profile(src.reading_profile_id, src.reading_profile_version)
        object_key, sha, total = src.object_key, src.sha256, src.page_count
        page_rows = {
            r.page_index: r for r in s.execute(select(SourcePage).where(SourcePage.source_id == source_id)).scalars()
        }
        headings: dict[int, list[tuple[str, str | None]]] = {}
        for h in s.execute(
            select(DocumentHeading).where(DocumentHeading.source_id == source_id).order_by(DocumentHeading.ordinal)
        ).scalars():
            headings.setdefault(h.page_index, []).append((h.kind, h.code_canonical))
        grid_counts = dict(
            s.execute(
                select(TableGridRecord.page_index, func.count())
                .where(TableGridRecord.source_id == source_id, TableGridRecord.is_primary.is_(True))
                .group_by(TableGridRecord.page_index)
            ).all()
        )
        ocr_text = _ocr_texts(s, storage, source_id)

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

    pages: list[PageInfo] = []
    for idx in range(1, total + 1):
        row = page_rows.get(idx)
        layer = doc[idx - 1].get_text("text", sort=True) if row is None or row.has_text_layer else ""
        if layer.strip():
            text, source = layer, "text_layer"
        elif idx in ocr_text and ocr_text[idx].strip():
            text, source = ocr_text[idx], "ocr"
        else:
            text, source = "", "none"
        pages.append(
            PageInfo(
                page_index=idx,
                printed_label=row.printed_label if row else None,
                page_class=row.page_class if row and row.page_class else "unknown",
                text=text,
                text_source=source,
                headings=headings.get(idx, []),
                grid_count=int(grid_counts.get(idx, 0)),
            )
        )
        if idx % 25 == 0 or idx == total:
            ctx.save_checkpoint("localise", {"pages_read": idx}, {"pages_done": idx, "pages_total": total})
    result = localise(profile, pages)

    tool_version = f"rules@{LOCALISATION_VERSION}+profile@{profile.ref}"
    key = f"{sha}/{STAGE}/{tool_version}/document.json"
    payload = {
        "profile": {"id": profile.id, "version": profile.version},
        "page_text_sources": {p.page_index: p.text_source for p in pages},
        **result.to_dict(),
    }
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    storage.put(ObjectStore.ARTEFACTS, key, body, "application/json")

    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        s.execute(
            pg_insert(StageArtefact)
            .values(
                id=uuid.uuid4(),
                source_id=source_id,
                stage=STAGE,
                tool="rules",
                tool_version=tool_version,
                page_index=0,
                object_key=key,
                content_sha256=hashlib.sha256(body).hexdigest(),
                size_bytes=len(body),
            )
            .on_conflict_do_nothing(constraint="uq_stage_artefact")
        )
        regions = []
        for r in result.regions:
            d = r.to_dict()
            d["grid_count"] = sum(int(grid_counts.get(i, 0)) for i in range(r.page_start, r.page_end + 1))
            regions.append(d)
        _write_record(
            s,
            src,
            status=result.status,
            profile_ref=profile.ref,
            findings=[f.to_dict() for f in result.findings],
            regions=regions,
            artefact_key=key,
        )
        src.localisation_version = LOCALISATION_VERSION
        src.localised_at = datetime.now(UTC)
        if src.state != SourceState.localised:
            transition(s, src, SourceState.localised, actor=ctx.worker, reason=tool_version)
    return {
        "status": result.status,
        "profile": profile.ref,
        "regions": len(result.regions),
        "blocking_findings": sum(1 for f in result.findings if f.severity == "blocking"),
    }


def _write_record(s, src: SourceDocument, *, status, profile_ref, findings, regions, artefact_key) -> None:
    """Replace the current record and regions with the rules' output.  A reviewer's earlier
    decision does not survive a re-run: the pages may have been re-read with new rules or a
    new profile, so the checkpoint is opened again (visible in decision_count and the audit)."""
    s.execute(delete(LocalisationRegion).where(LocalisationRegion.source_id == src.id))
    rec = s.get(LocalisationRecord, src.id)
    if rec is None:
        rec = LocalisationRecord(
            source_id=src.id,
            status=status,
            rules_version=LOCALISATION_VERSION,
            profile_ref=profile_ref,
            findings=[],
            decision_count=0,
            version=0,
        )
        s.add(rec)
    rec.status = status
    rec.rules_version = LOCALISATION_VERSION
    rec.profile_ref = profile_ref
    rec.findings = findings
    rec.extraction_allowed = False
    rec.decided_by = None
    rec.decided_at = None
    rec.decision_rationale = None
    rec.artefact_key = artefact_key
    rec.version = (rec.version or 0) + 1  # a new row has no Python-side default until flush
    s.flush()
    for i, r in enumerate(regions, start=1):
        s.add(
            LocalisationRegion(
                source_id=src.id,
                ordinal=i,
                role=r["role"],
                sub_role=r.get("sub_role"),
                page_start=r["page_start"],
                page_end=r["page_end"],
                cue_text=r["cue_text"][:300],
                cue_page=r["cue_page"],
                cue_kind=r["cue_kind"],
                utility=r.get("utility"),
                period=r.get("period"),
                note=r.get("note"),
                origin=r.get("origin", "detected"),
                grid_count=r.get("grid_count", 0),
            )
        )
