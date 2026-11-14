"""The Section Reader: an order's power purchase, renewable portfolio, tariff schedule, wheeling /
open access and time-of-day tables, read from the PDF's text layer.

Deterministic, no model.  Where the tables are:
- **Numbered tables** come from the order's own list of tables ("TABLE 6-21: APPROVED POWER
  PURCHASE FOR FY 2026-27 ...... 291"): each title is classified into a section by its words, and
  the table is found on that page (or the nearest page printing its number) below its number.
- **The rate schedule** is the annexure that prints "RATE SCHEDULE <category>" headings; each
  category's ruled tables are read in order, and a table under a "TOD" / "Time of Day" heading
  goes to the time-of-day section.  A category whose rates are printed as running text (no ruled
  table) keeps that text, as printed, so nothing of the schedule is silently missing.

Cells are the text layer's words inside each ruled cell (PyMuPDF ``find_tables``): nothing is
typed, computed or converted.  Empty columns (left by merged cells) are dropped, header rows are
joined per column, and a table continued on the next page is joined to its start.  Every row
keeps its page; ``check`` confirms every number of every row is on that page.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

VERSION = "section-reader 2"
SECTIONS = ("power_purchase", "re_portfolio", "tariff_schedule", "wheeling", "tod")

# the order of the tests matters: "APPC OF RENEWABLE SOURCES" is renewable, not power purchase
CLASSIFY: list[tuple[str, re.Pattern[str]]] = [
    ("tod", re.compile(r"\bTOD\b|\bToD\b|TIME OF DAY|TIME-OF-DAY", re.I)),
    ("re_portfolio", re.compile(r"\bRPO\b|\bRCO\b|RENEWABLE|GREEN TARIFF|GREEN ENERGY|\bSOLAR\b|HYDRO PURCHASE|STORAGE OBLIGATION", re.I)),  # noqa: E501
    (
        "wheeling",
        re.compile(
            r"WHEELING|CROSS[- ]?SUBSIDY SURCHARGE|ADDITIONAL SURCHARGE|OPEN ACCESS|TRANSMISSION CHARGES|"
            r"DISTRIBUTION CHARGES|VOLTAGE[- ]WISE (COST|LOSS)|\bCSS\b|TC[- ]INT(ER|RA)|AGGREGATE OF TRANSMISSION",
            re.I,
        ),
    ),
    (
        "power_purchase",
        re.compile(
            r"POWER PURCHASE|BULK SUPPLY TARIFF|\bAPPC\b|GENERATING STATION|MERIT ORDER|SOURCE[- ]WISE|STATION[- ]WISE",
            re.I,
        ),
    ),
    # last: a table of the retail tariff itself, where the order prints it in its body (MP, Maharashtra,
    # Odisha ... tabulate "Approved tariff for LT domestic" rather than a separate rate schedule)
    (
        "tariff_schedule",
        re.compile(
            r"RETAIL (SUPPLY )?TARIFF|TARIFF SCHEDULE|RATE SCHEDULE|SCHEDULE OF (RETAIL )?TARIFF|APPROVED TARIFF|"
            r"TARIFF (FOR|OF) (LT|HT|LV|HV|EHT|DOMESTIC|NON[- ]DOMESTIC|INDUSTRIAL|AGRICULTUR)|ENERGY CHARGES?\b|"
            r"FIXED CHARGES?\b|DEMAND CHARGES?\b|TARIFF STRUCTURE|CATEGORY[- ]WISE (TARIFF|ABR|AVERAGE)|"
            r"AVERAGE BILLING RATE|\bABR\b",
            re.I,
        ),
    ),
]  # fmt: skip
TABLE_NO = re.compile(r"(?i)\btable\s*(?:no\.?\s*)?[-–:]?\s*(\d{1,3}(?:\s*[-.–]\s*\d{1,3})*)\s*[:.\-–]?")
# a caption printed above a table: 'Table 4.52: Aggregate Revenue Requirement ...' at the start of a line
CAPTION = re.compile(r"^\s*table\s*(?:no\.?\s*)?[-–:]?\s*(\d{1,3}(?:\s*[-.–]\s*\d{1,3})*)\s*[:.\-–]?\s*(.*)$", re.I)
NUM = re.compile(r"^\(?[-–]?\s*[\d,]*\d(?:\.\d+)?\s*\)?\s*%?\*?$")
RATE_SCHEDULE = re.compile(
    r"(?:RATE|TARIFF)\s+SCHEDULE\s*[-–:]?\s*((?:LMV|HV|LV)\s*[-–]?\s*\d+(?:\.\d+)?[A-Z]?)\s*[:\-–]?\s*([^\n]*)", re.I
)
# the heading that opens a whole schedule, in the forms the commissions print it ("Chapter 14: TARIFF
# SCHEDULE", "Annexure 1: Rate Schedule Effective from 01.04.2026", "Appendix-1 / TARIFF SCHEDULE",
# "RETAIL SUPPLY TARIFF EFFECTIVE FROM 1st APRIL, 2023", "TARIFF SCHEDULE FOR FY 2025-26")
SCHEDULE_START = re.compile(
    r"^\s*(?:(?:chapter|annexure|appendix|schedule)\s*[-–]?\s*[\dIVX]+[A-Z]?\s*[:.\-–]?\s*|\d+(?:\.\d+)*\.?\s+)*"
    r"(?:(?:TARIFF|RATE)\s+SCHEDULE\b|RETAIL\s+SUPPLY\s+TARIFF\s+(?:EFFECTIVE|FOR|SCHEDULE)|SCHEDULE\s+OF\s+(?:RETAIL\s+)?TARIFF)",
    re.I,
)
# a heading inside a schedule that names the category the next tables belong to
CATEGORY_LINE = re.compile(
    r"^\s*(?:\(?\d+(?:\.\d+)*\)?\.?\s+|[A-Z]\.\s+|PART\s*[-–]?\s*[A-Z]\s*[:\-–]\s*)?"
    r"((?:RTS|LMV|LV|LT|HT|HV|EHT|EHV|DS|NDS|HTS|HTSS|HTIS|LTIS|IAS|SS|MES|PWW|KJ|AG|BPL)\b[^\n]{0,80}"
    r"|[A-Z][A-Z &/()\-–,.']{4,70}"
    r"|[A-Z][A-Za-z &/,\-–]{3,60}\([A-Z]{2,6}(?:[-–/ ][A-Za-z0-9]+)?\)[^\n.]{0,40})\s*:?\s*$"
)
# a capitals-only heading is a category only when it names a class of consumer or supply
CATEGORY_WORDS = re.compile(
    r"DOMESTIC|COMMERCIAL|INDUSTR|AGRICULT|IRRIGATION|PUMP|PUBLIC|STREET|LIGHT|WATER|RAILWAY|TRACTION|METRO|"
    r"TEMPORARY|BULK|SUPPLY|SERVICE|INSTITUTION|HOSPITAL|EDUCATION|VEHICLE|CHARGING|GENERAL|MILITARY|SCHEDULE|"
    r"CONSUMER|TENSION|VOLTAGE|KUTIR|BPL|HOUSING|COLONY|NON[- ]?DOMESTIC|SEASONAL|CAPTIVE|OPEN ACCESS|NET MET",
    re.I,
)
TOD_HEAD = re.compile(r"TOD\s+(Structure|Rates|Tariff)|TIME\s+OF\s+DAY|\bToD\b", re.I)


def classify(title: str) -> str | None:
    for name, rx in CLASSIFY:
        if rx.search(title):
            # fixed / energy charges of generating stations, or in crore, are a power purchase cost,
            # not a retail tariff ("Fixed cost and Energy charges of MPPMCL allocated stations")
            if name == "tariff_schedule" and (
                re.search(r"\bCRORE\b|\bRs\.?\s*Cr\b", title, re.I)
                or re.search(r"(?<!CHARGING )\bSTATIONS?\b|\bPPAs?\b|GENCO", title, re.I)
            ):
                return "power_purchase"
            return name
    return None


@dataclass
class SectionTable:
    section: str
    seq: int
    label: str | None  # "Table 6-21", "LMV-1" — as printed
    title: str
    page: int
    pages: list[int]
    columns: list[str]
    rows: list[dict[str, Any]]  # {"cells": [...], "page": n}
    kind: str = "table"  # table | text
    category: str | None = None  # the rate schedule's category, e.g. "LMV-1"
    fiscal_year: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ws(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _norm_label(s: str) -> str:
    return re.sub(r"\s*[-.–]\s*", "-", s.strip())


def fiscal_year_of(title: str) -> str | None:
    m = re.search(r"FY\s*'?(20)?(\d{2})\s*[-–]\s*(20)?(\d{2})", title, re.I)
    return f"FY20{m.group(2)}-{m.group(4)}" if m else None


# ------------------------------------------------------------------ the list of tables


def table_index(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The order's list of tables: [{label, title, page}] from its contents pages."""
    from .readers.llm_extractor import is_contents

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in pages[:40]:
        if not p.get("has_text_layer") or not is_contents(p["text"]):
            continue
        text = _ws(p["text"])
        starts = [m for m in TABLE_NO.finditer(text)]
        for i, m in enumerate(starts):
            seg = text[m.end() : starts[i + 1].start() if i + 1 < len(starts) else len(text)]
            pm = re.search(r"\.{2,}\s*(\d{1,4})\b", seg) or re.search(r"\s(\d{1,4})\s*$", seg)
            if not pm:
                continue
            title = _ws(seg[: pm.start()]).strip(" .:-–")
            label = f"Table {_norm_label(m.group(1))}"
            key = f"{label}|{title}"
            if not title or key in seen:
                continue
            seen.add(key)
            out.append({"label": label, "title": title, "page": int(pm.group(1))})
    # captions printed above the tables themselves: the only index of an order with no list of
    # tables, and a complement to one that omits some
    listed = {x["label"] for x in out}
    for p in pages:
        if not p.get("has_text_layer") or is_contents(p["text"]):
            continue
        lines = [ln for ln in p["text"].splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            m = CAPTION.match(ln)
            if not m:
                continue
            label = f"Table {_norm_label(m.group(1))}"
            # 'Table – 25' alone on its line: the title is the next line
            title = _ws(m.group(2) or (lines[i + 1] if i + 1 < len(lines) else "")).strip(" .:-–")
            if label in listed or re.search(r"\.{4,}", title) or len(title) < 6:
                continue
            listed.add(label)
            out.append({"label": label, "title": title[:200], "page": p["page"]})
    return out


# ------------------------------------------------------------------ cleaning a ruled table


FIGURE = re.compile(r"^(?:Rs\.?\s*)?\(?[-+–]?\)?\s*\(?[-–]?[\d,]*\d(?:\.\d+)?\)?\s*(?:%|/|\*|$)", re.I)


def _is_num(c: str) -> bool:
    """A printed figure: '1,234.56', '(12.3)', '13.07%', '(-) 15%', 'Rs. 7.05/kWh' — not '132 kV'."""
    return any(ch.isdigit() for ch in c) and bool(NUM.match(c) or FIGURE.match(c))


def tidy(cols: list[str], body: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Header lines left at the top of the body (no figure, first cell empty; e.g. 'Charge', or the
    'A B C' letters of a derivation) join the column names."""
    while (
        body
        and not body[0][0]
        and any(body[0][1:])
        and (not any(_is_num(c) for c in body[0]) or (len(body[0]) >= 3 and not body[0][1]))
    ):
        cols = [_ws(f"{a} {b}") for a, b in zip(cols, body[0], strict=False)]
        body = body[1:]
    return cols, body


def join_wrapped(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A label wrapped onto the next line ('Long term' / 'Sources') is one row: a row with no
    figure and text in at most two cells, after a row with no figure on the same page, is appended
    to it cell by cell."""
    out: list[dict[str, Any]] = []
    for r in rows:
        cells = r["cells"]
        filled = [c for c in cells if c]
        prev = out[-1] if out else None
        if (
            prev is not None
            and prev["page"] == r["page"]
            and not cells[0]
            and len(filled) <= 2
            and not any(_is_num(c) for c in cells)
            and not any(_is_num(c) for c in prev["cells"])
        ):
            prev["cells"] = [_ws(f"{a} {b}") for a, b in zip(prev["cells"], cells, strict=False)]
            continue
        out.append({**r, "cells": list(cells)})
    return out


def drop_empty(cols: list[str], rows: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    """Columns with no cell in any row are dropped (after all pages are joined): a header over no
    figure is a layout artefact of merged cells."""
    keep = [j for j in range(len(cols)) if any(j < len(r["cells"]) and r["cells"][j] for r in rows)] or list(
        range(len(cols))
    )
    return [cols[j] for j in keep], [
        {**r, "cells": [r["cells"][j] if j < len(r["cells"]) else "" for j in keep]} for r in rows
    ]


SERIAL = re.compile(r"^(?:[A-Za-z]|[ivxIVX]{1,4}|\d{1,3})[.)]?$")


def clean(raw: list[list[Any]]) -> tuple[list[str], list[list[str]]]:
    """(columns, body rows) from cell texts alone: empty columns dropped, header rows (the leading
    rows without a figure) joined per column.  Used where no cell positions are known."""
    rows = [[_ws(c) for c in r] for r in raw]
    if not rows:
        return [], []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    keep = [j for j in range(width) if any(r[j] for r in rows)]
    rows = [[r[j] for j in keep] for r in rows]
    rows = [r for r in rows if any(r)]
    n_head = _n_head(rows)
    head, body = rows[:n_head], rows[n_head:]
    cols = [_ws(" ".join(h[j] for h in head if h[j])) for j in range(len(rows[0]))] if head else [""] * len(rows[0])
    return cols, body


def _n_head(rows: list[list[str]]) -> int:
    """Leading rows that head the table: no figure outside the first cell, and not a group row
    opened by a serial mark ('A', 'a', 'ii', '3')."""
    n = 0
    for r in rows:
        cells = [c for c in r if c]
        # a wrapped header line ("1307/2020", "Fixed | Energy") opens with two empty cells
        header_line = n > 0 and len(r) >= 3 and not r[0] and not r[1]
        if not cells or (any(_is_num(c) for c in r[1:]) and not header_line) or SERIAL.match(cells[0]) and n > 0:
            break
        n += 1
        if n >= 6:
            break
    if n == len(rows):  # words only (a TOD structure, a list): its first row heads it
        n = 1
    return n


def grid(
    t: Any, leaves: list[tuple[float, float]] | None = None
) -> tuple[list[str], list[list[str]], list[tuple[float, float]]]:
    """(columns, body rows, column x-ranges) for a PyMuPDF table, by cell position: the header
    cells' x-ranges give the logical columns (a merged cell that spans others is a group heading,
    its text prefixed to theirs), and every body cell goes to the column it overlaps most.  With
    ``leaves`` (a continuation page), the first page's columns are used for the body."""
    own_header = leaves is None
    texts = [[_ws(c) for c in r] for r in t.extract()]
    boxes = [list(r.cells) for r in t.rows]
    for tx, bx in zip(texts, boxes, strict=False):
        # a word cut by a sliver cell ("For supply up to 1" | "1" | "kV") joins its left neighbour
        last = None
        for j in range(len(tx)):
            b = bx[j] if j < len(bx) else None
            if b and b[2] - b[0] < 12 and tx[j] and last is not None:
                glue = "" if tx[last][-1:].isdigit() and tx[j][:1].isdigit() else " "
                tx[last] = tx[last] + glue + tx[j]
                tx[j] = ""
            elif tx[j]:
                last = j
    rows = [(tx, bx) for tx, bx in zip(texts, boxes, strict=False) if any(tx)]
    if not rows:
        return [], [], leaves or []
    n_head = _n_head([tx for tx, _ in rows])
    head = rows[:n_head]
    hcells = [(tx[j], bx[j]) for tx, bx in head for j in range(len(tx)) if tx[j] and j < len(bx) and bx[j]]
    if leaves is None or (head and len(hcells) > 1 and _leaves(hcells) and len(_leaves(hcells)) == len(leaves)):
        own = _leaves(hcells) if hcells else []
        if leaves is None:
            leaves = own
    body_rows = rows[n_head:] if hcells and leaves is not None else rows
    if not leaves:  # no header with positions: fall back to the cell texts
        cols, body = clean(t.extract())
        return cols, body, []
    if own_header:
        # a column of data under no header cell (e.g. the row labels) is a column too
        extra: list[tuple[float, float]] = []
        for tx, bx in body_rows:
            for j, c in enumerate(tx):
                b = bx[j] if j < len(bx) else None
                if not c or not b:
                    continue
                w = b[2] - b[0]
                if all(_overlap((b[0], b[2]), lf) < 0.3 * w for lf in leaves + extra):
                    extra.append((b[0], b[2]))
        leaves = sorted(leaves + extra)
    names = []
    for lo, hi in leaves:
        parts = [tx for tx, (x0, _, x1, _) in hcells if _overlap((x0, x1), (lo, hi)) > 0.5 * min(hi - lo, x1 - x0)]
        names.append(_ws(" ".join(dict.fromkeys(parts))))
    body: list[list[str]] = []
    for tx, bx in body_rows:
        out = [""] * len(leaves)
        for j, c in enumerate(tx):
            if not c or j >= len(bx) or not bx[j]:
                continue
            x0, _, x1, _ = bx[j]
            k = max(
                range(len(leaves)),
                key=lambda i: (_overlap((x0, x1), leaves[i]), -abs((x0 + x1) / 2 - sum(leaves[i]) / 2)),
            )
            out[k] = _ws(f"{out[k]} {c}")
        if any(out):
            body.append(out)
    if own_header:
        names, body = tidy(names, body)
    return names, body, leaves


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def _leaves(hcells: list[tuple[str, Any]]) -> list[tuple[float, float]]:
    """The header cells that contain no other header cell, left to right."""
    spans = sorted({(round(b[0], 1), round(b[2], 1)) for _, b in hcells})
    leaves = [s for s in spans if not any(o != s and o[0] >= s[0] - 1 and o[1] <= s[1] + 1 for o in spans)]
    return sorted(leaves)


# ------------------------------------------------------------------ reading


_CACHE: dict[tuple[int, str, int], Any] = {}


def _blocks(doc: Any, pno: int) -> list[Any]:
    """A page's text blocks, read once per document (the reader asks for them many times)."""
    key = (id(doc), "blocks", pno)
    if key not in _CACHE:
        _CACHE[key] = doc[pno - 1].get_text("blocks")
    return _CACHE[key]


def _find_label(doc: Any, label: str, near: int, span: int = 3) -> tuple[int, float] | None:
    """(page, y of the label) for 'Table 6-21' on the page nearest to ``near``."""
    num = label.split(" ", 1)[1]
    rx = re.compile(
        r"(?i)table\s*(?:no\.?\s*)?[-–:]?\s*"
        + r"\s*[-.–]\s*".join(re.escape(x) for x in num.split("-"))
        + r"(?![\d.]\d)\b"
    )
    for d in sorted(range(-span, span + 1), key=abs):
        pno = near + d
        if not 1 <= pno <= doc.page_count:
            continue
        for b in _blocks(doc, pno):
            if rx.search(_ws(b[4])) and not re.search(r"\.{4,}", b[4]):
                return pno, b[1]
    # the list of tables may print page numbers offset from the file's (front matter numbered apart):
    # the first caption that opens a block with this number, anywhere after the contents
    start = re.compile(r"^\s*" + rx.pattern.removeprefix("(?i)"), re.I)
    for pno in range(1, doc.page_count + 1):
        for b in _blocks(doc, pno):
            if start.search(str(b[4])) and not re.search(r"\.{4,}", b[4]):
                return pno, b[1]
    return None


def _tables_on(doc: Any, pno: int) -> list[Any]:
    try:
        key = (id(doc), "tables", pno)
        if key not in _CACHE:
            _CACHE[key] = list(doc[pno - 1].find_tables().tables)
        return _CACHE[key]
    except Exception:  # a page PyMuPDF cannot analyse has no table for us
        return []


def _starts_new_table(doc: Any, pno: int, y_top: float) -> bool:
    """Is there a 'Table x-y' or 'RATE SCHEDULE' heading above y_top on page pno?"""
    for b in _blocks(doc, pno):
        if b[3] <= y_top + 1 and (TABLE_NO.search(_ws(b[4])) or RATE_SCHEDULE.search(b[4])):
            return True
    return False


def _read_from(
    doc: Any, pno: int, y_from: float, max_pages: int = 12
) -> tuple[list[str], list[dict], list[int]] | None:
    """The first ruled table on page pno below y_from, joined with its continuations."""
    tabs = [t for t in _tables_on(doc, pno) if t.bbox[1] >= y_from - 2]
    if not tabs:
        return None
    t = min(tabs, key=lambda t: t.bbox[1])
    cols, body, leaves = grid(t)
    if not cols and not body:
        return None
    rows = [{"cells": r, "page": pno} for r in body]
    pages = [pno]
    page_h = doc[pno - 1].rect.height
    last, cur = t, pno
    # continued: the table runs to the foot of its page and the next page opens with a table and
    # no new table heading above it; its cells are placed in the first page's columns
    while len(pages) < max_pages and last.bbox[3] > page_h * 0.80 and cur < doc.page_count and leaves:
        nxt = _tables_on(doc, cur + 1)
        if not nxt:
            break
        first = min(nxt, key=lambda x: x.bbox[1])
        if first.bbox[1] > doc[cur].rect.height * 0.30 or _starts_new_table(doc, cur + 1, first.bbox[1]):
            break
        if abs(first.bbox[0] - t.bbox[0]) > 25 or abs(first.bbox[2] - t.bbox[2]) > 25:
            break  # not the same frame
        _, b2, _ = grid(first, leaves)
        cur += 1
        rows += [{"cells": r, "page": cur} for r in b2]
        pages.append(cur)
        last = first
    cols, rows = drop_empty(cols, join_wrapped(rows))
    return cols, rows, pages


def read_numbered(doc: Any, pages: list[dict[str, Any]]) -> tuple[list[SectionTable], list[str]]:
    out: list[SectionTable] = []
    notes: list[str] = []
    for item in table_index(pages):
        section = classify(item["title"])
        if section is None:
            continue
        loc = _find_label(doc, item["label"], item["page"])
        if not loc:
            notes.append(f"{item['label']} (p. {item['page']}): its number is not printed near that page")
            continue
        pno, y = loc
        got = _read_from(doc, pno, y)
        if not got or not got[1]:
            notes.append(f"{item['label']} (p. {pno}): no ruled table under its title")
            continue
        cols, rows, pgs = got
        out.append(
            SectionTable(
                section=section, seq=0, label=item["label"], title=item["title"], page=pno, pages=pgs,
                columns=cols, rows=rows, fiscal_year=fiscal_year_of(item["title"]),
            )
        )  # fmt: skip
    return out, notes


# headings that open a part of the rate schedule: "RATE SCHEDULE LMV - 1 ...", the lettered general
# parts after the categories ("E. SCHEDULE OF MISCELLANEOUS CHARGES") and the category-wise
# billing-rate / revenue annexure
LETTERED = re.compile(
    r"^\s*([A-H])\.\s+((?:SCHEDULE OF |LIST OF |PUBLIC |STATE |RETAIL |GENERAL )?[A-Z][A-Z ,&/()\-]{6,}?)\s*:?\s*$",
    re.M,
)
CATEGORY_ANNEX = re.compile(
    r"CATEGORY\s*/\s*SUB[- ]?CATEGORY\s+WISE\s+([A-Z0-9 ,()/\-]{8,80}?)(?:\s+CATEGORY\b|\)|$)", re.I | re.M
)


def _rate_schedule_parts(doc: Any) -> list[tuple[int, str, str]]:
    """[(page, part, heading)] in page order: each 'RATE SCHEDULE <category>' heading, then the
    lettered general parts and the category-wise annexure tables that follow the categories."""
    out: list[tuple[int, str, str]] = []
    first = None
    for i in range(doc.page_count):
        t = doc[i].get_text()
        for m in RATE_SCHEDULE.finditer(t):
            cat = re.sub(r"\s*[-–]\s*|\s+", "-", m.group(1).upper()).replace("--", "-")
            out.append((i + 1, cat, _ws(m.group(0))[:160]))
            first = first or i + 1
    if not out:
        return out
    # the schedule is one run of headings; a heading named in the body of the order ("as per rate
    # schedule HV-3", page 51 of a 765-page order) is not a part of it
    runs: list[list[tuple[int, str, str]]] = [[out[0]]]
    for h in out[1:]:
        (runs[-1].append(h) if h[0] - runs[-1][-1][0] <= 15 else runs.append([h]))
    out = max(runs, key=len)
    last_cat = out[-1][0]
    for i in range(last_cat, min(doc.page_count, last_cat + 25)):
        t = doc[i].get_text()
        for m in LETTERED.finditer(t):
            name = _ws(m.group(2)).capitalize()
            if not re.search(
                r"RATE|TARIFF|CHARGE|LAMP|TUBE|APPARATUS|SURCHARGE|REBATE|BILLING|MISCELLANEOUS", m.group(2), re.I
            ):
                continue
            out.append((i + 1, f"{m.group(1)}. {name}"[:60], _ws(m.group(0))[:160]))
        m = CATEGORY_ANNEX.search(t[:400])
        if m and not any(p == i + 1 for p, _, _ in out):
            out.append((i + 1, ("Category-wise " + _ws(m.group(1)).lower())[:70], _ws(m.group(0))[:160]))
    out.sort(key=lambda x: x[0])
    # a part ends where the next begins; the last one ends at the next annexure heading
    return out


def _heading_y(page: Any, heading: str) -> float:
    key = _ws(heading)[:40].lower()
    for b in page.get_text("blocks"):
        if key and key in _ws(b[4]).lower():
            return b[1]
    return 0.0


HEADING_LINE = re.compile(r"^(?:\(?[A-Za-z0-9]{1,4}\)|[A-Z0-9]{1,3}[.)])\s+\S")


def _title_above(blocks: list[Any], y_top: float, fallback: str) -> str:
    """The sub-heading printed just above a table: the nearest line within 90 pt above it that
    reads as a heading — numbered or lettered ('(a) …', 'A. …', '2. …'), or ending with ':', or
    starting with a capital and printing no charge — else the part's own heading."""
    lines: list[str] = []
    for b in sorted(blocks, key=lambda b: b[3]):
        if y_top - 90 <= b[3] <= y_top + 1:
            lines += [_ws(ln) for ln in str(b[4]).splitlines() if _ws(ln)]
    for ln in reversed(lines):
        if re.fullmatch(r"ANNEXURES?|Page \d+ of \d+|\d+", ln, re.I) or re.search(r"Rs\.|/\s*k(W|VA)h?\b", ln):
            continue
        if not (ln[:1].isupper() or ln[:1].isdigit() or ln[:1] == "("):  # the tail of a sentence
            continue
        if HEADING_LINE.match(ln) or ln.endswith(":") or (ln[:1].isupper() and len(ln) <= 90):
            return ln.rstrip(":")[:160]
    return fallback


def _schedule_region(doc: Any) -> tuple[int, int, str] | None:
    """(first page, last page, heading) of the order's schedule: its last opening heading (earlier
    mentions are in the body), to the next unrelated chapter / annexure or at most 70 pages."""
    start = None
    for i in range(doc.page_count):
        for ln in [_ws(x) for x in doc[i].get_text().splitlines()[:12]]:
            if ln and len(ln) < 140 and SCHEDULE_START.search(ln) and not re.search(r"\.{4,}", ln):
                start = (i + 1, ln)
                break
    if not start:
        return None
    first, heading = start
    last = min(doc.page_count, first + 70)
    for p in range(first + 1, last + 1):
        for ln in [_ws(x) for x in doc[p - 1].get_text().splitlines()[:14]]:
            if re.match(r"^(chapter|annexure|appendix)\b", ln, re.I) and not re.search(
                r"tariff|rate|schedule|condition|charges|supply", ln, re.I
            ):
                return first, p - 1, heading
    return first, last, heading


def _category_above(doc: Any, region: tuple[int, int], p: int, y: float) -> str | None:
    """The nearest category heading printed before (page p, y) inside the schedule region."""
    for q in range(p, region[0] - 1, -1):
        blocks = [b for b in _blocks(doc, q) if q < p or b[3] <= y + 1]
        for b in sorted(blocks, key=lambda b: -b[1]):
            for ln in reversed([_ws(x) for x in str(b[4]).splitlines() if _ws(x)]):
                m = CATEGORY_LINE.match(ln)
                if not m or re.search(r"Rs\.|\d{3,}|ANNEXURE|^PAGE\b|ORDER FOR|COMMISSION", ln, re.I):
                    continue
                cat = _ws(m.group(1)).rstrip(":")
                if cat.endswith(".") or len(cat.split()) > 12:  # a sentence, not a heading
                    continue
                bracket = re.search(r"\([A-Z]{2,6}(?:[-–/ ][A-Za-z0-9]+)?\)", cat)
                if bracket:  # "Low Tension Industrial Service (LTIS): AC, 50 Cycles ..." -> up to its code
                    cat = cat[: bracket.end()]
                coded = re.match(
                    r"(RTS|LMV|LV|LT|HT|HV|EHT|EHV|DS|NDS|HTS|HTSS|HTIS|LTIS|IAS|SS|MES|PWW|KJ|AG|BPL)\b", cat
                )
                if coded or CATEGORY_WORDS.search(cat):
                    return cat[:80]
    return None


def read_schedule_region(doc: Any) -> tuple[list[SectionTable], list[str]]:
    """Where the schedule has no per-category headings this reader knows: every ruled table between
    the schedule's opening heading and its end, under the nearest category heading above it."""
    region = _schedule_region(doc)
    if not region:
        return [], ["no tariff / rate schedule heading in the order"]
    first, last, heading = region
    out: list[SectionTable] = []
    for p in range(first, last + 1):
        blocks = _blocks(doc, p)
        for t in _tables_on(doc, p):
            cols, body, _ = grid(t)
            if not body:
                continue
            cols, rws = drop_empty(cols, join_wrapped([{"cells": r, "page": p} for r in body]))
            body = [r["cells"] for r in rws]
            cells = " ".join(" ".join(r) for r in body) + " " + " ".join(cols)
            slots = len(re.findall(r"\d{1,2}[:.]\d{2}\s*(?:hrs|hours|a\.?m\.?|p\.?m\.?)", cells, re.I))
            section = "tod" if slots >= 2 else "tariff_schedule"
            cat = _category_above(doc, (first, last), p, t.bbox[1])
            out.append(
                SectionTable(
                    section=section, seq=0, label=cat, title=_title_above(blocks, t.bbox[1], cat or heading), page=p,
                    pages=[p], columns=cols, rows=rws, category=cat,
                )
            )  # fmt: skip
    notes = [] if out else [f"schedule pp. {first}-{last} ({heading[:60]}): no ruled table"]
    return out, notes


def read_rate_schedule(doc: Any) -> tuple[list[SectionTable], list[str]]:
    """Each part of the rate schedule: its ruled tables, a table of time slots going to the
    time-of-day section; a category with no ruled table keeps its 'RATE' text as printed."""
    parts = _rate_schedule_parts(doc)
    out: list[SectionTable] = []
    notes: list[str] = []
    if not parts:
        return read_schedule_region(doc)
    for k, (pno, cat, heading) in enumerate(parts):
        nxt = parts[k + 1] if k + 1 < len(parts) else None
        end = nxt[0] if nxt else min(pno + 3, doc.page_count)
        found = 0
        for p in range(pno, end + 1):
            page = doc[p - 1]
            blocks = _blocks(doc, p)
            y_start = _heading_y(page, heading) if p == pno else 0.0
            y_stop = _heading_y(page, nxt[2]) if nxt and p == nxt[0] else page.rect.height + 1
            if nxt and p == nxt[0] and y_stop == 0.0:
                continue
            for t in _tables_on(doc, p):
                if not (y_start - 2 <= t.bbox[1] < y_stop):
                    continue
                cols, body, _ = grid(t)
                if not body:
                    continue
                cols, rws = drop_empty(cols, join_wrapped([{"cells": r, "page": p} for r in body]))
                body = [r["cells"] for r in rws]
                cells = " ".join(" ".join(r) for r in body) + " " + " ".join(cols)
                above = " ".join(_ws(b[4]) for b in blocks if t.bbox[1] - 60 <= b[3] <= t.bbox[1] + 1)
                slots = len(re.findall(r"\d{1,2}[:.]\d{2}\s*(?:hrs|hours|a\.?m\.?|p\.?m\.?)", cells, re.I))
                section = "tod" if slots >= 2 or (TOD_HEAD.search(above) and slots) else "tariff_schedule"
                found += 1
                out.append(
                    SectionTable(
                        section=section, seq=0, label=cat, title=_title_above(blocks, t.bbox[1], heading), page=p,
                        pages=[p], columns=cols, rows=[{"cells": r, "page": p} for r in body], category=cat,
                    )
                )  # fmt: skip
        if not found and re.match(r"(LMV|HV)-", cat):
            text = _rate_text(doc, pno, end)
            if text:
                out.append(
                    SectionTable(
                        section="tariff_schedule", seq=0, label=cat, title=heading, page=text[0]["page"],
                        pages=sorted({r["page"] for r in text}), columns=["Rate, as printed"], rows=text,
                        kind="text", category=cat,
                    )
                )  # fmt: skip
            else:
                notes.append(f"{cat} (p. {pno}): no ruled table and no 'RATE' text found")
    return out, notes


def _rate_text(doc: Any, start: int, end: int) -> list[dict[str, Any]]:
    """The lines of a category's 'RATE' paragraph that print a charge, as printed."""
    out = []
    on = False
    for p in range(start, end + 1):
        for line in doc[p - 1].get_text().splitlines():
            s = _ws(line)
            if re.match(r"^\d+\.\s*RATE\b|^RATE\s*:", s, re.I):
                on = True
            elif on and re.match(r"^\d+\.\s*[A-Z][A-Z ]{4,}", s) and not re.search(r"RATE", s):
                on = False
            if on and re.search(r"Rs\.?|/kWh|/kW|/kVA|%", s) and re.search(r"\d", s):
                out.append({"cells": [s], "page": p})
    return out


def read(pdf: str | Path, pages: list[dict[str, Any]]) -> tuple[list[SectionTable], list[str]]:
    import pymupdf

    doc = pymupdf.open(str(pdf))
    try:
        numbered, n1 = read_numbered(doc, pages)
        sched, n2 = read_rate_schedule(doc)
    finally:
        for k in [k for k in _CACHE if k[0] == id(doc)]:
            del _CACHE[k]
        doc.close()
    tables = numbered + sched
    for name in SECTIONS:
        for i, t in enumerate(t for t in tables if t.section == name):
            t.seq = i + 1
    tables.sort(key=lambda t: (SECTIONS.index(t.section), t.seq))
    return tables, n1 + n2


# ------------------------------------------------------------------ the evidence test


def _tokens(s: str) -> list[str]:
    return [t.rstrip(",") for t in re.findall(r"\d[\d,]*(?:\.\d+)?", s or "")]


def check(tables: Iterable[SectionTable], pages: list[dict[str, Any]]) -> dict[str, int]:
    """Every number of every row on that row's page (text layer).  Rows that fail are dropped and
    counted; the cells came from the text layer, so a failure is a reading fault, not a source."""
    toks: dict[int, set[str]] = {}
    for p in pages:
        ts = _tokens(p["text"])
        toks[p["page"]] = set(ts) | {t.replace(",", "") for t in ts}
    checked = failed = 0
    for t in tables:
        kept = []
        for r in t.rows:
            have = toks.get(r["page"], set())
            ok = all(x in have or x.replace(",", "") in have for c in r["cells"] for x in _tokens(c))
            checked += 1
            if ok:
                kept.append(r)
            else:
                failed += 1
        t.rows = kept
    return {"rows_checked": checked, "rows_failed": failed}
