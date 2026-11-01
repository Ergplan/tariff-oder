"""ARR cases (ADR-0019): a client organisation's ARR process for one licensee, from setup to
a draft petition, driving the Increment A engine.  A case adds no arithmetic: it owns an
assumption set, runs formulations on it, freezes one and drafts the filing from it, and
tells the client at every step what is ready and what is missing.

Filing kinds:
- ``annual_arr``: the ARR of the year after the base, as petitioned.
- ``myt``: every year of a control period, as petitioned for the control period.
- ``true_up``: a past year's audited actuals against the commission's approval (ADR-0020).
- ``apr``: the running year's actuals and estimates against the approval (ADR-0020).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.storage import ObjectStore
from ..errors import AppError
from ..models import (
    ArrActual,
    ArrAssumption,
    ArrAssumptionSet,
    ArrCase,
    ArrFact,
    ArrFormulation,
    AuditEvent,
    DatasetKind,
    FilingDraft,
    LibraryEntry,
    Organisation,
    SourceDocument,
    Utility,
)
from ..telemetry import request_id_var
from . import filing as fl
from . import formulate as fm
from . import service as arr
from . import trueup as tu

CASE_VALUE_TYPE = {
    "annual_arr": "petitioned",
    "myt": "control_period",
    "true_up": "final_true_up",
    "apr": "provisional_true_up",
}
TRUE_UP_KINDS = ("true_up", "apr")


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
    if filing_kind in TRUE_UP_KINDS:
        # the year trued up is the case's base year and its only target
        if sorted(set(years)) != [base_fy]:
            raise AppError("validation_failed", f"a {filing_kind} case covers one year: target_years = [{base_fy}]")
        return [{"fiscal_year": base_fy, "value_type": CASE_VALUE_TYPE[filing_kind]}]
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
        if filing_kind not in TRUE_UP_KINDS:
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


def _documents(session: Session, utility: Utility, fy: str) -> list[dict[str, Any]]:
    docs = (
        session.execute(
            select(LibraryEntry).where(LibraryEntry.utility_id == utility.id, LibraryEntry.fiscal_year.in_([fy, ""]))
        )
        .scalars()
        .all()
    )
    out = []
    for d in docs:
        src = session.get(SourceDocument, d.source_id) if d.source_id else None
        out.append(
            {
                "kind": d.document_kind,
                "fiscal_year": d.fiscal_year,
                "status": d.status,
                "arr_state": src.arr_state if src else None,
                "source_id": str(src.id) if src else None,
            }
        )
    return out


def readiness(session: Session, case: ArrCase) -> dict[str, Any]:
    """What the case has and what it lacks, line by line, before anything is computed."""
    if case.filing_kind in TRUE_UP_KINDS:
        return true_up_readiness(session, case)
    utility = session.get(Utility, case.utility_id)
    assert utility is not None
    plan = fm.load_plan(utility.commission.code)
    facts = arr._base_facts(session, utility)
    base = fm.select_base(facts, plan.base_rule, case.base_fy)
    doc_rows = _documents(session, utility, case.base_fy)
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


def _not_true_up(case: ArrCase, what: str) -> None:
    if case.filing_kind in TRUE_UP_KINDS:
        raise AppError("invalid_transition", f"a {case.filing_kind} case has no {what}; use its statement")


def formulate(session: Session, case: ArrCase, *, actor: str) -> ArrFormulation:
    _not_true_up(case, "formulation")
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
    _not_true_up(case, "formulation")
    if case.formulation_id is None or case.status != "formulated":
        raise AppError("invalid_transition", "formulate the case before freezing it")
    f = session.get(ArrFormulation, case.formulation_id)
    assert f is not None
    arr.freeze_formulation(session, f, actor=actor)
    _touch(case, "frozen")
    _audit(session, actor, "arr_case.frozen", case, after={"input_hash": f.input_hash})
    return f


def draft(session: Session, storage: ObjectStore, case: ArrCase, *, actor: str):
    if case.filing_kind in TRUE_UP_KINDS:
        return draft_true_up(session, storage, case, actor=actor)
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
    if case.filing_kind in TRUE_UP_KINDS:
        # the frozen statement stays in the audit and in each draft's trace
        case.statement, case.draft_id = None, None
        _touch(case, "assumptions")
        _audit(session, actor, "arr_case.revised", case, after={"kind": case.filing_kind})
        return case
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


# ------------------------------------------------------------------ true-up and APR (ADR-0020)

ACTUAL_SOURCE_KINDS = ("fact", "document", "statement", "estimate")


def _year_of(case: ArrCase) -> str:
    return case.targets[0]["fiscal_year"]


def _approved(session: Session, utility: Utility, fy: str) -> dict[str, tu.ApprovedRef]:
    """The current reviewed approval of each line for the year, newest order first."""
    out: dict[str, tu.ApprovedRef] = {}
    for f, src in arr.current_facts(session, utility.id):
        if (
            f.value_type != "approved"
            or f.fiscal_year != fy
            or f.category_code
            or f.canonical_value is None
            or f.value_state not in ("value", "zero")
            or f.line_code in out
        ):
            continue
        ev = (f.evidence or [{}])[0]
        out[f.line_code] = tu.ApprovedRef(
            str(f.id),
            f.line_code,
            f.canonical_value,
            f.canonical_unit,
            str(src.id),
            src.original_filename,
            ev.get("page_index"),
            ev.get("excerpt"),
            f.is_fixture,
        )
    return out


def actuals_of(session: Session, case: ArrCase) -> list[ArrActual]:
    return list(
        session.execute(select(ArrActual).where(ArrActual.case_id == case.id).order_by(ArrActual.line_code))
        .scalars()
        .all()
    )


def _actual_ref(a: ArrActual) -> tu.ActualRef:
    origin: dict[str, Any] = {"entered_by": a.entered_by, "rationale": a.rationale}
    if a.source_kind == "fact":
        origin.update({"fact_id": str(a.fact_id), "order": a.document_name, "page": a.page_index})
    elif a.source_kind == "document":
        origin.update(
            {"source_id": str(a.source_id), "document": a.document_name, "page": a.page_index, "excerpt": a.excerpt}
        )
    else:
        origin.update({"document": a.document_name, "page": a.page_index})
    return tu.ActualRef(
        str(a.id),
        a.line_code,
        a.canonical_value,
        a.canonical_unit,
        a.stated_value,
        a.stated_unit,
        a.source_kind,
        origin,
    )


def statement(session: Session, case: ArrCase) -> dict[str, Any]:
    """The live statement: today's reviewed approvals against today's actuals."""
    from .identities import Value, evaluate
    from .taxonomy import load_mapping, load_taxonomy

    utility = session.get(Utility, case.utility_id)
    assert utility is not None
    fy = _year_of(case)
    tax = load_taxonomy()
    approved = _approved(session, utility, fy)
    actuals = {a.line_code: _actual_ref(a) for a in actuals_of(session, case)}
    try:
        mapping = load_mapping(utility.commission.code, fallback=True)
    except FileNotFoundError:
        mapping = None
    values = [
        Value(a.line_code, Decimal(a.value), a.unit, f"actual:{a.actual_id}")
        for a in actuals.values()
        if a.value is not None
    ]
    findings = [
        {"identity_id": f.identity_id, "severity": f.severity, "message": f.message, "lines": f.lines}
        for f in evaluate(values, taxonomy=tax, mapping=mapping, group={"fiscal_year": fy, "value_type": "actual"})
    ]
    return tu.compute(
        fy=fy,
        kind=case.filing_kind,
        approved=approved,
        actuals=actuals,
        order=[i.code for i in tax.line_items],
        labels={i.code: i.label for i in tax.line_items},
        findings=findings,
    )


def true_up_readiness(session: Session, case: ArrCase) -> dict[str, Any]:
    utility = session.get(Utility, case.utility_id)
    assert utility is not None
    fy = _year_of(case)
    st = statement(session, case)
    return {
        "kind": case.filing_kind,
        "fiscal_year": fy,
        "years": [fy],
        "base_fy": case.base_fy,
        "statement": st,
        "documents": _documents(session, utility, fy),
        "missing_actuals": [r["line_code"] for r in st["rows"] if r["status"] == "actual_missing"],
        "ready_to_freeze": st["summary"]["ready"],
        # the keys an ARR case's screen reads, empty here
        "base_facts": [],
        "parameters": [],
        "missing_base_facts": [],
        "missing_parameters": [],
        "ready_to_formulate": st["summary"]["ready"],
        "note": (
            "Approved figures come only from reviewed, published ARR facts of this licensee for the year; a missing "
            "one means the order that approved the year is not in the library, not read, or not yet reviewed."
        ),
    }


def _editable(case: ArrCase) -> None:
    if case.filing_kind not in TRUE_UP_KINDS:
        raise AppError("invalid_transition", "actuals belong to true-up and APR cases")
    if case.status in ("frozen", "drafted", "closed"):
        raise AppError("invalid_transition", "the case's statement is frozen; revise the case to change actuals")


def _stale(case: ArrCase) -> None:
    if case.status == "formulated":
        case.statement = None
    _touch(case, "assumptions")


def _printed_in(value: str, excerpt: str) -> bool:
    plain = re.sub(r"(?<=\d),(?=\d)", "", excerpt)
    return bool(re.search(rf"(?<![0-9.]){re.escape(value)}(?![0-9])", plain))


def add_actual(
    session: Session,
    storage: ObjectStore,
    case: ArrCase,
    *,
    line_code: str,
    stated_value: str | None,
    stated_unit: str | None,
    source_kind: str,
    fact_id: uuid.UUID | None,
    source_id: uuid.UUID | None,
    page_index: int | None,
    excerpt: str | None,
    document_name: str | None,
    rationale: str | None,
    actor: str,
) -> ArrActual:
    from .schema import to_canonical
    from .taxonomy import load_taxonomy

    _editable(case)
    fy = _year_of(case)
    tax = load_taxonomy()
    if line_code not in tax.by_code():
        raise AppError("validation_failed", f"{line_code} is not a line of the ARR taxonomy")
    if source_kind not in ACTUAL_SOURCE_KINDS:
        raise AppError("validation_failed", f"source_kind is one of {', '.join(ACTUAL_SOURCE_KINDS)}")
    if source_kind == "estimate" and case.filing_kind != "apr":
        raise AppError("validation_failed", "an estimate belongs to an APR; a true-up is of audited actuals")
    rationale = (rationale or "").strip() or None
    if source_kind in ("statement", "estimate") and (not rationale or not (document_name or "").strip()):
        raise AppError("validation_failed", f"a {source_kind} needs the document it rests on and a rationale")
    row = ArrActual(case_id=case.id, line_code=line_code, fiscal_year=fy, source_kind=source_kind, entered_by=actor)
    if source_kind == "fact":
        f = session.get(ArrFact, fact_id) if fact_id else None
        if (
            f is None
            or f.utility_id != case.utility_id
            or f.superseded_by_id is not None
            or f.value_type != "actual"
            or f.fiscal_year != fy
            or f.line_code != line_code
            or f.category_code
            or f.stated_value is None
        ):
            raise AppError(
                "validation_failed",
                f"fact_id must be a current reviewed fact of voice actual for {line_code} {fy} of this licensee",
            )
        src = session.get(SourceDocument, f.source_id)
        ev = (f.evidence or [{}])[0]
        row.fact_id, row.source_id = f.id, f.source_id
        row.stated_value, row.stated_unit = f.stated_value, f.stated_unit or (f.canonical_unit or "")
        row.canonical_value, row.canonical_unit = f.canonical_value, f.canonical_unit
        row.conversion = f.conversion or "identity"
        row.document_name, row.page_index, row.excerpt = (
            src.original_filename if src else None,
            ev.get("page_index"),
            ev.get("excerpt"),
        )
    else:
        if not stated_value or not stated_unit:
            raise AppError("validation_failed", "an actual needs the value and the unit as written in its source")
        stated_value = stated_value.replace(",", "").strip()
        try:
            Decimal(stated_value)
        except InvalidOperation as e:
            raise AppError("validation_failed", f"value must be a decimal, got {stated_value!r}") from e
        cv, cu, conv = to_canonical(stated_value, stated_unit, tax.unit_conversions)
        row.stated_value, row.stated_unit = stated_value, stated_unit
        row.canonical_value, row.canonical_unit, row.conversion = cv, cu, conv
        row.rationale, row.page_index = rationale, page_index
        if source_kind == "document":
            src = session.get(SourceDocument, source_id) if source_id else None
            if src is None:
                raise AppError("validation_failed", "source_id must be a registered document")
            if not page_index or not (excerpt or "").strip():
                raise AppError("validation_failed", "a document actual needs the page and the excerpt that prints it")
            squashed = arr._squash(excerpt or "")
            if squashed not in arr._squash(arr._page_text(storage, src, int(page_index))):
                raise AppError(
                    "validation_failed", f"the excerpt is not on page {page_index} of {src.original_filename}"
                )
            if not _printed_in(stated_value, squashed):
                raise AppError("validation_failed", f"the value {stated_value} is not printed in the cited excerpt")
            row.source_id, row.excerpt, row.document_name = src.id, squashed[:600], src.original_filename
        else:
            row.document_name = (document_name or "").strip()[:300]
    existing = session.execute(
        select(ArrActual).where(ArrActual.case_id == case.id, ArrActual.line_code == line_code)
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError("validation_failed", f"{line_code} already has an actual in this case; remove it first")
    session.add(row)
    session.flush()
    _stale(case)
    _audit(
        session,
        actor,
        "arr_case.actual_added",
        case,
        after={
            "line_code": line_code,
            "fiscal_year": fy,
            "stated_value": row.stated_value,
            "stated_unit": row.stated_unit,
            "source_kind": source_kind,
        },
        reason=rationale,
    )
    return row


def remove_actual(session: Session, case: ArrCase, actual_id: uuid.UUID, *, actor: str) -> None:
    _editable(case)
    a = session.get(ArrActual, actual_id)
    if a is None or a.case_id != case.id:
        raise AppError("not_found", "actual not in this case")
    _audit(
        session,
        actor,
        "arr_case.actual_removed",
        case,
        before={"line_code": a.line_code, "stated_value": a.stated_value, "source_kind": a.source_kind},
    )
    session.delete(a)
    _stale(case)


def compute_statement(session: Session, case: ArrCase, *, actor: str) -> dict[str, Any]:
    _editable(case)
    st = statement(session, case)
    st["computed_at"], st["computed_by"] = datetime.now(UTC).isoformat(), actor
    case.statement = st
    _touch(case, "formulated")
    _audit(session, actor, "arr_case.statement_computed", case, after={"input_hash": st["input_hash"], **st["summary"]})
    return st


def freeze_statement(session: Session, case: ArrCase, *, actor: str) -> dict[str, Any]:
    if case.filing_kind not in TRUE_UP_KINDS or case.status != "formulated" or not case.statement:
        raise AppError("invalid_transition", "compute the statement before freezing it")
    live = statement(session, case)
    if live["input_hash"] != case.statement["input_hash"]:
        raise AppError("invalid_transition", "the approvals or actuals changed since the statement was computed")
    if not live["summary"]["ready"]:
        raise AppError(
            "validation_failed",
            "the statement is not ready: " + "; ".join(live["summary"]["not_ready_because"]),
        )
    st = dict(case.statement)
    st["frozen_at"], st["frozen_by"] = datetime.now(UTC).isoformat(), actor
    case.statement = st
    _touch(case, "frozen")
    _audit(session, actor, "arr_case.frozen", case, after={"input_hash": st["input_hash"]})
    return st


def draft_true_up(session: Session, storage: ObjectStore, case: ArrCase, *, actor: str) -> FilingDraft:
    if case.status not in ("frozen", "drafted") or not case.statement or not case.statement.get("frozen_at"):
        raise AppError("invalid_transition", "freeze the case's statement before drafting the petition")
    if statement(session, case)["input_hash"] != case.statement["input_hash"]:
        raise AppError(
            "invalid_transition",
            "a reviewed approval or an actual changed since the freeze; revise the case and freeze again",
        )
    utility = session.get(Utility, case.utility_id)
    assert utility is not None
    is_fixture = utility.dataset.kind == DatasetKind.fixture or any(
        r["approved"] and r["approved"]["is_fixture"] for r in case.statement["rows"]
    )
    try:
        docx, xlsx, trace = tu.render(
            case.statement,
            utility_code=utility.code,
            utility_name=utility.name,
            case_title=case.title,
            is_fixture=is_fixture,
        )
    except fl.FilingError as e:
        raise AppError(e.code, str(e), extra=e.detail) from e
    draft_id = uuid.uuid4()
    prefix = f"filing/{utility.code}/case-{case.id}/{draft_id}"
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
    d = FilingDraft(
        id=draft_id,
        formulation_id=None,
        case_id=case.id,
        template_id="true-up-builtin",
        template_version=1,
        template_status="builtin",
        docx_key=docx_key,
        docx_sha256=hashlib.sha256(docx).hexdigest(),
        xlsx_key=xlsx_key,
        xlsx_sha256=hashlib.sha256(xlsx).hexdigest(),
        trace=trace,
        status="draft",
        is_fixture=is_fixture,
        generated_by=actor,
    )
    session.add(d)
    session.flush()
    case.draft_id = d.id
    _touch(case, "drafted")
    _audit(session, actor, "arr_case.drafted", case, after={"draft_id": str(d.id), "numbers": trace["numbers"]})
    return d
