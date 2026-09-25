"""The hand-mapping scanner (ARR spec section 3): from an order's page text, every line that
looks like a table row (a label followed by numbers) is placed on the taxonomy or listed as
unplaced, with its pages and an example; the year and voice words seen in column headers
are collected so the mapping's patterns can be filled.  A diagnostic for the reviewer's
mapping pass; it writes no facts."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .taxonomy import Mapping, Placer, Taxonomy, load_mapping, load_taxonomy, norm_label

_NUM = r"\(?-?\d[\d,]*(?:\.\d+)?\)?%?"
_ROW = re.compile(rf"^(?P<label>[A-Za-z(][^\n]*?[A-Za-z)%.])\s{{1,}}(?P<nums>(?:{_NUM}\s*){{1,14}})$")
_FY = re.compile(r"\bFY\s*[-]?\s*(\d{4})\s*[-–/]\s*(\d{2,4})\b|\b(\d{4})\s*[-–/]\s*(\d{2})\b")
_VOICE = re.compile(
    r"\b(petition(?:er)?|claimed|proposed|submitted|approved|allowed|commission|provisional|apr|"
    r"revised estimate|true[- ]?up|trued[- ]?up|final|actual|audited)\b",
    re.I,
)
_HEADING = re.compile(r"^\s*(?:\d{1,2}(?:\.\d{1,2}){0,2}\s+)?[A-Z][A-Za-z&/,()' -]{6,90}$")
_UNIT_CTX = [
    ("INR_crore", re.compile(r"(?:\brs\.?|\binr\b|₹)\s*(?:in\s+)?(?:crore|cr\b\.?|lakh)|\bcrore\b|\(cr\.?\)", re.I)),
    ("MU", re.compile(r"\bmus?\b|million units|\bgwh\b|\bkwh\b", re.I)),
    ("MW", re.compile(r"\bmw\b|\bmva\b", re.I)),
    ("percent", re.compile(r"\(%\)|\bin %|percent|percentage", re.I)),
]


def unit_context(line: str) -> str | None:
    """The unit a line names, if any: header lines ("Rs. Crore", "(MU)") set the table's
    unit, a row's own hint ("Sales (MU)") outranks it."""
    for unit, rx in _UNIT_CTX:
        if rx.search(line):
            return unit
    return None


@dataclass
class ScanReport:
    commission: str
    licensee_kind: str
    pages_scanned: int = 0
    rows_seen: int = 0
    placed: dict[str, dict[str, Any]] = field(default_factory=dict)
    ambiguous: dict[str, dict[str, Any]] = field(default_factory=dict)
    unplaced: dict[str, dict[str, Any]] = field(default_factory=dict)
    year_columns_seen: Counter = field(default_factory=Counter)
    voice_words_seen: Counter = field(default_factory=Counter)
    chapters: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def rows(d: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
            return sorted(
                ({"key": k, **v, "pages": sorted(v["pages"])[:40]} for k, v in d.items()),
                key=lambda x: (-x["count"], x["key"]),
            )

        return {
            "commission": self.commission,
            "licensee_kind": self.licensee_kind,
            "pages_scanned": self.pages_scanned,
            "rows_seen": self.rows_seen,
            "placed_rows": sum(v["count"] for v in self.placed.values()),
            "unplaced_rows": sum(v["count"] for v in self.unplaced.values()),
            "placed": rows(self.placed),
            "ambiguous": rows(self.ambiguous),
            "unplaced": rows(self.unplaced),
            "year_columns_seen": dict(self.year_columns_seen.most_common(40)),
            "voice_words_seen": dict(self.voice_words_seen.most_common(20)),
            "chapters": self.chapters[:400],
        }


def _fy(m: re.Match) -> str:
    a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    return f"FY{a}-{b[-2:]}"


def scan_texts(
    page_texts: dict[int, str],
    *,
    commission: str,
    licensee_kind: str = "distribution",
    taxonomy: Taxonomy | None = None,
    mapping: Mapping | None = None,
) -> ScanReport:
    tax = taxonomy or load_taxonomy()
    if mapping is None:
        try:
            mapping = load_mapping(commission)
        except FileNotFoundError:
            mapping = None
    placer = Placer(tax, mapping, licensee_kind)
    cues = [
        (c.branch, re.compile("|".join(re.escape(p) for p in c.heading_patterns), re.I))
        for c in (mapping.chapter_map if mapping else [])
    ]
    rep = ScanReport(commission=commission, licensee_kind=licensee_kind)
    by_code = tax.by_code()

    def bump(
        bucket: dict[str, dict[str, Any]], key: str, page: int, example: str, extra: dict[str, Any] | None = None
    ) -> None:
        row = bucket.setdefault(key, {"count": 0, "pages": set(), "example": example, **(extra or {})})
        row["count"] += 1
        row["pages"].add(page)

    for page in sorted(page_texts):
        text = page_texts[page] or ""
        if not text.strip():
            continue
        rep.pages_scanned += 1
        table_unit: str | None = None  # from the most recent header-like line naming a unit
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            row_match = _ROW.match(line)
            if row_match is None and (u := unit_context(line)):
                table_unit = u
            if row_match is None:
                # a header or prose line: the years and voices it names, and chapter cues
                for m in _FY.finditer(line):
                    rep.year_columns_seen[_fy(m)] += 1
                for v in _VOICE.findall(line):
                    rep.voice_words_seen[v.lower()] += 1
                if _HEADING.match(line):
                    for branch, rx in cues:
                        if rx.search(line):
                            rep.chapters.append({"page": page, "heading": line[:120], "branch": branch})
                            break
                continue
            m = row_match
            label = m.group("label").strip()
            if len(norm_label(label)) < 3:
                continue
            rep.rows_seen += 1
            pl = placer.place(label, unit_context(label) or table_unit)
            if pl is not None:
                extra = {"matched": pl.matched, "how": pl.how, "label": by_code[pl.code].label}
                bump(rep.placed, pl.code, page, line[:160], extra)
            elif placer.options(label):
                bump(rep.ambiguous, norm_label(label), page, line[:160], {"codes": placer.options(label)})
            else:
                bump(rep.unplaced, norm_label(label), page, line[:160])
    return rep


def scan_exchange_folder(
    folder: Path, *, commission: str | None = None, licensee_kind: str | None = None
) -> ScanReport:
    """Scan an exported order (`exchange/<COMMISSION>/<order>/`): page_texts.json for the
    text, source.json for the commission and licensee."""
    src = json.loads((folder / "source.json").read_text())
    texts_doc = json.loads((folder / "page_texts.json").read_text())
    texts = {int(k): v for k, v in texts_doc.get("texts", {}).items()}
    if not texts:
        raise ValueError(f"{folder}: page_texts.json holds no text (export version 2 or later is needed)")
    return scan_texts(
        texts,
        commission=commission or src.get("commission") or "UNKNOWN",
        licensee_kind=licensee_kind or src.get("licensee_kind") or "distribution",
    )
