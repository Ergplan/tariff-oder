"""ARR arithmetic identities (ARR spec section 4, ``ARR-I*`` in ``taxonomy.json``): run over
read facts per (year, voice, order) and over a formulation's projections per year.  An
identity flags, it never corrects.  Tolerances are the file's printed-precision tolerances.
Identities that need a detail table or a second order (I5, I6, I9, I10, I11) are listed as
not evaluated until those readings exist."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .taxonomy import Mapping, Taxonomy

IDENTITIES_VERSION = "arr-id-1"
EVALUATED = ("ARR-I1", "ARR-I2", "ARR-I3", "ARR-I4", "ARR-I7", "ARR-I8", "ARR-I12")
# lines that split a parent another way (fixed/variable of power purchase): never rolled up
# into the parent beside the source classes, or the parent would count twice
SPLIT_LINES = frozenset({"C.PP.FIXED", "C.PP.VARIABLE", "C.PP.SURPLUS_SALE_INCOME"})
LESS_ITEMS = ("L.NTI", "L.OTHER_BUSINESS", "L.OA", "L.OTHER")


@dataclass(frozen=True)
class Value:
    """One number an identity can use: a read fact or a projection line."""

    line_code: str
    value: Decimal
    unit: str | None
    ref: str  # candidate id, fact id or "line:<code>@<fy>"
    category_code: str | None = None


@dataclass
class IdentityFinding:
    identity_id: str
    severity: str
    message: str
    group: dict[str, str]
    expected: str
    printed: str
    difference: str
    lines: list[str]
    refs: list[str]
    detail: dict[str, Any] = field(default_factory=dict)


def _tol(identity_tol: dict[str, float] | None, unit: str | None, expected: Decimal) -> Decimal:
    t = identity_tol or {}
    key = {"INR_crore": "abs_inr_crore", "MU": "abs_mu", "INR_per_kWh": "abs_inr_per_kwh"}.get(unit or "", "")
    abs_t = Decimal(str(t.get(key, 0)))
    rel_t = Decimal(str(t.get("rel", 0))) * abs(expected)
    return max(abs_t, rel_t)


class _Group:
    def __init__(self, values: list[Value], taxonomy: Taxonomy):
        self.by_code: dict[str, Value] = {}
        self.categories: dict[str, list[Value]] = {}
        for v in values:
            if v.category_code:
                self.categories.setdefault(v.line_code, []).append(v)
            else:
                self.by_code.setdefault(v.line_code, v)
        self.items = taxonomy.by_code()
        self.children: dict[str, list[str]] = {}
        for i in taxonomy.line_items:
            if i.parent:
                self.children.setdefault(i.parent, []).append(i.code)

    def get(self, code: str) -> Value | None:
        return self.by_code.get(code)

    def rollup(self, code: str, used: list[Value]) -> Decimal | None:
        """The printed value of a line, or the sum of its printed descendants when the line
        itself is not printed (``C.RETURN`` from ``C.RETURN.ROE``)."""
        v = self.by_code.get(code)
        if v is not None:
            used.append(v)
            return v.value
        total: Decimal | None = None
        for child in self.children.get(code, []):
            if child in SPLIT_LINES:
                continue
            cv = self.rollup(child, used)
            if cv is not None:
                sign = self.items[child].sign or 1
                total = (total or Decimal(0)) + sign * cv
        return total


def _finding(
    identity, group, expected: Decimal, printed: Value, used: list[Value], unit, what: str
) -> IdentityFinding | None:
    diff = printed.value - expected
    if abs(diff) <= _tol(identity.tolerance, unit, expected):
        return None
    lines = sorted({u.line_code for u in used} | {printed.line_code})
    return IdentityFinding(
        identity_id=identity.id,
        severity=identity.severity,
        message=(
            f"{identity.id} {identity.name}: {printed.line_code} is {printed.value} but {what} gives "
            f"{expected} (difference {diff}) for {group.get('fiscal_year')} {group.get('value_type')}"
            + (f" of {group['utility']}" if group.get("utility") else "")
        ),
        group=group,
        expected=str(expected),
        printed=str(printed.value),
        difference=str(diff),
        lines=lines,
        refs=sorted({u.ref for u in used} | {printed.ref}),
    )


def evaluate(
    values: list[Value],
    *,
    taxonomy: Taxonomy,
    mapping: Mapping | None,
    group: dict[str, str],
) -> list[IdentityFinding]:
    """Every evaluable identity over one group of values (one year, one voice, one order; or
    one year of a formulation)."""
    g = _Group(values, taxonomy)
    ids = {i.id: i for i in taxonomy.identities}
    out: list[IdentityFinding] = []

    # I1: C.TOTAL = sum of the printed components of C
    total = g.get("C.TOTAL")
    if total is not None:
        used: list[Value] = []
        parts = 0
        s = Decimal(0)
        for child in g.children.get("C", []):
            if child == "C.TOTAL":
                continue
            cv = g.rollup(child, used)
            if cv is not None:
                parts += 1
                s += (g.items[child].sign or 1) * cv
        if parts >= 2:
            f = _finding(ids["ARR-I1"], group, s, total, used, "INR_crore", "the sum of its components")
            if f:
                out.append(f)

    # I2: R.ARR = C.TOTAL - less items
    arr = g.get("R.ARR")
    if arr is not None and total is not None:
        used = [total]
        s = total.value
        for code in LESS_ITEMS:
            lv = g.rollup(code, used)
            if lv is not None:
                s -= lv
        f = _finding(ids["ARR-I2"], group, s, arr, used, "INR_crore", "total expenditure less the less-items")
        if f:
            out.append(f)

    # I3: R.GAP = R.ARR - R.REV.EXISTING (- R.REV.SUBSIDY after subsidy)
    gap, rev = g.get("R.GAP"), g.get("R.REV.EXISTING")
    if gap is not None and arr is not None and rev is not None:
        sub = g.get("R.REV.SUBSIDY")
        convention = (mapping.gap_convention.value if mapping else None) or None
        options: list[tuple[str, Decimal, list[Value]]] = []
        if convention in (None, "before_subsidy") or sub is None:
            options.append(("ARR less revenue", arr.value - rev.value, [arr, rev]))
        if sub is not None and convention in (None, "after_subsidy"):
            options.append(("ARR less revenue and subsidy", arr.value - rev.value - sub.value, [arr, rev, sub]))
        results = [_finding(ids["ARR-I3"], group, e, gap, used, "INR_crore", what) for what, e, used in options]
        if results and all(results):
            f = results[0]
            assert f is not None
            if convention is None:
                f.detail["gap_convention"] = "unconfirmed: both conventions tried"
            out.append(f)

    # I4: E.INPUT.DIST = E.SALES / (1 - loss / 100)
    inp, sales, loss = g.get("E.INPUT.DIST"), g.get("E.SALES"), g.get("E.LOSS.DIST_PCT")
    if inp is not None and sales is not None and loss is not None and loss.value < 100:
        e = sales.value / (1 - loss.value / 100)
        f = _finding(ids["ARR-I4"], group, e, inp, [sales, loss], "MU", "sales grossed up by the loss")
        if f:
            out.append(f)

    # I7: R.ACOS = R.ARR / E.SALES * 10 (Rs/kWh from crore and MU)
    acos = g.get("R.ACOS")
    if acos is not None and arr is not None and sales is not None and sales.value:
        e = arr.value / sales.value * 10
        f = _finding(ids["ARR-I7"], group, e, acos, [arr, sales], "INR_per_kWh", "ARR over sales")
        if f:
            out.append(f)

    # I8: C.PP = fixed + variable - surplus sale income, when the split is printed
    pp, fx, var = g.get("C.PP"), g.get("C.PP.FIXED"), g.get("C.PP.VARIABLE")
    if pp is not None and fx is not None and var is not None:
        used = [fx, var]
        e = fx.value + var.value
        ssi = g.get("C.PP.SURPLUS_SALE_INCOME")
        if ssi is not None:
            e -= ssi.value
            used.append(ssi)
        f = _finding(ids["ARR-I8"], group, e, pp, used, "INR_crore", "fixed plus variable")
        if f:
            out.append(f)

    # I12: E.SALES = sum of category sales
    if sales is not None and g.categories.get("E.SALES"):
        cats = g.categories["E.SALES"]
        e = sum((c.value for c in cats), Decimal(0))
        f = _finding(ids["ARR-I12"], group, e, sales, cats, "MU", "the category sales")
        if f:
            out.append(f)
    return out
