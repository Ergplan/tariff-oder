"""The atlas (increment 52): the way into the regulatory record and the petition, state by state.

Three read-only views, in the order a user travels them:

- every state and union territory with its commissions, its licensees, how far its documents
  have come, how many of its real orders are being read, and how many reviewed ARR facts exist;
- one state: its commissions and each licensee with the same counts;
- one commission's norms: the regulations its ARR mapping names, the conventions it states
  (each with whether a reviewer has confirmed it), and the method its formulation plan uses for
  every ARR line, in words.  The plan says how a line is formed; the values of its parameters
  come from the regulation or the petitioner and are never invented here.

Nothing here decides anything; every count is of records a person can open."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .errors import AppError
from .models import ArrFact, Commission, Jurisdiction, LibraryEntry, SourceDocument, Utility

_DIST = ("distribution", "transmission")


def _counts(session: Session) -> dict[str, Any]:
    """Per licensee: library documents by status, real orders being read, reviewed ARR facts."""
    docs: dict[Any, Counter] = {}
    for uid, cid, status in session.execute(
        select(LibraryEntry.utility_id, LibraryEntry.commission_id, LibraryEntry.status)
    ).all():
        docs.setdefault(uid or ("c", cid), Counter())[status] += 1
    reading = Counter(
        uid
        for (uid,) in session.execute(
            select(SourceDocument.utility_id).where(SourceDocument.arr_state.is_not(None))
        ).all()
        if uid
    )
    facts = dict(
        session.execute(
            select(ArrFact.utility_id, func.count())
            .where(ArrFact.superseded_by_id.is_(None))
            .group_by(ArrFact.utility_id)
        ).all()
    )
    latest = dict(
        session.execute(
            select(ArrFact.utility_id, func.max(ArrFact.fiscal_year))
            .where(ArrFact.superseded_by_id.is_(None))
            .group_by(ArrFact.utility_id)
        ).all()
    )
    return {"docs": docs, "reading": reading, "facts": facts, "latest": latest}


def _licensee(u: Utility, c: dict[str, Any]) -> dict[str, Any]:
    d = c["docs"].get(u.id, Counter())
    return {
        "code": u.code,
        "name": u.name,
        "kind": u.licensee_kind,
        "dataset": u.dataset.kind.value if u.dataset else None,
        "documents": sum(d.values()),
        "documents_located": sum(n for s, n in d.items() if s != "expected"),
        "orders_reading": c["reading"].get(u.id, 0),
        "reviewed_facts": c["facts"].get(u.id, 0),
        "latest_reviewed_year": c["latest"].get(u.id),
    }


def atlas(session: Session) -> dict[str, Any]:
    c = _counts(session)
    out = []
    for j in session.execute(select(Jurisdiction).order_by(Jurisdiction.name)).scalars():
        coms = []
        lics: list[dict[str, Any]] = []
        for com in sorted(j.commissions, key=lambda x: x.code):
            ls = [_licensee(u, c) for u in sorted(com.utilities, key=lambda u: u.code) if u.licensee_kind in _DIST]
            lics += ls
            coms.append({"code": com.code, "name": com.name, "licensees": len(ls)})
        if not coms:
            continue
        fixture = bool(lics) and all(x["dataset"] == "fixture" for x in lics)
        out.append(
            {
                "code": j.code,
                "name": j.name,
                "kind": j.kind.value,
                "fixture": fixture,
                "commissions": coms,
                "licensees": len(lics),
                "documents": sum(x["documents"] for x in lics),
                "documents_located": sum(x["documents_located"] for x in lics),
                "orders_reading": sum(x["orders_reading"] for x in lics),
                "reviewed_facts": sum(x["reviewed_facts"] for x in lics),
            }
        )
    return {
        "states": out,
        "note": (
            "Counts are of records in the application: documents in the library (located or expected), real "
            "orders whose ARR is being read, and reviewed ARR facts. A number becomes a fact only when a reviewer "
            "approves it and it is published."
        ),
    }


def state(session: Session, code: str) -> dict[str, Any]:
    j = session.execute(select(Jurisdiction).where(Jurisdiction.code == code.upper())).scalar_one_or_none()
    if j is None:
        raise AppError("not_found", f"state {code} not found")
    c = _counts(session)
    coms = []
    for com in sorted(j.commissions, key=lambda x: x.code):
        cdocs = c["docs"].get(("c", com.id), Counter())
        coms.append(
            {
                "code": com.code,
                "name": com.name,
                "commission_documents": sum(cdocs.values()),
                "licensees": [
                    _licensee(u, c) for u in sorted(com.utilities, key=lambda u: u.code) if u.licensee_kind in _DIST
                ],
            }
        )
    return {"code": j.code, "name": j.name, "kind": j.kind.value, "commissions": coms}


def licensee(session: Session, code: str) -> dict[str, Any]:
    """Where a licensee sits: its commission and state, for the way back up the atlas."""
    u = session.execute(select(Utility).where(func.upper(Utility.code) == code.strip().upper())).scalar_one_or_none()
    if u is None:
        raise AppError("not_found", f"licensee {code} not found")
    com = u.commission
    j = com.jurisdiction
    return {
        **_licensee(u, _counts(session)),
        "commission": com.code,
        "commission_name": com.name,
        "state": j.code,
        "state_name": j.name,
    }


# how a formulation plan forms a line, in the words a petition uses
_METHOD = {
    "assumption": "entered for each year by the petitioner — a forecast, or the value a regulation clause fixes",
    "quantity_x_rate": "the year's quantity multiplied by a rate",
    "escalate": "the base year's reviewed figure escalated each year by a rate",
    "carry_forward": "the base year's reviewed figure carried forward",
    "energy_input": "sales grossed up by the distribution loss",
    "sum": "the sum of its components",
    "net": "the requirement less the items set off against it",
    "acos": "the revenue requirement divided by the energy sold",
}
_PARAM = {
    "param.pp_rate_inr_per_kwh": "average power purchase rate (Rs/kWh)",
    "param.tx_growth_pct": "transmission charges growth (%)",
    "param.om_escalation_pct": "O&M escalation (%) — the regulation's escalation index",
    "param.iwc_growth_pct": "interest on working capital growth (%)",
    "param.avg_realisation_inr_per_kwh": "average realisation at existing tariff (Rs/kWh)",
}


# the lines a commission's norms decide, as its reviewed orders applied them
NORM_LINES = ("E.LOSS.DIST_PCT", "C.OM", "C.RETURN.ROE", "C.INT.WC", "C.DEP", "C.INT.LOAN")
_STRONG = ("final_true_up", "provisional_true_up", "approved")


def _applied(session: Session, com: Commission) -> list[dict[str, Any]]:
    """Per licensee and norm line: the latest reviewed figure the commission approved or trued
    up, with its order and page.  Only published reviewed facts; nothing is derived."""
    out = []
    utils = [u for u in com.utilities if u.licensee_kind == "distribution"]
    if not utils:
        return out
    facts = session.execute(
        select(ArrFact, SourceDocument.original_filename)
        .join(SourceDocument, SourceDocument.id == ArrFact.source_id)
        .where(
            ArrFact.utility_id.in_([u.id for u in utils]),
            ArrFact.superseded_by_id.is_(None),
            ArrFact.line_code.in_(NORM_LINES),
            ArrFact.value_type.in_(_STRONG),
            ArrFact.category_code == "",
            ArrFact.canonical_value.is_not(None),
        )
    ).all()
    best: dict[tuple, tuple] = {}
    for f, order in facts:
        key = (f.utility_id, f.line_code)
        rank = (f.fiscal_year, -_STRONG.index(f.value_type))
        if key not in best or rank > best[key][0]:
            best[key] = (rank, f, order)
    code = {u.id: u.code for u in utils}
    for (uid, line), (_, f, order) in sorted(best.items(), key=lambda kv: (code[kv[0][0]], NORM_LINES.index(kv[0][1]))):
        ev = (f.evidence or [{}])[0]
        out.append(
            {
                "licensee": code[uid],
                "line_code": line,
                "fiscal_year": f.fiscal_year,
                "voice": f.value_type,
                "value": f.canonical_value,
                "unit": f.canonical_unit,
                "order": order,
                "page": ev.get("page_index"),
                "source_id": str(f.source_id),
                "is_fixture": f.is_fixture,
            }
        )
    return out


def norms(session: Session, commission: str) -> dict[str, Any]:
    from .arr.formulate import load_plan
    from .arr.taxonomy import load_mapping, load_taxonomy
    from .library import reading_level

    com = session.execute(select(Commission).where(Commission.code == commission.upper())).scalar_one_or_none()
    if com is None:
        raise AppError("not_found", f"commission {commission} not found")
    tax = load_taxonomy().by_code()
    plan = load_plan(com.code, fallback=True)
    mapping = load_mapping(com.code, fallback=True)
    lines = []
    for ln in plan.lines:
        item = tax.get(ln.line_code)
        params = [
            {"key": v, "words": _PARAM.get(v, v)}
            for v in (ln.params or {}).values()
            if isinstance(v, str) and v.startswith("param.")
        ]
        lines.append(
            {
                "line_code": ln.line_code,
                "label": item.label if item else ln.line_code,
                "method": ln.formula,
                "method_words": _METHOD.get(ln.formula, ln.formula),
                "parameters": params,
                "unit": ln.unit,
                "note": ln.note,
            }
        )

    def conv(noted: Any) -> dict[str, Any]:
        return {"value": getattr(noted, "value", None), "note": getattr(noted, "note", None)}

    regs = (
        session.execute(
            select(LibraryEntry)
            .where(
                LibraryEntry.commission_id == com.id,
                LibraryEntry.document_kind.in_(("regulation", "regulation_amendment")),
            )
            .order_by(LibraryEntry.fiscal_year.desc())
        )
        .scalars()
        .all()
    )
    from .models import MappingDecision

    decided = [
        {"key": d.label.removeprefix("convention:"), "value": d.code, "note": d.note, "by": d.decided_by}
        for d in session.execute(
            select(MappingDecision)
            .where(MappingDecision.commission_code == com.code, MappingDecision.kind == "convention")
            .order_by(MappingDecision.label)
        ).scalars()
    ]
    confirmed = mapping.status.lower().startswith("confirmed")
    return {
        "commission": com.code,
        "commission_name": com.name,
        "plan": {"id": plan.id, "version": plan.version, "status": plan.status.split(";")[0][:80]},
        "plan_confirmed": plan.status.lower().startswith("confirmed"),
        "mapping": {"id": mapping.id, "version": mapping.version, "status": mapping.status.split(";")[0][:80]},
        "mapping_confirmed": confirmed,
        "regulations": [
            {
                "role": r.role,
                "title": r.title,
                "year": r.year,
                "control_periods": list(r.control_periods),
                "amendments": list(r.amendments),
                "note": r.note,
            }
            for r in mapping.regulations
        ],
        "regulations_in_library": [
            {
                "title": e.title,
                "fiscal_year": e.fiscal_year,
                "kind": e.document_kind,
                "url": e.url,
                "level": reading_level(session, e),
                "source_id": str(e.source_id) if e.source_id else None,
            }
            for e in regs
        ],
        "conventions": {
            "return_basis": conv(mapping.return_basis),
            "gap_convention": conv(mapping.gap_convention),
            "loss_basis": conv(mapping.loss_basis),
            "total_includes": [t.model_dump() for t in mapping.total_includes],
            "decided_by_reviewer": decided,
        },
        "base_rule": plan.base_rule.model_dump(),
        "lines": lines,
        "applied": _applied(session, com),
        "note": (
            "The method of each line is the formulation plan's; the parameters' values come from the regulation "
            "or the petitioner, entered with their source in a petition. A plan or a mapping that is not confirmed "
            "by a reviewer is a working estimate of the commission's norms."
        ),
    }
