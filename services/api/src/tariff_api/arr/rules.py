"""Executable, versioned calculation rules (ADR-0021; docs/arr-filing-requirements.md §3 and §5).

A **rule** is data (`packages/arr-rules/<commission>/*.json`): one output computed by a
formula from typed inputs, with the clause it comes from, where it applies, how it rounds,
worked examples, and who approved it.  This module loads rules, checks them, and evaluates a
set of them for one financial year with a full trace.

Guarantees (each tested):

- **Decimal only** (R-NUM-1).  Literals are parsed from their text; no binary float enters.
- **Dimensions** (R-NUM-2).  Every quantity carries a unit; ``+``/``-`` require the same
  dimension (scales are converted exactly), ``*``/``/`` combine dimensions, and the result is
  converted to the rule's declared output unit or refused.  ACoS (Rs/kWh) from ARR (Rs crore) and
  sales (MU) therefore needs no hand-written ``× 10``: the units do it.
- **A restricted language.**  Formulas are parsed with :mod:`ast` and only numbers, input names,
  ``+ - * /``, unary minus, parentheses and the functions ``avg``, ``min``, ``max``, ``sum`` and
  ``ifneg(test, then, otherwise)`` are accepted.  No attribute access, subscripts, comparisons or
  other calls: a formula cannot do anything but arithmetic.
- **Dependency order** (R-NUM-4).  Rules referring to other rules' outputs are evaluated
  topologically; a cycle is refused with its members named.
- **Rounding policy per rule** (R-NUM-3): places, mode (half-up as orders print, unless a rule
  says otherwise) and whether the rounded or the unrounded value feeds dependants.
- **Approval is a human act** (R-RULE-4).  Status ``draft`` | ``approved`` | ``superseded``;
  nothing here approves.  ``filing_ready`` is true only when every rule used is approved and its
  clause is verified (R-APP-4).
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------- units and dimensions

# unit → (scale to base, dimensions).  Bases: INR (money), kWh (energy), kW (power),
# month (time).  Dimensionless units: fraction, percent (scale 1/100), number.
UNITS: dict[str, tuple[Decimal, dict[str, int]]] = {
    "INR": (Decimal(1), {"money": 1}),
    "INR_lakh": (Decimal(10) ** 5, {"money": 1}),
    "INR_crore": (Decimal(10) ** 7, {"money": 1}),
    "kWh": (Decimal(1), {"energy": 1}),
    "MU": (Decimal(10) ** 6, {"energy": 1}),
    "kW": (Decimal(1), {"power": 1}),
    "MW": (Decimal(10) ** 3, {"power": 1}),
    "INR_per_kWh": (Decimal(1), {"money": 1, "energy": -1}),
    "paise_per_kWh": (Decimal("0.01"), {"money": 1, "energy": -1}),
    "month": (Decimal(1), {"time": 1}),
    "year": (Decimal(12), {"time": 1}),
    "fraction": (Decimal(1), {}),
    "percent": (Decimal("0.01"), {}),
    "number": (Decimal(1), {}),
}


class RuleError(ValueError):
    """A rule that cannot be loaded, checked or evaluated, with the reason."""


@dataclass(frozen=True)
class Q:
    """A quantity in base units: ``value`` × base, with ``dims``."""

    value: Decimal
    dims: tuple[tuple[str, int], ...] = ()

    @staticmethod
    def of(value: Decimal | str | int, unit: str) -> Q:
        if unit not in UNITS:
            raise RuleError(f"unknown unit {unit!r}")
        scale, dims = UNITS[unit]
        return Q(Decimal(str(value)) * scale, tuple(sorted(dims.items())))

    def to(self, unit: str) -> Decimal:
        scale, dims = UNITS[unit]
        if self.dims != tuple(sorted(dims.items())):
            raise RuleError(f"a quantity of dimension {dim_words(self.dims)} cannot be expressed in {unit}")
        return self.value / scale


def dim_words(dims: tuple[tuple[str, int], ...]) -> str:
    return " ".join(f"{d}^{p}" if p != 1 else d for d, p in dims) or "dimensionless"


def _combine(a: tuple, b: tuple, sign: int) -> tuple:
    out = dict(a)
    for d, p in b:
        out[d] = out.get(d, 0) + sign * p
    return tuple(sorted((d, p) for d, p in out.items() if p))


# ---------------------------------------------------------------- the formula language

_FUNCS = {"avg", "min", "max", "sum", "ifneg"}


def parse(formula: str) -> ast.Expression:
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as e:
        raise RuleError(f"formula does not parse: {e.msg}") from e
    for node in ast.walk(tree):
        if isinstance(node, ast.Expression | ast.Load | ast.Add | ast.Sub | ast.Mult | ast.Div | ast.USub):
            continue
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub | ast.Mult | ast.Div):
            continue
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            continue
        if isinstance(node, ast.Name):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
            continue
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCS
            and not node.keywords
        ):
            continue
        raise RuleError(f"formula uses {type(node).__name__}, which the rule language does not allow")
    return tree


def names_in(tree: ast.Expression) -> set[str]:
    return {
        n.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and not any(isinstance(p, ast.Call) and p.func is n for p in ast.walk(tree))
    }


def evaluate(tree: ast.Expression, env: dict[str, Q], source: str) -> Q:
    def ev(node: ast.AST) -> Q:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            # the literal's own text, never the float the parser made of it
            text = ast.get_source_segment(source, node) or repr(node.value)
            return Q(Decimal(text))
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise RuleError(f"input {node.id!r} has no value")
            return env[node.id]
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            return Q(-v.value, v.dims)
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add | ast.Sub):
                if a.dims != b.dims:
                    raise RuleError(f"cannot add or subtract {dim_words(a.dims)} and {dim_words(b.dims)}")
                return Q(a.value + b.value if isinstance(node.op, ast.Add) else a.value - b.value, a.dims)
            if isinstance(node.op, ast.Mult):
                return Q(a.value * b.value, _combine(a.dims, b.dims, 1))
            if b.value == 0:
                raise RuleError("division by zero")
            return Q(a.value / b.value, _combine(a.dims, b.dims, -1))
        if isinstance(node, ast.Call) and node.func.id == "ifneg":
            # ifneg(test, then, otherwise): "then" when test < 0 — the one conditional (a gap
            # carries one rate, a surplus another); both branches must be the same dimension
            if len(node.args) != 3:
                raise RuleError("ifneg() takes (test, then, otherwise)")
            test, a, b = (ev(x) for x in node.args)
            if a.dims != b.dims:
                raise RuleError("ifneg() branches of different dimensions")
            return a if test.value < 0 else b
        if isinstance(node, ast.Call):
            args = [ev(x) for x in node.args]
            if not args:
                raise RuleError(f"{node.func.id}() needs arguments")
            if any(x.dims != args[0].dims for x in args):
                raise RuleError(f"{node.func.id}() of quantities of different dimensions")
            vals = [x.value for x in args]
            f = node.func.id
            v = (
                sum(vals, Decimal(0)) / len(vals)
                if f == "avg"
                else min(vals)
                if f == "min"
                else max(vals)
                if f == "max"
                else sum(vals, Decimal(0))
            )
            return Q(v, args[0].dims)
        raise RuleError(f"unexpected {type(node).__name__}")

    return ev(tree)


# ---------------------------------------------------------------- rule documents


class Clause(BaseModel):
    model_config = ConfigDict(extra="forbid")
    regulation: str  # title and year, e.g. "UPERC (Multi Year Distribution Tariff) Regulations, 2025"
    clause: str | None = None  # e.g. "Regulation 25.2"
    source_id: str | None = None  # the registered regulation, when on file
    page: int | None = None
    excerpt: str | None = None
    verified: bool = False  # the excerpt checked against the page by a person


class Applies(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commission: str
    licensee_kinds: list[str] = Field(default_factory=lambda: ["distribution"])
    proceedings: list[str] = Field(default_factory=lambda: ["annual_arr", "myt", "true_up", "apr"])
    from_fy: str | None = None  # inclusive, "FY2025-26"
    to_fy: str | None = None


class InputSpec(BaseModel):
    """Where an input comes from.  ``source`` is ``fact:<LINE>`` (a reviewed fact),
    ``record:<name>`` (a utility record), ``assumption:<name>`` (the petitioner's, with its
    source), ``rule:<output>`` (another rule this year), ``prior:<output>`` (that output last
    year), or ``regulation`` — a parameter the clause itself fixes, whose ``value`` is then given
    here and cited by the rule's clause."""

    model_config = ConfigDict(extra="forbid")
    unit: str
    source: str
    value: str | None = None  # only for source "regulation"
    note: str | None = None


class Rounding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    places: int = 2
    mode: Literal["half_up", "half_even"] = "half_up"
    feeds: Literal["unrounded", "rounded"] = "unrounded"  # which value dependants use


class Example(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inputs: dict[str, str]  # name → value in the input's unit
    expected: str  # in the output unit, at the rule's printed precision
    source: str  # where the example comes from (an order page, a filed format cell)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9_.-]+$")
    version: int = Field(ge=1)
    status: Literal["draft", "approved", "superseded"] = "draft"
    title: str
    output: str  # the name other rules refer to
    unit: str
    line_code: str | None = None  # the taxonomy line the output is, when it is one
    schedule: str | None = None  # R-SCH id, e.g. "R-SCH-9"
    formula: str
    inputs: dict[str, InputSpec]
    rounding: Rounding = Field(default_factory=Rounding)
    clause: Clause
    applies: Applies
    exceptions: list[str] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
    approved_by: str | None = None
    approved_at: str | None = None
    note: str | None = None
    # evaluated once per category of this kind (e.g. "asset_class"), on the category's own
    # values; a rule without ``per`` takes the categories' outputs only as ``sum:<output>``
    per: str | None = None


def rules_dir() -> Path:
    here = Path(__file__).resolve()
    for p in [here, *here.parents]:
        cand = p / "packages" / "arr-rules"
        if cand.is_dir():
            return cand
    raise RuleError("packages/arr-rules not found")


def load_rules(commission: str) -> list[Rule]:
    d = rules_dir() / commission.lower()
    if not d.is_dir():
        return []
    out: list[Rule] = []
    for f in sorted(d.glob("*.json")):
        doc = json.loads(f.read_text())
        for r in doc["rules"] if "rules" in doc else [doc]:
            out.append(Rule.model_validate(r))
    return out


def _round(v: Decimal, r: Rounding) -> Decimal:
    return v.quantize(Decimal(1).scaleb(-r.places), rounding=ROUND_HALF_UP if r.mode == "half_up" else ROUND_HALF_EVEN)


@dataclass
class Result:
    output: str
    rule: str
    version: int
    status: str
    value: Decimal  # unrounded, in the rule's unit
    rounded: Decimal
    unit: str
    inputs: dict[str, tuple[Decimal, str]]
    formula: str


@dataclass
class Evaluation:
    fiscal_year: str
    results: dict[str, Result] = field(default_factory=dict)
    blocked: dict[str, str] = field(default_factory=dict)  # output → why it could not be computed
    order: list[str] = field(default_factory=list)
    by_category: dict[str, dict[str, Result]] = field(default_factory=dict)  # category → output → result
    blocked_by_category: dict[str, dict[str, str]] = field(default_factory=dict)

    clauses_verified: bool = False

    @property
    def filing_ready(self) -> bool:
        """Every output computed, by approved rules on verified clauses (R-APP-4)."""
        computed = [*self.results.values(), *(r for rs in self.by_category.values() for r in rs.values())]
        return (
            not self.blocked
            and not any(self.blocked_by_category.values())
            and self.clauses_verified
            and all(r.status == "approved" for r in computed)
        )


def _fy(fy: str) -> int:
    return int(fy[2:6])


def applies_in(r: Rule, fiscal_year: str) -> bool:
    y = _fy(fiscal_year)
    return (r.applies.from_fy is None or _fy(r.applies.from_fy) <= y) and (
        r.applies.to_fy is None or y <= _fy(r.applies.to_fy)
    )


def check_rule(r: Rule) -> ast.Expression:
    """A rule's own checks, whatever the year: the formula parses in the restricted language,
    names exactly its inputs, units are known, regulation parameters carry their value, and the
    formula's dimension is the output's."""
    tree = parse(r.formula)
    used = names_in(tree)
    if missing := used - set(r.inputs):
        raise RuleError(f"rule {r.id}: formula names {sorted(missing)} that are not declared inputs")
    if unused := set(r.inputs) - used:
        raise RuleError(f"rule {r.id}: inputs {sorted(unused)} are declared but not used")
    for name, spec in r.inputs.items():
        if spec.unit not in UNITS:
            raise RuleError(f"rule {r.id}: input {name} has unknown unit {spec.unit!r}")
        if (spec.source == "regulation") != (spec.value is not None):
            raise RuleError(f"rule {r.id}: input {name}: a value is given exactly when the regulation fixes it")
    if r.unit not in UNITS:
        raise RuleError(f"rule {r.id}: unknown output unit {r.unit!r}")
    # the check is about units, not values: distinct small probes keep "1 - loss" from being zero
    env = {
        n: Q.of(Decimal("0.137") + Decimal("0.0731") * i, s.unit) for i, (n, s) in enumerate(sorted(r.inputs.items()))
    }
    try:
        evaluate(tree, env, r.formula).to(r.unit)
    except RuleError as e:
        raise RuleError(f"rule {r.id}: {e}") from e
    return tree


def run_example(r: Rule, ex: Example) -> tuple[bool, Decimal]:
    env = {n: Q.of(Decimal(s.value if s.source == "regulation" else ex.inputs[n]), s.unit) for n, s in r.inputs.items()}
    got = _round(evaluate(parse(r.formula), env, r.formula).to(r.unit), r.rounding)
    return got == Decimal(ex.expected), got


class RuleSet:
    """A commission's rules for one financial year (one version per output) with their
    dependency order.  Rules are chosen **per year** by their applicability (R-APP-2): one
    petition can compute a true-up year under one regulation and the ARR year under the next.
    Without a year, every current rule is loaded (for checking)."""

    def __init__(self, rules: list[Rule], fiscal_year: str | None = None):
        current = [r for r in rules if r.status != "superseded"]
        if fiscal_year:
            current = [r for r in current if applies_in(r, fiscal_year)]
            outputs: dict[str, list[Rule]] = {}
            for r in current:
                outputs.setdefault(r.output, []).append(r)
            for o, rs in outputs.items():
                if len({x.id for x in rs}) > 1:
                    raise RuleError(f"{fiscal_year}: several rules apply to {o}: {sorted({x.id for x in rs})}")
        self.fiscal_year = fiscal_year
        by_output: dict[str, Rule] = {}
        for r in current:
            if r.output in by_output and by_output[r.output].version >= r.version:
                continue
            by_output[r.output] = r
        self.rules = by_output
        self.trees = {o: check_rule(r) for o, r in by_output.items()}
        self.order = self._order()
        self._check_categories()

    def _deps(self, r: Rule) -> set[str]:
        return {s.source.split(":", 1)[1] for s in r.inputs.values() if s.source.startswith(("rule:", "sum:"))}

    def _check_categories(self) -> None:
        for r in self.rules.values():
            for name, spec in r.inputs.items():
                kind, _, dep = spec.source.partition(":")
                if kind not in ("rule", "sum") or dep not in self.rules:
                    continue
                d = self.rules[dep]
                if kind == "sum" and not d.per:
                    raise RuleError(f"rule {r.id}: input {name} sums {dep}, which is not computed per category")
                if kind == "rule" and d.per and d.per != r.per:
                    raise RuleError(f"rule {r.id}: input {name} takes {dep} per {d.per}; sum it with sum:{dep}")

    def _order(self) -> list[str]:
        order: list[str] = []
        state: dict[str, int] = {}

        def visit(o: str, path: list[str]) -> None:
            if state.get(o) == 2:
                return
            if state.get(o) == 1:
                cycle = path[path.index(o) :] + [o]
                raise RuleError(f"rules form a cycle: {' → '.join(cycle)}")
            state[o] = 1
            for d in sorted(self._deps(self.rules[o])):
                if d not in self.rules:
                    raise RuleError(f"rule {self.rules[o].id} needs the output {d!r}, which no rule produces")
                visit(d, [*path, o])
            state[o] = 2
            order.append(o)

        for o in sorted(self.rules):
            visit(o, [])
        return order

    def run_example(self, r: Rule, ex: Example) -> tuple[bool, Decimal]:
        return run_example(r, ex)

    def evaluate(
        self,
        fiscal_year: str,
        values: dict[str, tuple[Decimal | str, str]],
        categories: dict[str, dict[str, tuple[Decimal | str, str]]] | None = None,
    ) -> Evaluation:
        """Compute every rule for one year.  ``values`` holds what the rules' non-rule inputs
        refer to, keyed by the source string ("fact:C.DEP", "record:gfa_opening",
        "assumption:roe_rate", "prior:equity_closing").  ``categories`` holds, per category
        (an asset class, a consumer category), the values of rules computed ``per`` category;
        a category's value of a source overrides the shared one.  A rule missing an input is
        **blocked** with the reason — never computed from a default."""
        ev = Evaluation(fiscal_year)
        ev.clauses_verified = all(r.clause.verified for r in self.rules.values())
        cats = categories or {}
        for o in self.order:
            r = self.rules[o]
            if r.per:
                for cat, own in cats.items():
                    res, why = self._one(r, {**values, **own}, ev, cat)
                    if res:
                        ev.by_category.setdefault(cat, {})[o] = res
                    else:
                        ev.blocked_by_category.setdefault(cat, {})[o] = why
                if not cats:
                    ev.blocked[o] = f"computed per {r.per}, and no {r.per} was given"
                continue
            res, why = self._one(r, values, ev, None)
            if res:
                ev.results[o] = res
                ev.order.append(o)
            else:
                ev.blocked[o] = why
        return ev

    def _one(
        self, r: Rule, values: dict[str, tuple[Decimal | str, str]], ev: Evaluation, cat: str | None
    ) -> tuple[Result | None, str | None]:
        env: dict[str, Q] = {}
        used: dict[str, tuple[Decimal, str]] = {}
        for name, spec in r.inputs.items():
            kind, _, dep = spec.source.partition(":")
            if kind == "rule":
                done = ev.by_category.get(cat, {}) if self.rules[dep].per else ev.results
                if dep not in done:
                    return None, f"needs {dep}, which is blocked"
                res = done[dep]
                v = res.rounded if self.rules[dep].rounding.feeds == "rounded" else res.value
                q = Q.of(v, res.unit)
            elif kind == "sum":
                parts = [(c, rs.get(dep)) for c, rs in ev.by_category.items()]
                missing = sorted(c for c, bl in ev.blocked_by_category.items() if dep in bl)
                if missing or not parts:
                    return None, f"needs {dep} for every category; blocked for {', '.join(missing) or 'all'}"
                unit = self.rules[dep].unit
                total = sum((p.value for _, p in parts if p), Decimal(0))
                q = Q.of(total, unit)
            elif spec.source == "regulation":
                q = Q.of(Decimal(spec.value), spec.unit)
            elif spec.source in values:
                raw, unit = values[spec.source]
                q = Q.of(Decimal(str(raw)), unit)
            else:
                return None, f"input {name} ({spec.source}) has no value"
            try:
                used[name] = (q.to(spec.unit), spec.unit)
            except RuleError as e:
                return None, f"input {name}: {e}"
            env[name] = q
        v = evaluate(self.trees[r.output], env, r.formula).to(r.unit)
        return Result(r.output, r.id, r.version, r.status, v, _round(v, r.rounding), r.unit, used, r.formula), None


def check_all(commission: str) -> list[str]:
    """Load a commission's rules, check each, check that every year a rule boundary names has an
    unambiguous, acyclic set, and run every worked example.  Returns the problems (empty when all
    is well).  Run in CI (R-RULE-2)."""
    problems: list[str] = []
    try:
        rules = load_rules(commission)
    except (RuleError, ValueError) as e:
        return [str(e)]
    good = []
    for r in rules:
        try:
            check_rule(r)
            good.append(r)
        except RuleError as e:
            problems.append(str(e))
    years = {fy for r in good for fy in (r.applies.from_fy, r.applies.to_fy) if fy}
    for fy in sorted(years):
        try:
            RuleSet(good, fy)
        except RuleError as e:
            problems.append(f"{fy}: {e}")
    for r in good:
        if r.status == "approved" and not r.examples:
            problems.append(f"rule {r.id}: approved without a worked example")
        if r.status == "approved" and not (r.approved_by and r.approved_at):
            problems.append(f"rule {r.id}: approved without an approver and a date")
        if r.status == "approved" and not r.clause.verified:
            problems.append(f"rule {r.id}: approved on a clause nobody verified")
        for i, ex in enumerate(r.examples):
            ok, got = run_example(r, ex)
            if not ok:
                problems.append(f"rule {r.id} example {i + 1} ({ex.source}): expected {ex.expected}, got {got}")
    return problems


def as_trace(ev: Evaluation) -> list[dict[str, Any]]:
    return [
        {
            "output": r.output,
            "rule": f"{r.rule} v{r.version} ({r.status})",
            "formula": r.formula,
            "inputs": {k: [str(v), u] for k, (v, u) in r.inputs.items()},
            "value": str(r.value),
            "rounded": str(r.rounded),
            "unit": r.unit,
        }
        for r in (ev.results[o] for o in ev.order)
    ]
