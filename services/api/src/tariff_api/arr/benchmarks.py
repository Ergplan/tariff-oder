"""Benchmarks across licensees (increment 34): ratios a licensee's ARR is argued with — power
purchase cost per unit of input, O&M and ARR per unit sold, distribution loss, the gap as a
share of the ARR — computed only from reviewed, published ARR facts of one year and one voice.

Every value is derived, never stored, and carries its inputs (the facts, their orders and
pages) and the words of its formula.  A licensee missing an input has no value for that
metric, with the reason; units are checked, never assumed.  Fixture licensees are left out
unless asked for, and labelled when included."""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import ArrFact, Commission, DatasetKind, SourceDocument, Utility


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    unit: str
    numerator: str
    numerator_unit: str
    denominator: str | None = None
    denominator_unit: str | None = None
    factor: str = "1"
    words: str = ""
    places: int = 2


METRICS: tuple[Metric, ...] = (
    Metric(
        "pp_cost_per_unit_input",
        "Power purchase cost per unit of input",
        "INR_per_kWh",
        "C.PP",
        "INR_crore",
        "E.INPUT.DIST",
        "MU",
        "10",
        "power purchase cost (Rs crore) ÷ energy input at the distribution periphery (MU) × 10 = Rs/kWh",
        3,
    ),
    Metric(
        "om_per_unit_sold",
        "O&M expenses per unit sold",
        "INR_per_kWh",
        "C.OM",
        "INR_crore",
        "E.SALES",
        "MU",
        "10",
        "O&M expenses (Rs crore) ÷ energy sales (MU) × 10 = Rs/kWh",
        3,
    ),
    Metric(
        "arr_per_unit_sold",
        "ARR per unit sold",
        "INR_per_kWh",
        "R.ARR",
        "INR_crore",
        "E.SALES",
        "MU",
        "10",
        "aggregate revenue requirement (Rs crore) ÷ energy sales (MU) × 10 = Rs/kWh",
        3,
    ),
    Metric(
        "distribution_loss",
        "Distribution loss",
        "percent",
        "E.LOSS.DIST_PCT",
        "percent",
        words="the distribution loss as the order prints it",
    ),
    Metric(
        "gap_share_of_arr",
        "Revenue gap as a share of the ARR",
        "percent",
        "R.GAP",
        "INR_crore",
        "R.ARR",
        "INR_crore",
        "100",
        "revenue gap ÷ aggregate revenue requirement × 100",
    ),
    Metric(
        "roe_share_of_expenditure",
        "Return on equity as a share of expenditure",
        "percent",
        "C.RETURN.ROE",
        "INR_crore",
        "C.TOTAL",
        "INR_crore",
        "100",
        "return on equity ÷ total expenditure × 100",
    ),
)


def _facts(session: Session, fiscal_year: str, value_type: str) -> dict[str, dict[str, dict[str, Any]]]:
    """utility id -> line code -> the current fact of that year and voice (newest order first)."""
    rows = session.execute(
        select(ArrFact, SourceDocument)
        .join(SourceDocument, SourceDocument.id == ArrFact.source_id)
        .where(
            ArrFact.fiscal_year == fiscal_year,
            ArrFact.value_type == value_type,
            ArrFact.superseded_by_id.is_(None),
            or_(ArrFact.category_code.is_(None), ArrFact.category_code == ""),
            ArrFact.value_state.in_(("value", "zero")),
            ArrFact.canonical_value.is_not(None),
        )
        .order_by(SourceDocument.acquired_at.desc(), ArrFact.published_at.desc())
    ).all()
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for f, src in rows:
        per = out.setdefault(str(f.utility_id), {})
        if f.line_code in per:
            continue
        ev = (f.evidence or [{}])[0]
        per[f.line_code] = {
            "line_code": f.line_code,
            "value": f.canonical_value,
            "unit": f.canonical_unit,
            "fact_id": str(f.id),
            "source_id": str(src.id),
            "order": src.original_filename,
            "page": ev.get("page_index"),
            "is_fixture": f.is_fixture,
        }
    return out


def _value(m: Metric, facts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    num = facts.get(m.numerator)
    den = facts.get(m.denominator) if m.denominator else None
    missing = [c for c, f in ((m.numerator, num), (m.denominator, den)) if c and f is None]
    if missing:
        return {"value": None, "reason": f"no reviewed {', '.join(missing)} for the year", "inputs": []}
    inputs = [num] + ([den] if den else [])
    wrong = [
        f"{i['line_code']} is in {i['unit']}"
        for i, u in zip(inputs, (m.numerator_unit, m.denominator_unit), strict=False)
        if i["unit"] != u
    ]
    if wrong:
        return {"value": None, "reason": "unit not as expected: " + "; ".join(wrong), "inputs": inputs}
    v = Decimal(num["value"])
    if den is not None:
        d = Decimal(den["value"])
        if d == 0:
            return {"value": None, "reason": f"{m.denominator} is zero", "inputs": inputs}
        v = v / d * Decimal(m.factor)
    q = Decimal(1).scaleb(-m.places)
    return {"value": format(v.quantize(q, rounding=ROUND_HALF_UP), "f"), "reason": None, "inputs": inputs}


def compute(
    session: Session,
    *,
    fiscal_year: str,
    value_type: str = "approved",
    include_fixtures: bool = False,
    commission: str | None = None,
) -> dict[str, Any]:
    facts = _facts(session, fiscal_year, value_type)
    rows: list[dict[str, Any]] = []
    utilities = (
        session.execute(select(Utility).where(Utility.id.in_([uuid.UUID(u) for u in facts]))).scalars().all()
        if facts
        else []
    )
    for u in utilities:
        fixture = u.dataset.kind == DatasetKind.fixture
        if fixture and not include_fixtures:
            continue
        c: Commission = u.commission
        if commission and c.code != commission:
            continue
        values = {m.id: _value(m, facts[str(u.id)]) for m in METRICS}
        rows.append(
            {
                "code": u.code,
                "name": u.name,
                "commission": c.code,
                "state": c.jurisdiction.name if c.jurisdiction else None,
                "is_fixture": fixture or any(f["is_fixture"] for f in facts[str(u.id)].values()),
                "values": values,
            }
        )
    rows.sort(key=lambda r: (r["commission"], r["code"]))
    stats: dict[str, Any] = {}
    for m in METRICS:
        vals = sorted(Decimal(r["values"][m.id]["value"]) for r in rows if r["values"][m.id]["value"] is not None)
        if not vals:
            stats[m.id] = {"n": 0}
            continue
        q = Decimal(1).scaleb(-m.places)
        stats[m.id] = {
            "n": len(vals),
            "min": format(vals[0], "f"),
            "median": format(Decimal(statistics.median(vals)).quantize(q, rounding=ROUND_HALF_UP), "f"),
            "max": format(vals[-1], "f"),
        }
        # rank 1 = lowest (cheapest / least loss)
        for r in rows:
            v = r["values"][m.id]["value"]
            if v is not None:
                r["values"][m.id]["rank"] = 1 + sum(1 for x in vals if x < Decimal(v))
    return {
        "fiscal_year": fiscal_year,
        "value_type": value_type,
        "include_fixtures": include_fixtures,
        "metrics": [
            {
                "id": m.id,
                "label": m.label,
                "unit": m.unit,
                "words": m.words,
                "inputs": [m.numerator, *([m.denominator] if m.denominator else [])],
            }
            for m in METRICS
        ],
        "licensees": rows,
        "stats": stats,
        "kind": "derived",
        "note": (
            "Derived from reviewed, published ARR facts of the year and voice; never stored and never a fact. "
            "A licensee without a reviewed input has no value for that metric. Rank 1 is the lowest value."
        ),
    }
