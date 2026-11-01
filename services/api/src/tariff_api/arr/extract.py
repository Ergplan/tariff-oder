"""ARR structure channel (ARR spec section 6, ADR-0018): deterministic rules over the primary
grids of a confirmed chapter.  Column headers give the fiscal year and the voice (the
mapping's voice words), the row label is placed on the taxonomy (generic aliases, then the
commission's own words), the caption or the label gives the unit, and every value cites its
cell.  A row the taxonomy cannot place is reported as unplaced, never guessed; a column
without a year or a voice is reported, never assumed.  Pure functions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from ..tariff_schema import EvidenceRef
from .schema import ArrCandidate, ArrExtractionOutput, to_canonical, unit_from_text
from .taxonomy import Mapping, Placer, Taxonomy

ARR_RULES_VERSION = "arr-rules-2"
_FY = re.compile(r"(?:FY\s*)?(20\d{2})\s*[-–/]\s*(\d{2}|20\d{2})\b", re.I)
_ABSENT = {"-", "–", "—", "na", "n.a.", "n/a", "nil*", ""}
_ZERO = {"nil", "0", "0.0", "0.00", "zero"}
_NUMBER = re.compile(r"^\(?-?\s*[0-9][0-9,]*(?:\.[0-9]+)?\)?$")
_ROW_NUMBER = re.compile(r"^\s*(?:\(?[a-z0-9]{1,3}[.)]?|[ivx]{1,4}[.)]?|\d+(?:\.\d+)*)\s*$", re.I)


@dataclass(frozen=True)
class GridIn:
    page_index: int
    ordinal: int
    rows: list[list[str]]
    header_rows: int
    caption: list[str] = field(default_factory=list)  # text lines just above the table
    reader_note: str | None = None  # set when the cells come from the second table reader


_MULTI_NUMBER = re.compile(r"-?\d[\d,]*\.\d+|(?<![\d.])\d{2,}(?![\d.])")


def collapsed_grid(rows: list[list[str]]) -> bool:
    """A table reader that merged a row's cells into one ("TPWODL 1827.481 2436.6", the rest
    blank: OERC FY2025-26): many filled cells each holding several numbers."""
    filled = [(c or "").strip() for r in rows for c in r if (c or "").strip()]
    multi = [c for c in filled if len(_MULTI_NUMBER.findall(_FY.sub(" ", c))) >= 2]  # "FY 2024-25" is one year
    return len(multi) >= 2 and len(multi) >= 0.3 * len(filled)


@dataclass
class ColumnSpec:
    col: int
    fiscal_year: str
    value_type: str
    label: str
    utility: str | None = None


_TOTAL_COL = re.compile(r"^\W*(?:total|state|all\s+discoms?|grand\s+total|combined|consolidated)\b", re.I)


def _skip(report: ReadReport, g: GridIn, j: int, h: str, reason: str) -> None:
    report.columns_skipped.append({"page": g.page_index, "grid": g.ordinal, "col": j, "header": h, "reason": reason})


_LICENSEE_HDR = re.compile(r"^\W*(?:discoms?|licensees?|name\s+of\s+(?:the\s+)?licensee|utility|company)\W*$", re.I)
_BY_ROW = "*row*"  # a column whose values belong to the licensee of each row


def row_licensees(
    g: GridIn, headers: list[str], licensees: dict[str, list[str]]
) -> tuple[int | None, dict[int, str | None], set[int]]:
    """A combined order's table that names the licensee per row (OERC): a licensee column
    ("DISCOM": TPCODL, then blank cells carried down), or a licensee's name alone on a row
    above its block.  Returns the licensee column (or None), each body row's licensee, and the
    rows that only name one.  A cell naming no licensee ("Total", "All Odisha") ends the
    carry: its rows belong to none."""
    start = max(1, g.header_rows)
    body = [[(c or "").strip() for c in r] for r in g.rows[start:]]
    lic_col = next((j for j, h in enumerate(headers) if _LICENSEE_HDR.match(h)), None)
    if lic_col is None:
        for j in range(min(2, len(headers))):
            named = {licensee_named(r[j], licensees) for r in body if j < len(r) and r[j]}
            if len(named - {None}) >= 2 and None not in named:
                lic_col = j
                break
    owner: dict[int, str | None] = {}
    heading_rows: set[int] = set()
    current: str | None = None
    for i, cells in enumerate(body, start=start):
        filled = [(j, c) for j, c in enumerate(cells) if c]
        if lic_col is not None and lic_col < len(cells) and cells[lic_col]:
            current = licensee_named(cells[lic_col], licensees)
        elif len(filled) == 1 and (named := licensee_named(filled[0][1], licensees)):
            current = named
            heading_rows.add(i)
        owner[i] = current
    if lic_col is None and not heading_rows:
        return None, {}, set()
    return lic_col, owner, heading_rows


_SUB_ROW = re.compile(r"^\W*(?:on|for|towards|of|to)\s+\S", re.I)


def sub_row_label(label: str, heading: str | None) -> str:
    """A sub-row read with its heading row ("Interest & Finance Charges", values blank) when its
    label opens with a preposition: "On Consumer Security Deposit" is "Interest on Consumer
    Security Deposit" — the heading's leading words, up to its first "&" or "and"."""
    if not heading or not _SUB_ROW.match(label):
        return label
    lead = re.split(r"\s*(?:&|\band\b|,|\()\s*", heading.strip(), maxsplit=1)[0].strip()
    return f"{lead} {label.strip()}" if lead else label


def licensee_named(text: str, licensees: dict[str, list[str]]) -> str | None:
    """The one licensee a header or caption names (by code or name), or None (none, or several)."""
    t = (text or "").lower()
    hits = {
        code
        for code, names in licensees.items()
        for n in [code, *names]
        if n and re.search(rf"(?<![a-z0-9]){re.escape(n.lower())}(?![a-z0-9])", t)
    }
    return hits.pop() if len(hits) == 1 else None


@dataclass
class ReadReport:
    grids_read: int = 0
    rows_placed: int = 0
    unplaced: list[dict[str, Any]] = field(default_factory=list)
    columns_skipped: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rules_version": ARR_RULES_VERSION,
            "grids_read": self.grids_read,
            "rows_placed": self.rows_placed,
            "unplaced": self.unplaced,
            "columns_skipped": self.columns_skipped,
            "duplicates": self.duplicates,
        }


_FY_SHORT = re.compile(r"\bFY\s?'?(\d{2})(?![\d-])", re.I)


def _all_years(text: str) -> set[str]:
    found = {f"FY{m.group(1)}-{m.group(2)[-2:]}" for m in _FY.finditer(text or "")}
    good = {fy for fy in found if int(fy[7:9]) == (int(fy[2:6]) + 1) % 100}
    # "FY27" is the financial year ending in March 2027 (Indian regulatory usage), only with
    # its "FY" prefix: a bare two-digit number is never a year
    for m in _FY_SHORT.finditer(text or ""):
        end = 2000 + int(m.group(1))
        good.add(f"FY{end - 1}-{m.group(1)}")
    return good


def fiscal_year(text: str) -> str | None:
    """ "FY 2025-26", "2025-26", "2025-2026", "FY26" -> "FY2025-26"; None when absent or
    ambiguous (several years named)."""
    good = _all_years(text)
    return good.pop() if len(good) == 1 else None


def voice(text: str, mapping: Mapping) -> str | None:
    """The first voice pattern of the mapping that the header names, or None.  A pattern
    matches only from the start of a word: the mapping's ``RE\b`` (revised estimate) must not
    find the end of "Crore" in a caption."""
    for p in mapping.voice_columns.patterns:
        if re.search(rf"(?<![a-z0-9])(?:{p['pattern']})", text or "", re.I):
            return p["value_type"]
    return None


def _header_texts(grid: GridIn) -> list[str]:
    """Each column's header text: the header rows joined top to bottom, with a heading that
    spans columns (printed once, blank to its right) carried rightwards."""
    n = max((len(r) for r in grid.rows), default=0)
    hdr = max(1, grid.header_rows)
    cols = ["" for _ in range(n)]
    rows = grid.rows[:hdr]
    for ri, r in enumerate(rows):
        carried = ""
        below = rows[ri + 1] if ri + 1 < len(rows) else None
        for j in range(n):
            cell = (r[j] if j < len(r) else "").strip()
            if cell:
                carried = cell
            elif j > 0 and fiscal_year(carried):
                cell = carried  # a merged year heading over its voice sub-columns
            elif (
                j > 0
                and carried
                and below is not None
                and (below[j] if j < len(below) else "").strip()
                and not _LABEL_HDR.search(carried)
                and not _SKIP_HDR.match(carried)
            ):
                cell = carried  # a merged group heading ("East DISCOM") over "Claimed | Admitted"
            cols[j] = f"{cols[j]} {cell}".strip()
    return cols


def parse_value(raw: str) -> tuple[str, str | None]:
    """(value_state, decimal string) for one cell, exactly as printed: commas removed,
    brackets as negative.  Nil, -, NA and blanks are states, never the number 0."""
    t = (raw or "").strip()
    # a footnote mark ("517.23*") or a percent sign printed with the value
    t = re.sub(r"(?<=[0-9)])\s*[*#^@†]+$", "", t)
    t = re.sub(r"(?<=[0-9])\s*%$", "", t)
    low = t.lower()
    if low in _ZERO:
        return "zero", "0"
    if low in _ABSENT:
        return "absent_in_source", None
    if not _NUMBER.match(t):
        return "unknown", None
    neg = t.startswith("(") and t.endswith(")") or t.lstrip("(").startswith("-")
    digits = re.sub(r"[^0-9.]", "", t)
    try:
        d = Decimal(digits)
    except InvalidOperation:
        return "unknown", None
    if d == 0:
        return "zero", "0"
    return "value", ("-" if neg else "") + digits


_LABEL_HDR = re.compile(
    r"particular|description|\bitems?\b|\bhead\b|nature|component|computation|parameter|\bsources?\b|category|"
    r"expense|\bline\b",
    re.I,
)
_SKIP_HDR = re.compile(r"^\W*(?:s\.?\s*no|sl\.?\s*no|sr\.?\s*no|ref|reference|formula|units?\b|uom\b)", re.I)
_AMOUNT_HDR = re.compile(r"^\W*(?:amount|value|rs\.?\s*(?:in\s+)?cr(?:ore)?s?\.?)\b", re.I)
_UNIT_HDR = re.compile(r"^\W*(?:units?|uom)\b", re.I)
_ORIGINAL_APPROVAL = re.compile(
    r"\b(?:in|as\s+per|per|vide|under)\s+(?:the\s+)?(?:t\.?\s?o\.?|tariff\s+order|mtr|myt\s+order)(?![a-z])"
    r"|\bt\.?\s?o\.?\s+(?:dated|dtd|of)\b",
    re.I,
)
_PART_WORDS = re.compile(
    r"tru(?:e|ing)[- ]?up|trued[- ]?up|\bapr\b|annual\s+performance|revenue\s+requirement|\barr\b", re.I
)
_TRUE_UP = re.compile(r"tru(?:e|ing)[- ]?up|trued[- ]?up", re.I)
_APR = re.compile(r"\bapr\b|annual\s+performance\s+review", re.I)


def voice_in_context(header: str, caption: str, part: str | None, mapping: Mapping) -> str | None:
    """The voice of a value column: the header's own word, else the caption's; an approval
    inside a true-up is the trued-up value and inside an APR the provisional one, unless the
    header says it is the approval of an earlier order ("Approved in TO dated 10.10.2024")."""
    vt = voice(header, mapping) or voice(caption, mapping)
    if vt != "approved" or _ORIGINAL_APPROVAL.search(header):
        return vt
    # the nearest words decide: the header's own, then the part the chapter sits in, then
    # the caption
    for text in (header, part or "", caption):
        apr, tu = _APR.search(text), _TRUE_UP.search(text)
        if apr and not tu:
            return "provisional_true_up"
        if tu and not apr:
            return "final_true_up"
    return vt


def label_unit(label: str) -> str | None:
    """The unit a row label states for itself: in brackets ("Sales (MU)") or at its end
    ("ACoS Rs./kWh"); a percentage inside the words ("@ 40% of R&M") is not the row's unit."""
    for inner in re.findall(r"\(([^()]{1,30})\)", label or ""):
        u = unit_from_text(inner)
        if u:
            return u
    tail = re.search(r"(?:in\s+)?(rs\.?\s*(?:cr(?:ore)?\.?|lakh|/\s*kwh)|mu|%|kwh|mw)\s*$", label or "", re.I)
    return unit_from_text(tail.group(1)) if tail else None


# the ARR's own totals: a "Total Cost" row of one power source's table is not total expenditure
_SUMMARY_LINES = frozenset({"C.TOTAL", "R.ARR", "R.GAP", "R.REV.EXISTING"})
_SUMMARY_TITLE = re.compile(
    r"summary|aggregate\s+revenue\s+requirement|annual\s+revenue\s+requirement|\barr\b|revenue\s+gap|"
    r"gap\s*/\s*\(?\s*surplus",
    re.I,
)
_TITLE = re.compile(r"^\s*(?:table|statement|format|annexure|schedule)\b", re.I)


def table_title(caption_lines: list[str]) -> str:
    """A table's own title among the lines printed above it: from its last "Table …" line to
    the table (a title wraps), else only the line right above.  The paragraphs of analysis
    above a table are not its title: their years and voices are not the table's."""
    lines = [ln for ln in caption_lines if ln.strip()]
    idx = next((i for i in range(len(lines) - 1, -1, -1) if _TITLE.match(lines[i])), None)
    if idx is not None:
        return " ".join(lines[idx:])
    return lines[-1] if lines else ""


def _years(text: str) -> set[str]:
    return _all_years(text)


def _texty(g: GridIn, j: int) -> bool:
    body = [(r[j] if j < len(r) else "").strip() for r in g.rows[max(1, g.header_rows) :]]
    body = [c for c in body if c]
    if not body:
        return False
    words = [c for c in body if re.search(r"[A-Za-z]{3,}", c) and not _NUMBER.match(c)]
    return len(words) / len(body) >= 0.5


def _with_second_header(g: GridIn, mapping: Mapping) -> GridIn:
    """A header printed on two rows ("FY 2024-25 (True-Up)" over "Claimed | Approved") whose
    second row the grid stage counted as data: no number in it and a voice word in it."""
    from dataclasses import replace

    h = max(1, g.header_rows)
    if len(g.rows) <= h + 1:
        return g
    nxt = [(c or "").strip() for c in g.rows[h]]
    if any(_NUMBER.match(c) for c in nxt if c) or not any(voice(c, mapping) for c in nxt if c):
        return g
    return replace(g, header_rows=h + 1)


def read_grids(
    grids: list[GridIn],
    *,
    taxonomy: Taxonomy,
    mapping: Mapping,
    placer: Placer,
    source_id: str,
    utility: str | None,
    licensees: dict[str, list[str]] | None = None,
    part: str | None = None,
    branch: str | None = None,
) -> tuple[ArrExtractionOutput, ReadReport]:
    """Candidates from a chapter's grids.  ``utility`` is the order's licensee; a combined
    order passes its ``licensees`` (code -> names) instead, and each value is attributed to the
    licensee its column header or its table's caption names.  A total across licensees, or a
    column no licensee can be read for, is reported and skipped, never attributed.

    ``part`` is the running header of the part the chapter sits in ("TRUING-UP OF FY
    2024-25"): it gives a column the year when neither its header nor the caption does, and
    the voice of an approval inside a true-up or an APR.  ``branch`` is the chapter's: the
    ARR's own totals are placed only in an ARR or gap chapter, or in a table titled as the
    summary."""
    combined = bool(licensees and len(licensees) > 1)
    # a running header that names no part ("NBPDCL & SBPDCL Tariff Order for FY 2026-27") is
    # not context: its year is the order's, not the table's
    if part and not _PART_WORDS.search(part):
        part = None
    report = ReadReport()
    out = ArrExtractionOutput()
    seen: dict[str, ArrCandidate] = {}
    for g in grids:
        if not g.rows:
            continue
        g = _with_second_header(g, mapping)
        headers = _header_texts(g)
        # the unit may be printed anywhere above the table; the year and the voice only in its title
        above = " ".join(g.caption)
        caption = table_title(g.caption)
        table_unit = (
            unit_from_text(caption)
            or next((unit_from_text(h) for h in headers if unit_from_text(h)), None)
            or unit_from_text(above)
        )
        columns: list[ColumnSpec] = []
        # the title's one year; a title naming several is ambiguous and never filled from the part
        title_years = _years(caption)
        table_fy = (
            next(iter(title_years))
            if len(title_years) == 1
            else (fiscal_year(part) if part and not title_years else None)
        )
        table_licensee = licensee_named(caption, licensees) if combined and licensees else None
        lic_col, row_owner, heading_rows = (
            row_licensees(g, headers, licensees) if combined and licensees and not table_licensee else (None, {}, set())
        )

        for j, h in enumerate(headers):
            if j == lic_col:
                continue
            fy = fiscal_year(h)
            col_licensee = licensee_named(h, licensees) if combined and licensees else None
            if combined and _TOTAL_COL.match(h) and (columns or fy):
                _skip(report, g, j, h, "a total across licensees, not one licensee's value")
                continue
            if fy is None and col_licensee is not None:
                # a column per licensee: the year comes from the caption; the voice from the
                # header's own words first ("East DISCOM Claimed" over "Admitted": MPERC), then
                # the part and the caption
                fy, vt = table_fy, voice_in_context(h, caption, part, mapping)
                if fy is None or vt is None:
                    _skip(report, g, j, h, "a licensee's column without a year and a voice in the caption")
                    continue
                columns.append(ColumnSpec(j, fy, vt, f"{h} | {caption}"[:200], col_licensee))
                continue
            if fy is None:
                # a voice-only header ("Claimed", "Approved"): the year is the caption's (or the
                # part's) when it names exactly one; a lone "Amount" column takes its voice from
                # the title too ("Petitioner Submission - …", "… approved by the Commission")
                amount = bool(_AMOUNT_HDR.match(h)) and voice_in_context("", caption, part, mapping) is not None
                if not h.strip() or _SKIP_HDR.match(h) or table_fy is None:
                    continue
                if voice(h, mapping) is None and not amount:
                    continue
                fy = table_fy
            vt = voice_in_context(h, caption, part, mapping)
            if vt is None:
                _skip(report, g, j, h, "no voice word")
                continue
            owner = col_licensee or table_licensee or (None if combined else utility)
            if combined and owner is None and row_owner:
                owner = _BY_ROW  # each row names its licensee
            if combined and owner is None:
                _skip(report, g, j, h, "no licensee named in the column or the table's caption (combined order)")
                continue
            columns.append(ColumnSpec(j, fy, vt, h, owner))
        if not columns:
            continue
        value_cols = {c.col for c in columns}
        others = [j for j in range(len(headers)) if j not in value_cols and j != lic_col]
        label_col = next(
            (
                j
                for j in others
                if headers[j].strip() and _LABEL_HDR.search(headers[j]) and not _SKIP_HDR.match(headers[j])
            ),
            None,
        )
        if label_col is None:
            label_col = next(
                (j for j in others if not _SKIP_HDR.match(headers[j]) and _texty(g, j)), others[0] if others else 0
            )
        unit_col = next((j for j in others if _UNIT_HDR.match(headers[j])), None)
        report.grids_read += 1
        group_heading: str | None = None  # the last row with a label and no values
        for i, row in enumerate(g.rows[max(1, g.header_rows) :], start=max(1, g.header_rows)):
            cells = [(c or "").strip() for c in row]
            if i in heading_rows:
                continue  # a licensee's name above its rows
            label = cells[label_col] if label_col < len(cells) else ""
            if _ROW_NUMBER.match(label) and label_col + 1 < len(cells):
                label = cells[label_col + 1]  # an S.No. column before the particulars
            if not label or label.lower() in ("particulars", "s. no.", "sl. no."):
                continue
            if all(not (cells[c.col] if c.col < len(cells) else "") for c in columns):
                group_heading = label  # a heading row with no values: its sub-rows follow
                continue
            elif _SUB_ROW.match(label):
                label = sub_row_label(label, group_heading)
            else:
                group_heading = None
            unit_cell = cells[unit_col] if unit_col is not None and unit_col < len(cells) else ""
            row_unit = label_unit(label) or unit_from_text(unit_cell) or table_unit
            placed = placer.place(label, unit_hint=_unit_class(row_unit))
            if placed is None:
                report.unplaced.append(
                    {
                        "page": g.page_index,
                        "grid": g.ordinal,
                        "row": i,
                        "label": label,
                        "options": placer.options(label),
                    }
                )
                continue
            if (
                placed.code in _SUMMARY_LINES
                and branch is not None
                and branch not in ("R", "C")
                and not _SUMMARY_TITLE.search(caption)
            ):
                report.unplaced.append(
                    {
                        "page": g.page_index,
                        "grid": g.ordinal,
                        "row": i,
                        "label": label,
                        "options": [placed.code],
                        "reason": f"a total of a {branch} table, not the ARR's {placed.code}",
                    }
                )
                continue
            item_unit = taxonomy.by_code()[placed.code].unit
            if row_unit and item_unit and _unit_class(row_unit) != item_unit:
                # a money row is never an energy line, nor a percentage a money one: the words
                # matched, the unit says no
                report.unplaced.append(
                    {
                        "page": g.page_index,
                        "grid": g.ordinal,
                        "row": i,
                        "label": label,
                        "options": [placed.code],
                        "reason": f"printed in {row_unit}, but {placed.code} is in {item_unit}",
                    }
                )
                continue
            unit = row_unit if row_unit else _default_unit(item_unit)
            report.rows_placed += 1
            for col in columns:
                owner = row_owner.get(i) if col.utility == _BY_ROW else col.utility
                if owner is None:
                    continue  # a row of no licensee (a total across them) in a per-row table
                raw = cells[col.col] if col.col < len(cells) else ""
                state, value = parse_value(raw)
                canonical, cunit, conversion = (None, None, "not_a_value")
                if value is not None:
                    canonical, cunit, conversion = to_canonical(value, unit, taxonomy.unit_conversions)
                missing = [] if unit else ["stated_unit"]
                cand = ArrCandidate(
                    line_code=placed.code,
                    fiscal_year=col.fiscal_year,
                    value_type=col.value_type,  # type: ignore[arg-type]
                    as_of_order=source_id,
                    utility=owner,
                    value_state=state,  # type: ignore[arg-type]
                    stated_value=value,
                    stated_unit=unit,
                    column_label=col.label[:200],
                    canonical_value=canonical,
                    canonical_unit=cunit,
                    conversion=conversion,
                    original_text=label[:400],
                    evidence=[
                        EvidenceRef(
                            page_index=g.page_index,
                            kind="cell",
                            grid_ordinal=g.ordinal,
                            row=i,
                            col=col.col,
                            header_path=[col.label],
                            row_path=[label],
                            excerpt=(raw or "(blank)")[:400],
                        )
                    ],
                    missing=missing,
                    rationale=(
                        f"Row '{label}' placed on {placed.code} ({placed.how} match of '{placed.matched}'); "
                        f"column '{col.label}' gives {col.fiscal_year} {col.value_type}"
                        + (
                            f"; unit from {'the row label' if unit_from_text(label) else 'the caption'}"
                            if row_unit
                            else ""
                        )
                        + (f"; {g.reader_note}" if g.reader_note else "")
                    )[:600],
                )
                k = cand.key()
                if k in seen:
                    prior = seen[k]
                    report.duplicates.append(
                        {
                            "key": k,
                            "kept": prior.evidence[0].model_dump(),
                            "dropped": cand.evidence[0].model_dump(),
                            "same_value": prior.stated_value == cand.stated_value,
                        }
                    )
                    if prior.stated_value != cand.stated_value:
                        prior.ambiguous = sorted({*prior.ambiguous, "stated_value"})
                        prior.notes = (
                            f"{(prior.notes or '')} Also printed as {cand.stated_value} on page "
                            f"{cand.evidence[0].page_index}."
                        ).strip()
                    continue
                seen[k] = cand
                out.candidates.append(cand)
    return out, report


def _unit_class(unit: str | None) -> str | None:
    """The taxonomy unit a printed unit belongs to, for resolving an energy/cost twin."""
    return {
        "INR_lakh": "INR_crore",
        "INR_million": "INR_crore",
        "INR": "INR_crore",
        "kWh": "MU",
        "MWh": "MU",
        "GWh": "MU",
        "paise_per_kWh": "INR_per_kWh",
    }.get(unit or "", unit)


def _default_unit(item_unit: str | None) -> str | None:
    """Only a percentage line states its unit by being a percentage; money and energy need a
    printed unit, so None is returned and the candidate lists ``stated_unit`` as missing."""
    return "percent" if item_unit == "percent" else None


def compare(structure: ArrCandidate, image: ArrCandidate | None) -> tuple[str, list[str]]:
    """Field-by-field agreement of the two channels on one fact."""
    if image is None:
        return "one_missing", []
    fields = ("value_state", "stated_value", "stated_unit", "line_code", "fiscal_year", "value_type")
    diff = [f for f in fields if getattr(structure, f) != getattr(image, f)]
    return ("agree" if not diff else "disagree"), diff
