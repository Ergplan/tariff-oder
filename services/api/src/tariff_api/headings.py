"""Document-wide heading inventory (Milestone 2; consumed by localisation in Milestone 3).

Recognises the heading shapes the three supplied orders use — UPERC ``RATE SCHEDULE LMV – 1``,
KERC ``TARIFF SCHEDULE LT-3(a)``, GERC ``11. RATE: HTP-1`` — plus annexure, chapter and table
captions.  The raw string is always kept; the canonical code exists so that ``LMV – 1``,
``LMV - 1`` and ``LMV-1`` count as one schedule (hazard D.1) and so that the KERC habit of
printing a schedule heading twice (title, then table caption) is counted once (hazard E.1).

Inventory is *expectation*: Part D says NPCL has exactly 15 ``RATE SCHEDULE`` headings and no
LMV-10; an inventory that finds 16, or an LMV-10, is a finding.  Bump ``HEADINGS_VERSION``
when patterns change.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

HEADINGS_VERSION = "2"

_DASHES = re.compile(r"\s*[-–—]\s*")
_WS = re.compile(r"\s+")

# Order matters: the first matching pattern wins.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "rate_schedule",
        re.compile(
            r"^\s*RATE\s+SCHEDULE\s+(?P<code>[A-Z]{2,4}\s*[-–—]?\s*\d{1,2}[A-Za-z0-9()\s]*?)"
            r"\s*(?:\(?\s*(?:continued|contd\.?|cont\.)\s*\)?)?\s*$",
            re.I,
        ),
    ),
    (
        "tariff_schedule",
        re.compile(
            r"^\s*TARIFF\s+SCHEDULE\s+(?P<code>[A-Z]{2}\s*-\s*\d{1,2}(?:\s*\([a-z]\))?(?:\s*\([ivx]+\))?(?:\s*/\s*HT)?)\s*$",
            re.I,
        ),
    ),
    ("rate_clause", re.compile(r"^\s*(?P<num>\d{1,2})\.\s*RATE\s*:\s*(?P<code>[A-Z][A-Z0-9 \-().]*?)\s*$", re.I)),
    ("annexure", re.compile(r"^\s*ANNEXURE\s*[-–—:]?\s*(?P<code>[IVX]+|\d+)?\s*(?:[:\-–—].*)?$", re.I)),
    # A chapter heading is the whole line: the number, optionally a separator and a short title.
    # Dot leaders or a trailing page number mean a contents entry; lowercase prose after the
    # number means a sentence ("Chapter 3 the commission shall ...").  Neither is a heading.
    (
        "chapter",
        re.compile(r"^\s*CHAPTER\s*[-–—:]?\s*(?P<code>\d{1,2})\s*(?:[:\-–—]\s*(?P<title>[^.]{1,60}\S))?\s*$", re.I),
    ),
    ("table_caption", re.compile(r"^\s*TABLE\s+(?P<code>\d{1,2}[-.]\d{1,2}[A-Z]?)\b", re.I)),
]


def canonical_code(kind: str, raw: str | None) -> str | None:
    if raw is None:
        return None
    s = _WS.sub(" ", raw).strip().upper()
    # v2: a continuation marker on a repeated heading (`LMV-1 (continued)`, `(Contd.)`) is
    # not part of the code — the page continues the same schedule
    s = re.sub(r"\s*\(?\s*(CONTINUED|CONTD\.?|CONT\.)\s*\)?\s*$", "", s)
    s = _DASHES.sub("-", s)
    s = re.sub(r"\s*\(\s*", "(", s)
    s = re.sub(r"\s*\)\s*", ")", s)
    if kind in ("rate_schedule", "tariff_schedule"):
        # LMV 1 / LMV1 -> LMV-1 ; HV-2 stays; LT-3(A) -> LT-3(A)
        s = re.sub(r"^([A-Z]{2,4})\s*-?\s*(\d)", r"\1-\2", s)
        s = s.replace(" ", "")
    if kind == "rate_clause":
        s = s.replace(" ", "")
    return s or None


@dataclass
class Heading:
    page_index: int
    line_no: int
    kind: str
    code_raw: str | None
    code_canonical: str | None
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def scan_headings(page_index: int, text: str) -> list[Heading]:
    out: list[Heading] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or len(stripped) > 90:
            continue  # headings are short; a long line is body text even if it starts with a keyword
        for kind, pattern in PATTERNS:
            m = pattern.match(stripped)
            if m:
                raw = m.groupdict().get("code")
                out.append(Heading(page_index, line_no, kind, raw, canonical_code(kind, raw), stripped))
                break
    return out


def dedupe_consecutive(headings: list[Heading]) -> list[Heading]:
    """Drop a heading that repeats the previous one's kind and canonical code on the same page
    (KERC prints ``TARIFF SCHEDULE LT-1`` as a title and again as the table caption)."""
    out: list[Heading] = []
    for h in headings:
        if (
            out
            and out[-1].page_index == h.page_index
            and out[-1].kind == h.kind
            and out[-1].code_canonical == h.code_canonical
        ):
            continue
        out.append(h)
    return out


def inventory(headings: list[Heading]) -> dict[str, Any]:
    by_kind: dict[str, Counter] = {}
    for h in headings:
        by_kind.setdefault(h.kind, Counter())[h.code_canonical or "(none)"] += 1
    return {
        "rules_version": HEADINGS_VERSION,
        "counts": {kind: sum(c.values()) for kind, c in by_kind.items()},
        "unique_codes": {kind: sorted(k for k in c if k != "(none)") for kind, c in by_kind.items()},
        "repeated_codes": {
            kind: sorted(k for k, n in c.items() if n > 1 and k != "(none)") for kind, c in by_kind.items()
        },
    }
