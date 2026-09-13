"""Stage ``triaged -> parsed`` (Sections 6.3 OCR routing and 6.4 multi-reader consensus).

Per page, in one pass:

* **OCR** where triage recommended it (image-only, vector-drawn, damaged text layer).  The
  result is an artefact with every word's confidence and box.  Where a text layer exists too,
  the agreement between the two is measured and stored; OCR never silently replaces a layer.
* **Table grids** from two independent readers on pages classed ``table`` or ``mixed`` (ruling
  strategy first; the whitespace strategy only when rulings find nothing, because it
  hallucinates tables on prose).  Each grid is an artefact; each pair gets an agreement class
  that decides routing — high agreement proceeds, minority disagreement tags risk, structural
  disagreement goes to a reviewer, a silent empty grid is recorded and never extracted.
  Grids from OCR word boxes are not attempted: an OCR'd table page is listed for review.
* **Headings** from the text layer or, failing that, the OCR text; the document inventory is
  de-duplicated and summarised for localisation (Milestone 3).

Resumable by page batch at the current ``PARSE_VERSION``; artefacts are immutable and keyed by
tool versions.  Nothing here extracts a tariff number.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from tariff_api import headings as H
from tariff_api import ocr as O
from tariff_api.adapters.storage import ObjectNotFound, ObjectStore
from tariff_api.db import session_scope
from tariff_api.inventory import NotAPdf, open_document
from tariff_api.models import (
    DocumentHeading,
    SourceDocument,
    SourcePage,
    SourceState,
    StageArtefact,
    TableGridRecord,
)
from tariff_api.readers import (
    PYMUPDF_VERSION,
    READERS_VERSION,
    GridAgreement,
    TableGrid,
    read_tables_pdfplumber,
    read_tables_pymupdf,
    score_agreement,
)
from tariff_api.services.sources import transition

from ..runner import JobContext, JobFailure

STAGE = "parse"
PARSE_VERSION = "1"
GRID_CLASSES = {"table", "mixed"}


def _tool_version() -> str:
    tess = O.tesseract_version() or "absent"
    import pdfplumber

    return f"pymupdf@{PYMUPDF_VERSION}+pdfplumber@{pdfplumber.__version__}+tesseract@{tess}+rules@{PARSE_VERSION}"


def _key(sha: str, tool_version: str, kind: str, page_index: int, suffix: str = "") -> str:
    name = f"page-{page_index:04d}{suffix}.json" if page_index else "document.json"
    return f"{sha}/{STAGE}/{tool_version}/{kind}/{name}"


def _artefact(session, storage: ObjectStore, *, source_id, sha, tool_version, key, page_index, payload) -> str:
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    storage.put(ObjectStore.ARTEFACTS, key, body, "application/json")
    session.execute(
        insert(StageArtefact)
        .values(
            id=uuid.uuid4(),
            source_id=source_id,
            stage=STAGE,
            tool=key.split("/")[3],
            tool_version=tool_version,
            page_index=page_index,
            object_key=key,
            content_sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
        )
        .on_conflict_do_nothing(constraint="uq_stage_artefact")
    )
    return key


def parse_source(ctx: JobContext) -> dict:
    source_id = uuid.UUID(ctx.payload["source_id"])
    storage: ObjectStore = ctx.adapters.storage
    settings = ctx.settings
    tool_version = _tool_version()

    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        if src is None:
            raise JobFailure("not_found", f"source {source_id} no longer exists", retry=False)
        if src.state == SourceState.parsed and src.parse_version == PARSE_VERSION:
            return {"skipped": "already_parsed"}
        if src.state not in (SourceState.triaged, SourceState.parsed, SourceState.needs_reprocessing):
            raise JobFailure(
                "invalid_transition", f"source in state {src.state.value}; parse needs triaged", retry=False
            )
        if src.triage_version is None or src.page_count is None:
            raise JobFailure("invalid_transition", "source has not been triaged", retry=False)
        object_key, sha, total = src.object_key, src.sha256, src.page_count
        plan = {
            r.page_index: (r.page_class, bool(r.ocr_recommended), bool(r.has_text_layer))
            for r in s.execute(select(SourcePage).where(SourcePage.source_id == source_id)).scalars()
        }
        done = {
            r.page_index
            for r in s.execute(
                select(SourcePage.page_index).where(
                    SourcePage.source_id == source_id, SourcePage.parse_version == PARSE_VERSION
                )
            )
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

    needs_ocr = any(p[1] for p in plan.values())
    if needs_ocr and O.tesseract_version() is None:
        raise JobFailure(
            "provider_unavailable",
            "OCR was recommended for at least one page but tesseract is not installed",
            retry=True,
        )

    if not ctx.checkpoint:
        ctx.save_checkpoint(STAGE, {"next_page": 1}, {"pages_done": 0, "pages_total": total})
    page = int(ctx.checkpoint.get("next_page", 1))
    batch = max(1, settings.inventory_checkpoint_every_pages)

    while page <= total:
        end = min(page + batch, total + 1)
        with session_scope() as s:
            for idx in range(page, end):
                if idx in done:
                    continue
                page_class, ocr_wanted, has_layer = plan.get(idx, ("unknown", False, False))
                pm_page = doc[idx - 1]
                layer_text = pm_page.get_text("text") or ""
                row = s.execute(
                    select(SourcePage).where(SourcePage.source_id == source_id, SourcePage.page_index == idx)
                ).scalar_one()
                flags = list(row.quality_flags or [])

                # ---- OCR
                heading_text, heading_source = layer_text, "text_layer"
                if ocr_wanted:
                    try:
                        res = O.ocr_page(
                            pm_page,
                            lang=settings.ocr_lang,
                            dpi=settings.ocr_dpi,
                            psm=settings.ocr_psm,
                            min_confidence=settings.ocr_min_confidence,
                        )
                    except O.OcrUnavailable as e:
                        raise JobFailure("provider_unavailable", str(e), retry=True) from e
                    _artefact(
                        s,
                        storage,
                        source_id=source_id,
                        sha=sha,
                        tool_version=tool_version,
                        key=_key(sha, tool_version, "ocr", idx),
                        page_index=idx,
                        payload={"page_index": idx, **res.to_dict()},
                    )
                    row.ocr_used = True
                    row.ocr_engine = f"{res.engine}@{res.engine_version}"
                    row.ocr_confidence = res.mean_confidence
                    row.ocr_word_count = res.word_count
                    row.ocr_text_chars = len("".join(res.text.split()))
                    if res.low_confidence:
                        flags.append("ocr_low_confidence")
                    if res.word_count == 0:
                        flags.append("ocr_no_text")
                    if has_layer and layer_text.strip():
                        row.ocr_agreement = O.text_agreement(layer_text, res.text)
                        if row.ocr_agreement < 0.5:
                            flags.append("ocr_layer_disagreement")
                    elif res.word_count:
                        heading_text, heading_source = res.text, "ocr"
                    if page_class in GRID_CLASSES or (not has_layer and res.word_count):
                        flags.append("grid_from_ocr_pending")  # honest: no grids from OCR boxes yet

                # ---- table grids from two readers (text-layer pages only)
                if page_class in GRID_CLASSES and has_layer:
                    strategy = "lines"
                    prim = read_tables_pymupdf(pm_page, idx, "lines")
                    sec = read_tables_pdfplumber(data, idx, "lines")
                    if not prim and not sec:
                        strategy = "text"
                        prim = read_tables_pymupdf(pm_page, idx, "text")
                        sec = read_tables_pdfplumber(data, idx, "text")
                    agreements = score_agreement(prim, sec)
                    _store_grids(s, storage, source_id, sha, tool_version, idx, prim, sec, agreements, strategy)
                    for a in agreements:
                        for tag in a.risk_tags:
                            if tag not in flags:
                                flags.append(tag)

                # ---- headings
                found = H.dedupe_consecutive(H.scan_headings(idx, heading_text))
                for h in found:
                    s.execute(
                        insert(DocumentHeading)
                        .values(
                            id=uuid.uuid4(),
                            source_id=source_id,
                            page_index=h.page_index,
                            line_no=h.line_no,
                            ordinal=0,  # assigned document-wide below
                            kind=h.kind,
                            code_raw=h.code_raw,
                            code_canonical=h.code_canonical,
                            text=h.text[:200],
                            text_source=heading_source,
                            rules_version=H.HEADINGS_VERSION,
                        )
                        .on_conflict_do_nothing(constraint="uq_document_heading")
                    )

                row.quality_flags = sorted(set(flags))
                row.parse_version = PARSE_VERSION
                row.parsed_at = datetime.now(UTC)
        page = end
        ctx.save_checkpoint(STAGE, {"next_page": page}, {"pages_done": page - 1, "pages_total": total})

    doc.close()

    # ---- document-wide summary
    with session_scope() as s:
        heads = (
            s.execute(
                select(DocumentHeading)
                .where(DocumentHeading.source_id == source_id, DocumentHeading.rules_version == H.HEADINGS_VERSION)
                .order_by(DocumentHeading.page_index, DocumentHeading.line_no)
            )
            .scalars()
            .all()
        )
        for i, h in enumerate(heads, start=1):
            h.ordinal = i
        inv = H.inventory(
            [H.Heading(h.page_index, h.line_no, h.kind, h.code_raw, h.code_canonical, h.text) for h in heads]
        )
        grids = s.execute(select(TableGridRecord).where(TableGridRecord.source_id == source_id)).scalars().all()
        primary = [g for g in grids if g.is_primary]
        classes = Counter(g.agreement_class for g in grids if g.agreement_class)
        pages_rows = s.execute(select(SourcePage).where(SourcePage.source_id == source_id)).scalars().all()
        table_summary = {
            "tool_version": tool_version,
            "grid_pages": sorted({g.page_index for g in grids}),
            "primary_grids": len(primary),
            "agreement_classes": dict(classes),
            "pages_needing_review": sorted(
                {
                    g.page_index
                    for g in grids
                    if g.agreement_class in ("structure_disagreement", "primary_missing", "secondary_missing")
                }
            ),
            "ocr_pages": sorted(r.page_index for r in pages_rows if r.ocr_used),
            "ocr_low_confidence_pages": sorted(
                r.page_index for r in pages_rows if "ocr_low_confidence" in (r.quality_flags or [])
            ),
            "grid_from_ocr_pending_pages": sorted(
                r.page_index for r in pages_rows if "grid_from_ocr_pending" in (r.quality_flags or [])
            ),
        }
        src = s.get(SourceDocument, source_id)
        src.heading_inventory = inv
        src.table_summary = table_summary
        src.parse_version = PARSE_VERSION
        src.parsed_at = datetime.now(UTC)
        _artefact(
            s,
            storage,
            source_id=source_id,
            sha=sha,
            tool_version=tool_version,
            key=_key(sha, tool_version, "summary", 0),
            page_index=0,
            payload={
                "heading_inventory": inv,
                "table_summary": table_summary,
                "headings": [
                    {"page_index": h.page_index, "kind": h.kind, "code": h.code_canonical, "text": h.text}
                    for h in heads
                ],
            },
        )
        if src.state != SourceState.parsed:
            transition(s, src, SourceState.parsed, actor=ctx.worker, reason=tool_version)
    return {
        "pages_total": total,
        "headings": inv["counts"],
        "primary_grids": table_summary["primary_grids"],
        "agreement_classes": table_summary["agreement_classes"],
        "ocr_pages": len(table_summary["ocr_pages"]),
    }


def _store_grids(
    s,
    storage: ObjectStore,
    source_id: uuid.UUID,
    sha: str,
    tool_version: str,
    page_index: int,
    prim: list[TableGrid],
    sec: list[TableGrid],
    agreements: list[GridAgreement],
    strategy: str,
) -> None:
    by_primary = {a.primary_ordinal: a for a in agreements if a.primary_ordinal is not None}
    by_secondary = {a.secondary_ordinal: a for a in agreements if a.secondary_ordinal is not None}
    # A re-run at this version replaces this page's grid rows (artefacts stay immutable).
    s.execute(
        delete(TableGridRecord).where(TableGridRecord.source_id == source_id, TableGridRecord.page_index == page_index)
    )
    for is_primary, grids, lookup in ((True, prim, by_primary), (False, sec, by_secondary)):
        for g in grids:
            a = lookup.get(g.ordinal)
            key = _key(sha, tool_version, f"grid-{g.reader}", page_index, f"-{g.ordinal}")
            _artefact(
                s,
                storage,
                source_id=source_id,
                sha=sha,
                tool_version=tool_version,
                key=key,
                page_index=page_index,
                payload={
                    "grid": g.to_dict(),
                    "agreement": a.to_dict() if a else None,
                    "readers_version": READERS_VERSION,
                },
            )
            s.add(
                TableGridRecord(
                    source_id=source_id,
                    page_index=page_index,
                    reader=g.reader,
                    reader_version=g.reader_version,
                    ordinal=g.ordinal,
                    strategy=strategy,
                    bbox=list(g.bbox),
                    row_count=g.row_count,
                    col_count=g.col_count,
                    header_rows=g.header_rows,
                    is_empty=g.is_empty,
                    is_primary=is_primary,
                    agreement_class=a.classification if a else None,
                    agreement_score=a.score if a else None,
                    paired_ordinal=(a.secondary_ordinal if is_primary else a.primary_ordinal) if a else None,
                    disagreeing_cells=len(a.disagreeing_cells) if a else 0,
                    risk_tags=a.risk_tags if a else [],
                    object_key=key,
                )
            )
