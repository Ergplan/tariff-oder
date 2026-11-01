"""ARR formulation (ADR-0018, prompt Increment A): compute the ARR for target years from
reviewed facts, assumptions and regulation parameters, by a versioned formula library and a
per-commission plan that says which formula computes which line.

- **Facts** come in already chosen by the base-selection rule (the plan's order of voices).
- **Parameters** are assumptions: entered by a named user with a rationale, or confirmed by
  a reviewer against a regulation clause.  A missing one blocks the line and everything that
  depends on it; nothing is defaulted (prompt rule 7).
- **Reproducible**: Decimal arithmetic, each line quantised to the plan's precision with
  ROUND_HALF_UP, inputs recorded by id; the same inputs give the same lines bit for bit.

Pure functions; ``tariff_api.arr.service`` reads and writes the rows."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .taxonomy import taxonomy_dir

LIBRARY_VERSION = "lib-1"
FY_RE = re.compile(r"^FY(\d{4})-(\d{2})$")


# ------------------------------------------------------------------ plan (data)


class PlanLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_code: str
    formula: Literal[
        "carry_forward", "escalate", "assumption", "sum", "net", "energy_input", "quantity_x_rate", "rate_on", "acos"
    ]
    inputs: dict[str, str | list[str]] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)
    unit: str
    note: str | None = None


class BaseRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 1
    prefer: list[str]  # voices in order of preference for the base year's value
    note: str | None = None


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z]+-plan$")
    version: int = Field(ge=1)
    commission: str
    status: str  # synthetic | skeleton | confirmed
    precision: str = "0.01"
    base_rule: BaseRule
    lines: list[PlanLine]
    note: str | None = None


def plans_dir() -> Path:
    return taxonomy_dir() / "formulation"


@lru_cache(maxsize=16)
def load_plan(commission: str, version: int | None = None) -> Plan:
    files: list[tuple[int, Path]] = []
    for p in plans_dir().glob(f"{commission.lower()}-plan.v*.json"):
        m = re.fullmatch(rf"{commission.lower()}-plan\.v(\d+)\.json", p.name)
        if m:
            files.append((int(m.group(1)), p))
    if not files:
        raise FileNotFoundError(f"no formulation plan for commission {commission!r}")
    chosen = max(files)[1] if version is None else next(p for v, p in files if v == version)
    return Plan.model_validate(json.loads(chosen.read_text()))


# ------------------------------------------------------------------ inputs


@dataclass(frozen=True)
class BaseFact:
    fact_id: str
    line_code: str
    fiscal_year: str
    value_type: str
    value: Decimal
    unit: str | None
    source_id: str


@dataclass(frozen=True)
class AssumptionIn:
    assumption_id: str
    key: str
    fiscal_year: str  # "" = every year
    value: Decimal
    unit: str
    source_kind: str
    clause_ref: dict[str, Any] | None


@dataclass
class LineResult:
    line_code: str
    fiscal_year: str
    status: str  # computed | blocked
    value: Decimal | None
    unit: str
    formula_id: str
    inputs: dict[str, list[Any]] = field(default_factory=lambda: {"facts": [], "assumptions": [], "lines": []})
    regulation_clause: dict[str, Any] | None = None
    blocked_reason: str | None = None


def fy_shift(fy: str, n: int) -> str:
    m = FY_RE.match(fy)
    if not m:
        raise ValueError(f"not a fiscal year: {fy!r}")
    start = int(m.group(1)) + n
    return f"FY{start}-{(start + 1) % 100:02d}"


def fy_range(base_fy: str, last_fy: str) -> list[str]:
    """The years after the base up to the last target, in order."""
    out, fy = [], base_fy
    while fy != last_fy:
        fy = fy_shift(fy, 1)
        out.append(fy)
        if len(out) > 20:
            raise ValueError("targets more than 20 years after the base year")
    return out


def select_base(facts: list[BaseFact], rule: BaseRule, base_fy: str) -> dict[str, BaseFact]:
    """Per line, the base year's fact in the plan's order of voices (``facts`` arrive newest
    order first, so the latest order wins within one voice)."""
    rank = {v: i for i, v in enumerate(rule.prefer)}
    out: dict[str, BaseFact] = {}
    for f in facts:
        if f.fiscal_year != base_fy or f.value_type not in rank:
            continue
        cur = out.get(f.line_code)
        if cur is None or rank[f.value_type] < rank[cur.value_type]:
            out[f.line_code] = f
    return out


class _Blocked(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def compute(
    plan: Plan,
    *,
    base_fy: str,
    last_fy: str,
    base: dict[str, BaseFact],
    assumptions: list[AssumptionIn],
) -> list[LineResult]:
    """Every plan line for every year after the base up to the last target, in plan order
    within a year.  A plan line may use any line computed before it in the same year, and
    its own (or another line's) value of the previous year."""
    q = Decimal(plan.precision)
    by_key: dict[tuple[str, str], AssumptionIn] = {(a.key, a.fiscal_year): a for a in assumptions}
    results: dict[tuple[str, str], LineResult] = {}
    order: list[LineResult] = []

    def assumption(key: str, fy: str, res: LineResult) -> Decimal:
        a = by_key.get((key, fy)) or by_key.get((key, ""))
        if a is None:
            raise _Blocked(f"parameter missing: {key} for {fy}")
        res.inputs["assumptions"].append(
            {"id": a.assumption_id, "key": a.key, "fiscal_year": fy, "value": str(a.value)}
        )
        if a.source_kind == "regulation_clause" and a.clause_ref:
            res.regulation_clause = a.clause_ref
        return a.value

    def value(code: str, fy: str, res: LineResult) -> Decimal:
        if fy == base_fy:
            f = base.get(code)
            if f is None:
                raise _Blocked(f"no reviewed fact for {code} in {base_fy} in the base rule's voices")
            res.inputs["facts"].append(
                {
                    "id": f.fact_id,
                    "line_code": code,
                    "fiscal_year": fy,
                    "value_type": f.value_type,
                    "value": str(f.value),
                }
            )
            return f.value
        r = results.get((code, fy))
        if r is None:
            raise _Blocked(f"{code} for {fy} is not computed before this line in the plan")
        if r.status == "blocked":
            raise _Blocked(f"input blocked: {code} {fy}")
        res.inputs["lines"].append({"line_code": code, "fiscal_year": fy, "value": str(r.value)})
        assert r.value is not None
        return r.value

    def one(inputs: dict[str, str | list[str]], name: str) -> str:
        v = inputs.get(name)
        if not isinstance(v, str):
            raise ValueError(f"plan input {name!r} must name one line")
        return v

    for fy in fy_range(base_fy, last_fy):
        prev = fy_shift(fy, -1)
        for pl in plan.lines:
            res = LineResult(pl.line_code, fy, "computed", None, pl.unit, pl.formula)
            try:
                if pl.formula == "carry_forward":
                    v = value(one(pl.inputs, "base") if "base" in pl.inputs else pl.line_code, prev, res)
                elif pl.formula == "escalate":
                    src = one(pl.inputs, "base") if "base" in pl.inputs else pl.line_code
                    rate = assumption(pl.params["rate_pct"], fy, res)
                    v = value(src, prev, res) * (1 + rate / 100)
                elif pl.formula == "assumption":
                    v = assumption(pl.params.get("value", pl.line_code), fy, res)
                elif pl.formula == "sum":
                    parts = pl.inputs["of"]
                    assert isinstance(parts, list)
                    v = sum((value(c, fy, res) for c in parts), Decimal(0))
                elif pl.formula == "net":
                    less = pl.inputs.get("less") or []
                    assert isinstance(less, list)
                    v = value(one(pl.inputs, "from"), fy, res) - sum((value(c, fy, res) for c in less), Decimal(0))
                elif pl.formula == "energy_input":
                    sales = value(one(pl.inputs, "sales"), fy, res)
                    loss = value(one(pl.inputs, "loss_pct"), fy, res)
                    if loss >= 100:
                        raise _Blocked(f"loss of {loss} percent cannot gross up sales")
                    v = sales / (1 - loss / 100)
                elif pl.formula == "quantity_x_rate":
                    # MU x Rs/kWh = 10^6 kWh x Rs/kWh = Rs 10^6 = 0.1 crore
                    qty = value(one(pl.inputs, "quantity"), fy, res)
                    v = qty * assumption(pl.params["rate_inr_per_kwh"], fy, res) / 10
                elif pl.formula == "rate_on":
                    v = value(one(pl.inputs, "base"), fy, res) * assumption(pl.params["rate_pct"], fy, res) / 100
                elif pl.formula == "acos":
                    arr, sales = value(one(pl.inputs, "arr"), fy, res), value(one(pl.inputs, "sales"), fy, res)
                    if not sales:
                        raise _Blocked("sales are zero")
                    v = arr / sales * 10
                else:  # pragma: no cover - the plan model forbids it
                    raise ValueError(pl.formula)
                res.value = v.quantize(q, rounding=ROUND_HALF_UP)
            except _Blocked as b:
                res.status, res.value, res.blocked_reason = "blocked", None, b.reason
            results[(pl.line_code, fy)] = res
            order.append(res)
    return order


def describe(pl: PlanLine) -> str:
    """Words for the "why" of a line (the filing narrative uses them; no numbers)."""
    i, p = pl.inputs, pl.params
    match pl.formula:
        case "carry_forward":
            return f"carried forward unchanged from the previous year's {i.get('base', pl.line_code)}"
        case "escalate":
            return f"previous year's {i.get('base', pl.line_code)} escalated by {p.get('rate_pct')}"
        case "assumption":
            return f"taken from the assumption {p.get('value', pl.line_code)}"
        case "sum":
            return "sum of " + ", ".join(i.get("of") or [])  # type: ignore[arg-type]
        case "net":
            return f"{i.get('from')} less " + ", ".join(i.get("less") or [])  # type: ignore[arg-type]
        case "energy_input":
            return f"{i.get('sales')} grossed up by the loss {i.get('loss_pct')}"
        case "quantity_x_rate":
            return f"{i.get('quantity')} at the rate {p.get('rate_inr_per_kwh')}"
        case "rate_on":
            return f"{p.get('rate_pct')} applied to {i.get('base')}"
        case "acos":
            return f"{i.get('arr')} over {i.get('sales')}"
    return pl.formula


def input_hash(
    *,
    plan: Plan,
    base_fy: str,
    targets: list[dict[str, str]],
    base: dict[str, BaseFact],
    assumptions: list[AssumptionIn],
) -> str:
    """Covers everything a formulation's numbers depend on."""
    payload = {
        "plan": [
            plan.id,
            plan.version,
            plan.precision,
            plan.base_rule.model_dump(),
            [pl.model_dump() for pl in plan.lines],
        ],
        "library": LIBRARY_VERSION,
        "base_fy": base_fy,
        "targets": targets,
        "base": sorted((f.line_code, f.fact_id, str(f.value), f.value_type) for f in base.values()),
        "assumptions": sorted(
            (a.assumption_id, a.key, a.fiscal_year, str(a.value), a.source_kind) for a in assumptions
        ),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
