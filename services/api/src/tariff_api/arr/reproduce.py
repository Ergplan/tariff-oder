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
    row: int
    label: str
    fiscal_year: str
    voice: str
    words: str
    result: str  # match | differs | blocked | not_a_value | no_filed_value
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


def reproduce(sheet: dict[str, Any], binding: dict[str, Any], rules: list[Rule]) -> FormatReproduction:
    """``sheet`` is one sheet of a reference (as `scripts/build_reference.py` writes it)."""
    rows = {r["row"]: r for r in sheet["rows"]}
    # the unit of rows the sheet leaves unstated (a format with no unit line), declared by the binding
    default_unit = binding.get("unit")
    missing = [n for n in [*binding["inputs"].values(), *binding["outputs"].values()] if n not in rows]
    if missing:
        raise RuleError(f"{sheet['sheet']}: bound rows {missing} are not rows the reference read")
    columns: list[tuple[str, str, str]] = []
    for r in sheet["rows"]:
        for c in r["cells"]:
            key = (c["fiscal_year"], c["voice"], c["words"])
            if key not in columns:
                columns.append(key)

    def cell(row: int, col: tuple[str, str, str]) -> dict | None:
        return next(
            (c for c in rows[row]["cells"] if (c["fiscal_year"], c["voice"], c["words"]) == col),
            None,
        )

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
                values[source] = (c["value"], c["unit"] or rows[row]["unit"] or default_unit)
        ev = rs.evaluate(fy, values) if isinstance(rs, RuleSet) else None
        for output, row in binding["outputs"].items():
            c = cell(row, col)
            base = dict(output=output, row=row, label=rows[row]["label"], fiscal_year=fy, voice=voice, words=words)
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
            unit = c["unit"] or rows[row]["unit"] or default_unit or res.unit
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
