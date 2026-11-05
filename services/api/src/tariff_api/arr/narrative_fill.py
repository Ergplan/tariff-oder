"""The narrative's summary tables filled from a formats workbook (increment 153).

Increment 93 bound nine summary tables of NPCL's narrative — the true-up, APR and ARR texts
(Appendices III–V), the executive summary and Form-1 — row by row to the ARR format
(``narrative/summary-tables.json``; ``narrative.reconcile_tables`` checks them).  This module uses
the same bindings the other way: given a workbook (a filled one, from ``petition_fill``) and the
narrative documents, it writes each bound figure into its table cell:

- **from the bound cells**: a row's figure is the sum of the format cells it names, with its sign
  (the narrative prints a gap positive), rounded half-up to the places the cell is printed with
  and in the printed style — thousands separators (international or Indian grouping), brackets
  or a minus for a negative, a dash for nil where the filing prints one, a % kept;
- **changed cells shaded green**; a cell whose figure is already right is left as it is;
- **figures in rows the binding does not cover** (loss on sale of retired assets, efficiency
  gains, power purchase provisions, …) are the petitioner's own: shaded yellow and listed,
  never computed;
- **the prose and every other table stay as filed**: each document filled gets a first
  paragraph saying so.  The prose restates the same figures; updating it is the petitioner's.

A filled narrative is a working draft from draft rules, never a filing.  The documents are
untrusted data: their text is read as text and written as figures, nothing in it is obeyed.
"""

from __future__ import annotations

import io
import re
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .narrative import Printed, _norm, _row_label, parse_figure

FILLED_SHADE = "C6EFCE"  # the workbook's computed green
OWN_SHADE = "FFF2CC"  # the petitioner's own figure: yellow
DASHES = ("-", "–", "—")
NOTE = (
    "WORKING DRAFT — the summary tables shaded green were filled from the formats workbook by draft "
    "rules (nothing verified or approved); figures shaded yellow are not taken from the formats and "
    "are the petitioner's to enter; the prose and every other table are as filed and still to be "
    "updated.  Not a filing."
)


@dataclass
class Cell:
    document: str
    table: str
    column: str
    key: str
    label: str
    cells: list[str]
    before: str
    after: str
    value: str  # the unrounded figure from the workbook
    result: str  # written | unchanged | merged (one cell spans two rows: left as filed) | no_format_value | not_printed


@dataclass
class Own:
    document: str
    table: str
    label: str
    column: str
    printed: str


@dataclass
class NarrativeReport:
    documents: list[str] = field(default_factory=list)
    cells: list[Cell] = field(default_factory=list)
    own: list[Own] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        count = {
            r: sum(c.result == r for c in self.cells)
            for r in ("written", "unchanged", "merged", "no_format_value", "not_printed")
        }
        return {
            "documents": len(self.documents),
            "tables": len({(c.document, c.table) for c in self.cells}),
            **count,
            "own": len(self.own),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "working draft — draft rules; the prose and the other tables are as filed; not a filing",
            "summary": self.summary(),
            "documents": self.documents,
            "cells": [asdict(c) for c in self.cells],
            "own": [asdict(o) for o in self.own],
        }


def _tables(d: Any) -> list[tuple[str, list[list[Any]]]]:
    """Each table of a python-docx document with its title and its rows of unique cells (a merged
    cell once) — as ``narrative.read_docx_tables`` reads them, but keeping the cell objects."""
    body = d.element.body
    out: list[tuple[str, list[list[Any]]]] = []
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
            rows: list[list[Any]] = []
            for r in t.rows:
                seen: set[int] = set()
                cells = []
                for c in r.cells:
                    if id(c._tc) in seen:
                        continue
                    seen.add(id(c._tc))
                    cells.append(c)
                rows.append(cells)
            first = rows[0] if rows else []
            first_text = _text(first[0]) if len(first) == 1 else ""
            out.append(((first_text or last_text)[:200], rows))
    return out


def _text(cell: Any) -> str:
    return re.sub(r"\s+", " ", cell.text).strip()


def _group(digits: str, indian: bool) -> str:
    if not indian or len(digits) <= 3:
        return f"{int(digits):,}"
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def render(value: Decimal, like: str, default_places: int = 2) -> str:
    """``value`` printed as the cell ``like`` prints its figure: the same places, grouping, sign
    style and % (or, for a blank or dash cell, ``default_places`` with thousands separators)."""
    p = parse_figure(like)
    places = p.places if p is not None else default_places
    q = Decimal(1).scaleb(-places)
    v = value.quantize(q, rounding=ROUND_HALF_UP)
    if v == 0 and like.strip() in DASHES:
        return like.strip()
    if v == 0:
        v = abs(v)  # never "-0.00"
    body = like.strip()
    grouped = p is None or "," in body or abs(v) < 1000
    indian = bool(re.search(r"\d,\d\d,\d{3}", body))
    whole, _, frac = format(abs(v), "f").partition(".")
    number = (_group(whole, indian) if grouped else whole) + (f".{frac}" if frac else "")
    if p is not None and p.percent:
        number += "%"
    if v < 0:
        return f"({number})" if body.startswith("(") or p is None else f"-{number}"
    return number


def _set_text(cell: Any, text: str, shade: str | None) -> None:
    """Replace a cell's text keeping the first run's formatting; shade the cell."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paras = cell.paragraphs
    runs = [r for p in paras for r in p.runs]
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r.text = ""
    else:
        paras[0].add_run(text)
    if shade:
        tc_pr = cell._tc.get_or_add_tcPr()
        for old in tc_pr.findall(qn("w:shd")):
            tc_pr.remove(old)
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), shade)
        tc_pr.append(shd)


def _shade_only(cell: Any, colour: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    for old in tc_pr.findall(qn("w:shd")):
        tc_pr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), colour)
    tc_pr.append(shd)


def _number(v: Any) -> Decimal | None:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    return Decimal(str(v))


def fill_narrative(
    binding: dict[str, Any], wb: Any, documents: dict[str, bytes], *, mark: bool = True
) -> tuple[dict[str, bytes], NarrativeReport]:
    """Fill the bound summary tables of ``documents`` (name → DOCX bytes) from ``wb`` (an
    openpyxl workbook of values).  Returns the filled documents (only those holding a bound
    table) and the report.  A bound table not found, a header without its word or a row
    matching two patterns is an error, as in ``reconcile_tables``."""
    import docx

    sheet = binding["sheet"]
    rows_spec = [(r["key"], re.compile(r["label"], re.I), r["rows"], int(r.get("sign", 1))) for r in binding["rows"]]
    report = NarrativeReport()
    out: dict[str, bytes] = {}
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for tb in binding["tables"]:
        by_doc.setdefault(tb["document"], []).append(tb)
    for name, specs in by_doc.items():
        if name not in documents:
            raise ValueError(f"{name}: narrative document not supplied")
        d = docx.Document(io.BytesIO(documents[name]))
        tables = _tables(d)
        for tb in specs:
            found = [(title, rows) for title, rows in tables if title.startswith(tb["title"])]
            if len(found) != 1:
                raise ValueError(f"{name}: {len(found)} tables titled {tb['title']!r}")
            title, rows = found[0]
            texts = [[_text(c) for c in r] for r in rows]
            header = next(
                (r for r in texts if any(w in " ".join(r) for w in ("Approved", "Projected", "Actual", "Estimated"))),
                None,
            )
            cols = {int(k): v for k, v in tb["columns"].items()}
            for j, spec in cols.items():
                if header is None or j >= len(header) or spec["header"].lower() not in header[j].lower():
                    raise ValueError(f"{title}: column {j} is not headed {spec['header']!r}")
            # a cell merged down across rows (one figure printed for two lines) cannot hold two
            # figures: it is left as filed and reported
            spans: dict[int, int] = {}
            for r in rows:
                for c in r:
                    spans[id(c._tc)] = spans.get(id(c._tc), 0) + 1
            seen: dict[str, int] = {}
            for i, (row, row_text) in enumerate(zip(rows, texts, strict=True)):
                label = _row_label(row_text)
                hits = [s for s in rows_spec if s[1].fullmatch(_norm(label))]
                if len(hits) > 1:
                    raise ValueError(f"{title}: row {label!r} matches {[h[0] for h in hits]}")
                if not hits:
                    # a figure in a row the binding does not cover is the petitioner's own
                    if row_text is not header and label:
                        for j in cols:
                            if j < len(row_text) and parse_figure(row_text[j]) is not None:
                                report.own.append(Own(name, title, label, cols[j]["header"], row_text[j]))
                                if mark:
                                    _shade_only(row[j], OWN_SHADE)
                    continue
                key, _, frows, sign = hits[0]
                if key in seen:
                    raise ValueError(f"{title}: {key} matches rows {seen[key]} and {i}")
                seen[key] = i
                for j, spec in cols.items():
                    if j >= len(row):
                        continue
                    refs = [f"{sheet}!{spec['column']}{r}" for r in frows]
                    nums = [n for r in frows if (n := _number(wb[sheet][f"{spec['column']}{r}"].value)) is not None]
                    before = row_text[j]
                    rec = Cell(name, title, spec["header"], key, label, refs, before, before, "", "unchanged")
                    if spans.get(id(row[j]._tc), 1) > 1:
                        rec.value = str(sign * sum(nums, Decimal(0))) if nums else ""
                        rec.result = "merged"
                        report.cells.append(rec)
                        continue
                    if not nums:
                        rec.result = "no_format_value"
                        report.cells.append(rec)
                        continue
                    value = sign * sum(nums, Decimal(0))
                    rec.value = str(value)
                    printed = parse_figure(before)
                    if printed is None and before not in DASHES and before:
                        rec.result = "not_printed"  # text, not a figure: left as it is
                        report.cells.append(rec)
                        continue
                    if not before and value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == 0:
                        report.cells.append(rec)  # the filing leaves a nil figure blank: so does the fill
                        continue
                    after = render(value, before)
                    rec.after = after
                    if after != before and not _same(printed, after):
                        rec.result = "written"
                        _set_text(row[j], after, FILLED_SHADE if mark else None)
                    report.cells.append(rec)
        if mark:
            first = d.paragraphs[0] if d.paragraphs else None
            note = first.insert_paragraph_before(NOTE) if first is not None else d.add_paragraph(NOTE)
            for r in note.runs:
                r.bold = True
        buf = io.BytesIO()
        d.save(buf)
        out[name] = buf.getvalue()
        report.documents.append(name)
    return out, report


def _same(printed: Printed | None, after: str) -> bool:
    """The printed figure and the new text are the same number at the same places (a style
    difference only, such as "1202.28" against "1,202.28")."""
    p2 = parse_figure(after)
    return printed is not None and p2 is not None and printed.value == p2.value and printed.places == p2.places
