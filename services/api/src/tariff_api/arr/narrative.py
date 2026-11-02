"""The petition's narrative reconciled to its formats (R-ACC-5, R-PKG-3).

A petition restates its figures in prose documents (the true-up, APR and ARR texts, the executive
summary): hundreds of tables whose every number should be one of the formats' numbers, rounded as
printed.  This module reads the narrative's tables, parses each printed figure with the precision
it is printed at, and looks for it among the formats' cells:

- **traced** — one or more cells carry the figure at its printed precision (half-up rounding);
- **near** — none does, but a cell is one unit of the last printed place away (a rounding or
  truncation difference, listed apart);
- **opposite sign** — a cell carries the figure with the other sign (a gap printed positive where
  the format holds a shortfall as a negative), listed apart;
- **untraced** — the figure is specific enough to mean something (``min_digits`` significant
  digits) and no cell carries it: a question for the reviewer, not an error by itself (a CAGR or a
  ratio the narrative computes is untraced too);
- **uninformative** — too few significant digits to trace honestly ("12 %", "9"): a short figure
  matches some cell of a large workbook by chance, so it is counted, never called traced.

Nothing here decides that a figure is right.  A trace says where a figure also appears; the
reviewer decides whether it is the same quantity.  The narrative is untrusted data: read as text.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

_FIGURE = re.compile(r"^\(?\s*(-|–|−)?\s*(?:Rs\.?\s*)?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(%)?\s*\)?$")


@dataclass(frozen=True)
class Printed:
    """A figure as printed: its value, the decimal places it is printed with, and whether it is a
    percentage."""

    value: Decimal
    places: int
    percent: bool

    @property
    def digits(self) -> int:
        """Significant digits as printed (leading zeros excluded): 452.58 has 5, 0.05 has 1."""
        text = format(abs(self.value), "f").replace(".", "").lstrip("0")
        return len(text)


def parse_figure(text: str) -> Printed | None:
    """A printed number: ``1,234.56``, ``(12.34)`` or ``-12.34`` (negative), ``12%``, ``Rs. 5``.
    Anything else — words, dates, ranges, "NA", "-" — is not a figure (None)."""
    t = text.strip().replace(" ", " ")
    if not t:
        return None
    m = _FIGURE.match(t)
    if not m:
        return None
    sign, number, pct = m.groups()
    if t.startswith("(") != t.endswith(")"):
        return None
    if "," in number and not re.fullmatch(r"[0-9]{1,3}(,[0-9]{2,3})*(\.[0-9]+)?", number):
        return None  # "1,2,3" is a list, not a number
    try:
        value = Decimal(number.replace(",", ""))
    except InvalidOperation:
        return None
    places = len(number.split(".")[1]) if "." in number else 0
    if sign or t.startswith("("):
        value = -value
    return Printed(value, places, pct is not None)


@dataclass
class Table:
    document: str
    index: int
    title: str
    rows: list[list[str]]


def read_docx_tables(path: Path) -> list[Table]:
    """Every table of a DOCX, each row's cells once (a merged cell repeats in python-docx's rows; it
    is kept once, by its underlying element).  The title is the table's first row when that row is
    one merged cell, else the paragraph just before the table."""
    import docx

    d = docx.Document(str(path))
    body = d.element.body
    out: list[Table] = []
    last_text = ""
    tables = iter(d.tables)
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = "".join(t.text or "" for t in child.iter() if t.tag.endswith("}t")).strip()
            if text:
                last_text = text
        elif tag == "tbl":
            t = next(tables)
            rows: list[list[str]] = []
            for r in t.rows:
                seen: set[int] = set()
                cells: list[str] = []
                for c in r.cells:
                    if id(c._tc) in seen:
                        continue
                    seen.add(id(c._tc))
                    cells.append(re.sub(r"\s+", " ", c.text).strip())
                rows.append(cells)
            title = rows[0][0] if rows and len(rows[0]) == 1 and rows[0][0] else last_text
            out.append(Table(path.name, len(out), title[:200], rows))
    return out


@dataclass
class Figure:
    document: str
    table: int
    title: str
    row: int
    col: int
    label: str
    text: str
    value: str
    places: int
    percent: bool
    result: str = ""
    cells: list[str] = field(default_factory=list)


def figures(table: Table) -> list[Figure]:
    """The figures of a table, each with its row's label (the first cell that is not a figure)."""
    out: list[Figure] = []
    for i, row in enumerate(table.rows):
        label = next((c for c in row if c and parse_figure(c) is None), "")
        for j, cell in enumerate(row):
            p = parse_figure(cell)
            if p is None:
                continue
            out.append(
                Figure(
                    table.document, table.index, table.title, i, j, label[:120], cell, str(p.value), p.places, p.percent
                )
            )
    return out


class FormatIndex:
    """The numeric cells of one or more workbooks, looked up by value at a given precision."""

    def __init__(self, books: dict[str, Any]):
        self.cells: list[tuple[Decimal, str]] = []
        for name, wb in books.items():
            for ws in wb.worksheets:
                for row in ws.iter_rows():
                    for c in row:
                        v = c.value
                        if isinstance(v, bool) or not isinstance(v, int | float | Decimal):
                            continue
                        self.cells.append((Decimal(str(v)), f"{name}::{ws.title}!{c.coordinate}"))
        self._by: dict[int, dict[Decimal, list[str]]] = {}

    def _at(self, places: int) -> dict[Decimal, list[str]]:
        if places not in self._by:
            q = Decimal(1).scaleb(-places)
            idx: dict[Decimal, list[str]] = {}
            for v, ref in self.cells:
                idx.setdefault(v.quantize(q, rounding=ROUND_HALF_UP), []).append(ref)
            self._by[places] = idx
        return self._by[places]

    def find(self, p: Printed, slack: int = 0) -> list[str]:
        """Cells equal to the printed figure at its precision (``slack`` units of the last place
        either side).  A percentage is looked for as printed (12.5) and as a fraction (0.125)."""
        forms = [(p.value, p.places)]
        if p.percent:
            forms.append((p.value / 100, p.places + 2))
        refs: list[str] = []
        for value, places in forms:
            idx = self._at(places)
            unit = Decimal(1).scaleb(-places)
            for k in range(-slack, slack + 1):
                refs.extend(idx.get((value + k * unit).quantize(unit), []))
        return refs


def reconcile(tables: list[Table], index: FormatIndex, min_digits: int = 4, keep: int = 5) -> dict[str, Any]:
    """Each figure of each table classified traced / near / untraced / uninformative (module
    docstring), with up to ``keep`` cells for a trace.  Returns the summary by document and every
    figure."""
    out: list[Figure] = []
    for t in tables:
        for f in figures(t):
            p = Printed(Decimal(f.value), f.places, f.percent)
            if p.digits < min_digits:
                f.result = "uninformative"
            elif refs := index.find(p):
                f.result, f.cells = "traced", refs[:keep]
            elif refs := index.find(p, slack=1):
                f.result, f.cells = "near", refs[:keep]
            elif refs := index.find(Printed(-p.value, p.places, p.percent)):
                f.result, f.cells = "opposite_sign", refs[:keep]
            else:
                f.result = "untraced"
            out.append(f)
    summary: dict[str, dict[str, int]] = {}
    for f in out:
        s = summary.setdefault(
            f.document, {"tables": 0, "traced": 0, "near": 0, "opposite_sign": 0, "untraced": 0, "uninformative": 0}
        )
        s[f.result] += 1
    for t in tables:
        summary.setdefault(
            t.document, {"tables": 0, "traced": 0, "near": 0, "opposite_sign": 0, "untraced": 0, "uninformative": 0}
        )
        summary[t.document]["tables"] += 1
    return {"min_digits": min_digits, "summary": summary, "figures": [asdict(f) for f in out]}


def _norm(label: str) -> str:
    return re.sub(r"\s+", " ", label).strip().lower()


def _row_label(row: list[str]) -> str:
    """The row's particulars: the first cell that is neither a figure nor a serial number or a
    short reference ("1", "a", "f=a-b-c")."""
    for c in row:
        t = c.strip()
        if not t or parse_figure(t) is not None:
            continue
        if re.fullmatch(r"[a-z]{1,2}|[a-z](=[a-z+\-]+)?|\d{1,2}\.?|[ivx]{1,4}\.?", t.lower()):
            continue
        return t
    return ""


def reconcile_tables(binding: dict[str, Any], wb: Any, tables: dict[str, list[Table]]) -> list[dict[str, Any]]:
    """Explicit bindings of a narrative's tables to the formats (``binding["tables"]``: each a
    document, a title prefix, and its figure columns, each with the format column it is and a word
    its header must contain; ``binding["rows"]``: each a key, a label pattern matched in full
    against the row's particulars, the format rows whose cells it sums, and a sign).  Each printed
    figure is compared with the format's value rounded half-up to the printed places:

    - ``match`` / ``differs`` (with the difference in units of the last printed place);
    - ``dash`` printed for a format value that rounds to zero is a match; a blank cell where the
      format has a value is ``not_printed``; a figure where the format is blank is
      ``no_format_value``.

    A table not found by its title, a header without its word, or a row pattern matching two rows
    of one table is an error — a binding never falls back to a guess."""
    sheet = binding["sheet"]
    rows_spec = [(r["key"], re.compile(r["label"], re.I), r["rows"], int(r.get("sign", 1))) for r in binding["rows"]]
    out: list[dict[str, Any]] = []
    for tb in binding["tables"]:
        found = [t for t in tables.get(tb["document"], []) if t.title.startswith(tb["title"])]
        if len(found) != 1:
            raise ValueError(f"{tb['document']}: {len(found)} tables titled {tb['title']!r}")
        t = found[0]
        header = next(
            (r for r in t.rows if any(w in " ".join(r) for w in ("Approved", "Projected", "Actual", "Estimated"))), None
        )
        for col, spec in tb["columns"].items():
            j = int(col)
            if header is None or j >= len(header) or spec["header"].lower() not in header[j].lower():
                raise ValueError(f"{t.title}: column {j} is not headed {spec['header']!r}")
        seen: dict[str, int] = {}
        for i, row in enumerate(t.rows):
            label = _norm(_row_label(row))
            hits = [s for s in rows_spec if s[1].fullmatch(label)]
            if not hits:
                continue
            if len(hits) > 1:
                raise ValueError(f"{t.title}: row {label!r} matches {[h[0] for h in hits]}")
            key, _, frows, sign = hits[0]
            if key in seen:
                raise ValueError(f"{t.title}: {key} matches rows {seen[key]} and {i}")
            seen[key] = i
            for col, spec in tb["columns"].items():
                j = int(col)
                text = row[j].strip() if j < len(row) else ""
                refs = [f"{sheet}!{spec['column']}{r}" for r in frows]
                vals = [wb[sheet][f"{spec['column']}{r}"].value for r in frows]
                nums = [Decimal(str(v)) for v in vals if isinstance(v, int | float) and not isinstance(v, bool)]
                fmt = sign * sum(nums, Decimal(0)) if nums else None
                rec: dict[str, Any] = {
                    "document": t.document,
                    "table": t.title,
                    "column": spec["header"],
                    "key": key,
                    "label": _row_label(row),
                    "printed": text,
                    "cells": refs,
                    "sign": sign,
                    "format_exact": None if fmt is None else str(fmt),
                }
                p = parse_figure(text)
                if text in ("-", "–", "—"):
                    p = Printed(Decimal(0), 2, False)
                if p is None:
                    rec["result"] = "not_printed" if fmt is not None and fmt.quantize(Decimal("0.01")) != 0 else "match"
                elif fmt is None:
                    rec["result"] = "no_format_value"
                else:
                    q = Decimal(1).scaleb(-p.places)
                    rounded = fmt.quantize(q, rounding=ROUND_HALF_UP)
                    rec["format_rounded"] = str(rounded)
                    rec["result"] = "match" if rounded == p.value else "differs"
                    if rec["result"] == "differs":
                        rec["last_place_units"] = int((p.value - rounded) / q)
                out.append(rec)
    return out
