"""Stage ``localised -> gridded`` (Section 6.6): build the structural representations that
extraction will read — table grids with header paths, row paths, unit bindings and flags, and
clause outlines with clause paths, roles and units — from the regions a reviewer confirmed.

Gate: the stage refuses to run while the localisation record's ``extraction_allowed`` is
false.  Only ``approved_schedule`` and ``approved_summary`` regions are read; every other
region is listed as skipped so a reviewer sees what was not gridded.  Every numeric cell
either resolves (header path + row path + unit) or is flagged and listed; nothing is defaulted.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tariff_api.adapters.storage import ObjectNotFound, ObjectStore
from tariff_api.clause_outline import CLAUSE_VERSION, reconstruct
from tariff_api.clause_outline import summarise as summarise_clauses
from tariff_api.db import session_scope
from tariff_api.grid_integrity import GRID_VERSION, GridInput, analyse_grids
from tariff_api.grid_integrity import summarise as summarise_grids
from tariff_api.inventory import NotAPdf, open_document
from tariff_api.models import (
    ClauseValueRecord,
    LocalisationRecord,
    LocalisationRegion,
    SourceDocument,
    SourceState,
    StageArtefact,
    StructureCell,
    TableGridRecord,
)
from tariff_api.normalise import NORMALISE_VERSION
from tariff_api.profiles import load_profile
from tariff_api.services.sources import enqueue_stage, transition

from ..runner import JobContext, JobFailure

STAGE = "grid"
# Regions whose grids become structure: the approved representations (extraction input) and
# the network-charge, loss-trajectory, green-tariff and amendment regions (network facts,
# derivation inputs and the amendment-consistency validator).  Existing/proposed/illustrative
# tables are never gridded: nothing from them may become a candidate.
READ_ROLES = (
    "approved_schedule",
    "approved_summary",
    "network_charges",
    "loss_trajectory",
    "green_tariff",
    "amendment_diff",
)


def _tool_version() -> str:
    return f"grid@{GRID_VERSION}+clauses@{CLAUSE_VERSION}+normalise@{NORMALISE_VERSION}"


def _lines_around(page, bbox: list[float]) -> tuple[list[str], list[str]]:
    """Text blocks above (title/caption) and below (footnotes) a grid on its page."""
    x0, y0, x1, y1 = bbox
    above: list[str] = []
    below: list[str] = []
    for b in page.get_text("blocks", sort=True):
        by0, by1, text = b[1], b[3], b[4]
        for ln in str(text).splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if by1 <= y0 + 2 and y0 - by1 < 160:
                above.append(ln)
            elif by0 >= y1 - 2 and by0 - y1 < 200:
                below.append(ln)
    return above[-6:], below[:12]


def grid_source(ctx: JobContext) -> dict:
    source_id = uuid.UUID(ctx.payload["source_id"])
    storage: ObjectStore = ctx.adapters.storage
    tool_version = _tool_version()

    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        if src is None:
            raise JobFailure("not_found", f"source {source_id} no longer exists", retry=False)
        if src.state not in (SourceState.localised, SourceState.gridded, SourceState.needs_reprocessing):
            raise JobFailure(
                "invalid_transition", f"source in state {src.state.value}; grid needs localised", retry=False
            )
        rec = s.get(LocalisationRecord, source_id)
        if rec is None or not rec.extraction_allowed:
            raise JobFailure(
                "invalid_transition",
                "localisation has not been confirmed by a reviewer; structure is built only from confirmed regions",
                retry=False,
            )
        if src.state == SourceState.gridded and src.structure_version == tool_version:
            return {"skipped": "already_gridded"}
        profile = load_profile(src.reading_profile_id, src.reading_profile_version)
        regions = [
            {
                "role": r.role,
                "page_start": r.page_start,
                "page_end": r.page_end,
                "ordinal": r.ordinal,
                "excluded": r.excluded,
                "reviewer_note": r.reviewer_note,
            }
            for r in s.execute(
                select(LocalisationRegion)
                .where(LocalisationRegion.source_id == source_id)
                .order_by(LocalisationRegion.ordinal)
            ).scalars()
        ]
        grid_rows = {
            (g.page_index, g.ordinal): g.object_key
            for g in s.execute(
                select(TableGridRecord).where(
                    TableGridRecord.source_id == source_id, TableGridRecord.is_primary.is_(True)
                )
            ).scalars()
        }
        object_key, sha = src.object_key, src.sha256

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

    representation = profile.schedule_representation
    cells_out: list[dict[str, Any]] = []
    clauses_out: list[dict[str, Any]] = []
    grid_summaries: list[dict[str, Any]] = []
    region_reports: list[dict[str, Any]] = []
    artefacts: list[tuple[str, dict[str, Any]]] = []
    seen_grids: set[tuple[int, int]] = set()  # regions may overlap on a page: each grid is read once
    for reg in regions:
        if reg["excluded"]:
            region_reports.append(
                {**reg, "status": "skipped", "reason": f"excluded by reviewer: {reg['reviewer_note']}"}
            )
            continue
        if reg["role"] not in READ_ROLES:
            region_reports.append({**reg, "status": "skipped", "reason": "not an approved representation"})
            continue
        pages = list(range(reg["page_start"], reg["page_end"] + 1))
        report: dict[str, Any] = {**reg, "status": "read", "pages": len(pages)}
        if representation in ("tables", "mixed") or reg["role"] not in ("approved_schedule", "approved_summary"):
            inputs: list[GridInput] = []
            for pi in pages:
                for (gp, ordinal), key in sorted(grid_rows.items()):
                    if gp != pi or (gp, ordinal) in seen_grids:
                        continue
                    seen_grids.add((gp, ordinal))
                    try:
                        payload = json.loads(storage.get(ObjectStore.ARTEFACTS, key))
                    except (ObjectNotFound, ValueError):
                        report.setdefault("missing_grid_artefacts", []).append(key)
                        continue
                    g = payload["grid"]
                    above, below = _lines_around(doc[pi - 1], g["bbox"])
                    inputs.append(
                        GridInput(
                            page_index=pi,
                            ordinal=ordinal,
                            rows=g["rows"],
                            header_rows=int(g.get("header_rows", 0)),
                            title_lines=above,
                            footnote_lines=below,
                            reader=g.get("reader", "pymupdf"),
                        )
                    )
            records = analyse_grids(inputs)
            report["grids"] = len(records)
            report["grid_summary"] = summarise_grids(records)
            if not records:
                report["finding"] = "no_grids_in_region"
            for r in records:
                grid_summaries.append({"region": reg["ordinal"], **r.summary()})
                for c in r.cells:
                    cells_out.append({"region_role": reg["role"], **c.to_dict(), "resolved": c.resolved})
                artefacts.append(
                    (
                        f"{sha}/{STAGE}/{tool_version}/region-{reg['ordinal']:02d}/grid-{r.page_index:04d}-{r.ordinal}.json",
                        r.to_dict(),
                    )
                )
        if representation in ("clause_outline", "mixed") and reg["role"] in ("approved_schedule", "approved_summary"):
            texts = [(pi, doc[pi - 1].get_text("text", sort=True)) for pi in pages]
            outline = reconstruct(texts)
            report["clauses"] = summarise_clauses(outline)
            for v in outline.values:
                clauses_out.append({"region_role": reg["role"], **v.to_dict()})
            artefacts.append(
                (f"{sha}/{STAGE}/{tool_version}/region-{reg['ordinal']:02d}/clauses.json", outline.to_dict())
            )
        region_reports.append(report)
        ctx.save_checkpoint(
            "grid", {"regions_done": reg["ordinal"]}, {"pages_done": reg["page_end"], "pages_total": doc.page_count}
        )

    summary = {
        "tool_version": tool_version,
        "representation": representation,
        "regions_read": sum(1 for r in region_reports if r["status"] == "read"),
        "regions_skipped": sum(1 for r in region_reports if r["status"] == "skipped"),
        "regions_without_grids": [r["ordinal"] for r in region_reports if r.get("finding") == "no_grids_in_region"],
        "regions_excluded": [r["ordinal"] for r in region_reports if r.get("excluded")],
        "cells": len(cells_out),
        "cells_resolved": sum(1 for c in cells_out if c["resolved"]),
        "cells_unresolved": sum(1 for c in cells_out if not c["resolved"]),
        "unresolved_by_flag": _count_flags(cells_out, ("unresolved_header", "unresolved_row", "unit_unresolved")),
        "flags": _count_flags(cells_out),
        "unit_sources": _count(cells_out, "unit_source"),
        "continuations": sum(1 for g in grid_summaries if g["continuation_of"]),
        "header_inherited_grids": sum(1 for g in grid_summaries if g["header_inherited"]),
        "clause_values": sum(1 for v in clauses_out if v["kind"] == "value"),
        "clause_cross_references": sum(1 for v in clauses_out if v["kind"] == "cross_reference"),
        "clause_conditions": sum(1 for v in clauses_out if v["kind"] == "condition"),
        "clause_categories": sorted({v["category_code"] for v in clauses_out if v["category_code"]}),
        "clause_option_groups": sum(r.get("clauses", {}).get("option_groups", 0) for r in region_reports),
        "regions": region_reports,
    }
    summary_key = f"{sha}/{STAGE}/{tool_version}/summary.json"
    artefacts.append((summary_key, {"summary": summary, "grids": grid_summaries}))

    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        for key, payload in artefacts:
            body = json.dumps(payload, sort_keys=True, default=str).encode()
            storage.put(ObjectStore.ARTEFACTS, key, body, "application/json")
            s.execute(
                pg_insert(StageArtefact)
                .values(
                    id=uuid.uuid4(),
                    source_id=source_id,
                    stage=STAGE,
                    tool=key.split("/")[3],
                    tool_version=tool_version,
                    page_index=0,
                    object_key=key,
                    content_sha256=hashlib.sha256(body).hexdigest(),
                    size_bytes=len(body),
                )
                .on_conflict_do_nothing(constraint="uq_stage_artefact")
            )
        # a re-run replaces the rows (artefacts stay immutable per tool version)
        s.execute(delete(StructureCell).where(StructureCell.source_id == source_id))
        s.execute(delete(ClauseValueRecord).where(ClauseValueRecord.source_id == source_id))
        for c in cells_out:
            s.add(
                StructureCell(
                    source_id=source_id,
                    region_role=c["region_role"],
                    page_index=c["page_index"],
                    grid_ordinal=c["grid_ordinal"],
                    row=c["row"],
                    col=c["col"],
                    raw=c["raw"][:300],
                    header_path=c["header_path"],
                    row_path=c["row_path"],
                    normalised=c["normalised"],
                    value_state=c["normalised"]["value_state"],
                    currency=c["currency"],
                    per_unit=c["per_unit"],
                    frequency=c["frequency"],
                    unit_source=c["unit_source"],
                    flags=c["flags"],
                    footnotes=c["footnotes"],
                    slab=c["slab"],
                    resolved=c["resolved"],
                    rules_version=GRID_VERSION,
                )
            )
        seen: dict[tuple[int, int], int] = {}
        for v in clauses_out:
            k = (v["page_index"], v["line_no"])
            seen[k] = seen.get(k, 0) + 1
            s.add(
                ClauseValueRecord(
                    source_id=source_id,
                    region_role=v["region_role"],
                    page_index=v["page_index"],
                    line_no=v["line_no"],
                    ordinal=seen[k],
                    category_code=v["category_code"],
                    clause_path=v["clause_path"],
                    role=v["role"],
                    kind=v["kind"],
                    connector=v["connector"],
                    alternative=v["alternative"],
                    line_text=v["line_text"][:400],
                    normalised=v["normalised"],
                    dimension=v["dimension"],
                    slab=v["slab"],
                    time_window=v["time_window"],
                    sign=v["sign"],
                    parameters=v["parameters"],
                    rules_version=CLAUSE_VERSION,
                )
            )
        src.structure_summary = summary
        src.structure_version = tool_version
        src.gridded_at = datetime.now(UTC)
        if src.state != SourceState.gridded:
            transition(s, src, SourceState.gridded, actor=ctx.worker, reason=tool_version)
        enqueue_stage(s, ctx.settings, src, "extract_source", actor=ctx.worker)
    return {
        "cells": summary["cells"],
        "cells_unresolved": summary["cells_unresolved"],
        "clause_values": summary["clause_values"],
        "regions_read": summary["regions_read"],
    }


def _count_flags(cells: list[dict[str, Any]], only: tuple[str, ...] | None = None) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in cells:
        for f in c["flags"]:
            if only is None or f in only:
                out[f] = out.get(f, 0) + 1
    return out


def _count(cells: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in cells:
        k = str(c.get(key) or "none")
        out[k] = out.get(k, 0) + 1
    return out
