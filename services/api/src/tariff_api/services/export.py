"""Export one order's pipeline state as JSON files (increment 20).

The operator wants to hand a whole order to an engineer, or keep it in a shared folder
per commission, without pasting screens: this module writes what the API and the page
dump show — the source record, localisation and regions, page dumps for every region
page, candidates with their review state, decisions, summaries, findings and runs — as
plain JSON, either zipped for a browser download or as objects in the export bucket.
Nothing here is a fact: candidates stay proposals and carry their review status.
"""

from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.storage import ObjectNotFound, ObjectStore
from ..config import Settings
from ..models import (
    CandidateRecord,
    CategorySummary,
    ExtractionRun,
    LocalisationRecord,
    LocalisationRegion,
    ReviewDecision,
    SourceDocument,
    StructureCell,
    TableGridRecord,
    ValidatorFindingRecord,
)

EXPORT_VERSION = "1"


def _js(obj: Any) -> bytes:
    return json.dumps(obj, indent=1, sort_keys=True, default=str, ensure_ascii=False).encode()


def export_name(src: SourceDocument) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", src.original_filename.rsplit(".", 1)[0])[:60]
    return f"{stem}-{str(src.id)[:8]}"


def export_prefix(src: SourceDocument) -> str:
    """`<COMMISSION>/<UTILITY>/<name>/` in the export bucket; unknown parts are literal."""
    u = src.utility
    comm = u.commission.code if u is not None and u.commission is not None else "UNASSIGNED"
    util = u.code if u is not None else "UNASSIGNED"
    return f"{comm}/{util}/{export_name(src)}/"


def _rows(session: Session, model, source_id: uuid.UUID, order_by=None) -> list[dict[str, Any]]:
    q = select(model).where(model.source_id == source_id)
    if order_by is not None:
        q = q.order_by(*order_by)
    out = []
    for r in session.execute(q).scalars():
        d = {k: v for k, v in vars(r).items() if not k.startswith("_")}
        out.append(d)
    return out


def build_files(session: Session, storage: ObjectStore, settings: Settings, src: SourceDocument) -> dict[str, bytes]:
    """`{relative path: bytes}` for one order."""
    files: dict[str, bytes] = {}
    files["source.json"] = _js(
        {
            "export_version": EXPORT_VERSION,
            "id": str(src.id),
            "original_filename": src.original_filename,
            "sha256": src.sha256,
            "state": src.state.value,
            "state_reason": src.state_reason,
            "page_count": src.page_count,
            "dataset": src.dataset.kind.value,
            "utility": src.utility.code if src.utility else None,
            "commission": src.utility.commission.code if src.utility and src.utility.commission else None,
            "reading_profile": {
                "id": src.reading_profile_id,
                "version": src.reading_profile_version,
                "source": src.reading_profile_source,
            },
            "assigned_to": src.assigned_to,
            "versions": {
                "triage": src.triage_version,
                "parse": src.parse_version,
                "localisation": src.localisation_version,
                "structure": src.structure_version,
                "extraction": src.extraction_version,
            },
            "heading_inventory": src.heading_inventory,
            "table_summary": src.table_summary,
            "structure_summary": src.structure_summary,
            "extraction_summary": src.extraction_summary,
        }
    )
    loc = session.get(LocalisationRecord, src.id)
    regions = _rows(session, LocalisationRegion, src.id, [LocalisationRegion.ordinal])
    files["localisation.json"] = _js(
        {
            "record": {k: v for k, v in vars(loc).items() if not k.startswith("_")} if loc else None,
            "regions": regions,
        }
    )
    cands = _rows(session, CandidateRecord, src.id, [CandidateRecord.created_at])
    files["candidates.json"] = _js(cands)
    files["decisions.json"] = _js(_rows(session, ReviewDecision, src.id, [ReviewDecision.sequence]))
    files["summaries.json"] = _js(_rows(session, CategorySummary, src.id))
    files["findings.json"] = _js(_rows(session, ValidatorFindingRecord, src.id))
    files["runs.json"] = _js(_rows(session, ExtractionRun, src.id, [ExtractionRun.started_at]))
    # page dumps for every page a region covers: grids as read and the structure cells
    pages: set[int] = set()
    for r in regions:
        if not r.get("excluded"):
            pages.update(range(int(r["page_start"]), int(r["page_end"]) + 1))
    for page in sorted(pages):
        grids = []
        for g in (
            session.execute(
                select(TableGridRecord)
                .where(
                    TableGridRecord.source_id == src.id,
                    TableGridRecord.page_index == page,
                    TableGridRecord.is_primary.is_(True),
                )
                .order_by(TableGridRecord.ordinal)
            )
            .scalars()
            .all()
        ):
            try:
                rows = json.loads(storage.get(ObjectStore.ARTEFACTS, g.object_key))["grid"]["rows"]
            except (ObjectNotFound, KeyError, ValueError):
                rows = None
            grids.append(
                {
                    "ordinal": g.ordinal,
                    "reader": g.reader,
                    "strategy": g.strategy,
                    "header_rows": g.header_rows,
                    "agreement_class": g.agreement_class,
                    "risk_tags": g.risk_tags,
                    "rows": rows,
                }
            )
        cells = [
            {
                "grid": c.grid_ordinal,
                "row": c.row,
                "col": c.col,
                "header_path": c.header_path,
                "row_path": c.row_path,
                "raw": c.raw,
                "value_state": c.value_state,
                "value": (c.normalised or {}).get("value"),
                "flags": c.flags,
                "region_role": c.region_role,
            }
            for c in session.execute(
                select(StructureCell)
                .where(StructureCell.source_id == src.id, StructureCell.page_index == page)
                .order_by(StructureCell.grid_ordinal, StructureCell.row, StructureCell.col)
            ).scalars()
        ]
        if grids or cells:
            files[f"pages/page-{page:04d}.json"] = _js({"page": page, "grids": grids, "cells": cells})
    files["README.txt"] = (
        b"Tariff Order Intelligence export.  Every value in candidates.json is a proposal with its review_status; "
        b"nothing here is a published fact.  pages/ holds each region page's tables as read and the structure cells; "
        b"decisions.json is the audit trail of reviewer decisions.\n"
    )
    return files


def build_zip(session: Session, storage: ObjectStore, settings: Settings, src: SourceDocument) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in build_files(session, storage, settings, src).items():
            z.writestr(f"{export_name(src)}/{path}", data)
    return buf.getvalue()


def write_to_bucket(session: Session, storage: ObjectStore, settings: Settings, src: SourceDocument) -> list[str]:
    """Write the files under `<COMMISSION>/<UTILITY>/<name>/` in the export bucket."""
    prefix = export_prefix(src)
    keys = []
    for path, data in build_files(session, storage, settings, src).items():
        key = prefix + path
        storage.put(ObjectStore.EXPORTS, key, data, "application/json" if path.endswith(".json") else "text/plain")
        keys.append(key)
    return keys
