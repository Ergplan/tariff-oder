"""Reproduce a filed format from its inputs through the rules (milestone 13, R-ACC-1).

A **binding** (`packages/reference-filings/<filing>/bindings/<format>.json`) says which rows of
a filed format sheet are the rules' inputs and which are their outputs:

    {"sheet": "F26_ROE",
     "inputs":  {"prior:equity_closing": 8, "record:equity_addition": 10, ...},
     "outputs": {"equity_closing": 11, "return_on_equity": 14},
     "unit": "INR_crore"}          # optional: for rows whose unit the sheet does not state

For every column of the sheet (a year and a voice) the input rows' stored values feed the
commission's rules for that year, and every bound output is compared with the filed figure at
the precision the format prints.  Each output is ``match``, ``differs`` (with both numbers) or
``blocked`` (with the reason: a missing input, or no rule for that year).  A filed figure that
is a state ("Incl. above", "NA") is ``not_a_value``.

This measures the *rules* against what the petitioner filed.  A match says the draft rule
computes what the petitioner computed — not that either is what the regulation requires.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .rules import Q, Rule, RuleError, RuleSet


@dataclass
class OutputCheck:
    output: str
    row: int | str
    label: str
    fiscal_year: str
    voice: str
    words: str
    result: str  # match | differs | blocked | not_a_value | no_filed_value | given (an input, not reproduced)
    filed: str | None = None
    computed: str | None = None
    unit: str | None = None
    why: str | None = None
    rule: str | None = None


@dataclass
class FormatReproduction:
    sheet: str
    columns: int
    checks: list[OutputCheck] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.checks:
            out[c.result] = out.get(c.result, 0) + 1
        return out


def _places(displayed: str) -> int:
    return max(0, -Decimal(displayed).as_tuple().exponent)


def reproduce(
    sheet: dict[str, Any], binding: dict[str, Any], rules: list[Rule], sheets: dict[str, dict] | None = None
) -> FormatReproduction:
    """``sheet`` is one sheet of a reference (as `scripts/build_reference.py` writes it).  A bound
    row is a row number of that sheet, or ``"<other sheet>!<row>"`` — an input or a check taken
    from another format (``sheets`` holds them), matched to the column by year and voice: a
    figure carried from one format to another is the same figure (R-SCH-16)."""
    rows = {r["row"]: r for r in sheet["rows"]}
    others = {name: {r["row"]: r for r in sh["rows"]} for name, sh in (sheets or {}).items()}

    def where(ref: int | str) -> tuple[dict[int, dict], int, bool]:
        if isinstance(ref, int):
            return rows, ref, True
        name, _, n = str(ref).rpartition("!")
        if name not in others:
            raise RuleError(f"{sheet['sheet']}: bound sheet {name!r} is not in the reference")
        return others[name], int(n), False

    # the unit of rows the sheet leaves unstated (a format with no unit line), declared by the binding
    default_unit = binding.get("unit")
    blank_is_zero = set(binding.get("blank_is_zero", {}).get("rows", []))
    negate = set(binding.get("negate", {}).get("rows", []))
    missing = [
        ref for ref in [*binding["inputs"].values(), *binding["outputs"].values()] if where(ref)[1] not in where(ref)[0]
    ]
    if missing:
        raise RuleError(f"{sheet['sheet']}: bound rows {missing} are not rows the reference read")
    columns: list[tuple[str, str, str]] = []
    for r in sheet["rows"]:
        for c in r["cells"]:
            key = (c["fiscal_year"], c["voice"], c["words"])
            if key not in columns:
                columns.append(key)

    def cell(ref: int | str, col: tuple[str, str, str]) -> dict | None:
        table, n, own = where(ref)
        cells = table[n]["cells"]
        exact = next((c for c in cells if (c["fiscal_year"], c["voice"], c["words"]) == col), None)
        if exact or own:
            return exact
        return next((c for c in cells if (c["fiscal_year"], c["voice"]) == col[:2]), None)

    def row_of(ref: int | str) -> dict:
        table, n, _ = where(ref)
        return table[n]

    def res_sources(output: str, ev: Any) -> set[str]:
        """The non-rule sources the year's rule for ``output`` read directly."""
        rule = next((r for r in rules if r.output == output and r.id == ev.results[output].rule), None)
        return {s.source for s in rule.inputs.values()} if rule else set()

    out = FormatReproduction(sheet["sheet"], len(columns))
    sets: dict[str, RuleSet | RuleError] = {}
    for col in columns:
        fy, voice, words = col
        if fy not in sets:
            try:
                sets[fy] = RuleSet(rules, fy)
            except RuleError as e:
                sets[fy] = e
        rs = sets[fy]
        values: dict[str, tuple[Decimal | str, str]] = {}
        for source, row in binding["inputs"].items():
            c = cell(row, col)
            if c and c["state"] == "value":
                v = c["value"]
                if row in negate:  # a deduction the format prints negative, declared by the binding
                    v = str(-Decimal(v))
                values[source] = (v, c["unit"] or row_of(row)["unit"] or default_unit)
            elif c is None and row in blank_is_zero:
                # declared by the binding, with its reason: the petitioner's formula reads this
                # blank cell as zero.  Never assumed: an undeclared blank blocks.
                values[source] = ("0", row_of(row)["unit"] or default_unit)
        ev = rs.evaluate(fy, values) if isinstance(rs, RuleSet) else None
        for output, row in binding["outputs"].items():
            c = cell(row, col)
            base = dict(output=output, row=row, label=row_of(row)["label"], fiscal_year=fy, voice=voice, words=words)
            if c is None:
                out.checks.append(OutputCheck(**base, result="no_filed_value"))
                continue
            if c["state"] != "value" or c["displayed"] is None:
                out.checks.append(OutputCheck(**base, result="not_a_value", filed=c["printed"]))
                continue
            if ev is None:
                out.checks.append(OutputCheck(**base, result="blocked", filed=c["displayed"], why=str(rs)))
                continue
            if output not in ev.results:
                why = ev.blocked.get(output, f"no rule for {output} applies in {fy}")
                out.checks.append(OutputCheck(**base, result="blocked", filed=c["displayed"], why=why))
                continue
            res = ev.results[output]
            if any(row == r and src in res_sources(output, ev) for src, r in binding["inputs"].items()):
                # the year's rule took this very row as its input: nothing was reproduced
                out.checks.append(OutputCheck(**base, result="given", filed=c["displayed"], rule=res.rule))
                continue
            unit = c["unit"] or row_of(row)["unit"] or default_unit or res.unit
            places = _places(c["displayed"])
            try:
                got = Q.of(res.value, res.unit).to(unit).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
            except RuleError as e:
                out.checks.append(OutputCheck(**base, result="blocked", filed=c["displayed"], why=str(e)))
                continue
            filed = Decimal(c["displayed"])
            out.checks.append(
                OutputCheck(
                    **base,
                    result="match" if got == filed else "differs",
                    filed=c["displayed"],
                    computed=str(got),
                    unit=unit,
                    rule=f"{res.rule} v{res.version} ({res.status})",
                )
            )
    return out


@dataclass
class BlockCheck:
    table: str
    fiscal_year: str
    category: str  # the row label (an asset class), or "TOTAL"
    output: str
    result: str  # match | differs | blocked | no_filed_value
    filed: str | None = None
    computed: str | None = None
    why: str | None = None


def reproduce_blocks(blocks: list, binding: dict[str, Any], rules: list[Rule]) -> list[BlockCheck]:
    """Reproduce year-block workings (see :mod:`tariff_api.arr.blocks`) category by category.

    ``binding``: ``{"inputs": {"record:gfa_opening": "opening_gfa", ...}, "outputs":
    {"gfa_closing": "closing_gfa", ...}, "totals": {"depreciation_gross_total": "gross_dep"},
    "places": 4}`` — the block columns that feed per-category rules, the columns the per-category
    outputs are compared with, and the block totals the aggregate rules are compared with, at
    ``places`` decimals of the stored values (workings keep unrounded figures)."""
    places = int(binding.get("places", 4))
    q = Decimal(1).scaleb(-places)
    out: list[BlockCheck] = []
    for b in blocks:
        try:
            rs = RuleSet(rules, b.fiscal_year)
        except RuleError as e:
            out.append(BlockCheck(b.title, b.fiscal_year, "*", "*", "blocked", why=str(e)))
            continue
        cats = {}
        blank_zero = set(binding.get("blank_is_zero", {}).get("columns", []))
        for r in b.rows:
            vals = {}
            for source, key in binding["inputs"].items():
                unit = binding.get("units", {}).get(key, "INR_crore")
                if key in r.values:
                    vals[source] = (r.values[key], unit)
                elif key in blank_zero:
                    vals[source] = ("0", unit)  # declared by the binding with its reason; never assumed
            cats[r.label] = vals
        ev = rs.evaluate(b.fiscal_year, {}, cats)
        for r in b.rows:
            for output, key in binding["outputs"].items():
                filed = r.values.get(key)
                if filed is None:
                    out.append(BlockCheck(b.title, b.fiscal_year, r.label, output, "no_filed_value"))
                    continue
                res = ev.by_category.get(r.label, {}).get(output)
                if res is None:
                    why = ev.blocked_by_category.get(r.label, {}).get(output, "not computed")
                    out.append(BlockCheck(b.title, b.fiscal_year, r.label, output, "blocked", filed=filed, why=why))
                    continue
                got, want = res.value.quantize(q), Decimal(filed).quantize(q)
                out.append(
                    BlockCheck(
                        b.title,
                        b.fiscal_year,
                        r.label,
                        output,
                        "match" if got == want else "differs",
                        filed=str(want),
                        computed=str(got),
                    )
                )
        for output, key in binding.get("totals", {}).items():
            filed = b.totals.get(key)
            res = ev.results.get(output)
            if filed is None:
                out.append(BlockCheck(b.title, b.fiscal_year, "TOTAL", output, "no_filed_value"))
            elif res is None:
                out.append(
                    BlockCheck(
                        b.title, b.fiscal_year, "TOTAL", output, "blocked", filed=filed, why=ev.blocked.get(output)
                    )
                )
            else:
                got, want = res.value.quantize(q), Decimal(filed).quantize(q)
                out.append(
                    BlockCheck(
                        b.title,
                        b.fiscal_year,
                        "TOTAL",
                        output,
                        "match" if got == want else "differs",
                        filed=str(want),
                        computed=str(got),
                    )
                )
    return out
