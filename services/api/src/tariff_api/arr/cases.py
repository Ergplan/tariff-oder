"""ARR cases (ADR-0019): a client organisation's ARR process for one licensee, from setup to
a draft petition, driving the Increment A engine.  A case adds no arithmetic: it owns an
assumption set, runs formulations on it, freezes one and drafts the filing from it, and
tells the client at every step what is ready and what is missing.

Filing kinds:
- ``annual_arr``: the ARR of the year after the base, as petitioned.
- ``myt``: every year of a control period, as petitioned for the control period.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.storage import ObjectStore
from ..errors import AppError
from ..models import (
    ArrAssumption,
    ArrAssumptionSet,
    ArrCase,
    ArrFormulation,
    AuditEvent,
    LibraryEntry,
    Organisation,
    SourceDocument,
    Utility,
)
from ..telemetry import request_id_var
from . import formulate as fm
from . import service as arr

CASE_VALUE_TYPE = {"annual_arr": "petitioned", "myt": "control_period"}


def _audit(session: Session, actor: str, action: str, case: ArrCase, **kw: Any) -> None:
    session.add(
        AuditEvent(
            actor=actor,
            action=action,
            entity_type="arr_case",
            entity_id=str(case.id),
            request_id=request_id_var.get(),
            **kw,
        )
    )


def validate_targets(filing_kind: str, base_fy: str, years: list[str]) -> list[dict[str, str]]:
    if not fm.FY_RE.match(base_fy) or any(not fm.FY_RE.match(y) for y in years):
        raise AppError("validation_failed", "years must look like FY2026-27")
    years = sorted(set(years), key=lambda y: int(y[2:6]))
    expected = [fm.fy_shift(base_fy, i + 1) for i in range(len(years))]
    if years != expected:
        raise AppError(
            "validation_failed",
            f"target years must follow the base year without gaps: expected {', '.join(expected)}",
        )
    if filing_kind == "annual_arr" and len(years) != 1:
        raise AppError("validation_failed", "an annual ARR case has one target year: the year after the base")
    if filing_kind == "myt" and len(years) < 2:
        raise AppError("validation_failed", "an MYT case covers the years of a control period (two or more)")
    return [{"fiscal_year": y, "value_type": CASE_VALUE_TYPE[filing_kind]} for y in years]


def create_case(
    session: Session,
    *,
    organisation: Organisation,
    utility: Utility,
    title: str,
    filing_kind: str,
    base_fy: str,
    target_years: list[str],
    copy_from: uuid.UUID | None,
    notes: str | None,
    actor: str,
) -> ArrCase:
    if utility.licensee_kind == "generation":
        raise AppError("validation_failed", "ARR cases are for distribution and transmission licensees")
    try:
        fm.load_plan(utility.commission.code)
    except FileNotFoundError as e:
        raise AppError(
            "validation_failed",
            f"no formulation plan for {utility.commission.code} yet: its ARR cannot be formulated",
        ) from e
    targets = validate_targets(filing_kind, base_fy, target_years)
    base_set = None
    if copy_from is not None:
        base_set = session.get(ArrAssumptionSet, copy_from)
        if base_set is None or base_set.organisation_id != organisation.id or base_set.utility_id != utility.id:
            raise AppError("not_found", "assumption set to copy not found in this organisation for this licensee")
    aset = arr.create_assumption_set(
        session,
        utility,
        f"Case: {title}"[:120],
        actor=actor,
        based_on=base_set.id if base_set else None,
        organisation_id=organisation.id,
    )
    case = ArrCase(
        organisation_id=organisation.id,
        utility_id=utility.id,
        title=title,
        filing_kind=filing_kind,
        base_fy=base_fy,
        targets=targets,
        assumption_set_id=aset.id,
        notes=notes,
        created_by=actor,
    )
    session.add(case)
    session.flush()
    _audit(
        session,
        actor,
        "arr_case.created",
        case,
        after={"utility": utility.code, "kind": filing_kind, "targets": targets},
    )
    return case


def _touch(case: ArrCase, status: str | None = None) -> None:
    if status:
        case.status = status
    case.updated_at = datetime.now(UTC)


def _needed_base(plan: fm.Plan) -> list[str]:
    """Lines whose base-year value the plan reads (carried forward or escalated)."""
    out: list[str] = []
    for pl in plan.lines:
        if pl.formula in ("carry_forward", "escalate"):
            code = pl.inputs.get("base") if isinstance(pl.inputs.get("base"), str) else pl.line_code
            if code not in out:
                out.append(str(code))
    return out


def _needed_params(plan: fm.Plan) -> list[tuple[str, str]]:
    """(key, the line that needs it) for every assumption the plan reads."""
    out: list[tuple[str, str]] = []
    for pl in plan.lines:
        keys = list(pl.params.values())
        if pl.formula == "assumption" and "value" not in pl.params:
            keys.append(pl.line_code)
        for k in keys:
            if (k, pl.line_code) not in out:
                out.append((k, pl.line_code))
    return out


def readiness(session: Session, case: ArrCase) -> dict[str, Any]:
    """What the case has and what it lacks, line by line, before anything is computed."""
    utility = session.get(Utility, case.utility_id)
    assert utility is not None
    plan = fm.load_plan(utility.commission.code)
    facts = arr._base_facts(session, utility)
    base = fm.select_base(facts, plan.base_rule, case.base_fy)
    docs = (
        session.execute(
            select(LibraryEntry).where(
                LibraryEntry.utility_id == utility.id, LibraryEntry.fiscal_year.in_([case.base_fy, ""])
            )
        )
        .scalars()
        .all()
    )
    doc_rows = []
    for d in docs:
        src = session.get(SourceDocument, d.source_id) if d.source_id else None
        doc_rows.append(
            {
                "kind": d.document_kind,
                "fiscal_year": d.fiscal_year,
                "status": d.status,
                "arr_state": src.arr_state if src else None,
                "source_id": str(src.id) if src else None,
            }
        )
    base_rows = []
    for code in _needed_base(plan):
        f = base.get(code)
        base_rows.append(
            {
                "line_code": code,
                "present": f is not None,
                "value": str(f.value) if f else None,
                "value_type": f.value_type if f else None,
                "fact_id": f.fact_id if f else None,
            }
        )
    supplied = {(a.key, a.fiscal_year) for a in arr.assumptions_of(session, case.assumption_set_id)}
    years = [t["fiscal_year"] for t in case.targets]
    param_rows = []
    for key, line in _needed_params(plan):
        missing = [y for y in years if (key, y) not in supplied and (key, "") not in supplied]
        param_rows.append({"key": key, "for_line": line, "missing_years": missing, "supplied": not missing})
    missing_base = [r["line_code"] for r in base_rows if not r["present"]]
    missing_params = [r["key"] for r in param_rows if not r["supplied"]]
    return {
        "plan": {"id": plan.id, "version": plan.version, "status": plan.status},
        "base_fy": case.base_fy,
        "years": years,
        "base_facts": base_rows,
        "parameters": param_rows,
        "documents": doc_rows,
        "missing_base_facts": missing_base,
        "missing_parameters": missing_params,
        "ready_to_formulate": not missing_base and not missing_params,
        "note": (
            "Base facts come only from reviewed, published ARR facts of this licensee; a missing one means the "
            "order that prints it is not in the library, not read, or not yet reviewed."
        ),
    }


def _case_set(session: Session, case: ArrCase) -> ArrAssumptionSet:
    aset = session.get(ArrAssumptionSet, case.assumption_set_id)
    assert aset is not None
    return aset


def add_assumption(session: Session, storage: ObjectStore, case: ArrCase, *, actor: str, **body: Any) -> ArrAssumption:
    if case.status in ("frozen", "drafted", "closed"):
        raise AppError("invalid_transition", "the case is frozen; revise it to change assumptions")
    a = arr.add_assumption(session, storage, _case_set(session, case), actor=actor, **body)
    _touch(case, "assumptions")
    return a


def remove_assumption(session: Session, case: ArrCase, assumption_id: uuid.UUID, *, actor: str) -> None:
    aset = _case_set(session, case)
    if aset.status != "draft":
        raise AppError("invalid_transition", "the case's assumptions are frozen; revise it to change them")
    a = session.get(ArrAssumption, assumption_id)
    if a is None or a.set_id != aset.id:
        raise AppError("not_found", "assumption not in this case")
    _audit(
        session,
        actor,
        "arr_case.assumption_removed",
        case,
        before={"key": a.key, "fiscal_year": a.fiscal_year, "value": a.value},
    )
    session.delete(a)
    _touch(case)


def formulate(session: Session, case: ArrCase, *, actor: str) -> ArrFormulation:
    if case.status in ("frozen", "drafted", "closed"):
        raise AppError("invalid_transition", "the case is frozen; revise it to formulate again")
    utility = session.get(Utility, case.utility_id)
    assert utility is not None
    runs = session.execute(
        select(ArrFormulation.id).where(ArrFormulation.assumption_set_id == case.assumption_set_id)
    ).all()
    f = arr.create_formulation(
        session,
        utility,
        name=f"{case.title} — run {len(runs) + 1}"[:120],
        base_fy=case.base_fy,
        targets=case.targets,
        assumption_set_id=case.assumption_set_id,
        actor=actor,
    )
    case.formulation_id = f.id
    _touch(case, "formulated")
    _audit(
        session,
        actor,
        "arr_case.formulated",
        case,
        after={"formulation_id": str(f.id), "blocked": f.summary.get("blocked")},
    )
    return f


def freeze(session: Session, case: ArrCase, *, actor: str) -> ArrFormulation:
    if case.formulation_id is None or case.status != "formulated":
        raise AppError("invalid_transition", "formulate the case before freezing it")
    f = session.get(ArrFormulation, case.formulation_id)
    assert f is not None
    arr.freeze_formulation(session, f, actor=actor)
    _touch(case, "frozen")
    _audit(session, actor, "arr_case.frozen", case, after={"input_hash": f.input_hash})
    return f


def draft(session: Session, storage: ObjectStore, case: ArrCase, *, actor: str):
    if case.formulation_id is None or case.status not in ("frozen", "drafted"):
        raise AppError("invalid_transition", "freeze the case's formulation before drafting the petition")
    f = session.get(ArrFormulation, case.formulation_id)
    assert f is not None
    d = arr.generate_draft(session, storage, f, actor=actor)
    case.draft_id = d.id
    _touch(case, "drafted")
    _audit(session, actor, "arr_case.drafted", case, after={"draft_id": str(d.id)})
    return d


def revise(session: Session, case: ArrCase, *, actor: str) -> ArrCase:
    """A new assumption-set version copied from the frozen one; the frozen formulation and its
    drafts stay as they are, for the record."""
    if case.status not in ("frozen", "drafted"):
        raise AppError("invalid_transition", "only a frozen case is revised; a draft case is edited directly")
    utility = session.get(Utility, case.utility_id)
    assert utility is not None
    old = _case_set(session, case)
    new = arr.create_assumption_set(
        session, utility, old.name, actor=actor, based_on=old.id, organisation_id=case.organisation_id
    )
    case.assumption_set_id, case.formulation_id, case.draft_id = new.id, None, None
    _touch(case, "assumptions")
    _audit(session, actor, "arr_case.revised", case, after={"assumption_set": f"{new.name} v{new.version}"})
    return case
