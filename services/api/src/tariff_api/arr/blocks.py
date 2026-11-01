"""Year-block tables (milestone 13): a utility's workings laid out as one block per year side by
side — e.g. NPCL's depreciation by asset class (Annexure-21: for each year a block of S.No.,
Particulars, Opening GFA, Additions, …, Closing Acc. Dep).

A block starts at a header cell "Particulars"; its year is the fiscal year printed in the rows
just above it; its columns are named by their header words (``COLUMN_WORDS``), not by position,
so a block whose opening column reads "Balance Depreciable …" is still the opening.  Values are
kept exactly as stored (Decimal from the stored binary value's shortest repr); a blank cell is
absent, never zero.  Unreviewed machine reading of the utility's own spreadsheet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .reference import _number, _text, fiscal_year

# header words → the column's key (first match wins; order matters)
COLUMN_WORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"opening\s*acc", re.I), "opening_acc_dep"),
    (re.compile(r"closing\s*acc", re.I), "closing_acc_dep"),
    (re.compile(r"allowable\s*gross", re.I), "gross_dep"),
    (re.compile(r"allowable\s*net", re.I), "net_dep"),
    (re.compile(r"dep\w*\s*on\s*con", re.I), "dep_on_contribution"),
    (re.compile(r"dep\w*\s*on\s*assets\s*ret", re.I), "dep_retired"),
    (re.compile(r"opening\s*gfa|balance\s*depreciable", re.I), "opening_gfa"),
    (re.compile(r"addition", re.I), "additions"),
    (re.compile(r"deduction\s*grants?|grants?", re.I), "grants"),
    (re.compile(r"deduction", re.I), "deductions"),
    (re.compile(r"closing\s*gfa", re.I), "closing_gfa"),
    (re.compile(r"average", re.I), "average_gfa"),
    (re.compile(r"rate", re.I), "rate"),
]
STOP = re.compile(r"^(total|depreciable assets|non depreciable)", re.I)


def column_key(header: str) -> str | None:
    return next((k for pat, k in COLUMN_WORDS if pat.search(header or "")), None)


@dataclass
class BlockRow:
    row: int
    label: str
    values: dict[str, str] = field(default_factory=dict)  # key → stored value (Decimal as string)


@dataclass
class YearBlock:
    fiscal_year: str
    title: str  # the words printed with the year ("Depreciation for Consumer Contribution assets …")
    first_col: int  # 1-based column of "Particulars"
    columns: dict[str, int]  # key → 1-based column
    rows: list[BlockRow]
    totals: dict[str, str] = field(default_factory=dict)  # the block's "Total" row, when present


def read_year_blocks(rows: list[list[Any]], *, max_rows: int = 60) -> list[YearBlock]:
    blocks: list[YearBlock] = []
    for i, r in enumerate(rows[:max_rows]):
        starts = [j for j, v in enumerate(r) if re.fullmatch(r"particulars\s*\*?", _text(v), re.I)]
        for n, j in enumerate(starts):
            end = starts[n + 1] - 1 if n + 1 < len(starts) else len(r)
            fy, title = None, ""
            for k in range(max(0, i - 3), i):
                for v in rows[k][max(0, j - 2) : end]:
                    if not fy and (y := fiscal_year(_text(v))):
                        fy = y
                        title = " ".join(
                            _text(x) for x in rows[k][max(0, j - 2) : end] if _text(x) and not fiscal_year(_text(x))
                        )
            if not fy:
                continue
            cols: dict[str, int] = {}
            for c in range(j + 1, end):
                key = column_key(_text(r[c]) if c < len(r) else "")
                if key and key not in cols:
                    cols[key] = c
            block = YearBlock(fy, title, j + 1, {k: c + 1 for k, c in cols.items()}, [])
            for k in range(i + 1, len(rows)):
                rr = rows[k]
                label = _text(rr[j]) if j < len(rr) else ""
                if not label:
                    if block.rows:
                        break
                    continue
                vals = {}
                for key, c in cols.items():
                    num = _number(rr[c]) if c < len(rr) else None
                    if num is not None:
                        vals[key] = str(num)
                if STOP.match(label):
                    if re.match(r"total", label, re.I):
                        block.totals = vals
                        break
                    continue
                block.rows.append(BlockRow(k + 1, label, vals))
            blocks.append(block)
    return blocks


def total_of(block: YearBlock, key: str) -> Decimal:
    return sum((Decimal(r.values[key]) for r in block.rows if key in r.values), Decimal(0))
