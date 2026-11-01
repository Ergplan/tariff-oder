"""The ARR reading track (ADR-0018), beside the tariff state machine:

- ``arr_localise_source``: chapters from the commission mapping's heading cues over the page
  text, plus the hand-mapping scan of the whole order (its ``unplaced`` list is the
  reviewer's work for the mapping gate); ``arr_state = chapters_proposed``.
- ``arr_extract_source`` (after a reviewer confirms the chapters): the rules read the
  primary grids of each confirmed chapter, the model channel reads its page images, the two
  are compared field by field and every reading becomes an ARR candidate in the shared
  envelope; ``arr_state = extracted``.
- ``arr_validate_source``: the ARR identities per (year, voice, order); findings attach to
  the lines involved; ``arr_state = awaiting_review``.

Nothing here approves, publishes or corrects."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tariff_api.adapters.storage import ObjectNotFound, ObjectStore
from tariff_api.arr.chapters import CHAPTERS_VERSION, furniture, is_furniture, part_from_note, propose_chapters
from tariff_api.arr.extract import ARR_RULES_VERSION, GridIn, compare, read_grids
from tariff_api.arr.identities import EVALUATED, IDENTITIES_VERSION, Value, evaluate
from tariff_api.arr.provider import ArrChannelUnavailable, build_arr_channel
from tariff_api.arr.scan import scan_texts
from tariff_api.arr.schema import ARR_SCHEMA_VERSION, ArrCandidate
from tariff_api.arr.taxonomy import Placer, load_mapping, load_taxonomy
from tariff_api.db import session_scope
from tariff_api.inventory import NotAPdf, open_document
from tariff_api.models import (
    ArrChapter,
    ArrFact,
    CandidateRecord,
    DatasetKind,
    ExtractionRun,
    SourceDocument,
    StageArtefact,
    TableGridRecord,
    ValidatorFindingRecord,
)
from tariff_api.services.sources import enqueue_stage, licensees_of

from ..runner import JobContext, JobFailure
from .grid import _lines_around

IMAGE_DPI = 72  # the fixture channel only hashes the images; the live channel sets its own


def _load(ctx: JobContext, s, states: tuple[str | None, ...]) -> SourceDocument:
    source_id = uuid.UUID(ctx.payload["source_id"])
    src = s.get(SourceDocument, source_id)
    if src is None:
        raise JobFailure("not_found", f"source {source_id} no longer exists", retry=False)
    if src.arr_state not in states:
        raise JobFailure(
            "invalid_transition", f"ARR reading is {src.arr_state}; this stage needs {states}", retry=False
        )
    if src.utility is None:
        raise JobFailure("validation_failed", "the order has no licensee", retry=False)
    return src


def _document(storage: ObjectStore, object_key: str, sha: str):
    try:
        data = storage.get(ObjectStore.SOURCES, object_key)
    except ObjectNotFound as e:
        raise JobFailure("storage_unavailable", f"object {object_key} missing", retry=True) from e
    if hashlib.sha256(data).hexdigest() != sha:
        raise JobFailure("source_unreadable", "stored bytes do not match the registered hash", retry=False)
    try:
        return open_document(data)
    except NotAPdf as e:
        raise JobFailure("source_unreadable", str(e), retry=False) from e


def _heading_y(doc, page: int, text: str) -> float | None:
    """The top of a chapter heading on its page, or None when the text cannot be found."""
    try:
        rects = doc[page - 1].search_for(text[:80])
    except Exception:  # noqa: BLE001 - a heading we cannot locate leaves the page undivided
        return None
    return float(rects[0].y0) if rects else None


def _artefact(s, storage: ObjectStore, src: SourceDocument, stage: str, tool_version: str, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    key = f"{src.sha256}/{stage}/{tool_version}/{hashlib.sha256(body).hexdigest()[:16]}.json"
    storage.put(ObjectStore.ARTEFACTS, key, body, "application/json")
    s.execute(
        pg_insert(StageArtefact)
        .values(
            source_id=src.id,
            stage=stage,
            tool=stage,
            tool_version=tool_version,
            page_index=0,
            object_key=key,
            content_sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
        )
        .on_conflict_do_nothing(constraint="uq_stage_artefact")
    )
    return key


# ------------------------------------------------------------------ chapters


def _chapter_grids(doc, storage: ObjectStore, grid_keys: dict, chapter_rows: list) -> dict[int, list[GridIn]]:  # noqa: ANN001
    """Each chapter's primary grids, with the lines printed above each.  A table belongs to the
    last chapter heading above it, so a page shared by two chapters splits at the second
    heading; a table is read once.  The running headers and footers are not a table's caption:
    "…Tariff determination for FY 2026-27" above a continued table names no year of it."""
    skip = furniture(
        {
            i + 1: [ln for ln in doc[i].get_text("text", sort=True).splitlines() if ln.strip()]
            for i in range(doc.page_count)
        }
    )
    cue_y = {ordinal: _heading_y(doc, cue_page, cue_text) for ordinal, _s, _e, _b, cue_page, cue_text in chapter_rows}
    seen: set[tuple[int, int]] = set()
    out: dict[int, list[GridIn]] = {}
    for ordinal, start, end, _branch, cue_page, _cue_text in chapter_rows:
        grids: list[GridIn] = []
        later = [(o, cp) for o, _s, _e, _b, cp, _t in chapter_rows if o > ordinal]
        for (page, g_ord), key in sorted(grid_keys.items()):
            if not (start <= page <= end) or (page, g_ord) in seen:
                continue
            try:
                payload = json.loads(storage.get(ObjectStore.ARTEFACTS, key))
            except (ObjectNotFound, ValueError):
                continue
            g = payload["grid"]
            top = float(g["bbox"][1])
            if page == cue_page and cue_y[ordinal] is not None and top < cue_y[ordinal]:
                continue  # above this chapter's own heading: the previous chapter's table
            if any(cp == page and cue_y[o] is not None and top >= cue_y[o] for o, cp in later):
                continue  # below a later chapter's heading on this page: that chapter's table
            seen.add((page, g_ord))
            above, _below = _lines_around(doc[page - 1], g["bbox"])
            above = [ln for ln in above if not is_furniture(ln, skip)]
            grids.append(GridIn(page, g_ord, g["rows"], int(g.get("header_rows") or 0), above))
        out[ordinal] = grids
    return out


def _preview(
    doc,
    storage: ObjectStore,
    grid_keys: dict,
    proposals: list,
    *,
    mapping,
    kind: str,
    utility: str,
    licensees: dict,  # noqa: ANN001
) -> dict[str, Any]:
    """What reading each proposed chapter would yield — tables read, values by year and voice,
    identity failures, the commonest unplaced labels — computed with the reading rules and
    recorded nowhere but here: a reviewer's aid for confirming chapters, not a reading."""
    tax = load_taxonomy()
    placer = Placer(tax, mapping, kind)
    rows = [(p.ordinal, p.page_start, p.page_end, p.branch, p.cue_page, p.cue_text) for p in proposals]
    by_chapter = _chapter_grids(doc, storage, grid_keys, rows)
    out = []
    for p in proposals:
        grids = by_chapter.get(p.ordinal, [])
        res, rep = read_grids(
            grids,
            taxonomy=tax,
            mapping=mapping,
            placer=placer,
            source_id="preview",
            utility=utility,
            licensees=licensees if len(licensees) > 1 else None,
            part=part_from_note(p.note),
            branch=p.branch,
        )
        groups: dict[tuple, list[Value]] = {}
        voices: dict[str, int] = {}
        for c in res.candidates:
            voices[f"{c.fiscal_year} {c.value_type}"] = voices.get(f"{c.fiscal_year} {c.value_type}", 0) + 1
            if c.canonical_value is not None:
                groups.setdefault((c.fiscal_year, c.value_type, c.utility), []).append(
                    Value(c.line_code, Decimal(c.canonical_value), c.canonical_unit, "preview")
                )
        found = [
            f
            for (fy, vt, _u), vals in groups.items()
            for f in evaluate(vals, taxonomy=tax, mapping=mapping, group={"fiscal_year": fy, "value_type": vt})
            if f.severity == "blocking"
        ]
        blocking = len(found)
        unplaced: dict[str, int] = {}
        for u in rep.unplaced:
            unplaced[u["label"][:60]] = unplaced.get(u["label"][:60], 0) + 1
        out.append(
            {
                "chapter": p.ordinal,
                "tables": len(grids),
                "tables_read": rep.grids_read,
                "values": len(res.candidates),
                "by_year_voice": dict(sorted(voices.items())),
                "identity_blocking": blocking,
                # the failures themselves, for the reviewer and the mapping workbench's convention
                # questions (a hint is a question, never a decision)
                "findings": [
                    {
                        "identity_id": f.identity_id,
                        "fiscal_year": f.group.get("fiscal_year"),
                        "value_type": f.group.get("value_type"),
                        "message": f.message[:400],
                        "reconciles_if": f.detail.get("reconciles_if"),
                    }
                    for f in found[:8]
                ],
                "unplaced_top": sorted(unplaced.items(), key=lambda x: -x[1])[:3],
            }
        )
    return {
        "rules": ARR_RULES_VERSION,
        "chapters": out,
        "note": "What reading each chapter would yield, before anything is read; nothing here is a candidate.",
    }


def arr_localise_source(ctx: JobContext) -> dict:
    storage: ObjectStore = ctx.adapters.storage
    with session_scope() as s:
        source_id = uuid.UUID(ctx.payload["source_id"])
        src = s.get(SourceDocument, source_id)
        if src is None:
            raise JobFailure("not_found", f"source {source_id} no longer exists", retry=False)
        if src.utility is None or src.parse_version is None or src.page_count is None:
            raise JobFailure("invalid_transition", "ARR reading needs a parsed order with a licensee", retry=False)
        commission = src.utility.commission.code
        kind = src.utility.licensee_kind
        utility_code = src.utility.code
        object_key, sha, page_count = src.object_key, src.sha256, src.page_count
        licensee_names = {u.code: [u.name, *(u.aliases or [])] for u in licensees_of(s, src)}
        grid_keys = {
            (g.page_index, g.ordinal): g.object_key
            for g in s.execute(
                select(TableGridRecord).where(
                    TableGridRecord.source_id == source_id, TableGridRecord.is_primary.is_(True)
                )
            ).scalars()
        }
    try:
        mapping = load_mapping(commission, fallback=True)
    except FileNotFoundError as e:
        raise JobFailure("validation_failed", f"no ARR mapping for {commission}", retry=False) from e
    doc = _document(storage, object_key, sha)
    texts = {i + 1: doc[i].get_text("text", sort=True) for i in range(doc.page_count)}
    lines = {p: [ln for ln in t.splitlines() if ln.strip()] for p, t in texts.items()}
    proposals = propose_chapters(lines, mapping, page_count)
    scan = scan_texts(texts, commission=commission, licensee_kind=kind, mapping=mapping).to_dict()
    preview = _preview(
        doc, storage, grid_keys, proposals, mapping=mapping, kind=kind, utility=utility_code, licensees=licensee_names
    )
    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        assert src is not None
        s.execute(delete(ArrChapter).where(ArrChapter.source_id == source_id))
        for p in proposals:
            s.add(
                ArrChapter(
                    source_id=source_id,
                    ordinal=p.ordinal,
                    branch=p.branch,
                    cue_text=p.cue_text,
                    cue_page=p.cue_page,
                    page_start=p.page_start,
                    page_end=p.page_end,
                    note=p.note,
                    mapping_id=mapping.id,
                    mapping_version=mapping.version,
                )
            )
        key = _artefact(s, storage, src, "arr_scan", f"scan+chapters@{CHAPTERS_VERSION}", scan)
        src.arr_state = "chapters_proposed"
        src.arr_summary = {
            "chapters_version": CHAPTERS_VERSION,
            "mapping": {"id": mapping.id, "version": mapping.version, "status": mapping.status},
            "chapters": len(proposals),
            "scan": {
                "artefact": key,
                "placed_rows": scan["placed_rows"],
                "unplaced_rows": scan["unplaced_rows"],
                "unplaced_labels": len(scan["unplaced"]),  # distinct labels; the 50 most frequent kept
                "unplaced": scan["unplaced"][:50],
            },
            "preview": preview,
            "localised_at": datetime.now(UTC).isoformat(),
        }
    return {"chapters": len(proposals), "unplaced_rows": scan["unplaced_rows"]}


# ------------------------------------------------------------------ extraction


def _candidate_row(
    source_id: uuid.UUID,
    cand: ArrCandidate,
    image: ArrCandidate | None,
    *,
    first_reading: bool,
    is_fixture: bool,
    extraction_version: str,
    structure_run: uuid.UUID,
    image_run: uuid.UUID | None,
) -> CandidateRecord:
    agreement, diff = compare(cand, image)
    risks: list[str] = []
    if agreement == "disagree":
        risks.append("channel_disagreement")
    elif agreement == "one_missing":
        risks.append("one_channel_missing")
    if "stated_unit" in cand.missing:
        risks.append("unit_missing")
    if "stated_value" in cand.ambiguous:
        risks.append("duplicate_conflict")
    if first_reading:
        risks.append("new_profile")  # the first ARR order read for this licensee: second review
    # the first-reading tag asks for a second reviewer; it says nothing about this reading
    confidence = "high" if agreement == "agree" and not [r for r in risks if r != "new_profile"] else "low"
    return CandidateRecord(
        source_id=source_id,
        payload_kind="arr",
        candidate_key=cand.key()[:400],
        family="arr_line",
        category_code=cand.line_code,
        component_type="arr_value",
        value=cand.stated_value,
        value_state=cand.value_state,
        per_unit=(cand.stated_unit or None) and cand.stated_unit[:16],
        decision_status=cand.value_type,
        period=cand.fiscal_year,
        utility=cand.utility,
        record=cand.model_dump(mode="json"),
        image_record=image.model_dump(mode="json") if image else None,
        channel_agreement=agreement,
        disagreeing_fields=diff,
        confidence=confidence,
        risk_tags=risks,
        routing="individual",  # no ARR batch approval in Increment A
        is_fixture=is_fixture,
        structure_run_id=structure_run,
        image_run_id=image_run,
        extraction_version=extraction_version[:80],
    )


def arr_extract_source(ctx: JobContext) -> dict:
    storage: ObjectStore = ctx.adapters.storage
    channel = build_arr_channel(ctx.settings, ctx.adapters.secrets)
    tax = load_taxonomy()
    with session_scope() as s:
        src = _load(ctx, s, ("chapters_confirmed", "extracted", "awaiting_review"))
        source_id, sha, object_key = src.id, src.sha256, src.object_key
        utility_code, kind = src.utility.code, src.utility.licensee_kind
        commission = src.utility.commission.code
        dataset_fixture = src.dataset.kind == DatasetKind.fixture
        # a combined order: each value is attributed to the licensee its column or caption names
        licensee_names = {u.code: [u.name, *(u.aliases or [])] for u in licensees_of(s, src)}
        first_reading = (
            s.execute(
                select(ArrFact.id)
                .where(ArrFact.utility_id == src.utility_id, ArrFact.superseded_by_id.is_(None))
                .limit(1)
            ).first()
            is None
        )
        chapter_rows = [
            (c.ordinal, c.page_start, c.page_end, c.branch, c.cue_page, c.cue_text)
            for c in s.execute(
                select(ArrChapter)
                .where(ArrChapter.source_id == source_id, ArrChapter.status == "confirmed")
                .order_by(ArrChapter.ordinal)
            ).scalars()
        ]
        grid_keys = {
            (g.page_index, g.ordinal): g.object_key
            for g in s.execute(
                select(TableGridRecord).where(
                    TableGridRecord.source_id == source_id, TableGridRecord.is_primary.is_(True)
                )
            ).scalars()
        }
    if not chapter_rows:
        raise JobFailure("validation_failed", "no confirmed chapter to read", retry=False)
    mapping = load_mapping(commission, fallback=True)
    placer = Placer(tax, mapping, kind)
    doc = _document(storage, object_key, sha)
    extraction_version = f"{ARR_RULES_VERSION}+{channel.name}:{channel.model}+schema:{ARR_SCHEMA_VERSION}"
    rows: list[CandidateRecord] = []
    runs: list[ExtractionRun] = []
    chapter_reports: list[dict[str, Any]] = []
    grids_by_chapter = _chapter_grids(doc, storage, grid_keys, chapter_rows)
    with session_scope() as s:
        parts = {
            c.ordinal: part_from_note(c.note)
            for c in s.execute(select(ArrChapter).where(ArrChapter.source_id == source_id)).scalars()
        }
    for ordinal, start, end, branch, _cue_page, _cue_text in chapter_rows:
        grids = grids_by_chapter.get(ordinal, [])
        structure, report = read_grids(
            grids,
            taxonomy=tax,
            mapping=mapping,
            placer=placer,
            source_id=str(source_id),
            utility=utility_code,
            licensees=licensee_names if len(licensee_names) > 1 else None,
            part=parts.get(ordinal),
            branch=branch,
        )
        for c in structure.candidates:
            c.chapter = ordinal
        s_run = ExtractionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            job_id=ctx.job_id,
            region_ordinal=ordinal,
            channel="structure",
            provider="rules",
            model=ARR_RULES_VERSION,
            prompt_version="-",
            schema_version=ARR_SCHEMA_VERSION,
            is_fixture=False,
            input_hash=hashlib.sha256(json.dumps([g.rows for g in grids]).encode()).hexdigest(),
            status="succeeded",
            candidates_returned=len(structure.candidates),
            finished_at=datetime.now(UTC),
        )
        runs.append(s_run)
        images = [doc[p - 1].get_pixmap(dpi=IMAGE_DPI).tobytes("png") for p in range(start, end + 1)]
        try:
            res = channel.read_chapter(
                structure,
                images,
                {
                    "pages": list(range(start, end + 1)),
                    "source_id": str(source_id),
                    "utility": utility_code,
                    "licensees": sorted(licensee_names) if len(licensee_names) > 1 else None,
                    "commission": commission,
                    "branch": branch,
                    "voices": [v.code for v in tax.value_types],
                    "line_items": [(i.code, i.label) for i in tax.line_items if i.kind != "group"],
                    "conversions": tax.unit_conversions,
                },
            )
        except ArrChannelUnavailable as e:
            raise JobFailure("provider_unavailable", str(e), retry=e.retry) from e
        i_run = ExtractionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            job_id=ctx.job_id,
            region_ordinal=ordinal,
            channel="image",
            provider=res.provider,
            model=res.model,
            prompt_version=res.prompt_version,
            schema_version=res.schema_version,
            is_fixture=res.is_fixture,
            input_hash=res.input_hash,
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            cost_usd=res.cost_usd,
            status="succeeded",
            candidates_returned=len(res.output.candidates),
            finished_at=datetime.now(UTC),
        )
        runs.append(i_run)
        by_key = {c.key(): c for c in res.output.candidates}
        for c in structure.candidates:
            rows.append(
                _candidate_row(
                    source_id,
                    c,
                    by_key.get(c.key()),
                    first_reading=first_reading,
                    is_fixture=dataset_fixture or res.is_fixture,
                    extraction_version=extraction_version,
                    structure_run=s_run.id,
                    image_run=i_run.id,
                )
            )
        chapter_reports.append({"chapter": ordinal, "branch": branch, "pages": [start, end], **report.to_dict()})
    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        assert src is not None
        for r in runs:
            s.add(r)
        # a re-read replaces pending ARR candidates; reviewed ones are kept and tagged stale
        s.execute(
            delete(CandidateRecord).where(
                CandidateRecord.source_id == source_id,
                CandidateRecord.payload_kind == "arr",
                CandidateRecord.review_status == "pending",
            )
        )
        new_keys = {r.candidate_key for r in rows}
        for old in s.execute(
            select(CandidateRecord).where(CandidateRecord.source_id == source_id, CandidateRecord.payload_kind == "arr")
        ).scalars():
            if old.candidate_key in new_keys:
                rows = [r for r in rows if r.candidate_key != old.candidate_key]  # the decision stands
            elif "stale_reading" not in (old.risk_tags or []):
                old.risk_tags = [*(old.risk_tags or []), "stale_reading"]
        for r in rows:
            s.add(r)
        key = _artefact(s, storage, src, "arr_extract", extraction_version, {"chapters": chapter_reports})
        src.arr_state = "extracted"
        src.arr_summary = {
            **(src.arr_summary or {}),
            "extraction": {
                "version": extraction_version,
                "artefact": key,
                "candidates": len(rows),
                "chapters": [
                    {k: v for k, v in c.items() if k not in ("duplicates",)} | {"duplicates": len(c["duplicates"])}
                    for c in chapter_reports
                ],
                "fixture_channel": channel.is_fixture,
            },
        }
        enqueue_stage(s, ctx.settings, src, "arr_validate_source", actor="worker")
    return {"candidates": len(rows), "chapters": len(chapter_rows)}


# ------------------------------------------------------------------ identities


def arr_validate_source(ctx: JobContext) -> dict:
    tax = load_taxonomy()
    with session_scope() as s:
        src = _load(ctx, s, ("extracted", "awaiting_review", "published"))
        try:
            mapping = load_mapping(src.utility.commission.code, fallback=True)
        except FileNotFoundError:
            mapping = None
        rows = (
            s.execute(
                select(CandidateRecord).where(
                    CandidateRecord.source_id == src.id,
                    CandidateRecord.payload_kind == "arr",
                    CandidateRecord.review_status != "rejected",
                )
            )
            .scalars()
            .all()
        )
        groups: dict[tuple[str, str, str], list[Value]] = {}
        for r in rows:
            rec = r.effective_record
            if rec.get("value_state") not in ("value", "zero") or rec.get("canonical_value") is None:
                continue
            # identities hold within one licensee's figures: a combined order is grouped by licensee
            g = (rec["fiscal_year"], rec["value_type"], rec["as_of_order"], rec.get("utility") or "")
            groups.setdefault(g, []).append(
                Value(
                    rec["line_code"],
                    Decimal(rec["canonical_value"]),
                    rec.get("canonical_unit"),
                    str(r.id),
                    rec.get("category_code"),
                )
            )
        s.execute(
            delete(ValidatorFindingRecord).where(
                ValidatorFindingRecord.source_id == src.id, ValidatorFindingRecord.validator_id.like("ARR-%")
            )
        )
        findings = []
        for (fy, vt, order, licensee), values in sorted(groups.items()):
            group = {"fiscal_year": fy, "value_type": vt, "as_of_order": order}
            if licensee:
                group["utility"] = licensee
            for f in evaluate(values, taxonomy=tax, mapping=mapping, group=group):
                findings.append(f)
                s.add(
                    ValidatorFindingRecord(
                        source_id=src.id,
                        validator_id=f.identity_id,
                        severity=f.severity,
                        message=f.message[:2000],
                        candidate_ids=f.refs,
                        detail={
                            "group": f.group,
                            "expected": f.expected,
                            "printed": f.printed,
                            "difference": f.difference,
                            "lines": f.lines,
                            **f.detail,
                        },
                        validators_version=IDENTITIES_VERSION,
                    )
                )
        counts: dict[str, list[int]] = {}
        for f in findings:
            for ref in f.refs:
                c = counts.setdefault(ref, [0, 0])
                c[0] += 1
                c[1] += f.severity == "blocking"
        for r in rows:
            total, blocking = counts.get(str(r.id), [0, 0])
            r.finding_count, r.blocking_finding_count = total, blocking
            tags = [t for t in (r.risk_tags or []) if t != "identity_failure"]
            if blocking:
                tags.append("identity_failure")
            r.risk_tags = tags
        if src.arr_state == "extracted":
            src.arr_state = "awaiting_review"
        src.arr_summary = {
            **(src.arr_summary or {}),
            "identities": {
                "version": IDENTITIES_VERSION,
                "evaluated": list(EVALUATED),
                "groups": len(groups),
                "findings": len(findings),
                "blocking": sum(1 for f in findings if f.severity == "blocking"),
                "validated_at": datetime.now(UTC).isoformat(),
            },
        }
    return {"findings": len(findings)}
