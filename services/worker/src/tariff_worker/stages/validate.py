"""Stage ``extracted -> validated -> awaiting_review`` (Sections 6.9, 6.10): run every
deterministic validator over the source's candidates, attach findings, add the
``validator_finding`` risk tag and re-route affected candidates to individual review, and
move the source to ``awaiting_review``.  Nothing here approves, publishes or corrects."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select

from tariff_api.adapters.storage import ObjectNotFound, ObjectStore
from tariff_api.db import session_scope
from tariff_api.inventory import NotAPdf, open_document
from tariff_api.models import (
    CandidateRecord,
    ClauseValueRecord,
    ConditionRecordRow,
    DocumentHeading,
    FamilyDisposition,
    LocalisationRegion,
    SourceDocument,
    SourceState,
    StructureCell,
    TableGridRecord,
    ValidatorFindingRecord,
)
from tariff_api.profiles import load_profile
from tariff_api.services.sources import transition
from tariff_api.tariff_schema import Candidate
from tariff_api.validators import VALIDATORS_VERSION, ValidationContext, run_all

from ..runner import JobContext, JobFailure


def validate_source(ctx: JobContext) -> dict:
    source_id = uuid.UUID(ctx.payload["source_id"])
    with session_scope() as s:
        src = s.get(SourceDocument, source_id)
        if src is None:
            raise JobFailure("not_found", f"source {source_id} no longer exists", retry=False)
        if src.state not in (
            SourceState.extracted,
            SourceState.validated,
            SourceState.awaiting_review,
            SourceState.needs_reprocessing,
        ):
            raise JobFailure(
                "invalid_transition", f"source in state {src.state.value}; validate needs extracted", retry=False
            )
        profile = load_profile(src.reading_profile_id, src.reading_profile_version)
        rows = s.execute(select(CandidateRecord).where(CandidateRecord.source_id == source_id)).scalars().all()
        cands = [Candidate.model_validate(r.record) for r in rows]
        by_key: dict[str, list[CandidateRecord]] = {}
        for r in rows:
            by_key.setdefault(r.candidate_key, []).append(r)
        roles: dict[int, set[str]] = {}
        for reg in s.execute(select(LocalisationRegion).where(LocalisationRegion.source_id == source_id)).scalars():
            for p in range(reg.page_start, reg.page_end + 1):
                roles.setdefault(p, set()).add(reg.role)
        cells = {
            (c.page_index, c.grid_ordinal, c.row, c.col): c.raw
            for c in s.execute(select(StructureCell).where(StructureCell.source_id == source_id)).scalars()
        }
        clause_lines = {
            (v.page_index, v.line_no): v.line_text
            for v in s.execute(select(ClauseValueRecord).where(ClauseValueRecord.source_id == source_id)).scalars()
        }
        inventory = sorted(
            {
                h.code_canonical
                for h in s.execute(select(DocumentHeading).where(DocumentHeading.source_id == source_id)).scalars()
                if h.kind == profile.schedule_heading_kind and h.code_canonical
            }
        )
        dispositions = {
            d.family: d.disposition
            for d in s.execute(select(FamilyDisposition).where(FamilyDisposition.source_id == source_id)).scalars()
        }
        # Milestone 4b inputs: the consolidated schedule text, the amendment table rows and
        # the condition records
        approved_pages = sorted(p for p, rs in roles.items() if rs & {"approved_schedule", "approved_summary"})
        amendment_pages = sorted(p for p, rs in roles.items() if "amendment_diff" in rs)
        amendment_grids = [
            g.object_key
            for g in s.execute(
                select(TableGridRecord).where(
                    TableGridRecord.source_id == source_id,
                    TableGridRecord.is_primary.is_(True),
                    TableGridRecord.page_index.in_(amendment_pages or [-1]),
                )
            ).scalars()
        ]
        object_key, sha = src.object_key, src.sha256
        condition_texts = [
            r.text
            for r in s.execute(select(ConditionRecordRow).where(ConditionRecordRow.source_id == source_id)).scalars()
        ] + [
            fn
            for c in s.execute(select(StructureCell).where(StructureCell.source_id == source_id)).scalars()
            for fn in c.footnotes
        ]
        ctxv = ValidationContext(
            candidates=cands,
            region_roles_by_page=roles,
            cells=cells,
            clause_lines=clause_lines,
            inventory_codes=inventory,
            dispositions=dispositions,
            utilities=profile.utilities,
            profile_id=profile.id,
            secondary_authoritative=profile.secondary_authoritative,
            approved_page_texts=_page_texts(ctx, object_key, sha, approved_pages),
            amendment_rows=_amendment_rows(ctx, amendment_grids),
            condition_texts=condition_texts,
        )
        findings = run_all(ctxv)
        s.execute(delete(ValidatorFindingRecord).where(ValidatorFindingRecord.source_id == source_id))
        per_candidate: dict[uuid.UUID, list[str]] = {}
        blocking: dict[uuid.UUID, int] = {}
        for f in findings:
            ids: list[uuid.UUID] = []
            for k in f.candidate_keys:
                for r in by_key.get(k[:400], []):
                    ids.append(r.id)
                    per_candidate.setdefault(r.id, []).append(f.validator_id)
                    if f.severity == "blocking":
                        blocking[r.id] = blocking.get(r.id, 0) + 1
            s.add(
                ValidatorFindingRecord(
                    source_id=source_id,
                    validator_id=f.validator_id,
                    severity=f.severity,
                    message=f.message,
                    candidate_ids=[str(i) for i in ids],
                    detail=f.detail,
                    validators_version=VALIDATORS_VERSION,
                )
            )
        for r in rows:
            ids = per_candidate.get(r.id, [])
            r.finding_count = len(ids)
            r.blocking_finding_count = blocking.get(r.id, 0)
            actionable = [v for v in ids]
            if actionable and "validator_finding" not in r.risk_tags:
                # info-only findings do not change routing; warnings and blockers do
                sev = [f.severity for f in findings if r.candidate_key in [k[:400] for k in f.candidate_keys]]
                if any(x in ("warning", "blocking") for x in sev):
                    r.risk_tags = [*r.risk_tags, "validator_finding"]
                    r.routing = "individual"
                    if r.confidence == "high":
                        r.confidence = "medium"
        summary = {
            "validators_version": VALIDATORS_VERSION,
            "findings": len(findings),
            "by_severity": _count([f.severity for f in findings]),
            "by_validator": _count([f.validator_id for f in findings]),
            "candidates_with_findings": len(per_candidate),
            "candidates_blocked": len(blocking),
            "source_level_findings": sum(1 for f in findings if not f.candidate_keys),
            "families_without_disposition": [
                f.detail["family"] for f in findings if f.validator_id == "VAL-06" and "family" in f.detail
            ],
            "routing": _count([r.routing for r in rows]),
            "confidence": _count([r.confidence for r in rows]),
        }
        src.validation_summary = summary
        src.validators_version = VALIDATORS_VERSION
        src.validated_at = datetime.now(UTC)
        if src.state == SourceState.extracted:
            transition(s, src, SourceState.validated, actor=ctx.worker, reason=f"validators@{VALIDATORS_VERSION}")
        if src.state == SourceState.validated:
            transition(
                s,
                src,
                SourceState.awaiting_review,
                actor=ctx.worker,
                reason=f"{len(rows)} candidates routed: {summary['routing']}",
            )
    return {"findings": summary["findings"], "candidates": len(rows), "blocked": summary["candidates_blocked"]}


def _count(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def _page_texts(ctx: JobContext, object_key: str, sha: str, pages: list[int]) -> dict[int, str]:
    if not pages:
        return {}
    storage: ObjectStore = ctx.adapters.storage
    try:
        data = storage.get(ObjectStore.SOURCES, object_key)
    except ObjectNotFound as e:
        raise JobFailure("storage_unavailable", f"object {object_key} missing", retry=True) from e
    try:
        doc = open_document(data)
    except NotAPdf as e:
        raise JobFailure("source_unreadable", str(e), retry=False) from e
    return {p: doc[p - 1].get_text("text", sort=True) for p in pages if p <= doc.page_count}


def _amendment_rows(ctx: JobContext, grid_keys: list[str]) -> list[dict]:
    """Rows of `Existing description / Modified description` grids, read from the parse
    stage's grid artefacts (text-only tables yield no numeric structure cells)."""
    import json

    storage: ObjectStore = ctx.adapters.storage
    out: list[dict] = []
    for key in grid_keys:
        try:
            grid = json.loads(storage.get(ObjectStore.ARTEFACTS, key))["grid"]
        except (ObjectNotFound, ValueError, KeyError):
            continue
        rows = grid.get("rows") or []
        if not rows:
            continue
        header = [(h or "").lower() for h in rows[0]]
        try:
            ex = next(i for i, h in enumerate(header) if "existing" in h)
            mo = next(i for i, h in enumerate(header) if "modified" in h)
        except StopIteration:
            continue
        for r_i, row in enumerate(rows[1:], start=1):
            out.append(
                {
                    "page": grid.get("page_index"),
                    "grid": grid.get("ordinal"),
                    "row": r_i,
                    "clause": (row[0] or "").strip() if row else None,
                    "existing": (row[ex] or "").strip() if ex < len(row) else None,
                    "modified": (row[mo] or "").strip() if mo < len(row) else None,
                }
            )
    return out
