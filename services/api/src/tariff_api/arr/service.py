"""ARR orchestration over the database (ADR-0018): the reading track of a source, chapter
decisions, publication of reviewed ARR facts, the ARR history of a licensee, assumption
sets, formulations and filing drafts.  Every write is audited; nothing here approves a
candidate (that is the review service, with a person behind it) and nothing files."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..adapters.storage import ObjectNotFound, ObjectStore
from ..config import Settings
from ..errors import AppError
from ..inventory import NotAPdf, open_document
from ..models import (
    ArrAssumption,
    ArrAssumptionSet,
    ArrChapter,
    ArrFact,
    ArrFormulation,
    ArrProjectionLine,
    AuditEvent,
    CandidateRecord,
    DatasetKind,
    FilingDraft,
    SourceDocument,
    Utility,
    ValidatorFindingRecord,
)
from ..services.sources import enqueue_stage
from ..telemetry import request_id_var
from . import filing as fl
from . import formulate as fm
from .identities import Value, evaluate
from .taxonomy import load_mapping, load_taxonomy

ARR_STATES = ("chapters_proposed", "chapters_confirmed", "extracted", "awaiting_review", "published")


def _audit(session: Session, actor: str, action: str, entity_type: str, entity_id: str, **kw: Any) -> None:
    session.add(
        AuditEvent(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request_id_var.get(),
            **kw,
        )
    )


def is_fixture_source(src: SourceDocument) -> bool:
    return src.dataset.kind == DatasetKind.fixture


def utility_by_code(session: Session, code: str) -> Utility:
    u = session.execute(select(Utility).where(Utility.code == code)).scalar_one_or_none()
    if u is None:
        raise AppError("not_found", f"utility {code} not found")
    return u


# ------------------------------------------------------------------ reading track


def start_reading(session: Session, settings: Settings, src: SourceDocument, *, actor: str):
    """Queue chapter localisation for a parsed source whose licensee and commission mapping
    are known.  Re-reading a source restarts its ARR track; published facts stay."""
    if src.utility is None:
        raise AppError("validation_failed", "set the licensee of this order before reading its ARR")
    if src.parse_version is None or src.page_count is None:
        raise AppError("invalid_transition", "the order is not parsed yet; ARR reading starts after the parse stage")
    try:
        load_mapping(src.utility.commission.code)
    except FileNotFoundError as e:
        raise AppError("validation_failed", f"no ARR mapping for {src.utility.commission.code}") from e
    job = enqueue_stage(session, settings, src, "arr_localise_source", actor=actor)
    _audit(session, actor, "arr.read_requested", "source", str(src.id), after={"job_id": str(job.id)})
    return job


def chapters(session: Session, source_id: uuid.UUID) -> list[ArrChapter]:
    return list(
        session.execute(select(ArrChapter).where(ArrChapter.source_id == source_id).order_by(ArrChapter.ordinal))
        .scalars()
        .all()
    )


def update_chapter(
    session: Session, src: SourceDocument, chapter_id: uuid.UUID, *, actor: str, **changes: Any
) -> ArrChapter:
    ch = session.get(ArrChapter, chapter_id)
    if ch is None or ch.source_id != src.id:
        raise AppError("not_found", "chapter not on this source")
    if src.arr_state not in ("chapters_proposed", "chapters_confirmed"):
        raise AppError("invalid_transition", f"the ARR reading is {src.arr_state}; chapters are fixed")
    before = {"page_start": ch.page_start, "page_end": ch.page_end, "status": ch.status, "branch": ch.branch}
    for k in ("page_start", "page_end", "status", "branch", "note"):
        if changes.get(k) is not None:
            setattr(ch, k, changes[k])
    if ch.page_start < 1 or ch.page_end < ch.page_start or (src.page_count and ch.page_end > src.page_count):
        raise AppError("validation_failed", "chapter pages out of range")
    ch.origin = "reviewer"
    ch.decided_by, ch.decided_at = actor, datetime.now(UTC)
    _audit(session, actor, "arr.chapter_updated", "arr_chapter", str(ch.id), before=before, after=changes)
    return ch


def confirm_chapters(session: Session, settings: Settings, src: SourceDocument, *, actor: str, rationale: str):
    """The reviewer's checkpoint: proposed chapters become confirmed (excluded ones stay
    excluded) and extraction is queued."""
    if src.arr_state != "chapters_proposed":
        raise AppError("invalid_transition", f"the ARR reading is {src.arr_state}; nothing to confirm")
    if not rationale.strip():
        raise AppError("validation_failed", "confirming chapters needs a rationale")
    rows = chapters(session, src.id)
    if not any(c.status != "excluded" for c in rows):
        raise AppError("validation_failed", "no chapter to read: every chapter is excluded")
    now = datetime.now(UTC)
    for c in rows:
        if c.status == "proposed":
            c.status, c.decided_by, c.decided_at = "confirmed", actor, now
    src.arr_state = "chapters_confirmed"
    job = enqueue_stage(session, settings, src, "arr_extract_source", actor=actor)
    _audit(
        session,
        actor,
        "arr.chapters_confirmed",
        "source",
        str(src.id),
        after={"chapters": [str(c.id) for c in rows if c.status == "confirmed"], "job_id": str(job.id)},
        reason=rationale,
    )
    return job


def arr_candidates(session: Session, source_id: uuid.UUID) -> list[CandidateRecord]:
    return list(
        session.execute(
            select(CandidateRecord)
            .where(CandidateRecord.source_id == source_id, CandidateRecord.payload_kind == "arr")
            .order_by(CandidateRecord.category_code, CandidateRecord.period, CandidateRecord.decision_status)
        )
        .scalars()
        .all()
    )


def arr_findings(session: Session, source_id: uuid.UUID) -> list[ValidatorFindingRecord]:
    return list(
        session.execute(
            select(ValidatorFindingRecord).where(
                ValidatorFindingRecord.source_id == source_id, ValidatorFindingRecord.validator_id.like("ARR-%")
            )
        )
        .scalars()
        .all()
    )


# ------------------------------------------------------------------ publication


def publish(session: Session, src: SourceDocument, *, actor: str) -> dict[str, Any]:
    """Copy the finally approved ARR candidates of this order into ``arr_facts``.  Refused
    while a blocking identity finding is open.  A fact of the same identity from an earlier
    publication of this order is superseded, never overwritten.  Candidates still pending
    stay candidates; the summary counts them."""
    if src.arr_state not in ("awaiting_review", "published"):
        raise AppError("invalid_transition", f"the ARR reading is {src.arr_state}; publication follows review")
    if src.utility_id is None:
        raise AppError("validation_failed", "the order has no licensee")
    blocking = [f for f in arr_findings(session, src.id) if f.severity == "blocking"]
    if blocking:
        raise AppError(
            "validation_failed",
            f"{len(blocking)} blocking identity finding(s) open: correct or reject the lines involved first",
            extra={"findings": [f.message for f in blocking][:10]},
        )
    rows = arr_candidates(session, src.id)
    publishable = [c for c in rows if c.review_status in ("approved", "corrected") and c.published_release_id is None]
    pending = [c for c in rows if c.review_status in ("pending", "awaiting_second_review")]
    now = datetime.now(UTC)
    created = superseded = 0
    for c in publishable:
        rec = c.effective_record
        cat = rec.get("category_code") or ""
        prior = session.execute(
            select(ArrFact).where(
                ArrFact.utility_id == src.utility_id,
                ArrFact.line_code == rec["line_code"],
                ArrFact.fiscal_year == rec["fiscal_year"],
                ArrFact.value_type == rec["value_type"],
                ArrFact.source_id == src.id,
                ArrFact.category_code == cat,
                ArrFact.superseded_by_id.is_(None),
            )
        ).scalar_one_or_none()
        fact = ArrFact(
            utility_id=src.utility_id,
            source_id=src.id,
            candidate_id=c.id,
            line_code=rec["line_code"],
            fiscal_year=rec["fiscal_year"],
            value_type=rec["value_type"],
            category_code=cat,
            value_state=rec["value_state"],
            stated_value=rec.get("stated_value"),
            stated_unit=rec.get("stated_unit"),
            column_label=rec.get("column_label"),
            canonical_value=rec.get("canonical_value"),
            canonical_unit=rec.get("canonical_unit"),
            conversion=rec.get("conversion"),
            basis=rec.get("basis"),
            reason_category=rec.get("reason_category"),
            reasoning_quote=rec.get("reasoning_quote"),
            regulation_clause=rec.get("regulation_clause"),
            evidence=rec.get("evidence") or [],
            record=rec,
            review_status=c.review_status,
            is_fixture=c.is_fixture,
            published_by=actor,
        )
        session.add(fact)
        session.flush()
        if prior is not None:
            prior.superseded_by_id, prior.superseded_at = fact.id, now
            superseded += 1
        # decisions on a published candidate are no longer reversible (as for tariffs)
        c.published_release_id = fact.id
        created += 1
    src.arr_state = "published"
    summary = {"published": created, "superseded": superseded, "pending": len(pending), "published_at": now.isoformat()}
    src.arr_summary = {**(src.arr_summary or {}), "publication": summary}
    _audit(session, actor, "arr.published", "source", str(src.id), after=summary)
    return summary


# ------------------------------------------------------------------ history


def current_facts(session: Session, utility_id: uuid.UUID) -> list[tuple[ArrFact, SourceDocument]]:
    """Current (not superseded) ARR facts of a licensee, newest order first."""
    return list(
        session.execute(
            select(ArrFact, SourceDocument)
            .join(SourceDocument, SourceDocument.id == ArrFact.source_id)
            .where(ArrFact.utility_id == utility_id, ArrFact.superseded_by_id.is_(None))
            .order_by(SourceDocument.acquired_at.desc(), ArrFact.published_at.desc())
        ).all()
    )


def history(session: Session, utility: Utility) -> dict[str, Any]:
    """Line x year x voice, every order that printed it; the disallowance (petitioned less
    approved, same order) is computed here for display and never stored."""
    tax = load_taxonomy().by_code()
    lines: dict[str, dict[str, list[dict[str, Any]]]] = {}
    years: set[str] = set()
    for f, src in current_facts(session, utility.id):
        years.add(f.fiscal_year)
        ev = (f.evidence or [{}])[0]
        lines.setdefault(f.line_code, {}).setdefault(f.fiscal_year, []).append(
            {
                "fact_id": str(f.id),
                "value_type": f.value_type,
                "category_code": f.category_code or None,
                "value_state": f.value_state,
                "stated_value": f.stated_value,
                "stated_unit": f.stated_unit,
                "canonical_value": f.canonical_value,
                "canonical_unit": f.canonical_unit,
                "source_id": str(src.id),
                "order": src.original_filename,
                "page": ev.get("page_index"),
                "excerpt": ev.get("excerpt"),
                "is_fixture": f.is_fixture,
            }
        )
    out_lines = []
    for code in sorted(lines, key=lambda c: (c[0] not in "ECLR", c)):
        cells = []
        for fy in sorted(lines[code]):
            entries = lines[code][fy]
            disallowed = []
            for e in entries:
                # a disallowance is money the commission did not allow; energy, losses and
                # rates have no disallowance
                if (
                    e["value_type"] != "petitioned"
                    or e["canonical_value"] is None
                    or e["canonical_unit"] != "INR_crore"
                ):
                    continue
                for a in entries:
                    if (
                        a["value_type"] == "approved"
                        and a["source_id"] == e["source_id"]
                        and a["canonical_value"] is not None
                        and a["category_code"] == e["category_code"]
                    ):
                        disallowed.append(
                            {
                                "source_id": e["source_id"],
                                "value": str(Decimal(e["canonical_value"]) - Decimal(a["canonical_value"])),
                                "unit": e["canonical_unit"],
                            }
                        )
            cells.append({"fiscal_year": fy, "facts": entries, "disallowance": disallowed})
        item = tax.get(code)
        out_lines.append({"line_code": code, "label": item.label if item else code, "cells": cells})
    return {
        "utility": utility.code,
        "utility_name": utility.name,
        "years": sorted(years),
        "lines": out_lines,
        "kind": "fact",
        "is_fixture": utility.dataset.kind == DatasetKind.fixture,
    }


# ------------------------------------------------------------------ assumptions


def create_assumption_set(
    session: Session,
    utility: Utility,
    name: str,
    *,
    actor: str,
    based_on: uuid.UUID | None,
    organisation_id: uuid.UUID | None = None,
):
    latest = session.execute(
        select(func.max(ArrAssumptionSet.version)).where(
            ArrAssumptionSet.utility_id == utility.id,
            ArrAssumptionSet.name == name,
            ArrAssumptionSet.organisation_id.is_(None)
            if organisation_id is None
            else ArrAssumptionSet.organisation_id == organisation_id,
        )
    ).scalar_one()
    s = ArrAssumptionSet(
        utility_id=utility.id,
        organisation_id=organisation_id,
        name=name,
        version=(latest or 0) + 1,
        created_by=actor,
        based_on_id=based_on,
    )
    session.add(s)
    session.flush()
    if based_on is not None:
        base = session.get(ArrAssumptionSet, based_on)
        if base is None or base.utility_id != utility.id or base.organisation_id != organisation_id:
            raise AppError("not_found", "the assumption set to copy is not this licensee's")
        for a in assumptions_of(session, base.id):
            session.add(
                ArrAssumption(
                    set_id=s.id,
                    key=a.key,
                    fiscal_year=a.fiscal_year,
                    value=a.value,
                    unit=a.unit,
                    source_kind=a.source_kind,
                    clause_ref=a.clause_ref,
                    rationale=a.rationale,
                    entered_by=a.entered_by,
                )
            )
    _audit(session, actor, "arr.assumption_set_created", "arr_assumption_set", str(s.id), after={"name": name})
    return s


def assumptions_of(session: Session, set_id: uuid.UUID) -> list[ArrAssumption]:
    return list(
        session.execute(
            select(ArrAssumption)
            .where(ArrAssumption.set_id == set_id)
            .order_by(ArrAssumption.key, ArrAssumption.fiscal_year)
        )
        .scalars()
        .all()
    )


def _page_text(storage: ObjectStore, src: SourceDocument, page: int) -> str:
    try:
        doc = open_document(storage.get(ObjectStore.SOURCES, src.object_key))
    except (ObjectNotFound, NotAPdf) as e:
        raise AppError("storage_unavailable", "the regulation's file cannot be opened") from e
    if page < 1 or page > doc.page_count:
        raise AppError("validation_failed", f"the regulation has {doc.page_count} pages")
    return doc[page - 1].get_text("text", sort=True)


def _squash(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def add_assumption(
    session: Session,
    storage: ObjectStore,
    aset: ArrAssumptionSet,
    *,
    key: str,
    fiscal_year: str,
    value: str,
    unit: str,
    source_kind: str,
    rationale: str,
    clause_ref: dict[str, Any] | None,
    actor: str,
) -> ArrAssumption:
    """A user assumption needs a rationale.  A regulation parameter needs the clause: the
    regulation must be a registered source of ``order_type`` regulation (or amendment), the
    excerpt must be on the cited page, and the value must be printed in the excerpt —
    grounding is mechanical, never the model's word."""
    if aset.status != "draft":
        raise AppError("invalid_transition", "this assumption set is frozen; create a new version to change it")
    if not rationale.strip():
        raise AppError("validation_failed", "an assumption needs a rationale")
    try:
        Decimal(value)
    except Exception as e:  # noqa: BLE001
        raise AppError("validation_failed", f"value must be a decimal, got {value!r}") from e
    if fiscal_year and not fm.FY_RE.match(fiscal_year):
        raise AppError("validation_failed", "fiscal_year must look like FY2026-27, or be empty for every year")
    ref: dict[str, Any] | None = None
    if source_kind == "regulation_clause":
        if not clause_ref:
            raise AppError("validation_failed", "a regulation parameter needs clause_ref")
        reg = session.get(SourceDocument, uuid.UUID(str(clause_ref.get("source_id"))))
        if reg is None or reg.order_type not in ("regulation", "regulation_amendment"):
            raise AppError("validation_failed", "clause_ref.source_id must be a registered regulation")
        page = int(clause_ref.get("page_index") or 0)
        excerpt = _squash(str(clause_ref.get("excerpt") or ""))
        if not excerpt or excerpt not in _squash(_page_text(storage, reg, page)):
            raise AppError("validation_failed", f"the excerpt is not on page {page} of {reg.original_filename}")
        if not re.search(rf"(?<![0-9.]){re.escape(value)}(?![0-9])", excerpt):
            raise AppError("validation_failed", f"the value {value} is not printed in the cited excerpt")
        ref = {
            "source_id": str(reg.id),
            "source_name": reg.original_filename,
            "page_index": page,
            "citation": str(clause_ref.get("citation") or "")[:120],
            "excerpt": excerpt[:600],
            "confirmed_by": actor,
        }
    elif source_kind != "user":
        raise AppError("validation_failed", "source_kind is user or regulation_clause")
    existing = session.execute(
        select(ArrAssumption).where(
            ArrAssumption.set_id == aset.id, ArrAssumption.key == key, ArrAssumption.fiscal_year == fiscal_year
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError("validation_failed", f"{key} {fiscal_year or '(all years)'} is already in this set")
    a = ArrAssumption(
        set_id=aset.id,
        key=key,
        fiscal_year=fiscal_year,
        value=value,
        unit=unit,
        source_kind=source_kind,
        clause_ref=ref,
        rationale=rationale.strip(),
        entered_by=actor,
    )
    session.add(a)
    session.flush()
    _audit(
        session,
        actor,
        "arr.assumption_added",
        "arr_assumption",
        str(a.id),
        after={"key": key, "fiscal_year": fiscal_year, "value": value, "source_kind": source_kind},
        reason=rationale,
    )
    return a


# ------------------------------------------------------------------ formulations


def _base_facts(session: Session, utility: Utility) -> list[fm.BaseFact]:
    out = []
    for f, _src in current_facts(session, utility.id):
        if f.category_code or f.canonical_value is None or f.value_state not in ("value", "zero"):
            continue
        out.append(
            fm.BaseFact(
                str(f.id),
                f.line_code,
                f.fiscal_year,
                f.value_type,
                Decimal(f.canonical_value),
                f.canonical_unit,
                str(f.source_id),
            )
        )
    return out


def _facts_by_id(session: Session, ids: list[str]) -> list[fm.BaseFact]:
    rows = session.execute(select(ArrFact).where(ArrFact.id.in_([uuid.UUID(i) for i in ids]))).scalars().all()
    return [
        fm.BaseFact(
            str(f.id),
            f.line_code,
            f.fiscal_year,
            f.value_type,
            Decimal(f.canonical_value or "0"),
            f.canonical_unit,
            str(f.source_id),
        )
        for f in rows
    ]


def _assumption_inputs(rows: list[ArrAssumption]) -> list[fm.AssumptionIn]:
    return [
        fm.AssumptionIn(str(a.id), a.key, a.fiscal_year, Decimal(a.value), a.unit, a.source_kind, a.clause_ref)
        for a in rows
    ]


def _run(plan: fm.Plan, base_fy: str, targets: list[dict[str, str]], base: dict[str, fm.BaseFact], assumptions):
    last = max((t["fiscal_year"] for t in targets), key=lambda fy: int(fy[2:6]))
    lines = fm.compute(plan, base_fy=base_fy, last_fy=last, base=base, assumptions=assumptions)
    h = fm.input_hash(plan=plan, base_fy=base_fy, targets=targets, base=base, assumptions=assumptions)
    return lines, h


def create_formulation(
    session: Session,
    utility: Utility,
    *,
    name: str,
    base_fy: str,
    targets: list[dict[str, str]],
    assumption_set_id: uuid.UUID,
    actor: str,
) -> ArrFormulation:
    aset = session.get(ArrAssumptionSet, assumption_set_id)
    if aset is None or aset.utility_id != utility.id:
        raise AppError("not_found", "assumption set not found for this licensee")
    if not fm.FY_RE.match(base_fy) or not targets or any(not fm.FY_RE.match(t["fiscal_year"]) for t in targets):
        raise AppError("validation_failed", "base_fy and every target fiscal_year must look like FY2026-27")
    if any(int(t["fiscal_year"][2:6]) <= int(base_fy[2:6]) for t in targets):
        raise AppError("validation_failed", "targets must be after the base year")
    commission = utility.commission.code
    try:
        plan = fm.load_plan(commission)
    except FileNotFoundError as e:
        raise AppError("validation_failed", f"no formulation plan for {commission}") from e
    base = fm.select_base(_base_facts(session, utility), plan.base_rule, base_fy)
    assumptions = _assumption_inputs(assumptions_of(session, aset.id))
    lines, h = _run(plan, base_fy, targets, base, assumptions)
    tax = load_taxonomy()
    try:
        mapping = load_mapping(commission)
    except FileNotFoundError:
        mapping = None
    findings = []
    for fy in sorted({r.fiscal_year for r in lines}):
        values = [
            Value(r.line_code, r.value, r.unit, f"line:{r.line_code}@{fy}")
            for r in lines
            if r.fiscal_year == fy and r.status == "computed" and r.value is not None
        ]
        for f in evaluate(values, taxonomy=tax, mapping=mapping, group={"fiscal_year": fy, "value_type": "projection"}):
            findings.append(
                {"identity_id": f.identity_id, "severity": f.severity, "message": f.message, "lines": f.lines}
            )
    blocked = [r for r in lines if r.status == "blocked"]
    formulation = ArrFormulation(
        utility_id=utility.id,
        organisation_id=aset.organisation_id,  # a formulation belongs to whoever owns its assumptions
        name=name,
        base_fy=base_fy,
        targets=targets,
        plan_id=plan.id,
        plan_version=plan.version,
        library_version=fm.LIBRARY_VERSION,
        base_rule=plan.base_rule.model_dump(),
        assumption_set_id=aset.id,
        inputs={
            "base_facts": sorted(f.fact_id for f in base.values()),
            "assumptions": sorted(a.assumption_id for a in assumptions),
        },
        input_hash=h,
        summary={
            "plan_status": plan.status,
            "lines": len(lines),
            "blocked": len(blocked),
            "blocked_lines": [f"{r.line_code} {r.fiscal_year}: {r.blocked_reason}" for r in blocked],
            "identity_findings": findings,
            "kind": "projection",
        },
        is_fixture=utility.dataset.kind == DatasetKind.fixture,
        created_by=actor,
    )
    session.add(formulation)
    session.flush()
    for r in lines:
        session.add(
            ArrProjectionLine(
                formulation_id=formulation.id,
                line_code=r.line_code,
                fiscal_year=r.fiscal_year,
                status=r.status,
                value=str(r.value) if r.value is not None else None,
                unit=r.unit,
                formula_id=r.formula_id,
                formula_version=fm.LIBRARY_VERSION,
                inputs=r.inputs,
                regulation_clause=r.regulation_clause,
                blocked_reason=r.blocked_reason,
            )
        )
    _audit(
        session,
        actor,
        "arr.formulation_created",
        "arr_formulation",
        str(formulation.id),
        after={"input_hash": h, "blocked": len(blocked), "plan": f"{plan.id} v{plan.version}"},
    )
    return formulation


def projection_lines(session: Session, formulation_id: uuid.UUID) -> list[ArrProjectionLine]:
    return list(
        session.execute(
            select(ArrProjectionLine)
            .where(ArrProjectionLine.formulation_id == formulation_id)
            .order_by(ArrProjectionLine.fiscal_year, ArrProjectionLine.line_code)
        )
        .scalars()
        .all()
    )


def freeze_formulation(session: Session, f: ArrFormulation, *, actor: str) -> ArrFormulation:
    if f.status == "frozen":
        raise AppError("invalid_transition", "this formulation is already frozen")
    if f.summary.get("blocked"):
        raise AppError(
            "arr_parameter_missing",
            f"{f.summary['blocked']} line(s) blocked; supply the missing parameters in a new formulation first",
            extra={"blocked_lines": f.summary.get("blocked_lines", [])[:20]},
        )
    now = datetime.now(UTC)
    f.status, f.frozen_by, f.frozen_at = "frozen", actor, now
    aset = session.get(ArrAssumptionSet, f.assumption_set_id)
    assert aset is not None
    if aset.status == "draft":
        aset.status, aset.frozen_at = "frozen", now
    _audit(session, actor, "arr.formulation_frozen", "arr_formulation", str(f.id), after={"input_hash": f.input_hash})
    return f


def reproduce(session: Session, f: ArrFormulation) -> dict[str, Any]:
    """Recompute from the recorded inputs (facts by id, even if superseded since; the frozen
    assumption set) and compare line by line and hash for hash."""
    utility = session.get(Utility, f.utility_id)
    assert utility is not None
    plan = fm.load_plan(utility.commission.code, f.plan_version)
    rule = fm.BaseRule.model_validate(f.base_rule)
    base = fm.select_base(_facts_by_id(session, f.inputs.get("base_facts", [])), rule, f.base_fy)
    assumptions = _assumption_inputs(
        [a for a in assumptions_of(session, f.assumption_set_id) if str(a.id) in set(f.inputs.get("assumptions", []))]
    )
    lines, h = _run(plan, f.base_fy, f.targets, base, assumptions)
    stored = {(p.line_code, p.fiscal_year): (p.status, p.value) for p in projection_lines(session, f.id)}
    now = {(r.line_code, r.fiscal_year): (r.status, str(r.value) if r.value is not None else None) for r in lines}
    diffs = [
        {"line": f"{k[0]} {k[1]}", "stored": stored.get(k), "recomputed": now.get(k)}
        for k in sorted(set(stored) | set(now))
        if stored.get(k) != now.get(k)
    ]
    return {
        "identical": not diffs and h == f.input_hash,
        "input_hash": f.input_hash,
        "recomputed_hash": h,
        "differences": diffs,
        "library_version": fm.LIBRARY_VERSION,
    }


# ------------------------------------------------------------------ filing drafts


def generate_draft(
    session: Session, storage: ObjectStore, f: ArrFormulation, *, actor: str, template_version: int | None = None
) -> FilingDraft:
    if f.status != "frozen":
        raise AppError("invalid_transition", "freeze the formulation before drafting a filing from it")
    utility = session.get(Utility, f.utility_id)
    assert utility is not None
    commission = utility.commission.code
    try:
        template = fl.load_template(commission, template_version)
        plan = fm.load_plan(commission, f.plan_version)
    except (FileNotFoundError, StopIteration) as e:
        raise AppError("validation_failed", f"no petition template or plan for {commission}") from e
    tax = load_taxonomy().by_code()
    projections = {
        (p.line_code, p.fiscal_year): fl.ProjectionRef(
            p.line_code,
            p.fiscal_year,
            p.status,
            p.value,
            p.unit,
            p.formula_id,
            fm.describe(next(pl for pl in plan.lines if pl.line_code == p.line_code)),
            p.blocked_reason,
            p.regulation_clause,
            p.inputs,
        )
        for p in projection_lines(session, f.id)
    }
    facts: dict[tuple[str, str, str], fl.FactRef] = {}
    for fact, src in current_facts(session, utility.id):
        if fact.category_code:
            continue
        key = (fact.line_code, fact.fiscal_year, fact.value_type)
        if key in facts:
            continue  # newest order first
        ev = (fact.evidence or [{}])[0]
        facts[key] = fl.FactRef(
            str(fact.id),
            fact.line_code,
            fact.fiscal_year,
            fact.value_type,
            fact.canonical_value,
            fact.canonical_unit,
            str(src.id),
            src.original_filename,
            ev.get("page_index"),
            ev.get("excerpt"),
        )
    assumptions = {
        (a.key, a.fiscal_year): fl.AssumptionRef(
            str(a.id), a.key, a.fiscal_year, a.value, a.unit, a.source_kind, a.rationale, a.entered_by, a.clause_ref
        )
        for a in assumptions_of(session, f.assumption_set_id)
    }
    ctx = fl.DraftContext(
        utility_code=utility.code,
        utility_name=utility.name,
        formulation_id=str(f.id),
        formulation_name=f.name,
        base_fy=f.base_fy,
        targets=[t["fiscal_year"] for t in f.targets],
        projections=projections,
        facts=facts,
        assumptions=assumptions,
        formula_words={pl.line_code: fm.describe(pl) for pl in plan.lines},
        labels={code: item.label for code, item in tax.items()},
        is_fixture=f.is_fixture,
    )
    try:
        docx, xlsx, trace = fl.render(template, ctx)
    except fl.FilingError as e:
        raise AppError(e.code, str(e), extra=e.detail) from e
    draft_id = uuid.uuid4()
    prefix = f"filing/{utility.code}/{f.id}/{draft_id}"
    docx_key, xlsx_key = f"{prefix}/petition.docx", f"{prefix}/formats.xlsx"
    storage.put(
        ObjectStore.ARTEFACTS,
        docx_key,
        docx,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    storage.put(
        ObjectStore.ARTEFACTS, xlsx_key, xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    draft = FilingDraft(
        id=draft_id,
        formulation_id=f.id,
        template_id=template.id,
        template_version=template.version,
        template_status=template.status,
        docx_key=docx_key,
        docx_sha256=hashlib.sha256(docx).hexdigest(),
        xlsx_key=xlsx_key,
        xlsx_sha256=hashlib.sha256(xlsx).hexdigest(),
        trace=trace,
        is_fixture=f.is_fixture,
        generated_by=actor,
    )
    session.add(draft)
    session.flush()
    _audit(
        session,
        actor,
        "arr.filing_draft_generated",
        "filing_draft",
        str(draft.id),
        after={"numbers": trace["numbers"], "template": f"{template.id} v{template.version} ({template.status})"},
    )
    return draft
