"""How a table's cells are read as ARR values — shared by the readers that find cells in other
ways than the text layer (Docling, LlamaParse), so that readers differ in how they find cells,
not in how they interpret them.

Everything that gives a cell its meaning is arrdb's: the title filter of ``arrdb.reader.read_tables``
(repeated here as ``title_ok`` because arrdb keeps it inline), the column meaning
(``arrdb.reader.column_meaning``: licensee, year, voice from the header cells), the head
(``arrdb.heads.head_of``), number parsing (``arrdb.reader.NUM`` / ``number``), the unit
(``arrdb.reader.unit_of``) and the serial-column and transposed-table rules of ``read_one``.
"""

from __future__ import annotations

import re
from typing import Any

from ..arrdb_bridge import (
    ARR_TITLE,
    DASH,
    NOT_ARR_TITLE,
    NUM,
    OTHER_ENTITY,
    OTHER_ENTITY_FOR_TRANSCO,
    PART_BUSINESS,
    TOC,
    Column,
    column_meaning,
    head_of,
    number,
    unit_of,
    voice_of,
    years_in,
)

SERIAL_CELL = re.compile(r"^(\(?[ivxlc]+[.)]?|\(?[a-z][.)]|\d{1,2}(\.\d)?[.)]?|[A-Z](=[A-Z+\-*/()]+)?)$", re.I)


def title_ok(title: str, licensees: list[str], aliases: dict[str, list[str]], kind: str = "discom") -> bool:
    """The title filter of arrdb.reader.read_tables: an ARR summary table of the licensee.  In a
    transmission order (kind 'transco') the tables skipped are the other businesses'."""
    if TOC.search(title) or not ARR_TITLE.search(title) or NOT_ARR_TITLE.search(title):
        return False
    if PART_BUSINESS.search(title) and not re.search(
        r"combined|consolidated|total|wires?\s*(\+|and|&)\s*supply|supply\s*(\+|and|&)\s*wires?", title, re.I
    ):
        return False
    if re.search(r"categor|agricultur|\bLT\b|\bHT\b|consumer class", title):
        return False
    other = OTHER_ENTITY_FOR_TRANSCO if kind == "transco" else OTHER_ENTITY
    if other.search(title) and not any(
        re.search(rf"(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])", title, re.I)
        for code in licensees
        for n in [code, *aliases.get(code, [])]
        if len(n) > 3
    ):
        return False
    return True


def clean_cell(s: Any) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def is_num(s: str) -> bool:
    return bool(NUM.match(s.replace(" ", "")))


def is_value_cell(s: str) -> bool:
    t = s.replace(" ", "")
    return bool(t) and (bool(NUM.match(t)) or bool(DASH.match(t)))


def grid_to_table(
    grid: list[list[str]],
    *,
    title: str,
    page: int,
    row_pages: list[int] | None,
    licensees: list[str],
    aliases: dict[str, list[str]],
    above: str = "",
    header_rows: int | None = None,
    min_lines: int = 4,
) -> dict[str, Any] | None:
    """A table (arrdb's Table shape: title, page, pages, unit, factor, columns, lines) from a cell
    grid.  ``row_pages`` gives each grid row's page (a table continued over pages)."""
    grid = [[clean_cell(c) for c in r] for r in grid]
    row_pages = list(row_pages) if row_pages else [page] * len(grid)
    if len(row_pages) != len(grid):
        raise ValueError(f"{len(grid)} rows but {len(row_pages)} row pages")
    kept = [(r, p) for r, p in zip(grid, row_pages, strict=True) if any(r)]
    grid, row_pages = [r for r, _ in kept], [p for _, p in kept]
    if len(grid) < 2:
        return None
    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    # header rows: given by the reader, else the rows above the first row that has a label and a number
    if header_rows is None:
        header_rows = 0
        for r in grid:
            label = [c for c in r if c and not is_value_cell(c)]
            vals = [c for c in r if is_num(c)]
            if label and vals and not (years_in(" ".join(label)) and not any("." in v for v in vals)):
                break
            header_rows += 1
        header_rows = min(header_rows, 8)
    head, body = grid[:header_rows], grid[header_rows:]
    bpages = row_pages[header_rows:]
    if not body:
        return None
    # the label column: the first whose body cells are mostly words (a serial-number column before it
    # is part of the label side); value columns are to its right, mostly numbers or dashes
    label_col = 0
    for j in range(width):
        cells = [r[j] for r in body if r[j]]
        if cells and sum(1 for c in cells if not is_value_cell(c) and not SERIAL_CELL.match(c)) >= 0.5 * len(cells):
            label_col = j
            break
    value_cols = []
    for j in range(label_col + 1, width):
        cells = [r[j] for r in body if r[j]]
        if cells and sum(1 for c in cells if is_value_cell(c)) >= 0.6 * len(cells) and any(is_num(c) for c in cells):
            value_cols.append(j)
    if not value_cols:
        return None
    first_val = value_cols[0]
    cols = [Column(float(j), float(j), float(j), header=[h[j] for h in head if h[j]]) for j in value_cols]
    unit, factor = unit_of([title, *(" ".join(h) for h in head[:4])])
    names = {code: [code, *aliases.get(code, [])] for code in licensees}
    columns = [column_meaning(c, title, licensees, names) for c in cols]
    ay = years_in(above)
    av = voice_of(above) if above else None
    for c in columns:
        c["year_from"] = "header" if years_in(c["header"]) else ("title" if c["fiscal_year"] else None)
        c["voice_from"] = "header" if voice_of(c["header"]) else ("title" if c["voice"] else None)
        if c["fiscal_year"] is None and len(ay) == 1:
            c["fiscal_year"], c["year_from"] = ay[0], "text above the table"
        if c["voice"] is None and av in ("claimed", "approved"):
            c["voice"], c["voice_from"] = av, "text above the table"
    lines: list[dict[str, Any]] = []
    pending: list[str] = []
    group: str | None = None
    for r, pg in zip(body, bpages, strict=True):
        label_cells = [c for c in r[:first_val] if c]
        while len(label_cells) > 1 and SERIAL_CELL.match(label_cells[0]):
            label_cells.pop(0)  # a serial number before the label
        if (
            len(label_cells) == 1
            and SERIAL_CELL.match(label_cells[0])
            and not re.search(r"[a-z]{3}", label_cells[0], re.I)
        ):
            label_cells = []
        ltext = " ".join(label_cells).strip(" :-")
        vals = [(k, r[j]) for k, j in enumerate(value_cols) if r[j] and is_num(r[j])]
        if not vals:
            if ltext:
                pending.append(ltext)
            continue
        row_voice = None
        if not ltext and pending:
            ltext, pending = " ".join(pending), []
        elif pending and ltext and ltext[0].islower():
            ltext, pending = f"{' '.join(pending)} {ltext}", []
        elif pending:
            group, pending = " ".join(pending), []
        if group and re.fullmatch(r"(proposed|approved|claimed|admitted|petition|allowed|projected)", ltext, re.I):
            row_voice = voice_of(ltext)
            ltext = f"{group} ({ltext})"
        if not ltext:
            ltext = group or ""
        quote = " ".join(c for c in r if c)
        for k, v in vals:
            val = number(v.replace(" ", ""))
            if val is None:
                continue
            lines.append(
                {
                    "row_voice": row_voice,
                    "label": ltext,
                    "group": group,
                    "head": head_of(ltext),
                    "column": k,
                    "value_printed": v.replace(" ", ""),
                    "value": val,
                    "page": pg,
                    "quote": quote,
                }
            )
    labelled = [ln for ln in lines if ln["label"]]
    yearly = [ln for ln in labelled if years_in(ln["label"]) and len(ln["label"]) <= 16]
    if labelled and len(yearly) >= 0.6 * len(labelled):
        out = []
        for ln in yearly:
            h = re.sub(r"^particulars\s*", "", columns[ln["column"]]["header"], flags=re.I)
            out.append({**ln, "label": h, "head": head_of(h), "row_year": years_in(ln["label"])[0]})
        lines = out
    serial = {
        i
        for i, c in enumerate(columns)
        if re.search(r"\b(s|sl|sr)\.?\s*(particulars\s*)?no\b|\breference\b", c["header"], re.I)
    }
    for i in range(len(columns)):
        vs = [ln["value_printed"] for ln in lines if ln["column"] == i]
        if len(vs) >= 3 and all(re.fullmatch(r"\d{1,2}", v) for v in vs):
            serial.add(i)
    lines = [ln for ln in lines if ln["column"] not in serial]
    if len(lines) < min_lines:
        return None
    used = sorted({ln["column"] for ln in lines})
    return {
        "title": title,
        "page": page,
        "pages": sorted(set(row_pages)),
        "unit": unit,
        "factor": factor,
        "columns": [{**c, "index": i} for i, c in enumerate(columns) if i in used],
        "lines": lines,
    }


def tables_to_rows(
    tables: list[dict[str, Any]], arr_year: str | None, stage_of
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """parsed_tables rows and arr_values rows (without order_url / reader / version) from arrdb-shaped
    tables, exactly as arrdb.build stores them."""
    trows, vrows = [], []
    for t in tables:
        trow = {
            "page": t["page"],
            "pages": t["pages"],
            "title": t["title"],
            "unit": t["unit"],
            "unit_from": t.get("unit_from"),
            "columns": t["columns"],
        }
        if t.get("cells") is not None:
            trow["cells"] = t["cells"]
        if t.get("markdown"):
            trow["markdown"] = t["markdown"]
        trows.append(trow)
        cols = {c["index"]: c for c in t["columns"]}
        for ln in t["lines"]:
            c = cols.get(ln["column"])
            if c is None:
                continue
            fy = ln.get("row_year") or c["fiscal_year"]
            voice = ln.get("row_voice") or c["voice"]
            vc = round(ln["value"] * t["factor"], 4) if t.get("factor") else None
            vrows.append(
                {
                    "table_page": t["page"],
                    "table_title": t["title"],
                    "utility": c["licensee"],
                    "fiscal_year": fy,
                    "voice": voice,
                    "stage": stage_of(fy, arr_year),
                    "head": ln["head"],
                    "label": ln["label"],
                    "group_label": ln.get("group"),
                    "value_printed": ln["value_printed"],
                    "value": ln["value"],
                    "unit": t["unit"],
                    "value_crore": vc,
                    "page": ln["page"],
                    "quote": ln["quote"],
                    "column_header": c["header"],
                    "year_from": "row label" if ln.get("row_year") else c.get("year_from"),
                    "voice_from": "row label" if ln.get("row_voice") else c.get("voice_from"),
                }
            )
    return trows, vrows


def markdown_tables(md: str) -> list[tuple[int, list[list[str]]]]:
    """(line index, grid) for every pipe table in a markdown text; separator rows dropped."""
    out: list[tuple[int, list[list[str]]]] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            start = i
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) or not c for c in cells) or not any(cells):
                    rows.append(cells)
                i += 1
            if rows:
                out.append((start, rows))
        else:
            i += 1
    return out


def group_for(title: str, groups: list[tuple[list[str], str]], aliases: dict[str, list[str]]) -> list[str] | None:
    """The licensees of the first reading pass whose title filter keeps this table, or None."""
    for lic, kind in groups:
        if title_ok(title, lic, aliases, kind):
            return lic
    return None
