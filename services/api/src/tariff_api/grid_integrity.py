"""Table-grid integrity (Section 6.6): every numeric cell resolves to a header path, a row
label path and a unit bound from somewhere it can cite — or it is flagged.  Continuation
grids inherit the previous grid's header; merged and spanning cells are expanded with the
propagation recorded; footnote markers are attached to their text; the row and column
indices are kept so a candidate cites a cell, not a page.  Pure functions over grids and the
page lines around them; bump ``GRID_VERSION`` on change."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .normalise import Normalised, check_slab_sequence, normalise_value, parse_slab, unit_hint

GRID_VERSION = "1"

_MARKER_LINE = re.compile(r"^\s*(?P<m>\*\*|\*|#|†|‡|\^)\s*(?P<text>.+)$")
_ROW_UNIT_HEADER = re.compile(r"billing\s+unit|\bunit\b\s*$|basis", re.I)
_VALUE_STATES = {"value", "zero", "not_applicable", "cross_reference", "formula", "footnote_only"}


@dataclass
class GridInput:
    page_index: int
    ordinal: int
    rows: list[list[str]]
    header_rows: int
    title_lines: list[str] = field(default_factory=list)  # caption / heading lines above the grid
    footnote_lines: list[str] = field(default_factory=list)  # lines below the grid on the page
    reader: str = "pymupdf"


@dataclass
class CellRecord:
    page_index: int
    grid_ordinal: int
    row: int
    col: int
    raw: str
    header_path: list[str]
    row_path: list[str]
    normalised: dict[str, Any]
    currency: str | None
    per_unit: str | None
    frequency: str | None
    unit_source: str | None  # cell | header | row_unit_column | title | footnote
    flags: list[str] = field(default_factory=list)
    footnotes: list[str] = field(default_factory=list)
    slab: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def resolved(self) -> bool:
        return not any(f in self.flags for f in ("unresolved_header", "unresolved_row", "unit_unresolved"))


@dataclass
class GridRecord:
    page_index: int
    ordinal: int
    header_paths: list[list[str]]
    label_columns: list[int]
    row_unit_column: int | None
    continuation_of: tuple[int, int] | None
    header_inherited: bool
    cells: list[CellRecord]
    flags: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        units = sorted({f"{c.currency or '?'}/{c.per_unit or '?'}" for c in self.cells if c.per_unit or c.currency})
        return {
            "page_index": self.page_index,
            "ordinal": self.ordinal,
            "cells": len(self.cells),
            "resolved": sum(1 for c in self.cells if c.resolved),
            "unresolved": [
                {"row": c.row, "col": c.col, "raw": c.raw, "flags": c.flags} for c in self.cells if not c.resolved
            ],
            "continuation_of": list(self.continuation_of) if self.continuation_of else None,
            "header_inherited": self.header_inherited,
            "units_seen": units,
            "flags": self.flags,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_index": self.page_index,
            "ordinal": self.ordinal,
            "header_paths": self.header_paths,
            "label_columns": self.label_columns,
            "row_unit_column": self.row_unit_column,
            "continuation_of": list(self.continuation_of) if self.continuation_of else None,
            "header_inherited": self.header_inherited,
            "flags": self.flags,
            "cells": [c.to_dict() for c in self.cells],
        }


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _is_numeric_state(n: Normalised) -> bool:
    return n.value_state in ("value", "zero") or n.percent


def header_paths(rows: list[list[str]], header_rows: int) -> tuple[list[list[str]], list[bool]]:
    """One path per column from the header rows, top to bottom.  An empty header cell inherits
    the cell to its left on the same row (a spanning super-header); the inheritance is
    reported per column so a reviewer sees it."""
    ncols = max((len(r) for r in rows), default=0)
    paths: list[list[str]] = [[] for _ in range(ncols)]
    inherited = [False] * ncols
    for r in range(min(header_rows, len(rows))):
        last = ""
        for c in range(ncols):
            txt = _clean(rows[r][c]) if c < len(rows[r]) else ""
            if txt:
                last = txt
            elif last:
                txt = last
                inherited[c] = True
            if txt and (not paths[c] or paths[c][-1] != txt):
                paths[c].append(txt)
    return paths, inherited


def _footnotes(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in lines:
        m = _MARKER_LINE.match(ln)
        if m and m["m"] not in out:
            out[m["m"]] = _clean(m["text"])
    return out


def _bind_unit(
    n: Normalised, header: list[str], row_unit: str | None, titles: list[str], notes: list[str]
) -> tuple[str | None, str | None, str | None, str | None, list[str]]:
    """Return (currency, per_unit, frequency, source, flags) for a numeric cell."""
    flags: list[str] = []
    if n.percent:
        base = n.percent_of or next((h for h in header if "%" in h or "percent" in h.lower()), None)
        return None, "percent", None, "cell" if n.percent_of else ("header" if base else "cell"), flags
    if n.value_state == "zero" and any(unit_hint(h)["percent"] for h in header):
        return None, "percent", None, "header", flags  # a bare `0` in a `% of Energy Charges` column
    if n.per_unit or n.currency:
        cur, unit, freq, src = n.currency, n.per_unit, n.frequency, "cell"
        if unit is None or cur is None:
            for source, texts in (("header", header), ("row_unit_column", [row_unit or ""])):
                h = {}
                for t in texts:
                    hh = unit_hint(t)
                    h = {k: h.get(k) or v for k, v in hh.items()}
                if unit is None and h.get("per_unit"):
                    unit, src = h["per_unit"], f"cell+{source}"
                if cur is None and h.get("currency"):
                    cur = h["currency"]
                    src = src if "+" in src else f"cell+{source}"
                if freq is None and h.get("frequency"):
                    freq = h["frequency"]
        return cur, unit, freq, src, flags
    candidates = (("header", header), ("row_unit_column", [row_unit or ""]), ("title", titles), ("footnote", notes))
    cur = unit = freq = None
    unit_src = cur_src = None
    for source, texts in candidates:
        for t in texts:
            h = unit_hint(t)
            if unit is None and h["per_unit"]:
                unit, unit_src = h["per_unit"], source
            if cur is None and h["currency"]:
                cur, cur_src = h["currency"], source
            if freq is None and h["frequency"]:
                freq = h["frequency"]
    if unit or cur:
        # the source cited is where the denominator came from (KERC: currency in the header,
        # `per KW` in the billing-unit column); a currency-only binding cites its own source
        if cur is None:
            flags.append("currency_unresolved")
        return cur, unit, freq, unit_src or cur_src, flags
    flags.append("unit_unresolved")
    return None, None, None, None, flags


def analyse_grid(g: GridInput, previous: GridRecord | None) -> GridRecord:
    rows = [[_clean(c) for c in r] for r in g.rows]
    ncols = max((len(r) for r in rows), default=0)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    flags: list[str] = []
    header_rows = g.header_rows
    continuation: tuple[int, int] | None = None
    inherited = False
    paths, span_inh = header_paths(rows, header_rows)
    if previous is not None and previous.page_index == g.page_index - 1 and len(previous.header_paths) == ncols:
        prev_header = [p[-1] if p else "" for p in previous.header_paths]
        this_header = [p[-1] if p else "" for p in paths]
        if header_rows == 0 or not any(this_header):
            continuation, inherited = (previous.page_index, previous.ordinal), True
            paths, span_inh, header_rows = previous.header_paths, [False] * ncols, 0
            flags.append("header_inherited")
        elif this_header == prev_header:
            continuation = (previous.page_index, previous.ordinal)
            flags.append("header_repeated")
    if header_rows == 0 and not inherited:
        flags.append("no_header_row")
    data = rows[header_rows:]
    # a row-unit column (KERC `Fixed Charges Billing Unit`: per KW / per HP / per KVA) is named
    # by its header and applies to the whole row
    row_unit_col = next((c for c, p in enumerate(paths) if any(_ROW_UNIT_HEADER.search(t) for t in p)), None)
    # label columns: every column whose data cells are mostly non-numeric — the first columns
    # (category, description) and, in the UPERC shape, a trailing slab column
    label_cols: list[int] = []
    for c in range(ncols):
        if c == row_unit_col:
            continue
        cells = [normalise_value(r[c]) for r in data if r[c]]
        numeric = sum(1 for n in cells if _is_numeric_state(n) or n.value_state in ("not_applicable", "footnote_only"))
        if (cells and numeric <= len(cells) // 3) or (not cells and c == 0):
            label_cols.append(c)  # an all-empty first column is a merged label column
    notes = _footnotes(g.footnote_lines)
    header_notes = {c: [m for m in notes if m in " ".join(paths[c])] for c in range(ncols)}
    # row paths with merged-cell propagation (within the grid, and from the previous grid's last
    # row for the first rows of a continuation)
    last_labels: list[str] = [""] * len(label_cols)
    carried_values: dict[int, str] = {}
    if continuation and previous.cells:
        prev_last_row = max(c.row for c in previous.cells)
        prev_cells = [c for c in previous.cells if c.row == prev_last_row]
        if prev_cells:
            last_labels = list(prev_cells[0].row_path[: len(label_cols)]) + [""] * (
                len(label_cols) - len(prev_cells[0].row_path)
            )
            carried_values = {c.col: c.raw for c in prev_cells}
    cells: list[CellRecord] = []
    row_slabs: list[tuple[int, Any]] = []
    for ri, r in enumerate(data, start=header_rows):
        row_flags: list[str] = []
        labels: list[str] = []
        own_label_empty = bool(label_cols) and not r[label_cols[0]]
        for i, c in enumerate(label_cols):
            if r[c]:
                last_labels[i] = r[c]
                for j in range(i + 1, len(label_cols)):
                    last_labels[j] = "" if not r[label_cols[j]] else last_labels[j]
            elif last_labels[i]:
                row_flags.append("merged_cell_propagated")
            labels.append(last_labels[i])
        row_path = [x for x in labels if x]
        if not row_path:
            row_flags.append("unresolved_row")
        row_unit = r[row_unit_col] if row_unit_col is not None else None
        slab = next((sb for sb in (parse_slab(x) for x in reversed(row_path)) if sb), None)
        if slab:
            row_slabs.append((len(cells), slab))
        for c in range(ncols):
            if c in label_cols or c == row_unit_col:
                continue
            raw = r[c]
            propagated = False
            if not raw and own_label_empty and c in carried_values and carried_values[c]:
                raw, propagated = carried_values[c], True  # D.2 hazard 1: the spanning value cell
            n = normalise_value(raw)
            if n.value_state == "unknown" and not raw:
                continue  # an empty cell with nothing to propagate is not a cell
            cur, unit, freq, src, uflags = _bind_unit(n, paths[c], row_unit, g.title_lines, list(notes.values()))
            cflags = [*row_flags, *uflags]
            if propagated:
                cflags.append("merged_cell_propagated")
            if inherited:
                cflags.append("header_inherited")
            if span_inh[c]:
                cflags.append("header_span_inherited")
            if not paths[c]:
                cflags.append("unresolved_header")
            if n.value_state == "unknown":
                cflags.append("unparsed_cell")
            markers = [*n.footnote_markers, *header_notes.get(c, [])]
            attached = [notes[m] for m in markers if m in notes]
            if markers and not attached:
                cflags.append("footnote_unresolved")
            elif attached:
                cflags.append("footnote_attached")
            if n.flags:
                cflags.extend(n.flags)
            cells.append(
                CellRecord(
                    page_index=g.page_index,
                    grid_ordinal=g.ordinal,
                    row=ri,
                    col=c,
                    raw=raw,
                    header_path=list(paths[c]),
                    row_path=row_path,
                    normalised=n.to_dict(),
                    currency=cur,
                    per_unit=unit,
                    frequency=freq,
                    unit_source=src,
                    flags=sorted(set(cflags)),
                    footnotes=attached,
                    slab=slab.to_dict() if slab else None,
                )
            )
            if raw:
                carried_values[c] = raw
        if not own_label_empty:
            carried_values = {c: r[c] for c in range(ncols) if c not in label_cols and r[c]}
    # adjacent slab rows claiming a boundary are ambiguous (V5)
    if len(row_slabs) > 1:
        checked = check_slab_sequence([s for _, s in row_slabs])
        by_row_path = {id(s): s for s in checked}
        for cell in cells:
            if cell.slab:
                for s in checked:
                    if s.original_text == cell.slab["original_text"]:
                        cell.slab = s.to_dict()
                        if s.inclusivity == "ambiguous" and "slab_inclusivity_ambiguous" not in cell.flags:
                            cell.flags.append("slab_inclusivity_ambiguous")
        del by_row_path
    units = {(c.currency, c.per_unit) for c in cells if c.per_unit and c.per_unit != "percent"}
    if len(units) > 1:
        flags.append("mixed_units_in_grid")
    return GridRecord(
        page_index=g.page_index,
        ordinal=g.ordinal,
        header_paths=paths,
        label_columns=label_cols,
        row_unit_column=row_unit_col,
        continuation_of=continuation,
        header_inherited=inherited,
        cells=cells,
        flags=flags,
    )


def analyse_grids(grids: list[GridInput]) -> list[GridRecord]:
    out: list[GridRecord] = []
    prev: GridRecord | None = None
    for g in sorted(grids, key=lambda x: (x.page_index, x.ordinal)):
        rec = analyse_grid(g, prev)
        out.append(rec)
        prev = rec
    return out


def summarise(records: list[GridRecord]) -> dict[str, Any]:
    cells = [c for r in records for c in r.cells]
    flag_counts: dict[str, int] = {}
    for c in cells:
        for f in c.flags:
            flag_counts[f] = flag_counts.get(f, 0) + 1
    sources: dict[str, int] = {}
    for c in cells:
        sources[c.unit_source or "none"] = sources.get(c.unit_source or "none", 0) + 1
    return {
        "version": GRID_VERSION,
        "grids": len(records),
        "cells": len(cells),
        "resolved": sum(1 for c in cells if c.resolved),
        "unresolved": sum(1 for c in cells if not c.resolved),
        "continuations": sum(1 for r in records if r.continuation_of),
        "header_inherited_grids": sum(1 for r in records if r.header_inherited),
        "unit_sources": sources,
        "flags": flag_counts,
        "mixed_unit_grids": sum(1 for r in records if "mixed_units_in_grid" in r.flags),
    }
