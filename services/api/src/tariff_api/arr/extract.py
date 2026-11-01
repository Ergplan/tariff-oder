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

ARR_RULES_VERSION = "arr-rules-1"
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


@dataclass
class ColumnSpec:
    col: int
    fiscal_year: str
    value_type: str
    label: str


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


def fiscal_year(text: str) -> str | None:
    """ "FY 2025-26", "2025-26", "2025-2026" -> "FY2025-26"; None when absent or ambiguous."""
    found = {f"FY{m.group(1)}-{m.group(2)[-2:]}" for m in _FY.finditer(text or "")}
    good = {fy for fy in found if int(fy[7:9]) == (int(fy[2:6]) + 1) % 100}
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
    for r in grid.rows[:hdr]:
        carried = ""
        for j in range(n):
            cell = (r[j] if j < len(r) else "").strip()
            if cell:
                carried = cell
            elif j > 0 and fiscal_year(carried):
                cell = carried  # a merged year heading over its voice sub-columns
            cols[j] = f"{cols[j]} {cell}".strip()
    return cols


def parse_value(raw: str) -> tuple[str, str | None]:
    """(value_state, decimal string) for one cell, exactly as printed: commas removed,
    brackets as negative.  Nil, -, NA and blanks are states, never the number 0."""
    t = (raw or "").strip()
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


def read_grids(
    grids: list[GridIn],
    *,
    taxonomy: Taxonomy,
    mapping: Mapping,
    placer: Placer,
    source_id: str,
    utility: str | None,
) -> tuple[ArrExtractionOutput, ReadReport]:
    report = ReadReport()
    out = ArrExtractionOutput()
    seen: dict[str, ArrCandidate] = {}
    for g in grids:
        if not g.rows:
            continue
        headers = _header_texts(g)
        caption = " ".join(g.caption)
        table_unit = unit_from_text(caption) or next((unit_from_text(h) for h in headers if unit_from_text(h)), None)
        columns: list[ColumnSpec] = []
        label_col = 0
        for j, h in enumerate(headers):
            fy = fiscal_year(h)
            if fy is None:
                if not columns:
                    label_col = j
                continue
            vt = voice(h, mapping) or voice(caption, mapping)
            if vt is None:
                report.columns_skipped.append(
                    {"page": g.page_index, "grid": g.ordinal, "col": j, "header": h, "reason": "no voice word"}
                )
                continue
            columns.append(ColumnSpec(j, fy, vt, h))
        if not columns:
            continue
        report.grids_read += 1
        for i, row in enumerate(g.rows[max(1, g.header_rows) :], start=max(1, g.header_rows)):
            cells = [(c or "").strip() for c in row]
            label = cells[label_col] if label_col < len(cells) else ""
            if _ROW_NUMBER.match(label) and label_col + 1 < len(cells):
                label = cells[label_col + 1]  # an S.No. column before the particulars
            if not label or label.lower() in ("particulars", "s. no.", "sl. no."):
                continue
            row_unit = unit_from_text(label) or table_unit
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
            item_unit = taxonomy.by_code()[placed.code].unit
            unit = row_unit if row_unit else _default_unit(item_unit)
            report.rows_placed += 1
            for col in columns:
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
                    utility=utility,
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
    return {"INR_lakh": "INR_crore", "INR_million": "INR_crore", "paise_per_kWh": "INR_per_kWh"}.get(unit or "", unit)


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
