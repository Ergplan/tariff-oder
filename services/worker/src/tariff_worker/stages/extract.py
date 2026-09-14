"""Stage ``gridded -> extracted`` (Section 6.8): dual-channel candidate extraction over the
reviewer-confirmed structure.  For every approved region the structure channel receives the
serialised grid/clause structure and the image channel receives the page images; each goes
through the provider adapter (fixture or real, never mixed — the flag is on every run and
every candidate); the channels are compared field by field and every candidate gets a
confidence, risk tags and a routing (Section 6.10).  Prose decisions for network-charge
families are read from the network-charge regions.

Cost limits (Section 6.13): the job stops with ``budget_exceeded`` when the order's provider
cost or tokens would pass the configured limits; nothing is skipped or lowered to fit.
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
from tariff_api.db import session_scope
from tariff_api.extraction import (
    EXTRACTION_RULES_VERSION,
    PROMPT_VERSION,
    Compared,
    StructureInput,
    compare_channels,
    extract_conditions,
    green_tariff_prose,
    network_extract,
    prose_decisions,
    route,
)
from tariff_api.inventory import NotAPdf, open_document
from tariff_api.models import (
    CandidateRecord,
    ClauseValueRecord,
    ConditionRecordRow,
    DocumentHeading,
    ExtractionRun,
    LocalisationRecord,
    LocalisationRegion,
    SourceDocument,
    SourcePage,
    SourceState,
    StageArtefact,
    StructureCell,
)
from tariff_api.profiles import load_profile
from tariff_api.providers import ProviderUnavailable, build_provider
from tariff_api.services.sources import enqueue_stage, transition
from tariff_api.tariff_schema import SCHEMA_VERSION, ExtractionOutput

from ..runner import JobContext, JobFailure

STAGE = "extract"
READ_ROLES = ("approved_schedule", "approved_summary")
PROSE_ROLES = ("network_charges", "green_tariff", "loss_trajectory")
GRID_FACT_ROLES = ("network_charges", "loss_trajectory")


def _row(o: Any, cols: tuple[str, ...]) -> dict[str, Any]:
    return {c: getattr(o, c) for c in cols}


_CELL_COLS = (
    "region_role",
    "page_index",
    "grid_ordinal",
    "row",
    "col",
    "raw",
    "header_path",
    "row_path",
    "normalised",
    "value_state",
    "currency",
    "per_unit",
    "frequency",
    "unit_source",
    "flags",
    "footnotes",
    "slab",
    "resolved",
)
_CLAUSE_COLS = (
    "page_index",
    "line_no",
    "ordinal",
    "category_code",
    "clause_path",
    "role",
    "kind",
    "connector",
    "alternative",
    "line_text",
    "normalised",
    "dimension",
    "slab",
    "time_window",
    "sign",
    "parameters",
)


def extract_source(ctx: JobContext) -> dict:
    source_id = uuid.UUID(ctx.payload["source_id"])
    storage: ObjectStore = ctx.adapters.storage
    settings = ctx.settings
    provider = build_provider(settings, ctx.adapters.secrets)
    extraction_version = (
        f"rules@{EXTRACTION_RULES_VERSION}+prompt@{PROMPT_VERSION}+schema@{SCHEMA_VERSION}"
        f"+{provider.name}:{provider.model}"
    )

    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        if src is None:
            raise JobFailure("not_found", f"source {source_id} no longer exists", retry=False)
        if src.state not in (SourceState.gridded, SourceState.extracted, SourceState.needs_reprocessing):
            raise JobFailure(
                "invalid_transition", f"source in state {src.state.value}; extract needs gridded", retry=False
            )
        rec = s.get(LocalisationRecord, source_id)
        if rec is None or not rec.extraction_allowed:
            raise JobFailure("invalid_transition", "localisation not confirmed; nothing is extracted", retry=False)
        if src.structure_version is None:
            raise JobFailure("invalid_transition", "structure has not been built", retry=False)
        if src.state == SourceState.extracted and src.extraction_version == extraction_version:
            return {"skipped": "already_extracted"}
        profile = load_profile(src.reading_profile_id, src.reading_profile_version)
        regions = [
            _row(r, ("ordinal", "role", "sub_role", "page_start", "page_end", "utility", "period"))
            for r in s.execute(
                select(LocalisationRegion)
                .where(LocalisationRegion.source_id == source_id)
                .order_by(LocalisationRegion.ordinal)
            ).scalars()
        ]
        cells = [
            _row(c, _CELL_COLS)
            for c in s.execute(select(StructureCell).where(StructureCell.source_id == source_id)).scalars()
        ]
        clauses = [
            _row(v, _CLAUSE_COLS)
            for v in s.execute(select(ClauseValueRecord).where(ClauseValueRecord.source_id == source_id)).scalars()
        ]
        headings = [
            _row(h, ("page_index", "kind", "code_canonical", "text"))
            for h in s.execute(
                select(DocumentHeading).where(DocumentHeading.source_id == source_id).order_by(DocumentHeading.ordinal)
            ).scalars()
        ]
        ocr_pages = {
            p.page_index
            for p in s.execute(select(SourcePage).where(SourcePage.source_id == source_id)).scalars()
            if p.ocr_used
        }
        object_key, sha, page_count = src.object_key, src.sha256, src.page_count or 0
        is_first_for_utility = (
            s.execute(
                select(SourceDocument.id).where(
                    SourceDocument.reading_profile_id == src.reading_profile_id,
                    SourceDocument.id != source_id,
                    SourceDocument.state.in_([SourceState.awaiting_review, SourceState.published]),
                )
            ).first()
            is None
        )

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

    total_cost = 0.0
    total_tokens = 0
    conditions_found: list[Any] = []
    claimed_grids: set[tuple[int, int]] = set()  # regions may overlap on a page: each grid feeds one region
    single_keys: set[str] = set()  # prose facts are read per region; overlapping regions must not repeat them

    def add_single(c, reg) -> None:
        # identity for de-duplication across overlapping regions: the fact and its evidence
        # span (regions may carry different periods for the same page)
        ev = c.evidence[0]
        ident = f"{c.family}|{c.category_code}|{c.applicability.voltage}|{c.value}|{ev.page_index}|{ev.excerpt}"
        if ident not in single_keys:
            single_keys.add(ident)
            compared_all.append((_single(c), reg))

    runs: list[dict[str, Any]] = []
    compared_all: list[tuple[Any, dict[str, Any]]] = []  # (Compared, region)
    artefacts: list[tuple[str, dict[str, Any]]] = []

    def check_budget() -> None:
        if (
            total_cost > settings.provider_max_cost_per_order_usd
            or total_tokens > settings.provider_max_tokens_per_order
        ):
            raise JobFailure(
                "budget_exceeded",
                f"provider cost {total_cost:.4f} USD / {total_tokens} tokens passed the order limit "
                f"({settings.provider_max_cost_per_order_usd} USD / {settings.provider_max_tokens_per_order} tokens); "
                "re-run after raising the limit — nothing was skipped to fit",
                retry=False,
            )

    def render(pages: list[int]) -> list[bytes]:
        out = []
        for pi in pages:
            pix = doc[pi - 1].get_pixmap(dpi=settings.image_channel_dpi)
            out.append(pix.tobytes("png"))
        return out

    for reg in regions:
        pages = list(range(reg["page_start"], reg["page_end"] + 1))
        page_texts = {pi: doc[pi - 1].get_text("text", sort=True) for pi in pages}
        inp = StructureInput(
            source_sha=sha,
            profile_id=profile.id,
            schedule_heading_kind=profile.schedule_heading_kind,
            region_role=reg["role"],
            region_ordinal=reg["ordinal"],
            page_indices=pages,
            cells=[
                c
                for c in cells
                if c["page_index"] in pages
                and c["region_role"] == reg["role"]
                and (c["page_index"], c["grid_ordinal"]) not in claimed_grids
            ]
            if reg["role"] in READ_ROLES + GRID_FACT_ROLES
            else [],
            clauses=[v for v in clauses if v["page_index"] in pages] if reg["role"] in READ_ROLES else [],
            headings=[h for h in headings if h["page_index"] <= reg["page_end"]],
            page_texts=page_texts if reg["role"] in PROSE_ROLES or reg["role"] in READ_ROLES else {},
            ocr_pages={p for p in ocr_pages if p in pages},
            utility=reg["utility"],
            period=reg["period"],
            utilities=profile.utilities,
            category_code_pattern=profile.category_code_pattern,
        )
        if reg["role"] not in READ_ROLES and reg["role"] not in PROSE_ROLES:
            continue
        claimed_grids |= {(c["page_index"], c["grid_ordinal"]) for c in inp.cells}
        if reg["role"] in PROSE_ROLES:
            # network-charge grids and prose decisions are deterministic rules: no provider call,
            # so they are single-channel candidates (risk `single_channel`, individual review)
            out = ExtractionOutput(candidates=prose_decisions(inp) + green_tariff_prose(inp))
            if reg["role"] in GRID_FACT_ROLES and inp.cells:
                net = network_extract(inp, reg["sub_role"])
                out.candidates.extend(net.candidates)
                out.missing.extend(net.missing)
            artefacts.append(
                (
                    f"{sha}/{STAGE}/{extraction_version}/region-{reg['ordinal']:02d}/rules.json",
                    {"output": out.model_dump(), "channel": "rules", "sub_role": reg["sub_role"]},
                )
            )
            for c in out.candidates:
                add_single(c, reg)
            continue
        # green tariff premiums printed among the general provisions of the approved region
        for c in green_tariff_prose(inp):
            add_single(c, reg)
        conditions_found.extend(extract_conditions(inp))
        try:
            structure_res = provider.extract_structure(inp)
        except ProviderUnavailable as e:
            runs.append(_run_row(reg, "structure", provider, None, str(e)))
            raise JobFailure("provider_unavailable", str(e), retry=True) from e
        total_cost += structure_res.cost_usd
        total_tokens += structure_res.input_tokens + structure_res.output_tokens
        check_budget()
        runs.append(_run_row(reg, "structure", provider, structure_res, None))
        artefacts.append(
            (
                f"{sha}/{STAGE}/{extraction_version}/region-{reg['ordinal']:02d}/structure.json",
                {
                    "input_hash": structure_res.input_hash,
                    "output": structure_res.output.model_dump(),
                    "raw": structure_res.raw,
                },
            )
        )
        image_res = None
        if settings.image_channel_enabled:
            try:
                image_res = provider.extract_image(inp, render(pages))
            except ProviderUnavailable as e:
                runs.append(_run_row(reg, "image", provider, None, str(e)))
                raise JobFailure("provider_unavailable", str(e), retry=True) from e
            total_cost += image_res.cost_usd
            total_tokens += image_res.input_tokens + image_res.output_tokens
            check_budget()
            runs.append(_run_row(reg, "image", provider, image_res, None))
            artefacts.append(
                (
                    f"{sha}/{STAGE}/{extraction_version}/region-{reg['ordinal']:02d}/image.json",
                    {"input_hash": image_res.input_hash, "output": image_res.output.model_dump(), "raw": image_res.raw},
                )
            )
        for cmp in compare_channels(structure_res.output, image_res.output if image_res else None):
            compared_all.append((cmp, reg))
        ctx.save_checkpoint(
            "extract", {"regions_done": reg["ordinal"]}, {"pages_done": reg["page_end"], "pages_total": page_count}
        )

    cell_flags = {(c["page_index"], c["grid_ordinal"], c["row"], c["col"]): c["flags"] for c in cells}
    candidate_rows: list[dict[str, Any]] = []
    for cmp, reg in compared_all:
        prim = cmp.primary
        flags: list[str] = []
        for e in prim.evidence:
            if e.kind == "cell":
                flags.extend(cell_flags.get((e.page_index, e.grid_ordinal or 0, e.row or 0, e.col or 0), []))
        ocr = any(e.page_index in ocr_pages for e in prim.evidence)
        r = route(cmp, flags, ocr_page=ocr, new_profile=is_first_for_utility)
        candidate_rows.append(
            {
                "candidate_key": cmp.key[:400],
                "family": prim.family,
                "category_code": prim.category_code,
                "component_type": prim.component_type,
                "value": prim.value,
                "value_state": prim.value_state,
                "currency": prim.currency,
                "per_unit": prim.per_unit,
                "frequency": prim.frequency,
                "decision_status": prim.decision_status,
                "period": prim.period,
                "utility": prim.utility,
                "record": prim.model_dump(),
                "image_record": cmp.image.model_dump() if cmp.image is not None and cmp.structure is not None else None,
                "channel_agreement": cmp.agreement,
                "disagreeing_fields": cmp.disagreeing_fields,
                "confidence": r.confidence,
                "risk_tags": r.risk_tags,
                "routing": r.routing,
                "is_fixture": provider.is_fixture,
                "region_ordinal": reg["ordinal"],
            }
        )

    summary = {
        "extraction_version": extraction_version,
        "provider": provider.name,
        "model": provider.model,
        "is_fixture": provider.is_fixture,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "runs": len(runs),
        "runs_failed": sum(1 for r in runs if r["status"] == "failed"),
        "cost_usd": round(total_cost, 6),
        "tokens": total_tokens,
        "candidates": len(candidate_rows),
        "by_family": _count(candidate_rows, "family"),
        "by_confidence": _count(candidate_rows, "confidence"),
        "by_agreement": _count(candidate_rows, "channel_agreement"),
        "by_routing": _count(candidate_rows, "routing"),
        "risk_tags": _count_list(candidate_rows, "risk_tags"),
        "image_channel": settings.image_channel_enabled,
        "new_profile": is_first_for_utility,
    }
    artefacts.append((f"{sha}/{STAGE}/{extraction_version}/summary.json", {"summary": summary, "runs": runs}))

    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        run_ids: dict[tuple[int, str], uuid.UUID] = {}
        for r in runs:
            row = ExtractionRun(
                source_id=source_id,
                job_id=ctx.job_id,
                region_ordinal=r["region_ordinal"],
                channel=r["channel"],
                provider=r["provider"],
                model=r["model"],
                prompt_version=r["prompt_version"],
                schema_version=r["schema_version"],
                is_fixture=r["is_fixture"],
                input_hash=r["input_hash"],
                input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"],
                cost_usd=r["cost_usd"],
                status=r["status"],
                error=r["error"],
                candidates_returned=r["candidates_returned"],
                finished_at=datetime.now(UTC),
            )
            s.add(row)
            s.flush()
            run_ids[(r["region_ordinal"], r["channel"])] = row.id
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
                    tool_version=extraction_version[:160],
                    page_index=0,
                    object_key=key,
                    content_sha256=hashlib.sha256(body).hexdigest(),
                    size_bytes=len(body),
                )
                .on_conflict_do_nothing(constraint="uq_stage_artefact")
            )
        # a re-run replaces pending candidates; reviewed ones are never overwritten silently
        s.execute(
            delete(CandidateRecord).where(
                CandidateRecord.source_id == source_id, CandidateRecord.review_status == "pending"
            )
        )
        for row in candidate_rows:
            reg_ord = row.pop("region_ordinal")
            s.add(
                CandidateRecord(
                    source_id=source_id,
                    structure_run_id=run_ids.get((reg_ord, "structure")),
                    image_run_id=run_ids.get((reg_ord, "image")),
                    extraction_version=extraction_version[:80],
                    **row,
                )
            )
        s.execute(delete(ConditionRecordRow).where(ConditionRecordRow.source_id == source_id))
        seen_conditions: set[tuple] = set()
        for cr in conditions_found:
            h = hashlib.sha256(cr.text.encode()).hexdigest()
            key = (cr.page_index, cr.line_no, cr.kind, h)
            if key in seen_conditions:
                continue
            seen_conditions.add(key)
            s.add(
                ConditionRecordRow(
                    source_id=source_id,
                    page_index=cr.page_index,
                    line_no=cr.line_no,
                    number=cr.number,
                    kind=cr.kind,
                    text=cr.text,
                    text_hash=h,
                    scope_codes=cr.scope_codes,
                    interpretation_status=cr.interpretation_status,
                    extraction_version=extraction_version[:80],
                )
            )
        summary["conditions"] = len(seen_conditions)
        src.extraction_summary = summary
        src.extraction_version = extraction_version[:80]
        src.extracted_at = datetime.now(UTC)
        if src.state != SourceState.extracted:
            transition(s, src, SourceState.extracted, actor=ctx.worker, reason=extraction_version[:200])
        enqueue_stage(s, settings, src, "validate_source", actor=ctx.worker)
    return {"candidates": len(candidate_rows), "cost_usd": summary["cost_usd"], "is_fixture": provider.is_fixture}


def _single(c) -> Compared:
    return Compared(c.key(), c, None, "single_channel")


def _run_row(reg, channel, provider, res, error) -> dict[str, Any]:
    return {
        "region_ordinal": reg["ordinal"],
        "channel": channel,
        "provider": provider.name,
        "model": provider.model,
        "prompt_version": res.prompt_version if res else PROMPT_VERSION,
        "schema_version": res.schema_version if res else SCHEMA_VERSION,
        "is_fixture": provider.is_fixture,
        "input_hash": res.input_hash if res else "",
        "input_tokens": res.input_tokens if res else 0,
        "output_tokens": res.output_tokens if res else 0,
        "cost_usd": res.cost_usd if res else 0.0,
        "status": "succeeded" if res else "failed",
        "error": error,
        "candidates_returned": len(res.output.candidates) if res else 0,
    }


def _count(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        k = str(r.get(key) or "none")
        out[k] = out.get(k, 0) + 1
    return out


def _count_list(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        for t in r.get(key) or []:
            out[t] = out.get(t, 0) + 1
    return out
