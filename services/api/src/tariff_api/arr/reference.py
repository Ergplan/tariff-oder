"""Reference filings (milestone 13, R-ACC-1): a licensee's filed tariff formats as the target a
reproduction is measured against.

A filed format sheet (e.g. UPERC's "Form No: ARR") is a grid: a title block, a header of
fiscal years over voice words ("Approved (in TO)", "Audited", "Claimed", "Estimated",
"Projected"), then rows of a serial number, a particulars label and one value per column.
This module reads such a sheet into typed rows, places each label on the ARR taxonomy with
the commission's mapping, and keeps what the petitioner printed exactly:

- values are Decimals from the stored cell value (the shortest repr of the stored binary
  number, never re-rounded); a cell formatted as a percentage is converted to percent and
  says so;
- text cells are **states**, never values: "Incl. above", "Incl. in A&G" → ``included``;
  "NA" → ``not_applicable``; blank → absent (not stored);
- each column keeps its printed words and its voice.  A petition restates commission figures
  ("Trued-Up", "Approved (in TO)"); those are the petitioner's restatement, marked
  ``restated``, and never become commission facts from this source.

The reference is **unreviewed** machine reading of the petitioner's own spreadsheet: a person
confirms it before any acceptance figure is computed against it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from .taxonomy import Mapping, Placer, Taxonomy

# "FY 21-22", "FY23-24", "FY 2024-25", "2025-26"
_FY = re.compile(r"(?:FY\s*'?)?((?:20)?\d{2})\s*[-–/]\s*(\d{2}|20\d{2})\b", re.I)

# printed column words → (voice, restated?).  Order matters: the first match wins.
COLUMN_VOICES: list[tuple[re.Pattern[str], str, bool]] = [
    (re.compile(r"trued\s*-?\s*up", re.I), "final_true_up", True),
    (re.compile(r"provisional", re.I), "provisional_true_up", True),
    (re.compile(r"approved", re.I), "approved", True),
    (re.compile(r"audited|actual", re.I), "actual", False),
    (re.compile(r"claimed|estimated|projected|proposed|petitioned", re.I), "petitioned", False),
]
INCLUDED = re.compile(r"^\s*incl(uded)?\.?\b", re.I)
NOT_APPLICABLE = re.compile(r"^\s*(na|n\.a\.?|not applicable|-+)\s*$", re.I)
UNIT_IN_LABEL = [
    (re.compile(r"\(\s*MU\s*\)|\bMU\b", re.I), "MU"),
    (re.compile(r"\(\s*%\s*\)|\bin\s*%|(?<![\d.])\s%\s*$", re.I), "percent"),  # not "@10%": a rate, not a unit
    (re.compile(r"Rs\.?\s*/\s*kWh|paise", re.I), "INR_per_kWh"),
]
SHEET_UNITS = [
    (re.compile(r"Rs\.?\s*(in\s*)?crores?|Rs\.?\s*Cr\b|crores?", re.I), "INR_crore"),
    (re.compile(r"\bMU\b", re.I), "MU"),
    (re.compile(r"Rs\.?\s*lakhs?", re.I), "INR_lakh"),
]


UNIT_WORDS = [
    (re.compile(r"^MU$", re.I), "MU"),
    (re.compile(r"^%$"), "percent"),
    (re.compile(r"^Rs\.?\s*(in\s*)?(crores?|cr\.?)$", re.I), "INR_crore"),
    (re.compile(r"^Rs\.?\s*lakhs?$", re.I), "INR_lakh"),
    (re.compile(r"^Rs\.?\s*/\s*kWh$", re.I), "INR_per_kWh"),
    (re.compile(r"^paise\s*/\s*kWh$", re.I), "paise_per_kWh"),
    (re.compile(r"^MW$", re.I), "MW"),
]


def unit_word(text: str) -> str | None:
    """A unit as a Units column prints it ("MU", "%", "Rs. Crore") → the canonical unit."""
    return next((u for pat, u in UNIT_WORDS if pat.match(text.strip())), None) if text else None


def fiscal_year(text: str) -> str | None:
    """'FY 21-22' → 'FY2021-22'; None when the text names no year or several."""
    found = set()
    for m in _FY.finditer(text or ""):
        a, b = m.group(1), m.group(2)
        start = int(a) + (2000 if len(a) == 2 else 0)
        end = int(b[-2:])
        if (start + 1) % 100 == end:
            found.add(f"FY{start}-{end:02d}")
    return found.pop() if len(found) == 1 else None


def column_voice(words: str) -> tuple[str | None, bool]:
    for pat, v, restated in COLUMN_VOICES:
        if pat.search(words or ""):
            return v, restated
    return None, False


def _text(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _number(v: Any) -> Decimal | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int | float):
        try:
            return Decimal(repr(v)) if isinstance(v, float) else Decimal(v)
        except InvalidOperation:
            return None
    return None


@dataclass
class Column:
    index: int
    fiscal_year: str
    words: str  # the printed column words, e.g. "Approved (in TO)"
    voice: str
    restated: bool  # a commission figure as the petitioner restates it


@dataclass
class Cell:
    fiscal_year: str
    voice: str
    words: str
    restated: bool
    value: str | None  # the stored value (Decimal as string); None when the cell is a state
    displayed: str | None  # the value as the sheet prints it (its number format's decimals)
    state: str  # "value" | "included" | "not_applicable" | "text"
    printed: str  # what the cell held, as text
    unit: str | None
    percent_from_fraction: bool = False


@dataclass
class Row:
    row: int  # 1-based sheet row
    serial: str
    label: str
    line_code: str | None  # a *proposed* placement: a reviewer confirms it
    matched: str | None
    unit: str | None
    cells: list[Cell] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class SheetReading:
    sheet: str
    form: str | None
    title: str
    unit: str | None
    columns: list[Column]
    rows: list[Row]
    unplaced: list[str]
    notes: list[str]


def decimals_of(number_format: str | None) -> int | None:
    """The decimals a number format prints: '0.00' → 2, '#,##0' → 0, '0.0%' → 1; None when the
    format is General or unknown."""
    f = (number_format or "").split(";")[0]
    if not f or f.lower() == "general":
        return None
    m = re.search(r"0\.(0+)", f)
    return len(m.group(1)) if m else (0 if "0" in f or "#" in f else None)


def _plain(d: Decimal) -> str:
    """A Decimal without exponent or trailing zeros ('6.970036526137036', '0')."""
    t = format(d.normalize(), "f")
    return t if t != "-0" else "0"


def read_columns(rows: list[list[Any]], *, max_header_rows: int = 12) -> tuple[int, list[Column], list[str]]:
    """Find the header: a row naming fiscal years, with the voice words in it or in the next
    rows.  A year printed once over a group of columns carries right until the next year.
    Returns (index of the last header row, columns, notes)."""
    notes: list[str] = []
    for i, row in enumerate(rows[:max_header_rows]):
        years = {j: fiscal_year(_text(v)) for j, v in enumerate(row)}
        years = {j: y for j, y in years.items() if y}
        if len(years) < 2:
            continue
        width = max(len(r) for r in rows[i : i + 4])
        carried: dict[int, str] = {}
        current = None
        for j in range(min(years), width):
            current = years.get(j, current)
            if current:
                carried[j] = current
        # the voice words: from this row and up to three rows below (the header may wrap)
        words: dict[int, str] = {}
        last = i
        for k in range(i, min(i + 4, len(rows))):
            r = rows[k]
            if k > i and any(_number(v) is not None for v in r):
                break
            hit = False
            for j in carried:
                t = _text(r[j]) if j < len(r) else ""
                if t and (k > i or not fiscal_year(t)):
                    words[j] = (words.get(j, "") + " " + t).strip()
                    hit = True
            if hit:
                last = k
        cols = []
        group_words: dict[str, str] = {}  # a group heading over a year ("True-Up", "APR")
        for j, y in carried.items():
            w = words.get(j, "")
            v, restated = column_voice(w)
            if v is None:
                # the year cell's own row may carry the group ("True- Up", "ARR")
                above = _text(rows[i - 1][j]) if i > 0 and j < len(rows[i - 1]) else ""
                g = group_words.setdefault(y, above)
                if re.search(r"\bARR\b|project", g, re.I) and not w:
                    v, restated, w = "petitioned", False, (w or "ARR (projected)")
            if v is None:
                notes.append(f"column {j + 1} ({y}, {w or 'no words'}): no voice; skipped")
                continue
            cols.append(Column(index=j, fiscal_year=y, words=w, voice=v, restated=restated))
        return last, cols, notes
    return -1, [], ["no header naming two or more fiscal years"]


def read_sheet(
    name: str,
    rows: list[list[Any]],
    formats: list[list[str | None]] | None,
    taxonomy: Taxonomy,
    mapping: Mapping | None,
) -> SheetReading:
    """Read one filed format sheet.  ``formats`` holds each cell's number format (to tell a
    percentage stored as a fraction); None when unknown."""
    texts = [_text(v) for r in rows[:6] for v in r if _text(v)]
    head = " ".join(texts)
    form = next(
        (m.group(1).strip() for t in texts if (m := re.match(r"Form\s*(?:No\.?)?\s*[:.]?\s*(\S.*)$", t, re.I))), None
    )
    unit = next((u for pat, u in SHEET_UNITS if pat.search(head)), None)
    title = next(
        (t for t in texts if len(t) > 12 and not t.lower().startswith("form") and not re.search(r"limited$", t, re.I)),
        "",
    )
    last, columns, notes = read_columns(rows)
    # a "Units" column in the header gives each row its unit (the Energy Balance format)
    units_col = next(
        (j for r in rows[: max(last + 1, 0)] for j, v in enumerate(r) if re.fullmatch(r"units?", _text(v), re.I)),
        None,
    )
    placer = Placer(taxonomy, mapping)
    out: list[Row] = []
    unplaced: list[str] = []
    for i in range(last + 1, len(rows)):
        r = rows[i]
        serial = _text(r[0]) if r else ""
        label = _text(r[1]) if len(r) > 1 else ""
        if not label:
            continue
        lu = unit_word(_text(r[units_col])) if units_col is not None and units_col < len(r) else None
        lu = lu or next((u for pat, u in UNIT_IN_LABEL if pat.search(label)), None)
        cells = []
        for c in columns:
            raw = r[c.index] if c.index < len(r) else None
            fmt = (formats[i][c.index] if formats and c.index < len(formats[i]) else None) or ""
            n = _number(raw)
            printed = _text(raw)
            if n is not None:
                pct = "%" in fmt
                v = n * 100 if pct else n
                places = decimals_of(fmt)
                shown = _plain(v.quantize(Decimal(1).scaleb(-places))) if places is not None else None
                u = "percent" if pct else (lu or unit)
                cells.append(
                    Cell(
                        c.fiscal_year,
                        c.voice,
                        c.words,
                        c.restated,
                        _plain(v),
                        shown,
                        "value",
                        printed,
                        u,
                        percent_from_fraction=pct,
                    )
                )
            elif printed:
                state = (
                    "included"
                    if INCLUDED.match(printed)
                    else "not_applicable"
                    if NOT_APPLICABLE.match(printed)
                    else "text"
                )
                cells.append(Cell(c.fiscal_year, c.voice, c.words, c.restated, None, None, state, printed, None))
        if not cells:
            continue  # a heading row ("B Expenditure", "c Net O&M Expenses")
        p = placer.place(label, lu or unit)
        if p is None:
            unplaced.append(label)
        out.append(
            Row(
                row=i + 1,
                serial=serial,
                label=label,
                line_code=p.code if p else None,
                matched=p.matched if p else None,
                unit=lu or unit,
                cells=cells,
            )
        )
    # a code proposed for several rows is suspect: one of them is a sub-row, a deduction or a
    # different line the mapping does not tell apart.  Flagged for the reviewer, never resolved here.
    by_code: dict[str, list[Row]] = {}
    for row in out:
        if row.line_code:
            by_code.setdefault(row.line_code, []).append(row)
    for code, rs in by_code.items():
        if len(rs) > 1:
            for row in rs:
                row.flags.append(f"{code} proposed for {len(rs)} rows")
    return SheetReading(name, form, title, unit, columns, out, unplaced, notes)


def load_workbook_sheet(path: str, sheet: str) -> tuple[list[list[Any]], list[list[str | None]]]:
    """The stored values and number formats of one sheet (no formulas evaluated, no macros)."""
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet]
    values: list[list[Any]] = []
    formats: list[list[str | None]] = []
    for row in ws.iter_rows(max_col=min(ws.max_column or 60, 60)):
        values.append([c.value for c in row])
        formats.append([getattr(c, "number_format", None) for c in row])
    wb.close()
    return values, formats


def as_dict(r: SheetReading) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(r)
