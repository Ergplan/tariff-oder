"""Fill a petition's formats workbook with the rule engine (the operator's next round: NPCL's ARR
petition).

The bindings that reproduce a filed petition (``packages/reference-filings/<id>/bindings``) say,
format by format, which cells are inputs, which rule computes which cell, and which cells carry a
figure from another format (ties).  Run in *fill mode*, the same bindings fill a workbook laid out
like the filed one:

- **Computed cells** — a binding's own output cell — are written when blank, and rewritten when
  this fill wrote them before (a later pass, its inputs complete).  **A figure someone entered is
  never overwritten**: it is checked, and a difference is reported with both figures.
- **Carried cells** (ties: the same figure in another format) are written only when blank,
  otherwise checked.
- Passes repeat until nothing changes: a format computed from another format's computed figures
  is filled once those are.  A cell two bindings would both write keeps the first binding's figure;
  the other is reported as a conflict, never silently resolved.
- **Nothing is defaulted**: an output whose inputs are missing stays blank and is listed with the
  reason the engine gives (``blocked``).

Verification-only bindings are not run here: a commission order's figures (``rates``), annexure
workbooks (``workbooks``), the trial-balance ledger, the end-to-end pipeline, records of another
workbook (``year_blocks``) — they check a petition, they do not fill one.

``inputs_template`` blanks every cell the engine computes in a filed workbook (and every carried
cell that is a formula there) — what a petitioner must enter is what remains.  Filling the template
and comparing with the filing is the round trip that shows the fill reproduces the petition.

Every rule used is a draft; a filled workbook is a working draft, never a filing (R-APP-4)."""

from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .reproduce import (
    OutputCheck,
    reproduce,
    reproduce_cells,
    reproduce_period_table,
    reproduce_row_table,
)
from .rules import Rule

FILL_TYPES = ("cells", "row_table", "period_table", "sheet")
SKIPPED_TYPES = ("pipeline", "ledger", "year_blocks")
MAX_PASSES = 12
COMPUTED_FILL = "E2F0D9"  # light green: a cell the engine computed
CARRIED_FILL = "DDEBF7"  # light blue: a figure carried from another format


@dataclass
class Written:
    cell: str
    value: str
    binding: str
    output: str
    fiscal_year: str
    kind: str  # computed | carried
    pass_no: int


@dataclass
class Checked:
    cell: str
    present: str
    computed: str
    binding: str
    output: str
    fiscal_year: str
    kind: str  # computed | carried
    result: str  # agrees | differs


@dataclass
class Blocked:
    cell: str
    binding: str
    output: str
    fiscal_year: str
    why: str | None


@dataclass
class Conflict:
    cell: str
    kept: str
    kept_from: str
    other: str
    other_from: str


@dataclass
class FillReport:
    package: str
    passes: int = 0
    bindings: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    written: list[Written] = field(default_factory=list)
    checked: list[Checked] = field(default_factory=list)
    blocked: list[Blocked] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    status: str = "working draft — every rule a draft, nothing verified or approved; not a filing"

    def summary(self) -> dict[str, Any]:
        by_sheet: dict[str, dict[str, int]] = {}
        for w in self.written:
            s = by_sheet.setdefault(w.cell.rpartition("!")[0], {})
            s[w.kind] = s.get(w.kind, 0) + 1
        for c in self.checked:
            s = by_sheet.setdefault(c.cell.rpartition("!")[0], {})
            s[c.result] = s.get(c.result, 0) + 1
        for b in self.blocked:
            s = by_sheet.setdefault(b.cell.rpartition("!")[0], {})
            s["blocked"] = s.get("blocked", 0) + 1
        return {
            "passes": self.passes,
            "computed": sum(w.kind == "computed" for w in self.written),
            "carried": sum(w.kind == "carried" for w in self.written),
            "agrees": sum(c.result == "agrees" for c in self.checked),
            "differs": sum(c.result == "differs" for c in self.checked),
            "blocked": len(self.blocked),
            "conflicts": len(self.conflicts),
            "by_sheet": dict(sorted(by_sheet.items())),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "status": self.status,
            "summary": self.summary(),
            **{k: [asdict(x) for x in getattr(self, k)] for k in ("written", "checked", "blocked", "conflicts")},
            "bindings": self.bindings,
            "skipped": self.skipped,
        }


def fill_bindings(folder: Path) -> tuple[list[tuple[str, dict[str, Any]]], list[dict[str, str]]]:
    """The bindings a fill runs, in name order, and those it leaves out with the reason."""
    run, skipped = [], []
    for p in sorted((folder / "bindings").glob("*.json")):
        b = json.loads(p.read_text())
        kind = b.get("type") or "sheet"
        if kind in SKIPPED_TYPES:
            skipped.append(
                {"binding": p.name, "why": f"{kind}: verification against another record, not a petition figure"}
            )
        elif b.get("fill") is False:
            skipped.append({"binding": p.name, "why": b.get("fill_why") or "declared not to fill"})
        elif kind == "cells" and b.get("rates"):
            skipped.append({"binding": p.name, "why": "checks a commission order's figures, not the petition's"})
        elif kind == "cells" and b.get("workbooks"):
            skipped.append({"binding": p.name, "why": "checks an annexure workbook, not the formats"})
        elif kind in FILL_TYPES:
            run.append((p.name, b))
        else:
            skipped.append({"binding": p.name, "why": f"type {kind!r} has no fill"})
    return run, skipped


def _number(v: Any) -> Decimal | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int | float):
        try:
            return Decimal(repr(v)) if isinstance(v, float) else Decimal(v)
        except InvalidOperation:
            return None
    return None


def _split(ref: str) -> tuple[str, str]:
    sheet, _, cell = ref.rpartition("!")
    return sheet, cell


def overlay(layout: dict[str, Any], wb: Any) -> dict[str, dict[str, Any]]:
    """The reference sheets with this workbook's values: the filed reference gives the layout (rows,
    columns, units, percentages, the decimals displayed), the workbook the figures.  A blank cell is
    absent, as the reader leaves it."""
    out: dict[str, dict[str, Any]] = {}
    for sh in layout["sheets"]:
        if sh["sheet"] not in wb.sheetnames:
            continue
        ws = wb[sh["sheet"]]
        idx = {(c["fiscal_year"], c["voice"], c["words"]): c["index"] for c in sh["columns"]}
        rows = []
        for r in sh["rows"]:
            cells = []
            for c in r["cells"]:
                i = idx.get((c["fiscal_year"], c["voice"], c["words"]))
                raw = ws.cell(r["row"], i + 1).value if i is not None else None
                n = _number(raw)
                if n is not None:
                    v = n * 100 if c.get("percent_from_fraction") else n
                    places = None
                    if c.get("displayed") is not None:
                        places = max(0, -Decimal(c["displayed"]).as_tuple().exponent)
                    elif c.get("state") != "value":
                        places = 2
                    shown = str(v.quantize(Decimal(1).scaleb(-places))) if places is not None else None
                    cells.append({**c, "value": str(v), "displayed": shown, "state": "value", "printed": str(raw)})
                elif raw is None or not str(raw).strip():
                    if c.get("state") == "value":  # blank now: kept with its unit, for the figure to fill
                        cells.append({**c, "value": None, "displayed": None, "state": "blank", "printed": ""})
                elif raw is not None and str(raw).strip():
                    cells.append(
                        c
                        if c.get("state") != "value"
                        else {**c, "value": None, "displayed": None, "state": "text", "printed": str(raw)}
                    )
            rows.append({**r, "cells": cells})
        out[sh["sheet"]] = {**sh, "rows": rows}
    return out


def _percent_cells(layout: dict[str, Any]) -> set[str]:
    """Cells the filed workbook stores as a fraction and the reference reads as a percentage."""
    from openpyxl.utils import get_column_letter

    out = set()
    for sh in layout["sheets"]:
        idx = {(c["fiscal_year"], c["voice"], c["words"]): c["index"] for c in sh["columns"]}
        for r in sh["rows"]:
            for c in r["cells"]:
                i = idx.get((c["fiscal_year"], c["voice"], c["words"]))
                if c.get("percent_from_fraction") and i is not None:
                    out.add(f"{sh['sheet']}!{get_column_letter(i + 1)}{r['row']}")
    return out


def _reads(b: dict[str, Any], sheetnames: list[str]) -> set[str]:
    """The sheets a binding reads or checks: its own and every sheet its references name."""
    text = json.dumps(b, ensure_ascii=False)
    return {b.get("sheet")} | {n for n in sheetnames if f"{n}!" in text}


def _evaluate(
    wb: Any,
    layout: dict[str, Any],
    bindings: list[tuple[str, dict]],
    rules: list[Rule],
    only: set[str] | None = None,
) -> list[tuple[str, Any]]:
    """Every binding's checks on the workbook as it stands (``only``: those bindings alone)."""
    sheets = overlay(layout, wb)
    out: list[tuple[str, Any]] = []
    for name, b in bindings:
        if only is not None and name not in only:
            continue
        kind = b.get("type") or "sheet"
        if kind == "cells":
            checks = reproduce_cells(wb, b, rules, fill=True)
        elif kind == "row_table":
            checks = reproduce_row_table(wb, b, rules, fill=True)
        elif kind == "period_table":
            checks = reproduce_period_table(wb, b, rules, fill=True)
        else:
            if b["sheet"] not in sheets:
                continue
            checks = reproduce(sheets[b["sheet"]], b, rules, sheets, fill=True).checks
        out.extend((name, c) for c in checks)
    return out


def _value_for(check: Any, cell: str, percent: set[str]) -> Decimal | None:
    """The figure to write: a format's row (read through the reference) is in the reference's unit,
    a percentage where the workbook stores a fraction; a cell read by address is the cell's own."""
    raw = getattr(check, "fill", None)
    if raw is None:
        return None
    v = Decimal(raw)
    return v / 100 if cell in percent and isinstance(check, OutputCheck) else v


def _same(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= Decimal("1e-9") * max(Decimal(1), abs(a), abs(b))


def fill(
    wb: Any,
    layout: dict[str, Any],
    bindings: list[tuple[str, dict]],
    rules: list[Rule],
    package: str = "",
    targets: set[str] | None = None,
) -> FillReport:
    """Fill ``wb`` (an openpyxl workbook of values, modified in place) and report.  ``layout`` is
    the filed reference (``reference.json``); ``targets`` the package's fill map — the cells a fill
    may write (the cells the engine computes that the filed format prints).  Without a map, any
    blank output cell may be written."""
    report = FillReport(package=package, bindings=[n for n, _ in bindings])
    percent = _percent_cells(layout)
    places_of = {n: b.get("fill_places") for n, b in bindings if b.get("fill_places") is not None}
    owner: dict[str, str] = {}  # cell → the binding whose figure it holds (written by this fill)
    written: dict[str, Written] = {}
    reads = {name: _reads(b, wb.sheetnames) for name, b in bindings}
    touched: set[str] | None = None  # sheets written in the last pass; None before the first
    for p in range(1, MAX_PASSES + 1):
        report.passes = p
        changed = 0
        seen_conflicts: set[str] = set()
        # a binding is evaluated again only when a sheet it reads was written in the last pass
        due = {n for n, r in reads.items() if touched is None or r & touched}
        touched = set()
        for name, c in _evaluate(wb, layout, bindings, rules, only=due):
            cell = getattr(c, "cell", None)
            if not cell or c.result in ("given", "not_a_value", "blocked"):
                continue
            if targets is not None and cell not in targets:
                continue
            v = _value_for(c, cell, percent)
            primary = getattr(c, "primary", None)
            if c.tie and primary:
                # a carried cell repeats its format's figure as it stands — entered or filled — as the
                # workbook's own formula does; the computation is the primary cell's to check
                ps, pr = _split(primary)
                pv = _number(wb[ps][pr].value) if ps in wb.sheetnames else None
                if pv is None:
                    continue
                v = pv
            if v is None:
                continue
            if name in places_of:  # the format rounds this figure (declared in the binding, with its reason)
                v = v.quantize(Decimal(1).scaleb(-int(places_of[name])), rounding=ROUND_HALF_UP)
            sheet, ref = _split(cell)
            if sheet not in wb.sheetnames:
                continue
            ws = wb[sheet]
            present = _number(ws[ref].value)
            kind = "carried" if c.tie else "computed"
            held_by = owner.get(cell)
            if held_by is not None and held_by != name:
                if kind == "computed" and written[cell].kind == "carried":
                    pass  # the format's own computation takes the cell over from a carried copy
                else:
                    if (
                        kind == "computed"
                        and present is not None
                        and not _same(present, v)
                        and cell not in seen_conflicts
                    ):
                        seen_conflicts.add(cell)
                        if not any(x.cell == cell and x.other_from == name for x in report.conflicts):
                            report.conflicts.append(Conflict(cell, str(present), held_by, str(v), name))
                    continue  # another binding's figure: checked at the end, never overwritten
            elif held_by is None and present is not None:
                continue  # a figure entered by someone: checked at the end, never overwritten
            if present is None or not _same(present, v):
                ws[ref].value = float(v)
                owner[cell] = name
                written[cell] = Written(cell, str(v), name, c.output, c.fiscal_year, kind, p)
                changed += 1
                touched.add(sheet)
        if not changed:
            break
    # the final state: what was written, what was checked against figures already there, what is blocked
    report.written = sorted(written.values(), key=lambda w: w.cell)
    final = _evaluate(wb, layout, bindings, rules)
    seen: set[tuple[str, str, str]] = set()
    for name, c in final:
        cell = getattr(c, "cell", None)
        if not cell:
            continue
        key = (cell, name, c.output)
        if key in seen:
            continue
        seen.add(key)
        if c.result == "blocked" or (c.result == "no_filed_value" and getattr(c, "fill", None) is None):
            report.blocked.append(Blocked(cell, name, c.output, c.fiscal_year, c.why))
            continue
        if cell in written and written[cell].binding == name:
            continue
        v = _value_for(c, cell, percent)
        sheet, ref = _split(cell)
        present = _number(wb[sheet][ref].value) if sheet in wb.sheetnames else None
        if v is None or present is None or c.result in ("given", "not_a_value"):
            continue
        result = "agrees" if c.result == "match" else "differs"
        report.checked.append(
            Checked(
                cell, str(present), str(v), name, c.output, c.fiscal_year, "carried" if c.tie else "computed", result
            )
        )
    return report


def mark(wb: Any, report: FillReport) -> None:
    """Shade the cells the fill wrote and add a trace sheet: each figure with the binding and the
    output that computed it."""
    from openpyxl.styles import PatternFill

    for w in report.written:
        sheet, ref = _split(w.cell)
        colour = COMPUTED_FILL if w.kind == "computed" else CARRIED_FILL
        wb[sheet][ref].fill = PatternFill("solid", start_color=colour, end_color=colour)
    if "Fill trace" in wb.sheetnames:
        del wb["Fill trace"]
    ws = wb.create_sheet("Fill trace")
    ws.append(["DRAFT — filled with software assistance from draft rules; nothing verified or approved; not filed"])
    ws.append(["cell", "value", "kind", "binding", "output", "fiscal year", "pass"])
    for w in report.written:
        ws.append([w.cell, float(Decimal(w.value)), w.kind, w.binding, w.output, w.fiscal_year, w.pass_no])
    ws.append([])
    ws.append(["checked against a figure already entered", "entered", "computed", "result", "binding", "output"])
    for c in report.checked:
        if c.result == "differs":
            ws.append([c.cell, float(Decimal(c.present)), float(Decimal(c.computed)), c.result, c.binding, c.output])
    ws.append([])
    ws.append(["blocked (left blank)", "binding", "output", "fiscal year", "why"])
    for b in report.blocked:
        ws.append([b.cell, b.binding, b.output, b.fiscal_year, b.why or ""])


def fill_map(
    filed_values: Any, filed_formulas: Any, layout: dict[str, Any], bindings: list[tuple[str, dict]], rules: list[Rule]
) -> dict[str, dict[str, str]]:
    """The cells a fill writes, from a filed workbook: every cell a binding computes as its own
    output that the filing prints a figure in, and every carried cell (a tie) the filing holds as a
    formula linking it to the format it repeats.  A cell the filing leaves blank stays blank: the
    engine may compute a figure there (an implied rate), but the format does not print one.
    cell → {binding, output, kind}."""
    out: dict[str, dict[str, str]] = {}
    for name, c in _evaluate(filed_values, layout, bindings, rules):
        cell = getattr(c, "cell", None)
        if not cell or c.result in ("given", "not_a_value", "blocked") or getattr(c, "fill", None) is None:
            continue
        sheet, ref = _split(cell)
        if sheet not in filed_values.sheetnames or _number(filed_values[sheet][ref].value) is None:
            continue
        if not c.tie:
            if out.get(cell, {}).get("kind") != "computed":
                out[cell] = {"binding": name, "output": c.output, "kind": "computed"}
        else:
            f = filed_formulas[sheet][ref].value
            if isinstance(f, str) and f.startswith("=") and cell not in out and _links(f, sheet, c, name, bindings):
                out[cell] = {"binding": name, "output": c.output, "kind": "carried"}
    return dict(sorted(out.items()))


def _links(formula: str, sheet: str, check: Any, name: str, bindings: list[tuple[str, dict]]) -> bool:
    """A carried cell is filled only where the filing's own formula links it to the format it
    repeats (ARR!J14 ='ESR_3 Curr Tariff FY25'!N136).  A cell the filing computes otherwise — the
    ARR's loss as 1 - J9/J8, a cash flow's opening line — is the petitioner's own: checked, not
    filled."""
    primary = getattr(check, "primary", None)
    source = primary.rpartition("!")[0] if primary else dict(bindings)[name].get("sheet")
    if not source:
        return False
    if source == sheet:
        return bool(primary) and primary.rpartition("!")[2] in formula
    return source in formula


def inputs_template(filed_values: Any, targets: Any) -> Any:
    """The filed workbook (values) with every cell of the fill map blanked: what remains is what a
    petitioner enters (modified in place)."""
    for cell in targets:
        sheet, ref = _split(cell)
        filed_values[sheet][ref].value = None
    return filed_values


def to_bytes(wb: Any) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def round_trip(
    book: Path,
    rules: list[Rule],
    layout: dict[str, Any],
    bindings: list[tuple[str, dict]],
    fmap: dict[str, Any],
    package: str = "",
    runs: tuple[str, ...] = ("known_kept", "none_kept"),
) -> dict[str, Any]:
    """The round trip on a filed workbook: blank the fill map, fill, compare cell by cell at the
    filing's printed precision (both rounded half-up to the places the format prints, as the
    reproduction compares).  ``known_kept``: the cells whose reproduction already differs from the
    filing are kept as filed, so what differs is what the fill itself does; ``none_kept``: none."""
    import openpyxl

    filed = openpyxl.load_workbook(book, data_only=True)
    places, known = {}, set()
    for _name, c in _evaluate(filed, layout, bindings, rules):
        cell = getattr(c, "cell", None)
        if not cell or cell not in fmap:
            continue
        if c.filed is not None:
            places.setdefault(cell, max(0, -Decimal(c.filed).as_tuple().exponent))
        if c.result == "differs" and not c.tie:
            known.add(cell)
    out: dict[str, Any] = {"package": package, "map": len(fmap), "known_differences": sorted(known), "runs": {}}
    for label, pinned in (("known_kept", known), ("none_kept", set())):
        if label not in runs:
            continue
        wb = openpyxl.load_workbook(book, data_only=True)
        targets = {c for c in fmap if c not in pinned}
        inputs_template(wb, targets)
        rep = fill(wb, layout, bindings, rules, package, targets=targets)
        same, differ, blank = 0, [], []
        for cell in sorted(targets):
            s, _, r = cell.rpartition("!")
            a, b = filed[s][r].value, wb[s][r].value
            if b is None:
                blank.append(cell)
                continue
            q = Decimal(1).scaleb(-places.get(cell, 6))
            da, db = Decimal(repr(a)), Decimal(repr(b))
            if da.quantize(q, rounding=ROUND_HALF_UP) == db.quantize(q, rounding=ROUND_HALF_UP):
                same += 1
            else:
                differ.append({"cell": cell, "filed": str(a), "filled": str(b), "known": cell in known})
        out["runs"][label] = {
            "targets": len(targets),
            "reproduced": same,
            "differs": len(differ),
            "not_filled": len(blank),
            "passes": rep.passes,
            "conflicts": [c.__dict__ for c in rep.conflicts],
            "differing": differ,
            "blank": blank,
        }
    return out
