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

import re
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
    sheet: dict[str, Any],
    binding: dict[str, Any],
    rules: list[Rule],
    sheets: dict[str, dict] | None = None,
    fed: dict[tuple[str, str], dict[str, tuple[Decimal | str, str]]] | None = None,
) -> FormatReproduction:
    """``sheet`` is one sheet of a reference (as `scripts/build_reference.py` writes it).  A bound
    row is a row number of that sheet, or ``"<other sheet>!<row>"`` — an input or a check taken
    from another format (``sheets`` holds them), matched to the column by year and voice: a
    figure carried from one format to another is the same figure (R-SCH-16).

    ``fed`` holds, per column (fiscal year, voice), values computed by other bindings (a
    schedule's reproduction): they replace the inputs they name, so the format is computed from
    the schedules rather than from its own rows.  Only those columns are evaluated."""
    rows = {r["row"]: r for r in sheet["rows"]}
    others = {name: {r["row"]: r for r in sh["rows"]} for name, sh in (sheets or {}).items()}

    def offset_of(ref: int | str) -> tuple[int | str, int]:
        """``"22@-1"`` / ``"F17_O&M_CPI!23@-2"``: the row, and how many columns to the left (the
        same row of an earlier year: last year's closing, the three years an average spans)."""
        if isinstance(ref, str) and "@" in ref:
            base, _, k = ref.rpartition("@")
            return (int(base) if base.isdigit() else base), int(k)
        return ref, 0

    def where(ref: int | str) -> tuple[dict[int, dict], int, bool]:
        ref, _ = offset_of(ref)
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
    states_as_zero = set(binding.get("states_as_zero", {}).get("states", []))
    year_only = set(binding.get("match_year_only", {}).get("sheets", []))
    # a row the binding declares blank-as-zero may be blank in every column, hence not read at all
    for ref in binding.get("blank_is_zero", {}).get("rows", []):
        if isinstance(ref, int) and ref not in rows:
            rows[ref] = {"row": ref, "label": "(blank in every column)", "unit": None, "cells": []}
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
        _, k = offset_of(ref)
        if k:
            # the column ``k`` places from this one, in the sheet's own column order
            ordered = sheet_columns if own else other_columns(ref)
            if col not in ordered and not own:
                col = next((c for c in ordered if c[:2] == col[:2]), col)
            if col not in ordered or not 0 <= ordered.index(col) + k < len(ordered):
                return None
            col = ordered[ordered.index(col) + k]
            own = True if own else own
            cells = table[n]["cells"]
            return next((c for c in cells if (c["fiscal_year"], c["voice"], c["words"]) == col), None)
        cells = table[n]["cells"]
        exact = next((c for c in cells if (c["fiscal_year"], c["voice"], c["words"]) == col), None)
        if exact or own:
            return exact
        same_voice = next((c for c in cells if (c["fiscal_year"], c["voice"]) == col[:2]), None)
        if same_voice:
            return same_voice
        # a format whose columns are a data series, not voices (a price index), may be matched by the
        # year alone — only when the binding declares that format so, and it has one column for the
        # year.  Never otherwise: a Commission's approval must not be fed a petitioner's estimate.
        name = str(offset_of(ref)[0]).rpartition("!")[0]
        if name not in year_only:
            return None
        of_year = [c for c in cells if c["fiscal_year"] == col[0]]
        return of_year[0] if len(of_year) == 1 else None

    def row_of(ref: int | str) -> dict:
        table, n, _ = where(ref)
        return table[n]

    def res_sources(output: str, ev: Any) -> set[str]:
        """The non-rule sources the year's rule for ``output`` read directly."""
        rule = next((r for r in rules if r.output == output and r.id == ev.results[output].rule), None)
        return {s.source for s in rule.inputs.values()} if rule else set()

    sheet_columns = columns

    def other_columns(ref: int | str) -> list[tuple[str, str, str]]:
        base, _ = offset_of(ref)
        name = str(base).rpartition("!")[0]
        seen: list[tuple[str, str, str]] = []
        for r in (sheets or {})[name]["rows"]:
            for c in r["cells"]:
                key = (c["fiscal_year"], c["voice"], c["words"])
                if key not in seen:
                    seen.append(key)
        return seen

    out = FormatReproduction(sheet["sheet"], len(columns))
    sets: dict[str, RuleSet | RuleError] = {}
    for col in columns:
        fy, voice, words = col
        if fed is not None and (fy, voice) not in fed:
            continue
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
            elif c and c["state"] in states_as_zero:
                # declared by the binding with its reason: "Incl. in A&G" / "NA" add nothing to a sum
                values[source] = ("0", c["unit"] or row_of(row)["unit"] or default_unit)
            elif c is None and row in blank_is_zero:
                # declared by the binding, with its reason: the petitioner's formula reads this
                # blank cell as zero.  Never assumed: an undeclared blank blocks.
                values[source] = ("0", row_of(row)["unit"] or default_unit)
        # per-year constants the binding declares, with their source (a rate typed inside the
        # petitioner's formula, not printed in any cell)
        for source, (v, unit) in binding.get("constants", {}).get(fy, {}).items():
            values.setdefault(source, (v, unit))
        if fed is not None:
            values.update(fed[(fy, voice)])
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
    exact: str | None = None  # the computed value unrounded, in the rule's unit (to feed another binding)


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


def reproduce_period_table(wb: Any, binding: dict[str, Any], rules: list[Rule]) -> list[BlockCheck]:
    """A table of periods within a year (e.g. the SBI MCLR revisions of F27: from, to, days,
    rate), each period a category, read by cell address from the filed workbook, and the derived
    figures checked against the cells the format prints them in (``"Sheet!E34"``)."""
    from openpyxl.utils import column_index_from_string

    places = int(binding.get("places", 6))
    q = Decimal(1).scaleb(-places)
    ws = wb[binding["sheet"]]
    out: list[BlockCheck] = []
    for t in binding["tables"]:
        cats = {}
        first, last = t["rows"]
        for r in range(first, last + 1):
            days = ws.cell(r, column_index_from_string(t["days_col"])).value
            rate = ws.cell(r, column_index_from_string(t["rate_col"])).value
            start = ws.cell(r, column_index_from_string(t["from_col"])).value
            if days is None or rate is None:
                continue
            cats[str(start)[:10]] = {
                "record:mclr_days": (str(days), "number"),
                "record:mclr_rate": (repr(rate) if isinstance(rate, float) else str(rate), "fraction"),
            }
        ev = RuleSet(rules, t["fiscal_year"]).evaluate(t["fiscal_year"], {}, cats)
        for output, ref in t["checks"].items():
            sheet, _, cell = ref.rpartition("!")
            filed = wb[sheet][cell].value
            res = ev.results.get(output)
            if res is None:
                out.append(
                    BlockCheck(binding["sheet"], t["fiscal_year"], ref, output, "blocked", why=ev.blocked.get(output))
                )
                continue
            want = Decimal(repr(filed) if isinstance(filed, float) else str(filed)).quantize(q)
            got = res.value.quantize(q)
            result = "match" if got == want else "differs"
            check = BlockCheck(
                binding["sheet"], t["fiscal_year"], ref, output, result, filed=str(want), computed=str(got)
            )
            check.exact = str(res.value)
            out.append(check)
    return out


def reproduce_row_table(wb: Any, binding: dict[str, Any], rules: list[Rule]) -> list[BlockCheck]:
    """A table whose rows are categories and whose columns are fixed attributes (UPERC's power
    purchase summary: one row per source; MU, charges, rates), read by cell address.  Each row with
    a label and at least one bound value is a category; per-category outputs are checked against
    their columns, aggregate outputs against the table's total cells.  A blank cell is absent
    unless the binding declares its column blank-as-zero, with the reason."""
    from openpyxl.utils import column_index_from_string as col_of

    places = int(binding.get("places", 2))
    q = Decimal(1).scaleb(-places)
    ws = wb[binding["sheet"]]
    first, last = binding["rows"]
    label_col = col_of(binding["label_col"])
    skip = re.compile(binding.get("skip_labels", r"^(sub\s*total|grand\s*total|total)\b"), re.I)
    blank_zero = set(binding.get("blank_is_zero", {}).get("columns", []))
    units = binding.get("units", {})
    out: list[BlockCheck] = []
    cats: dict[str, dict] = {}
    rows_of: dict[str, int] = {}
    skip_rows = set(binding.get("skip_rows", {}).get("rows", []))  # subtotal rows, with the reason
    for r in range(first, last + 1):
        label = str(ws.cell(r, label_col).value or "").strip()
        if not label or skip.search(label) or r in skip_rows:
            continue
        vals = {}
        for source, col in binding["inputs"].items():
            v = ws.cell(r, col_of(col)).value
            if isinstance(v, int | float) and not isinstance(v, bool):
                vals[source] = (repr(v) if isinstance(v, float) else str(v), units.get(col, "INR_crore"))
        if not vals:
            continue  # a heading row ("Medium Term Power")
        for source, col in binding["inputs"].items():
            if source not in vals and col in blank_zero:
                vals[source] = ("0", units.get(col, "INR_crore"))
        key = f"{label} (row {r})"
        cats[key], rows_of[key] = vals, r
    fy = binding["fiscal_year"]
    shared: dict[str, tuple[Decimal | str, str]] = {}
    for source, spec in binding.get("shared", {}).items():
        # a value for every row: a cell of the sheet (a deduction printed below the total), or a
        # stated constant — each with its reason in the binding
        if "cell" in spec:
            raw = ws[spec["cell"]].value
            if not isinstance(raw, int | float) or isinstance(raw, bool):
                continue  # blank: absent, never 0
            v = Decimal(repr(raw) if isinstance(raw, float) else str(raw))
            shared[source] = (-v if spec.get("negate") else v, spec.get("unit", "INR_crore"))
        else:
            shared[source] = (str(spec["value"]), spec.get("unit", "INR_crore"))
    ev = RuleSet(rules, fy).evaluate(fy, shared, cats)
    for cat, r in rows_of.items():
        for output, col in binding.get("outputs", {}).items():
            filed = ws.cell(r, col_of(col)).value
            if not isinstance(filed, int | float):
                continue
            res = ev.by_category.get(cat, {}).get(output)
            if res is None:
                why = ev.blocked_by_category.get(cat, {}).get(output)
                out.append(BlockCheck(binding["sheet"], fy, cat, output, "blocked", why=why))
                continue
            want = Decimal(repr(filed)).quantize(q)
            got = Q.of(res.value, res.unit).to(units.get(col, res.unit)).quantize(q)
            out.append(
                BlockCheck(
                    binding["sheet"],
                    fy,
                    cat,
                    output,
                    "match" if got == want else "differs",
                    filed=str(want),
                    computed=str(got),
                )
            )
    for output, refs in binding.get("totals", {}).items():
        for ref in [refs] if isinstance(refs, str) else refs:
            sheet, _, cell = ref.rpartition("!")
            filed = wb[sheet or binding["sheet"]][cell].value
            res = ev.results.get(output)
            label = f"TOTAL {ref}"
            if res is None:
                out.append(BlockCheck(binding["sheet"], fy, label, output, "blocked", why=ev.blocked.get(output)))
                continue
            if not isinstance(filed, int | float) or isinstance(filed, bool):
                out.append(BlockCheck(binding["sheet"], fy, label, output, "no_filed_value", computed=str(res.value)))
                continue
            want = Decimal(repr(filed) if isinstance(filed, float) else str(filed)).quantize(q)
            got = res.value.quantize(q)
            result = "match" if got == want else "differs"
            check = BlockCheck(binding["sheet"], fy, label, output, result, filed=str(want), computed=str(got))
            check.exact = str(res.value)
            out.append(check)
    return out


def _stored(value: Any) -> Decimal | None:
    """A stored cell value as Decimal (the binary value's shortest repr), or None when blank or
    not a number — never zero."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, int):
        return Decimal(value)
    return None


def reproduce_cells(
    wb: Any, binding: dict[str, Any], rules: list[Rule], others: dict[str, Any] | None = None
) -> list[BlockCheck]:
    """Workings laid out freely on a sheet (e.g. NPCL's base-year determination of employee and
    A&G expenses: five years' actuals, their average, the year-by-year escalation, the growth
    factors), read by cell address.  Each evaluation names its year, its input cells
    (``{"record:x": ["C9", "INR_crore"]}``; ``"Sheet!C9"`` for another sheet) and the cells its
    outputs are checked against — on this sheet, and wherever the figure is carried (the ARR
    format).  An evaluation may also have ``categories`` (the months of a year: each with its own
    inputs and checks) whose results its aggregate rules sum.  An input may instead be a stated
    constant (``{"value": "0.065", "unit": "fraction", "why": …}`` — a literal in the utility's
    formula) or a cell declared blank-as-zero (``{"cell": …, "unit": …, "blank_is_zero": why}``);
    otherwise a blank input cell blocks the outputs that need it — never zero.  A reference
    ``"<name>::Sheet!A1"`` reads another workbook of the filing (``others``: name → workbook,
    as the binding's ``workbooks`` names them) — a utility's record checked against the formats."""
    places = int(binding.get("places", 6))
    q = Decimal(1).scaleb(-places)

    def at(ref: str) -> Any:
        book = wb
        if "::" in ref:
            name, _, ref = ref.partition("::")
            if not others or name not in others:
                raise RuleError(f"{binding['sheet']}: workbook {name!r} is not loaded")
            book = others[name]
        sheet, _, cell = ref.rpartition("!")
        return book[sheet or binding["sheet"]][cell].value

    def read(inputs: dict[str, Any]) -> dict[str, tuple[Decimal | str, str]]:
        values: dict[str, tuple[Decimal | str, str]] = {}
        for source, spec in inputs.items():
            if isinstance(spec, dict):
                if "value" in spec:
                    if not spec.get("why"):
                        raise ValueError(f"{source}: a stated constant needs its reason")
                    values[source] = (str(spec["value"]), spec["unit"])
                    continue
                ref, unit = spec["cell"], spec["unit"]
            else:
                ref, unit = spec
            v = _stored(at(ref))
            if v is None and isinstance(spec, dict) and spec.get("blank_is_zero"):
                v = Decimal(0)
            if v is not None:
                values[source] = (v, unit)
        return values

    def check(fy: str, label: str, output: str, ref: str, res: Any, why: str | None) -> BlockCheck:
        tag = f"{label} {ref}".strip()
        if res is None:
            return BlockCheck(binding["sheet"], fy, tag, output, "blocked", why=why)
        filed = _stored(at(ref))
        if filed is None:
            return BlockCheck(binding["sheet"], fy, tag, output, "no_filed_value", computed=str(res.value))
        want, got = filed.quantize(q), res.value.quantize(q)
        result = "match" if got == want else "differs"
        check = BlockCheck(binding["sheet"], fy, tag, output, result, filed=str(want), computed=str(got))
        check.exact = str(res.value)
        return check

    out: list[BlockCheck] = []
    for e in binding["evaluations"]:
        fy = e["fiscal_year"]
        cats = {name: read(c.get("inputs", {})) for name, c in e.get("categories", {}).items()}
        ev = RuleSet(rules, fy).evaluate(fy, read(e.get("inputs", {})), cats or None)
        for name, c in e.get("categories", {}).items():
            for output, refs in c.get("checks", {}).items():
                for ref in [refs] if isinstance(refs, str) else refs:
                    res = ev.by_category.get(name, {}).get(output)
                    why = ev.blocked_by_category.get(name, {}).get(output)
                    out.append(check(fy, f"{e.get('label', '')} {name}".strip(), output, ref, res, why))
        for output, refs in e.get("checks", {}).items():
            for ref in [refs] if isinstance(refs, str) else refs:
                out.append(check(fy, e.get("label", ""), output, ref, ev.results.get(output), ev.blocked.get(output)))
    return out


def reproduce_pipeline(
    binding: dict[str, Any],
    chain: dict[str, Any],
    rules: list[Rule],
    sheets: dict[str, dict],
    results: dict[str, list[BlockCheck]],
) -> dict[str, Any]:
    """The chain computed end to end for the columns a pipeline binding names
    (``{"columns": {"FY2026-27|petitioned": {"record:pp": {"binding": …, "output": …}}}}``): each
    fed input is the value a schedule's binding computed for that year (``results``: binding →
    its checks; the unrounded result, in the rule's unit), not the format's own row.  A feed whose
    schedule computed nothing is listed as not fed; every input not fed stays a record, listed."""
    from collections import Counter
    from dataclasses import asdict

    unit_of = {r.output: r.unit for r in rules}
    out: dict[str, Any] = {"chain": binding["chain"], "columns": []}
    for key, feeds in binding["columns"].items():
        fy, voice = key.split("|")
        fed: dict[str, tuple[Decimal | str, str]] = {}
        sources: dict[str, dict[str, str]] = {}
        missing: list[str] = []
        for source, f in feeds.items():
            # a feed may take another year's value — the petitioner carries a rate forward
            # (NPCL's FY2026-27 loan rate is its FY2025-26 rate) — only with the binding's reason
            year = f.get("fiscal_year", fy)
            if year != fy and not f.get("why"):
                raise RuleError(f"{key}: {source} is fed from {year} without a reason")
            got = next(
                (
                    c
                    for c in results.get(f["binding"], [])
                    if c.fiscal_year == year and c.output == f["output"] and c.exact is not None
                ),
                None,
            )
            if got is None or got.exact is None:
                missing.append(source)
                continue
            fed[source] = (got.exact, unit_of[f["output"]])
            sources[source] = {"binding": f["binding"], "output": f["output"], "value": got.exact}
            if year != fy:
                sources[source]["fiscal_year"] = year
        rep = reproduce(sheets[chain["sheet"]], chain, rules, sheets, fed={(fy, voice): fed})
        checks = [asdict(c) for c in rep.checks if c.result != "no_filed_value"]
        out["columns"].append(
            {
                "fiscal_year": fy,
                "voice": voice,
                "fed": sources,
                "not_fed": missing,
                "records": sorted(s for s in chain["inputs"] if s not in fed),
                "counts": dict(Counter(c["result"] for c in checks)),
                "checks": checks,
            }
        )
    return out


def reproduce_ledger(
    wb: Any, binding: dict[str, Any], rules: list[Rule], others: dict[str, Any] | None = None
) -> list[BlockCheck]:
    """A utility's trial balance reconciled to its claim (R-DATA): for each comparison, the
    accounts whose grouping columns match (``{"G": "Note - 30 …"}``, or ``{"H": {"not": "…"}}``)
    — or one of a list — are the categories, their amounts summed by the rules (``ledger_amount`` per account in the
    ledger's unit, ``ledger_total`` in Rs crore — the units convert, no hand-written factor), and
    compared with the claimed cell at the precision it is filed (``places``).  A ledger account
    is never moved between groups by resemblance: the binding names the groups."""
    from openpyxl.utils import column_index_from_string as col

    ws = wb[binding["sheet"]]
    first, last = binding["rows"]
    unit = binding.get("unit", "INR")

    def at(ref: str) -> Any:
        book = wb
        if "::" in ref:
            name, _, ref = ref.partition("::")
            if not others or name not in others:
                raise RuleError(f"{binding['sheet']}: workbook {name!r} is not loaded")
            book = others[name]
        sheet, _, cell = ref.rpartition("!")
        return book[sheet or binding["sheet"]][cell].value

    def matches(value: Any, cond: Any) -> bool:
        text = str(value or "").strip()
        if isinstance(cond, dict):
            return text != str(cond["not"]).strip()
        if isinstance(cond, list):  # one of the named groupings
            return text in {str(c).strip() for c in cond}
        return text == str(cond).strip()

    out: list[BlockCheck] = []
    for comp in binding["comparisons"]:
        fy = comp["fiscal_year"]
        sign = Decimal(-1) if comp.get("negate") else Decimal(1)
        cats: dict[str, dict[str, tuple[Decimal | str, str]]] = {}
        for r in range(first, last + 1):
            amount = _stored(ws.cell(r, col(binding["amount_col"])).value)
            if amount is None:
                continue
            # one condition set, or several (an account in any of them counts once)
            sets = comp["where"] if isinstance(comp["where"], list) else [comp["where"]]
            if any(all(matches(ws.cell(r, col(c)).value, cond) for c, cond in w.items()) for w in sets):
                key = f"{ws.cell(r, col(binding['account_col'])).value} (row {r})"
                cats[key] = {"record:ledger_amount": (sign * amount, unit)}
        places = int(comp.get("places", binding.get("places", 2)))
        q = Decimal(1).scaleb(-places)
        ev = RuleSet(rules, fy).evaluate(fy, {}, cats or None)
        res = ev.results.get("ledger_total")
        for ref in [comp["target"]] if isinstance(comp["target"], str) else comp["target"]:
            tag = f"{comp['label']} {ref}"
            if res is None:
                out.append(
                    BlockCheck(binding["sheet"], fy, tag, "ledger_total", "blocked", why=ev.blocked.get("ledger_total"))
                )
                continue
            filed = _stored(at(ref))
            got = res.value.quantize(q, rounding=ROUND_HALF_UP)
            if filed is None:
                out.append(BlockCheck(binding["sheet"], fy, tag, "ledger_total", "no_filed_value", computed=str(got)))
                continue
            want = filed.quantize(q, rounding=ROUND_HALF_UP)
            result = "match" if got == want else "differs"
            check = BlockCheck(binding["sheet"], fy, tag, "ledger_total", result, filed=str(want), computed=str(got))
            check.exact, check.why = str(res.value), f"{len(cats)} accounts"
            out.append(check)
    return out
